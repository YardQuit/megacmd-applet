// app.rs: the MEGA applet's state, messages and actions.
// SPDX-License-Identifier: GPL-3.0-or-later

use std::path::PathBuf;
use std::time::Duration;

use cosmic::Element;
use cosmic::app::Core;
use cosmic::app::Task;
use cosmic::cosmic_config::{Config as ConfigHelper, CosmicConfigEntry};
use cosmic::iced::platform_specific::shell::wayland::commands::popup::destroy_popup;
use cosmic::iced::{Subscription, time, window::Id};

use crate::config::Config;
use crate::model::{Notice, View, panel_icon};
use crate::{core, popup};

/// The applet's ID: its desktop file, settings and icon names.
pub const APP_ID: &str = "io.github.yardquit.MegaCmd";

/// The applet: polls the shared core for MEGAcmd's state, shows it in the
/// panel icon and popup, runs the core's actions and shows the notifications
/// the core hands it. Polls every 3 seconds while the popup is open and every
/// `refresh_interval_sec` otherwise.
pub struct Applet {
    core: Core,
    pub(crate) config: Config,
    pub(crate) view: View,
    pub(crate) last_error: String,
    pub(crate) action_status: String,
    /// The key of the sync or backup whose remove button is armed.
    pub(crate) armed: Option<String>,
    popup: Option<Id>,
    shown_preview: Option<String>,
}

#[derive(Debug, Clone)]
pub enum Message {
    TogglePopup,
    OpenPopup,
    PopupClosed(Id),
    Refresh,
    Status(Result<View, String>),
    Act(Vec<String>),
    ActDone(Result<String, String>),
    Guided(&'static str, Vec<String>),
    OpenFolder(String),
    OpenWeb,
    Arm(String),
    Disarm(String),
    ClearActionStatus,
    ConfigChanged(Config),
    Ignore,
}

impl Applet {
    fn core_dir(&self) -> Option<PathBuf> {
        core::core_dir(&self.config.core_dir)
    }

    fn preview_name(&self) -> String {
        self.config
            .preview_name
            .chars()
            .filter(|c| c.is_ascii_alphanumeric() || *c == '-' || *c == '_')
            .collect()
    }

    fn refresh(&mut self) -> Task<Message> {
        let dir = self.core_dir();
        let preview = self.preview_name();
        let mut args: Vec<String> = vec!["status".into(), "--timeout".into(), "20".into()];
        if !preview.is_empty() {
            // The saved states in fixtures/ are written for the home folder /home/user.
            let fixture = dir
                .clone()
                .unwrap_or_default()
                .join("fixtures")
                .join(format!("{preview}.json"));
            args = vec![
                "status".into(),
                "--fixture".into(),
                fixture.to_string_lossy().into_owned(),
                "--home".into(),
                "/home/user".into(),
            ];
            if self.shown_preview.as_deref() != Some(preview.as_str()) {
                args.push("--fresh".into());
            }
        }
        self.shown_preview = Some(preview);
        Task::perform(core::status(dir, args), |result| {
            cosmic::Action::App(Message::Status(result))
        })
    }

    /// False, with a note in the popup, while a preview is shown.
    fn actions_allowed(&mut self) -> bool {
        if self.preview_name().is_empty() {
            return true;
        }
        self.action_status = "Preview: actions are off".into();
        false
    }

    fn later(seconds: u64, message: Message) -> Task<Message> {
        Task::perform(
            tokio::time::sleep(Duration::from_secs(seconds)),
            move |()| cosmic::Action::App(message.clone()),
        )
    }

    fn notify(&self, notice: Notice) -> Task<Message> {
        let label = if self.preview_name().is_empty() {
            ""
        } else {
            " (preview)"
        };
        let title = format!("{}{label}", notice.title);
        Task::perform(show_notice(title, notice), |opened| {
            cosmic::Action::App(if opened {
                Message::OpenPopup
            } else {
                Message::Ignore
            })
        })
    }

