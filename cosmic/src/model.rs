// model.rs: the view the shared core prints, as Rust types.
// SPDX-License-Identifier: GPL-3.0-or-later

use serde::Deserialize;

/// Serde default for fields that are true unless the core says otherwise.
fn yes() -> bool {
    true
}

/// What the applet shows: MEGAcmd's state with its meaning and texts, as
/// `megacmd-applet status` prints it (see core/megacmd_applet/view.py).
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct View {
    /// False when the state could not be read; `kind_text` says why.
    #[serde(default = "yes")]
    pub ok: bool,
    /// Whether an account is logged in.
    pub logged_in: bool,
    /// The logged-in account's e-mail address.
    pub email: String,
    /// The overall state: "synced", "syncing", "paused", "warning", "error",
    /// "stopped", "off", "missing" or "unknown".
    pub kind: String,
    /// The overall state in words.
    pub kind_text: String,
    /// What the popup offers when nobody is logged in: "login", "start" or
    /// empty for nothing.
    pub offer: String,
    /// The label of the offer's button.
    pub offer_text: String,
    /// One sentence saying what the offer's button does.
    pub offer_hint: String,
    /// Whether any sync runs, so "pause all" applies.
    pub any_running: bool,
    /// The storage line, such as "860 GB of 2.00 TB (42%)".
    pub usage_text: String,
    /// The storage warning level: 0 when all is well, else 90 or 95.
    pub storage_level: u32,
    /// The transfer summary, one line a direction.
    pub transfers_text: String,
    /// The sync folders.
    pub syncs: Vec<SyncRow>,
    /// The backups.
    pub backups: Vec<BackupRow>,
    /// Files that are not syncing, at most five.
    pub issues: Vec<Issue>,
    /// A note on further files not syncing; empty when there are none.
    pub issues_more_text: String,
    /// The notifications to show now, in order.
    pub notices: Vec<Notice>,
    /// With `ok`, a note to show under the state; empty when all is well.
    pub error: String,
}

impl View {
    /// A view of a state that could not be read, saying so with TEXT: kind
    /// "unknown", nothing offered.
    pub fn unknown(text: impl Into<String>) -> Self {
        Self {
            ok: false,
            kind: "unknown".into(),
            kind_text: text.into(),
            ..Default::default()
        }
    }

    /// Whether the account, storage, syncs and backups can be shown.
    pub fn signed_in(&self) -> bool {
        self.ok && self.logged_in
    }

    /// The note to show under the state; empty when there is none.
    pub fn note(&self) -> &str {
        if self.ok { &self.error } else { "" }
    }
}

/// One sync folder with its state and texts.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct SyncRow {
    /// MEGAcmd's ID of the sync.
    pub id: String,
    /// The local folder.
    pub local: String,
    /// The row's title: the local folder and the folder in MEGA.
    pub title: String,
    /// A key that stays the same for this sync while the list changes.
    pub key: String,
    /// The sync's state, named as the overall one.
    pub kind: String,
    /// The second line: state, file count and size.
    pub meta: String,
    /// Whether the sync is paused.
    pub paused: bool,
}

/// One backup with its state and texts.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct BackupRow {
    /// MEGAcmd's tag of the backup.
    pub tag: String,
    /// The local folder backed up.
    pub local: String,
    /// The row's title: the local folder and the folder in MEGA.
    pub title: String,
    /// The schedule, as MEGAcmd states it.
    pub period: String,
    /// How many backups are kept.
    pub max_backups: u64,
    /// A key that stays the same for this backup while the list changes.
    pub key: String,
    /// "error" when the last backup failed, "synced" when one completed,
    /// "pending" before the first.
    pub kind: String,
    /// The second line: schedule, number kept and the last result.
    pub meta: String,
}

