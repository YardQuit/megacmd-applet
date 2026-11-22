// app.rs: the MEGA applet's state, messages and actions.
// SPDX-License-Identifier: GPL-3.0-or-later

use std::collections::HashSet;
use std::path::PathBuf;
use std::time::Duration;

use cosmic::Element;
use cosmic::app::Core;
use cosmic::app::Task;
use cosmic::cosmic_config::{Config as ConfigHelper, CosmicConfigEntry};
use cosmic::iced::futures::{SinkExt, StreamExt, stream::FuturesUnordered};
use cosmic::iced::platform_specific::shell::wayland::commands::popup::destroy_popup;
use cosmic::iced::{Subscription, time, window::Id};

use crate::config::Config;
use crate::model::{Notice, View, notice_icon, panel_icon};
use crate::{core, popup};

/// The applet's ID: its desktop file, settings and icon names.
pub const APP_ID: &str = "io.github.yardquit.MegaCmd";

/// Seconds between checks while the popup is open.
const OPEN_POLL_SECS: u64 = 3;
/// The fewest seconds between checks while the popup is closed.
const MIN_POLL_SECS: u64 = 10;
/// Seconds between checks while a guided dialog may be open.
const GUIDED_CHECK_SECS: u64 = 5;
/// How many checks follow the opening of a guided dialog (5 minutes).
const GUIDED_CHECKS: u32 = 60;
/// Seconds after an action until the second check.
const AFTER_ACTION_SECS: u64 = 2;
/// Seconds a remove button stays armed.
const ARM_SECS: u64 = 4;
/// Seconds an action's status note stays.
const STATUS_SECS: u64 = 4;
/// How long a shown notification is watched for a click.
const NOTICE_WATCH: Duration = Duration::from_secs(30 * 60);
/// The web address of MEGA's file manager.
const MEGA_WEB: &str = "https://mega.nz/fm";

/// The applet: polls the shared core for MEGAcmd's state, shows it in the
/// panel icon and popup, runs the core's actions and shows the notifications
/// the core hands it. Polls every 3 seconds while the popup is open and every
/// `refresh_interval_sec` (at least 10) otherwise.
pub struct Applet {
    /// COSMIC's state of the applet.
    core: Core,
    /// The settings in use.
    pub(crate) config: Config,
    /// The last view the core printed.
    pub(crate) view: View,
    /// A short note about the last action; empty when there is none.
    pub(crate) action_status: String,
    /// Counts status notes, so only the latest one's timer clears it.
    status_generation: u64,
    /// The key of the sync or backup whose remove button is armed.
    pub(crate) armed: Option<String>,
    /// Counts arming, so only the latest arming's timer disarms.
    arm_generation: u64,
    /// The popup's window, while it is open.
    popup: Option<Id>,
    /// The preview name of the status run in progress, if one runs.
    status_running: Option<String>,
    /// Whether another status run is wanted when the current one ends.
    status_pending: bool,
    /// How many guided-dialog checks are left.
    guided_checks: u32,
    /// The actions running now, so the same one is not started twice.
    acting: HashSet<Vec<String>>,
}

/// What happens in the applet.
#[derive(Debug, Clone)]
pub enum Message {
    /// The panel icon was pressed: open or close the popup.
    TogglePopup,
    /// Open the popup unless it is open already.
    OpenPopup,
    /// The popup with this ID was closed.
    PopupClosed(Id),
    /// Ask the core for the state again.
    Refresh,
    /// A status run for the preview name (empty for the live state) ended.
    Status(String, Result<View, String>),
    /// Run the core's command line with these arguments.
    Act(Vec<String>),
    /// The action with these arguments ended.
    ActDone(Vec<String>, Result<String, String>),
    /// Open the named guided dialog with these data arguments.
    Guided(&'static str, Vec<String>),
    /// Check again while a guided dialog may be open.
    GuidedCheck,
    /// Open this folder in the file manager.
    OpenFolder(String),
    /// Open MEGA in the web browser.
    OpenWeb,
    /// Opening a folder or the browser ended.
    Opened(Result<(), String>),
    /// Arm the remove button of the row with this key.
    Arm(String),
    /// Disarm the remove button if it was armed by this arming.
    Disarm(u64),
    /// The armed remove button was pressed again: run this removal.
    Remove(Vec<String>),
    /// Clear the status note if it is still this one.
    ClearActionStatus(u64),
    /// A notification could not be shown, for this reason.
    NoticeFailed(String),
    /// The settings changed.
    ConfigChanged(Config),
}

impl Applet {
    /// An applet in COSMIC's state CORE with the settings CONFIG, showing
    /// the unknown state until the first status arrives.
    fn new(core: Core, config: Config) -> Self {
        Self {
            core,
            config,
            view: View::unknown(""),
            action_status: String::new(),
            status_generation: 0,
            armed: None,
            arm_generation: 0,
            popup: None,
            status_running: None,
            status_pending: false,
            guided_checks: 0,
            acting: HashSet::new(),
        }
    }

