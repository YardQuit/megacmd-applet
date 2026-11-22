// config.rs: settings of the MEGA applet, kept by COSMIC's settings store.
// SPDX-License-Identifier: GPL-3.0-or-later

use cosmic::cosmic_config::{self, CosmicConfigEntry, cosmic_config_derive::CosmicConfigEntry};
use serde::{Deserialize, Serialize};

/// The applet's settings, read from (and watched in) COSMIC's settings store
/// under the applet's ID, in ~/.config/cosmic/<ID>/v1/.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, CosmicConfigEntry)]
#[version = 1]
pub struct Config {
    /// How often to check MEGAcmd while the popup is closed, in seconds.
    pub refresh_interval_sec: u64,
    /// Suggested parent folder in MEGA when adding a sync.
    pub sync_folder: String,
    /// Suggested parent folder in MEGA when adding a backup.
    pub backup_folder: String,
    /// Command that runs a program in a terminal; empty lets the core find one.
    pub terminal: String,
    /// Folder holding MEGAcmd's mega-* commands, searched before the PATH;
    /// empty uses the PATH alone.
    pub megacmd_dir: String,
    /// Folder of the shared core (holding bin/megacmd-applet); empty finds it
    /// under the data folders.
    pub core_dir: String,
    /// Saved state from fixtures/ to show instead of MEGAcmd's; empty for the live state.
    pub preview_name: String,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            refresh_interval_sec: 60,
            sync_folder: "/".into(),
            backup_folder: "/Backups".into(),
            terminal: String::new(),
            megacmd_dir: String::new(),
            core_dir: String::new(),
            preview_name: String::new(),
        }
    }
}