/// A file that is not syncing, with the buttons that can settle it.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct Issue {
    /// A key that stays the same for this file while the list changes.
    pub key: String,
    /// The file's name.
    pub title: String,
    /// The title of the sync the file belongs to.
    pub sync_title: String,
    /// One sentence saying what is wrong.
    pub text: String,
    /// One short line for each copy or path of the file.
    pub lines: Vec<String>,
    /// The buttons to show.
    pub actions: Vec<IssueAction>,
}

/// A button of an issue: pressing it runs the core with `args`.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(default)]
pub struct IssueAction {
    /// The button's text.
    pub label: String,
    /// The button's tooltip.
    pub hint: String,
    /// The core's command line, without the program name and options.
    pub args: Vec<String>,
}

/// A notification the core decided is new.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(default)]
pub struct Notice {
    /// The notification's title, plain text.
    pub title: String,
    /// The notification's text, plain text.
    pub body: String,
    /// "normal" or "critical".
    pub urgency: String,
    /// "cloud" for storage use, "off" for being logged out or a stopped
    /// engine, "error" for a sync or backup problem.
    pub icon: String,
}

/// The symbolic icon of each state the core names, for the popup's rows and
/// header; states it does not know get the warning icon.
pub fn state_icon(kind: &str) -> &'static str {
    match kind {
        "synced" => "object-select-symbolic",
        "syncing" => "view-refresh-symbolic",
        "paused" => "media-playback-pause-symbolic",
        "pending" => "document-save-symbolic",
        "error" => "dialog-error-symbolic",
        "stopped" | "off" => "network-offline-symbolic",
        _ => "dialog-warning-symbolic",
    }
}

/// The applet's own panel icon for each state the core names; states it does
/// not know (such as "missing" and "unknown") get the attention icon.
pub fn panel_icon(kind: &str) -> &'static str {
    match kind {
        "synced" => "io.github.yardquit.MegaCmd-synced-symbolic",
        "syncing" => "io.github.yardquit.MegaCmd-syncing-symbolic",
        "paused" => "io.github.yardquit.MegaCmd-paused-symbolic",
        "stopped" | "off" => "io.github.yardquit.MegaCmd-off-symbolic",
        _ => "io.github.yardquit.MegaCmd-attention-symbolic",
    }
}