    fn open_popup(&mut self) -> Task<Message> {
        cosmic::surface::surface_task(cosmic::surface::action::app_popup(
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
        ))
    }
}

/// Shows NOTICE titled TITLE as a desktop notification; true when it was clicked.
async fn show_notice(title: String, notice: Notice) -> bool {
    tokio::task::spawn_blocking(move || {
        let urgency = if notice.urgency == "critical" {
            notify_rust::Urgency::Critical
        } else {
            notify_rust::Urgency::Normal
        };
        let Ok(handle) = notify_rust::Notification::new()
            .appname("MEGA")
            .summary(&title)
            .body(&escape_markup(&notice.body))
            .icon(if notice.icon == "cloud" {
                "folder-remote-symbolic"
            } else {
                "dialog-error-symbolic"
            })
            .urgency(urgency)
            .action("default", "Open")
            .show()
        else {
            return false;
        };
        let mut opened = false;
        handle.wait_for_action(|action| opened = action == "default");
        opened
    })
    .await
    .unwrap_or(false)
}

/// TEXT with "&", "<" and ">" escaped, for notification bodies, which the
/// notification service may render as styled text.
fn escape_markup(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
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
        let mut applet = Self {
            core,
            config,
            view: View {
                kind: "off".into(),
                kind_text: "Not logged in".into(),
                ..Default::default()
            },
            last_error: String::new(),
            action_status: String::new(),
            armed: None,
            popup: None,
            shown_preview: None,
        };
        let task = applet.refresh();
        (applet, task)
    }

    fn on_close_requested(&self, id: Id) -> Option<Message> {
        Some(Message::PopupClosed(id))
    }

    fn subscription(&self) -> Subscription<Message> {
        let seconds = if self.popup.is_some() {
            3
        } else {
            self.config.refresh_interval_sec.max(10)
        };
        Subscription::batch([
            time::every(Duration::from_secs(seconds)).map(|_| Message::Refresh),
            self.core
                .watch_config::<Config>(APP_ID)
                .map(|update| Message::ConfigChanged(update.config)),
        ])
    }

    fn update(&mut self, message: Message) -> Task<Message> {
        match message {
            Message::TogglePopup => {
                if let Some(id) = self.popup.take() {
                    return destroy_popup(id);
                }
                return Task::batch([self.open_popup(), self.refresh()]);
            }
            Message::OpenPopup => {
                if self.popup.is_none() {
                    return Task::batch([self.open_popup(), self.refresh()]);
                }
            }
            Message::PopupClosed(id) => {
                if self.popup == Some(id) {
                    self.popup = None;
                }
            }
            Message::Refresh => return self.refresh(),
            Message::Status(Ok(mut view)) => {
                let notices = std::mem::take(&mut view.notices);
                self.last_error = view.error.clone();
                self.view = view;
                return Task::batch(notices.into_iter().map(|notice| self.notify(notice)));
            }
            Message::Status(Err(error)) => self.last_error = error,
            Message::Act(args) => {
                if !self.actions_allowed() {
                    return Self::later(4, Message::ClearActionStatus);
                }
                return Task::perform(core::run(self.core_dir(), args), |result| {
                    cosmic::Action::App(Message::ActDone(result))
                });
            }
            Message::ActDone(result) => {
                let mut tasks = vec![self.refresh(), Self::later(2, Message::Refresh)];
                if let Err(error) = result {
                    self.action_status = error;
                    tasks.push(Self::later(4, Message::ClearActionStatus));
                }
                return Task::batch(tasks);
            }
            Message::Guided(name, args) => {
                let mut command = vec!["guided".to_string(), name.to_string()];
                command.extend(args);
                if !self.config.terminal.is_empty() {
                    command.extend(["--terminal".to_string(), self.config.terminal.clone()]);
                }
                // A guided dialog runs on its own; keep checking for a while.
                let checks = (1..=60).map(|i| Self::later(5 * i, Message::Refresh));
                return Task::batch(
                    std::iter::once(self.update(Message::Act(command))).chain(checks),
                );
            }
            Message::OpenFolder(path) => {
                // Only absolute paths, so a value can never pass for an option or address.
                if !path.starts_with('/') {
                    return Task::none();
                }
                if !self.actions_allowed() {
                    return Self::later(4, Message::ClearActionStatus);
                }
                let _ = std::process::Command::new("xdg-open").arg(&path).spawn();
            }
            Message::OpenWeb => {
                let _ = std::process::Command::new("xdg-open")
                    .arg("https://mega.nz/fm")
                    .spawn();
            }
            Message::Arm(key) => {
                self.armed = Some(key.clone());
                return Self::later(4, Message::Disarm(key));
            }
            Message::Disarm(key) => {
                if self.armed.as_deref() == Some(key.as_str()) {
                    self.armed = None;
                }
            }
            Message::ClearActionStatus => self.action_status.clear(),
            Message::ConfigChanged(config) => {
                self.config = config;
                return self.refresh();
            }
            Message::Ignore => {}
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