    /// The core's folder, from the settings or the data folders.
    fn core_dir(&self) -> Option<PathBuf> {
        core::core_dir(&self.config.core_dir)
    }

    /// Whether a saved state is shown instead of MEGAcmd's.
    fn previewing(&self) -> bool {
        !self.config.preview_name.is_empty()
    }

    /// ARGS for the core's command line, after the MEGAcmd folder when one is set.
    fn core_args(&self, args: Vec<String>) -> Vec<String> {
        if self.config.megacmd_dir.is_empty() {
            return args;
        }
        std::iter::once(format!("--megacmd-dir={}", self.config.megacmd_dir))
            .chain(args)
            .collect()
    }

    /// Starts a status run, or, while one runs, has another run once it ends.
    fn refresh(&mut self) -> Task<Message> {
        if self.status_running.is_some() {
            self.status_pending = true;
            return Task::none();
        }
        let preview = self.config.preview_name.clone();
        let mut args: Vec<String> = vec!["status".into(), "--timeout".into(), "20".into()];
        if !preview.is_empty() {
            args.extend(["--preview".into(), preview.clone()]);
        }
        self.status_running = Some(preview.clone());
        self.status_pending = false;
        Task::perform(
            core::status(self.core_dir(), self.core_args(args)),
            move |result| cosmic::Action::App(Message::Status(preview.clone(), result)),
        )
    }

    /// Takes the result of the status run for PREVIEW: shows it unless the
    /// preview setting changed meanwhile, and starts a wanted run.
    fn status_done(&mut self, preview: String, result: Result<View, String>) -> Task<Message> {
        self.status_running = None;
        let mut tasks = Vec::new();
        if preview == self.config.preview_name {
            match result {
                Ok(mut view) => {
                    let notices = std::mem::take(&mut view.notices);
                    self.view = view;
                    if !notices.is_empty() {
                        tasks.push(self.notify(notices));
                    }
                }
                Err(error) => self.view = View::unknown(error),
            }
        } else {
            self.status_pending = true;
        }
        if self.status_pending {
            tasks.push(self.refresh());
        }
        Task::batch(tasks)
    }

    /// Shows TEXT as the status note for a few seconds.
    fn show_status(&mut self, text: String) -> Task<Message> {
        self.action_status = text;
        self.status_generation += 1;
        later(
            STATUS_SECS,
            Message::ClearActionStatus(self.status_generation),
        )
    }

    /// While a preview is shown, refuses actions: shows a note and returns
    /// its task; otherwise returns `None`.
    fn preview_refusal(&mut self) -> Option<Task<Message>> {
        self.previewing()
            .then(|| self.show_status("Preview: actions are off".into()))
    }

    /// Runs the core's command line with ARGS, unless the same action runs.
    fn act(&mut self, args: Vec<String>) -> Task<Message> {
        if let Some(refused) = self.preview_refusal() {
            return refused;
        }
        if !self.acting.insert(args.clone()) {
            return Task::none();
        }
        let call = core::run(self.core_dir(), self.core_args(args.clone()));
        Task::perform(call, move |result| {
            cosmic::Action::App(Message::ActDone(args.clone(), result))
        })
    }

    /// Shows NOTICES as desktop notifications, in their order.
    fn notify(&self, notices: Vec<Notice>) -> Task<Message> {
        let preview = self.previewing();
        Task::run(
            cosmic::iced::stream::channel(1, async move |mut output| {
                let mut watched = FuturesUnordered::new();
                for notice in notices {
                    match show_notice(&notice, preview).await {
                        Ok(handle) => watched.push(watch_notice(handle)),
                        Err(error) => {
                            let _ = output.send(Message::NoticeFailed(error)).await;
                        }
                    }
                }
                while let Some(clicked) = watched.next().await {
                    if clicked {
                        let _ = output.send(Message::OpenPopup).await;
                    }
                }
            }),
            cosmic::Action::App,
        )
    }