/// The symbolic icon of a notice's `icon` value.
pub fn notice_icon(icon: &str) -> &'static str {
    match icon {
        "cloud" => "folder-remote-symbolic",
        "off" => state_icon("off"),
        _ => state_icon("error"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Every kind the core can name for the overall state.
    const KINDS: [&str; 9] = [
        "synced", "syncing", "paused", "warning", "error", "stopped", "off", "missing", "unknown",
    ];

    #[test]
    fn a_view_reads_the_cores_field_names() {
        let view: View = serde_json::from_str(
            r#"{"ok": true, "loggedIn": true, "email": "user@example.com",
                "kind": "error", "kindText": "A sync needs attention",
                "offer": "", "anyRunning": true, "storageLevel": 90,
                "syncs": [{"id": "AbC1", "kind": "error", "paused": false,
                           "title": "~/Documents ↔ /Sync/Documents"}],
                "backups": [{"tag": "7", "maxBackups": 14, "kind": "pending",
                             "title": "~/Pictures → /Backups"}],
                "notices": [{"title": "MEGA sync stopped", "urgency": "critical", "icon": "error"}],
                "error": "Some syncs could not be read"}"#,
        )
        .unwrap();
        assert!(view.signed_in() && view.any_running);
        assert_eq!(view.kind_text, "A sync needs attention");
        assert_eq!(view.storage_level, 90);
        assert_eq!(view.syncs[0].title, "~/Documents ↔ /Sync/Documents");
        assert_eq!(view.backups[0].max_backups, 14);
        assert_eq!(view.backups[0].kind, "pending");
        assert_eq!(view.notices[0].urgency, "critical");
        assert_eq!(view.note(), "Some syncs could not be read");
    }

    #[test]
    fn issues_are_read_with_their_buttons() {
        let view: View = serde_json::from_str(r#"{"issues": [{"key": "issue:a", "title": "Budget.ods",
            "syncTitle": "~/Documents", "text": "Two copies.", "lines": ["On MEGA: newer"],
            "actions": [{"label": "Keep both", "hint": "Keeps both.", "args": ["resolve", "i1", "both"]}]}],
            "issuesMoreText": "3 more"}"#)
        .unwrap();
        let issue = &view.issues[0];
        assert_eq!(issue.sync_title, "~/Documents");
        assert_eq!(issue.lines, ["On MEGA: newer"]);
        assert_eq!(issue.actions[0].args, ["resolve", "i1", "both"]);
        assert_eq!(view.issues_more_text, "3 more");
    }

    #[test]
    fn an_offer_comes_with_its_label_and_hint() {
        let view: View = serde_json::from_str(
            r#"{"ok": true, "loggedIn": false, "kind": "off", "offer": "login",
                "offerText": "Log in to MEGA", "offerHint": "Opens the log-in dialog."}"#,
        )
        .unwrap();
        assert!(!view.signed_in());
        assert_eq!(view.offer, "login");
        assert_eq!(view.offer_text, "Log in to MEGA");
        assert_eq!(view.offer_hint, "Opens the log-in dialog.");
    }

    #[test]
    fn an_unreadable_state_shows_no_rows_and_no_note() {
        let view: View = serde_json::from_str(
            r#"{"ok": false, "loggedIn": false, "kind": "unknown",
                "kindText": "MEGAcmd is busy", "error": "MEGAcmd is busy"}"#,
        )
        .unwrap();
        assert!(!view.signed_in());
        assert_eq!(view.note(), "");
    }

    #[test]
    fn the_start_view_is_unknown_with_nothing_offered() {
        let view = View::unknown("");
        assert_eq!(view.kind, "unknown");
        assert!(view.offer.is_empty() && !view.signed_in());
        assert_eq!(panel_icon(&view.kind), panel_icon("warning"));
    }

    #[test]
    fn missing_fields_leave_the_view_readable() {
        let view: View = serde_json::from_str(r#"{"kind": "off"}"#).unwrap();
        assert!(view.ok && !view.logged_in);
        assert!(view.syncs.is_empty());
    }

    #[test]
    fn every_state_has_its_own_panel_icon() {
        let kinds = ["synced", "syncing", "paused", "error", "stopped"];
        let icons: std::collections::HashSet<_> =
            kinds.iter().map(|kind| panel_icon(kind)).collect();
        assert_eq!(icons.len(), kinds.len());
        assert_eq!(panel_icon("warning"), panel_icon("error"));
        assert_eq!(panel_icon("off"), panel_icon("stopped"));
    }

    #[test]
    fn missing_and_unknown_never_look_synced() {
        for kind in ["missing", "unknown", "something-new"] {
            assert_eq!(panel_icon(kind), panel_icon("warning"), "{kind}");
            assert_eq!(state_icon(kind), state_icon("warning"), "{kind}");
        }
    }

    #[test]
    fn each_backup_kind_has_its_own_row_icon() {
        let icons: std::collections::HashSet<_> = ["error", "synced", "pending"]
            .iter()
            .map(|kind| state_icon(kind))
            .collect();
        assert_eq!(icons.len(), 3);
    }

    #[test]
    fn each_notice_icon_has_its_own_symbol() {
        let icons: std::collections::HashSet<_> = ["error", "off", "cloud"]
            .iter()
            .map(|icon| notice_icon(icon))
            .collect();
        assert_eq!(icons.len(), 3);
    }

    #[test]
    fn every_panel_icon_ships_with_the_applet() {
        let icons = concat!(env!("CARGO_MANIFEST_DIR"), "/data/icons");
        for kind in KINDS {
            let file = format!("{icons}/{}.svg", panel_icon(kind));
            assert!(std::path::Path::new(&file).is_file(), "{file} is missing");
        }
    }
}
