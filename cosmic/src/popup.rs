// popup.rs: the MEGA applet's popup.
// SPDX-License-Identifier: GPL-3.0-or-later

use cosmic::applet::{menu_button, padded_control};
use cosmic::iced::widget::{column, row};
use cosmic::iced::{Alignment, Length, Limits};
use cosmic::widget::{button, divider, icon, scrollable, text, toggler};
use cosmic::{Application, Element};

use crate::app::{Applet, Message};
use crate::model::state_icon;

/// The popup's width, room for a folder pair on one line.
pub const WIDTH: f32 = 440.0;

/// The popup: the overall state, the account's storage and transfers with a
/// switch that pauses or resumes all syncing, the sync folders and backups
/// with their buttons, and the actions to add more. When logged out it
/// offers to log in (or to start MEGAcmd).
pub fn view(app: &Applet) -> Element<'_, Message> {
    let view = &app.view;
    let mut content = column![padded_control(
        row![
            icon::from_name(state_icon(&view.kind)).size(24),
            column![
                text::heading("MEGA"),
                text::caption(if view.installed {
                    view.kind_text.clone()
                } else {
                    "MEGAcmd is not installed".into()
                }),
            ],
        ]
        .spacing(8)
        .align_y(Alignment::Center)
    )]
    .padding([8, 0]);

    if view.logged_in {
        content = content.push(account(app));
        content = content.push(separator());
        content = content.push(heading("Sync folders"));
        for sync in &view.syncs {
            content = content.push(item_row(
                app,
                &sync.key,
                state_icon(&sync.kind),
                format!("{}  ↔  {}", sync.local_display, sync.remote),
                &sync.meta,
                if sync.paused {
                    "media-playback-start-symbolic"
                } else {
                    "media-playback-pause-symbolic"
                },
                Message::Act(vec![
                    if sync.paused { "resume" } else { "pause" }.into(),
                    sync.id.clone(),
                ]),
                Message::OpenFolder(sync.local.clone()),
                Message::Act(vec!["remove-sync".into(), sync.id.clone()]),
            ));
        }
        content = content.push(
            menu_button(text::body("Add sync…")).on_press(Message::Guided(
                "mega-add-sync",
                vec![app.config.sync_folder.clone()],
            )),
        );
        content = content.push(separator());
        content = content.push(heading("Backups"));
        for backup in &view.backups {
            let icon_name = if backup.failed {
                state_icon("error")
            } else if backup.last_status.is_empty() {
                "document-save-symbolic"
            } else {
                state_icon("synced")
            };
            content = content.push(item_row(
                app,
                &backup.key,
                icon_name,
                format!("{}  →  {}", backup.local_display, backup.remote),
                &backup.meta,
                "emblem-system-symbolic",
                Message::Guided(
                    "mega-edit-backup",
                    vec![
                        backup.tag.clone(),
                        backup.period.clone(),
                        backup.max_backups.to_string(),
                    ],
                ),
                Message::OpenFolder(backup.local.clone()),
                Message::Act(vec!["remove-backup".into(), backup.tag.clone()]),
            ));
        }
        content = content.push(
            menu_button(text::body("Add backup…")).on_press(Message::Guided(
                "mega-add-backup",
                vec![app.config.backup_folder.clone()],
            )),
        );
        content = content.push(separator());
        content = content
            .push(menu_button(text::body("Open MEGA in the browser")).on_press(Message::OpenWeb));
    } else {
        let label = if view.running {
            "Log in to MEGA"
        } else {
            "Start MEGAcmd"
        };
        content = content.push(
            menu_button(text::body(label)).on_press(Message::Guided("mega-account-login", vec![])),
        );
    }

    let note = if app.action_status.is_empty() {
        &app.last_error
    } else {
        &app.action_status
    };
    if !note.is_empty() {
        content = content.push(padded_control(text::caption(note.clone())));
    }

    app.core()
        .applet
        .popup_container(scrollable(content).height(Length::Shrink))
        .limits(Limits::NONE.width(WIDTH).min_height(1.0).max_height(1000.0))
        .into()
}

fn account(app: &Applet) -> Element<'_, Message> {
    let view = &app.view;
    let mut lines = column![text::body(view.email.clone())].spacing(2);
    if !view.usage_text.is_empty() {
        lines = lines.push(text::body(format!("Stored: {}", view.usage_text)));
    }
    if !view.transfers_text.is_empty() {
        lines = lines.push(text::caption(view.transfers_text.clone()));
    }
    if !view.syncs.is_empty() {
        lines = lines.push(
            toggler(view.any_running)
                .label("Syncing".to_string())
                .width(Length::Fill)
                .on_toggle(|_| Message::Act(vec!["toggle-all".into()])),
        );
    }
    padded_control(lines).into()
}

fn heading(label: &str) -> Element<'_, Message> {
    padded_control(text::heading(label.to_string())).into()
}

fn separator<'a>() -> Element<'a, Message> {
    padded_control(divider::horizontal::default())
        .padding([4, 12])
        .into()
}

/// One sync folder or backup: its status icon, folder pair and second line,
/// and buttons for its main action, opening its folder and removing it.
/// Removing asks twice: the first press arms the button for a few seconds.
#[allow(clippy::too_many_arguments)]
fn item_row<'a>(
    app: &'a Applet,
    key: &str,
    icon_name: &'static str,
    title: String,
    meta: &str,
    action_icon: &'static str,
    action: Message,
    open: Message,
    remove: Message,
) -> Element<'a, Message> {
    let armed = app.armed.as_deref() == Some(key);
    let remove_button = if armed {
        button::icon(icon::from_name("object-select-symbolic")).on_press(remove)
    } else {
        button::icon(icon::from_name("user-trash-symbolic")).on_press(Message::Arm(key.to_string()))
    };
    padded_control(
        row![
            icon::from_name(icon_name).size(16),
            column![text::body(title), text::caption(meta.to_string())].width(Length::Fill),
            button::icon(icon::from_name(action_icon)).on_press(action),
            button::icon(icon::from_name("folder-open-symbolic")).on_press(open),
            remove_button,
        ]
        .spacing(8)
        .align_y(Alignment::Center),
    )
    .into()
}