    /// Opens the popup and checks the state.
    fn open_popup(&mut self) -> Task<Message> {
        let open = cosmic::surface::surface_task(cosmic::surface::action::app_popup(
            |_| Default::default(),
            |app: &mut Self| {
                let id = Id::unique();
                app.popup = Some(id);
                app.core.applet.get_popup_settings(
                    app.core.main_window_id().unwrap(),
                    id,
                    None,
                    None,
                    None,
                )
            },
            None,
        ));
        Task::batch([open, self.refresh()])
    }
}

/// A task that hands back MESSAGE after SECONDS.
fn later(seconds: u64, message: Message) -> Task<Message> {
    Task::perform(
        async move { tokio::time::sleep(Duration::from_secs(seconds)).await },
        move |()| cosmic::Action::App(message.clone()),
    )
}

/// The title of a notification, marked when it comes from a preview.
fn notice_title(title: &str, preview: bool) -> String {
    if preview {
        format!("{title} (preview)")
    } else {
        title.to_string()
    }
}

/// Shows NOTICE as a desktop notification with plain-text title and body;
/// returns its handle, or why it could not be shown.
async fn show_notice(
    notice: &Notice,
    preview: bool,
) -> Result<notify_rust::NotificationHandle, String> {
    let urgency = if notice.urgency == "critical" {
        notify_rust::Urgency::Critical
    } else {
        notify_rust::Urgency::Normal
    };
    notify_rust::Notification::new()
        .appname("MEGA")
        .summary(&notice_title(&notice.title, preview))
        .body(&notice.body)
        .icon(notice_icon(&notice.icon))
        .urgency(urgency)
        .action("default", "Open")
        .show_async()
        .await
        .map_err(|error| error.to_string())
}

/// Waits until the notification HANDLE is clicked or closed, for at most
/// [`NOTICE_WATCH`]; true when it was clicked.
async fn watch_notice(handle: notify_rust::NotificationHandle) -> bool {
    let mut clicked = false;
    let wait = handle.wait_for_action_async(|response| {
        clicked = matches!(response, notify_rust::NotificationResponse::Default);
    });
    let _ = tokio::time::timeout(NOTICE_WATCH, wait).await;
    clicked
}

/// Opens MEGA's web pages in the default browser and waits for the opener to end.
async fn open_web() -> Result<(), String> {
    let status = tokio::process::Command::new("xdg-open")
        .arg(MEGA_WEB)
        .stdin(std::process::Stdio::null())
        .status()
        .await
        .map_err(|error| format!("Could not open the browser: {error}"))?;
    if status.success() {
        Ok(())
    } else {
        Err("Could not open the browser".into())
    }
}

impl cosmic::Application for Applet {
    type Executor = cosmic::SingleThreadExecutor;
    type Flags = ();
    type Message = Message;
    const APP_ID: &'static str = APP_ID;

    fn core(&self) -> &Core {
        &self.core
    }

    fn core_mut(&mut self) -> &mut Core {
        &mut self.core
    }

    fn init(core: Core, _flags: Self::Flags) -> (Self, Task<Message>) {
        let config = ConfigHelper::new(APP_ID, Config::VERSION)
            .map(|helper| Config::get_entry(&helper).unwrap_or_else(|(_, config)| config))
            .unwrap_or_default();
        let mut applet = Self::new(core, config);
        let task = applet.refresh();
        (applet, task)
    }

    fn on_close_requested(&self, id: Id) -> Option<Message> {
        Some(Message::PopupClosed(id))
    }

    fn subscription(&self) -> Subscription<Message> {
        let seconds = if self.popup.is_some() {
            OPEN_POLL_SECS
        } else {
            self.config.refresh_interval_sec.max(MIN_POLL_SECS)
        };
        let mut subscriptions = vec![
            time::every(Duration::from_secs(seconds)).map(|_| Message::Refresh),
            self.core
                .watch_config::<Config>(APP_ID)
                .map(|update| Message::ConfigChanged(update.config)),
        ];
        if self.guided_checks > 0 {
            subscriptions.push(
                time::every(Duration::from_secs(GUIDED_CHECK_SECS)).map(|_| Message::GuidedCheck),
            );
        }
        Subscription::batch(subscriptions)
    }

