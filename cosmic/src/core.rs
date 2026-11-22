// core.rs: find and run the shared core's command line.
// SPDX-License-Identifier: GPL-3.0-or-later

use std::env;
use std::path::PathBuf;

use crate::model::View;

/// The core's folder: SETTING when given, else the first
/// `megacmd-applet/` under $XDG_DATA_HOME and $XDG_DATA_DIRS holding
/// `bin/megacmd-applet`.
pub fn core_dir(setting: &str) -> Option<PathBuf> {
    if !setting.is_empty() {
        return Some(PathBuf::from(setting));
    }
    let home = env::var_os("HOME").map(PathBuf::from).unwrap_or_default();
    let data_home = env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| home.join(".local/share"));
    let data_dirs =
        env::var("XDG_DATA_DIRS").unwrap_or_else(|_| "/usr/local/share:/usr/share".into());
    std::iter::once(data_home)
        .chain(
            data_dirs
                .split(':')
                .filter(|dir| !dir.is_empty())
                .map(PathBuf::from),
        )
        .map(|dir| dir.join("megacmd-applet"))
        .find(|dir| dir.join("bin/megacmd-applet").is_file())
}

/// Runs `megacmd-applet ARGS` from the core in DIR, without a shell; returns
/// its standard output, or its standard error when it fails.
pub async fn run(dir: Option<PathBuf>, args: Vec<String>) -> Result<String, String> {
    let dir = dir.ok_or_else(|| "The MEGA applet's core is not installed".to_string())?;
    let output = tokio::process::Command::new("python3")
        .arg("-I")
        .arg(dir.join("bin/megacmd-applet"))
        .args(&args)
        .output()
        .await
        .map_err(|error| format!("Could not run the MEGA applet's core: {error}"))?;
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).into_owned())
    } else {
        let message = String::from_utf8_lossy(&output.stderr).trim().to_string();
        Err(if message.is_empty() {
            "MEGA command failed".into()
        } else {
            message
        })
    }
}

/// Runs `megacmd-applet status ARGS` and reads the view it prints.
pub async fn status(dir: Option<PathBuf>, args: Vec<String>) -> Result<View, String> {
    let stdout = run(dir, args).await?;
    let view: View =
        serde_json::from_str(&stdout).map_err(|_| "Unreadable MEGA status".to_string())?;
    if view.ok {
        Ok(view)
    } else if view.error.is_empty() {
        Err("Could not read MEGA status".into())
    } else {
        Err(view.error)
    }
}
