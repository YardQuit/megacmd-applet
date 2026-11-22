// popup.rs: the MEGA applet's popup.
// SPDX-License-Identifier: GPL-3.0-or-later

use cosmic::applet::{menu_button, padded_control};
use cosmic::iced::widget::text::Wrapping;
use cosmic::iced::widget::{column, row};
use cosmic::iced::{Alignment, Color, Length, Limits};
use cosmic::widget::{button, divider, icon, scrollable, text, toggler, tooltip};
use cosmic::{Application, Element};

use crate::app::{Applet, Message};
use crate::model::state_icon;

/// The popup's width, room for a folder pair on one line.
pub const WIDTH: f32 = 440.0;

/// The popup: the overall state, the account's storage and transfers with a
/// switch that pauses or resumes all syncing, the sync folders and backups
/// with their buttons, and the actions to add more. When nobody is logged
/// in it shows the state and the core's offer (to log in or start MEGAcmd).
pub fn view(app: &Applet) -> Element<'_, Message> {
    let view = &app.view;
    let mut content = column![padded_control(
        row![
            icon::from_name(state_icon(&view.kind)).size(24),
            column![
                text::heading("MEGA"),
                text::caption(view.kind_text.as_str()).wrapping(Wrapping::WordOrGlyph),
            ]
            .width(Length::Fill),
        ]
        .spacing(8)
        .align_y(Alignment::Center)
    )]
    .padding([8, 0]);

    if view.signed_in() {
        content = content.push(account(app));
        content = content.push(separator());
        content = content.push(heading("Sync folders"));
        for sync in &view.syncs {
            let (action_icon, action_label, verb) = if sync.paused {
                ("media-playback-start-symbolic", "Resume", "resume")
            } else {
                ("media-playback-pause-symbolic", "Pause", "pause")
            };
            content = content.push(item_row(
                app,
                Item {
                    key: &sync.key,
                    icon_name: state_icon(&sync.kind),
                    title: &sync.title,
                    meta: &sync.meta,
                    action_icon,
                    action_label,
                    action: Message::Act(vec![verb.into(), sync.id.clone()]),
                    open: Message::OpenFolder(sync.local.clone()),
                    remove: Message::Remove(vec!["remove-sync".into(), sync.id.clone()]),
                },
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
            content = content.push(item_row(
                app,
                Item {
                    key: &backup.key,
                    icon_name: state_icon(&backup.kind),
                    title: &backup.title,
                    meta: &backup.meta,
                    action_icon: "emblem-system-symbolic",
                    action_label: "Edit",
                    action: Message::Guided(
                        "mega-edit-backup",
                        vec![
                            backup.tag.clone(),
                            backup.period.clone(),
                            backup.max_backups.to_string(),
                        ],
                    ),
                    open: Message::OpenFolder(backup.local.clone()),
                    remove: Message::Remove(vec!["remove-backup".into(), backup.tag.clone()]),
                },
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
    } else if !view.offer.is_empty() {
        content = content.push(tooltip(
            menu_button(text::body(view.offer_text.as_str()))
                .on_press(Message::Guided("mega-account-login", vec![])),
            text::caption(view.offer_hint.as_str()),
            tooltip::Position::Bottom,
        ));
    }

    for note in [app.action_status.as_str(), view.note()] {
        if !note.is_empty() {
            content = content.push(padded_control(
                text::caption(note).wrapping(Wrapping::WordOrGlyph),
            ));
        }
    }

    app.core()
        .applet
        .popup_container(scrollable(content).height(Length::Shrink))
        .limits(Limits::NONE.width(WIDTH).min_height(1.0).max_height(1000.0))
        .into()
}

/// The account's address, storage line (highlighted when storage runs
/// short), transfers and the switch that pauses or resumes all syncs.
fn account(app: &Applet) -> Element<'_, Message> {
    let view = &app.view;
    let mut lines =
        column![text::body(view.email.as_str()).wrapping(Wrapping::WordOrGlyph)].spacing(2);
    if !view.usage_text.is_empty() {
        let mut stored = text::body(format!("Stored: {}", view.usage_text));
        if view.storage_level > 0 {
            stored = stored.class(warning_text());
        }
        lines = lines.push(stored);
    }
    if !view.transfers_text.is_empty() {
        lines = lines.push(text::caption(view.transfers_text.as_str()));
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

/// The text style of a warning, in the theme's colour for negative states.
fn warning_text() -> cosmic::theme::Text {
    let colour = cosmic::theme::active().cosmic().destructive_text_color();
    cosmic::theme::Text::Color(Color::from(colour))
}

/// A section heading reading LABEL.
fn heading(label: &str) -> Element<'_, Message> {
    padded_control(text::heading(label)).into()
}

/// A horizontal line between sections.
fn separator<'a>() -> Element<'a, Message> {
    padded_control(divider::horizontal::default())
        .padding([4, 12])
        .into()
}

/// What a row of the sync or backup list shows and does.
struct Item<'a> {
    /// The key that stays the same for this sync or backup.
    key: &'a str,
    /// The state icon.
    icon_name: &'static str,
    /// The first line: the folder pair.
    title: &'a str,
    /// The second line.
    meta: &'a str,
    /// The icon of the main action's button.
    action_icon: &'static str,
    /// The tooltip of the main action's button.
    action_label: &'static str,
    /// The main action.
    action: Message,
    /// Opening the local folder.
    open: Message,
    /// Removing the sync or backup.
    remove: Message,
}

/// One sync folder or backup: its status icon, title and second line, and
/// buttons for its main action, opening its folder and removing it. Removing
/// asks twice: the first press arms the button for a few seconds. The texts
/// wrap, also inside long names, so they never push the buttons aside.
fn item_row<'a>(app: &'a Applet, item: Item<'a>) -> Element<'a, Message> {
    let remove_button = if app.armed.as_deref() == Some(item.key) {
        icon_button("object-select-symbolic", "Remove for good", item.remove)
    } else {
        icon_button(
            "user-trash-symbolic",
            "Remove",
            Message::Arm(item.key.to_string()),
        )
    };
    padded_control(
        row![
            icon::from_name(item.icon_name).size(16),
            column![
                text::body(item.title).wrapping(Wrapping::WordOrGlyph),
                text::caption(item.meta).wrapping(Wrapping::WordOrGlyph),
            ]
            .width(Length::Fill),
            icon_button(item.action_icon, item.action_label, item.action),
            icon_button("folder-open-symbolic", "Open folder", item.open),
            remove_button,
        ]
        .spacing(8)
        .align_y(Alignment::Center),
    )
    .into()
}

/// A button showing the icon NAME with the tooltip LABEL that sends MESSAGE.
fn icon_button<'a>(
    name: &'static str,
    label: &'static str,
    message: Message,
) -> Element<'a, Message> {
    button::icon(icon::from_name(name))
        .tooltip(label)
        .on_press(message)
        .into()
}