    fn update(&mut self, message: Message) -> Task<Message> {
        match message {
            Message::TogglePopup => {
                if let Some(id) = self.popup.take() {
                    return destroy_popup(id);
                }
                return self.open_popup();
            }
            Message::OpenPopup => {
                if self.popup.is_none() {
                    return self.open_popup();
                }
            }
            Message::PopupClosed(id) => {
                if self.popup == Some(id) {
                    self.popup = None;
                }
            }
            Message::Refresh => return self.refresh(),
            Message::Status(preview, result) => return self.status_done(preview, result),
            Message::Act(args) => return self.act(args),
            Message::ActDone(args, result) => {
                self.acting.remove(&args);
                let mut tasks = vec![self.refresh(), later(AFTER_ACTION_SECS, Message::Refresh)];
                if let Err(error) = result {
                    tasks.push(self.show_status(error));
                }
                return Task::batch(tasks);
            }
            Message::Guided(name, args) => {
                let mut command = vec!["guided".to_string()];
                if !self.config.terminal.is_empty() {
                    command.push(format!("--terminal={}", self.config.terminal));
                }
                command.extend([name.to_string(), "--".to_string()]);
                command.extend(args);
                if !self.previewing() {
                    self.guided_checks = GUIDED_CHECKS;
                }
                return self.act(command);
            }
            Message::GuidedCheck => {
                self.guided_checks = self.guided_checks.saturating_sub(1);
                return self.refresh();
            }
            Message::OpenFolder(path) => {
                if let Some(refused) = self.preview_refusal() {
                    return refused;
                }
                let call = core::run(
                    self.core_dir(),
                    self.core_args(vec!["open-folder".into(), path]),
                );
                return Task::perform(call, |result| {
                    cosmic::Action::App(Message::Opened(result.map(drop)))
                });
            }
            Message::OpenWeb => {
                return Task::perform(open_web(), |result| {
                    cosmic::Action::App(Message::Opened(result))
                });
            }
            Message::Opened(Ok(())) => {}
            Message::Opened(Err(error)) => return self.show_status(error),
            Message::Arm(key) => {
                self.armed = Some(key);
                self.arm_generation += 1;
                return later(ARM_SECS, Message::Disarm(self.arm_generation));
            }
            Message::Disarm(generation) => {
                if generation == self.arm_generation {
                    self.armed = None;
                }
            }
            Message::Remove(args) => {
                self.armed = None;
                self.arm_generation += 1;
                return self.act(args);
            }
            Message::ClearActionStatus(generation) => {
                if generation == self.status_generation {
                    self.action_status.clear();
                }
            }
            Message::NoticeFailed(error) => {
                eprintln!("Could not show a notification: {error}");
                return self.show_status(format!("Could not show a notification: {error}"));
            }
            Message::ConfigChanged(config) => {
                self.config = config;
                return self.refresh();
            }
        }
        Task::none()
    }

    fn view(&self) -> Element<'_, Message> {
        self.core
            .applet
            .icon_button(panel_icon(&self.view.kind))
            .on_press_down(Message::TogglePopup)
            .into()
    }

