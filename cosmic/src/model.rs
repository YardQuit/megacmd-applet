// model.rs: the view the shared core prints, as Rust types.
// SPDX-License-Identifier: GPL-3.0-or-later

use serde::Deserialize;

fn yes() -> bool {
    true
}

/// What the applet shows: MEGAcmd's state with its meaning and texts, as
/// `megacmd-applet status` prints it (see core/megacmd_applet/view.py).
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct View {
    #[serde(default = "yes")]
    pub ok: bool,
    #[serde(default = "yes")]
    pub installed: bool,
    #[serde(default = "yes")]
    pub running: bool,
    pub logged_in: bool,
    pub email: String,
    pub kind: String,
    pub kind_text: String,
    pub any_running: bool,
    pub usage_text: String,
    pub storage_level: u32,
    pub transfers_text: String,
    pub syncs: Vec<SyncRow>,
    pub backups: Vec<BackupRow>,
    pub notices: Vec<Notice>,
    pub error: String,
}

/// One sync folder with its state and texts.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct SyncRow {
    pub id: String,
    pub local: String,
    pub remote: String,
    pub key: String,
    pub kind: String,
    pub meta: String,
    pub paused: bool,
    pub local_display: String,
}

/// One backup with its state and texts.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct BackupRow {
    pub tag: String,
    pub local: String,
    pub remote: String,
    pub period: String,
    pub max_backups: u64,
    pub last_status: String,
    pub key: String,
    pub failed: bool,
    pub meta: String,
    pub local_display: String,
}

/// A notification the core decided is new.
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(default)]
pub struct Notice {
    pub title: String,
    pub body: String,
    pub urgency: String,
    pub icon: String,
}

/// The symbolic icon of each state the core names, for the popup's rows.
pub fn state_icon(kind: &str) -> &'static str {
    match kind {
        "stopped" | "off" => "network-offline-symbolic",
        "error" => "dialog-error-symbolic",
        "warning" => "dialog-warning-symbolic",
        "paused" => "media-playback-pause-symbolic",
        "syncing" => "view-refresh-symbolic",
        _ => "object-select-symbolic",
    }
}

/// The applet's own panel icon for each state the core names.
pub fn panel_icon(kind: &str) -> &'static str {
    match kind {
        "stopped" | "off" => "io.github.yardquit.MegaCmd-off-symbolic",
        "error" | "warning" => "io.github.yardquit.MegaCmd-attention-symbolic",
        "paused" => "io.github.yardquit.MegaCmd-paused-symbolic",
        "syncing" => "io.github.yardquit.MegaCmd-syncing-symbolic",
        _ => "io.github.yardquit.MegaCmd-synced-symbolic",
    }
}