    fn view_window(&self, _id: Id) -> Element<'_, Message> {
        popup::view(self)
    }

    fn style(&self) -> Option<cosmic::iced::theme::Style> {
        Some(cosmic::applet::style())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use cosmic::Application;

    /// An applet showing the saved state PREVIEW (empty for the live state).
    fn applet(preview: &str) -> Applet {
        Applet::new(
            Core::default(),
            Config {
                preview_name: preview.into(),
                ..Config::default()
            },
        )
    }

    /// A readable view of the state KIND.
    fn view(kind: &str) -> View {
        View {
            ok: true,
            kind: kind.into(),
            ..View::default()
        }
    }

    #[test]
    fn preview_notices_are_marked() {
        assert_eq!(
            notice_title("MEGA sync stopped", true),
            "MEGA sync stopped (preview)"
        );
        assert_eq!(
            notice_title("MEGA sync stopped", false),
            "MEGA sync stopped"
        );
    }

    #[test]
    fn the_start_view_is_unknown() {
        let applet = applet("");
        assert_eq!(applet.view.kind, "unknown");
        assert!(applet.view.offer.is_empty());
    }

    #[test]
    fn one_status_run_at_a_time_and_one_more_after_it() {
        let mut applet = applet("");
        let _ = applet.update(Message::Refresh);
        let _ = applet.update(Message::Refresh);
        let _ = applet.update(Message::Refresh);
        assert_eq!(applet.status_running.as_deref(), Some(""));
        assert!(applet.status_pending);
        let _ = applet.update(Message::Status(String::new(), Ok(view("paused"))));
        assert_eq!(applet.view.kind, "paused");
        assert_eq!(applet.status_running.as_deref(), Some(""));
        assert!(!applet.status_pending);
        let _ = applet.update(Message::Status(String::new(), Ok(view("synced"))));
        assert_eq!(applet.status_running, None);
    }

    #[test]
    fn a_result_for_another_mode_is_dropped() {
        let mut applet = applet("");
        let _ = applet.update(Message::Refresh);
        applet.config.preview_name = "errors".into();
        let _ = applet.update(Message::Status(String::new(), Ok(view("paused"))));
        assert_eq!(applet.view.kind, "unknown");
        assert_eq!(applet.status_running.as_deref(), Some("errors"));
    }

    #[test]
    fn a_core_that_cannot_run_shows_the_unknown_state() {
        let mut applet = applet("");
        let _ = applet.update(Message::Refresh);
        let _ = applet.update(Message::Status(String::new(), Err("No python3".into())));
        assert_eq!(applet.view.kind, "unknown");
        assert_eq!(applet.view.kind_text, "No python3");
    }

    #[test]
    fn the_same_action_does_not_run_twice_at_once() {
        let mut applet = applet("");
        let toggle = vec!["toggle-all".to_string()];
        let _ = applet.update(Message::Act(toggle.clone()));
        let _ = applet.update(Message::Act(toggle.clone()));
        assert_eq!(applet.acting.len(), 1);
        let _ = applet.update(Message::ActDone(toggle.clone(), Ok(String::new())));
        assert!(applet.acting.is_empty());
        let _ = applet.update(Message::Act(toggle));
        assert_eq!(applet.acting.len(), 1);
    }

    #[test]
    fn a_failed_action_leaves_its_reason() {
        let mut applet = applet("");
        let _ = applet.update(Message::ActDone(vec![], Err("Nobody is logged in".into())));
        assert_eq!(applet.action_status, "Nobody is logged in");
    }

    #[test]
    fn a_later_arming_is_not_cut_short_by_an_earlier_timer() {
        let mut applet = applet("");
        let _ = applet.update(Message::Arm("a".into()));
        let first = applet.arm_generation;
        let _ = applet.update(Message::Arm("b".into()));
        let _ = applet.update(Message::Arm("a".into()));
        let _ = applet.update(Message::Disarm(first));
        assert_eq!(applet.armed.as_deref(), Some("a"));
        let _ = applet.update(Message::Disarm(applet.arm_generation));
        assert_eq!(applet.armed, None);
    }

    #[test]
    fn confirming_a_removal_disarms() {
        let mut applet = applet("");
        let _ = applet.update(Message::Arm("a".into()));
        let _ = applet.update(Message::Remove(vec!["remove-sync".into(), "AbC1".into()]));
        assert_eq!(applet.armed, None);
        assert!(
            applet
                .acting
                .contains(&vec!["remove-sync".to_string(), "AbC1".to_string()])
        );
    }

    #[test]
    fn a_later_status_note_outlives_an_earlier_timer() {
        let mut applet = applet("");
        let _ = applet.update(Message::Opened(Err("first".into())));
        let first = applet.status_generation;
        let _ = applet.update(Message::Opened(Err("second".into())));
        let _ = applet.update(Message::ClearActionStatus(first));
        assert_eq!(applet.action_status, "second");
        let _ = applet.update(Message::ClearActionStatus(applet.status_generation));
        assert!(applet.action_status.is_empty());
    }

    #[test]
    fn a_guided_dialog_gets_its_arguments_after_the_options() {
        let mut applet = applet("");
        applet.config.terminal = "foot -e".into();
        let _ = applet.update(Message::Guided("mega-add-sync", vec!["--x".into()]));
        let expected: Vec<String> = ["guided", "--terminal=foot -e", "mega-add-sync", "--", "--x"]
            .map(String::from)
            .into();
        assert!(applet.acting.contains(&expected));
        assert_eq!(applet.guided_checks, GUIDED_CHECKS);
        let _ = applet.update(Message::GuidedCheck);
        assert_eq!(applet.guided_checks, GUIDED_CHECKS - 1);
    }

    #[test]
    fn the_megacmd_folder_goes_first_as_one_token() {
        let mut applet = applet("");
        applet.config.megacmd_dir = "/opt/megacmd".into();
        assert_eq!(
            applet.core_args(vec!["pause-all".into()]),
            ["--megacmd-dir=/opt/megacmd", "pause-all"].map(String::from)
        );
    }

    #[test]
    fn a_preview_refuses_actions_and_starts_no_checks() {
        let mut applet = applet("errors");
        let _ = applet.update(Message::Guided("mega-account-login", vec![]));
        let _ = applet.update(Message::OpenFolder("/home/user".into()));
        let _ = applet.update(Message::Act(vec!["pause-all".into()]));
        assert!(applet.acting.is_empty());
        assert_eq!(applet.guided_checks, 0);
        assert_eq!(applet.action_status, "Preview: actions are off");
    }
}
