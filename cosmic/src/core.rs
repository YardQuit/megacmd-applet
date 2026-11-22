// core.rs: find and run the shared core's command line.
// SPDX-License-Identifier: GPL-3.0-or-later

use std::env;
use std::path::{Path, PathBuf};
use std::time::Duration;

use crate::model::View;

/// How long one run of the core may take in all before it is stopped; longer
/// than the limits the core puts on each MEGAcmd command it runs.
pub const TIMEOUT: Duration = Duration::from_secs(90);

/// Finds the core's folder from the environment: SETTING when given, else
/// the first `megacmd-applet/` holding `bin/megacmd-applet` under
/// `$XDG_DATA_HOME` (default `~/.local/share`) and then `$XDG_DATA_DIRS`
/// (default `/usr/local/share:/usr/share`). See [`find_core`].
pub fn core_dir(setting: &str) -> Option<PathBuf> {
    let home = env::var_os("HOME").map(PathBuf::from).unwrap_or_default();
    let data_home = env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| home.join(".local/share"));
    let data_dirs =
        env::var("XDG_DATA_DIRS").unwrap_or_else(|_| "/usr/local/share:/usr/share".into());
    find_core(setting, &data_home, &data_dirs)
}

/// Searches the given folders for the core, without reading the environment:
/// returns SETTING when it is not empty, else the first `megacmd-applet/`
/// under DATA_HOME or one of the colon-separated DATA_DIRS that holds
/// `bin/megacmd-applet`, or `None` when none does.
fn find_core(setting: &str, data_home: &Path, data_dirs: &str) -> Option<PathBuf> {
    if !setting.is_empty() {
        return Some(PathBuf::from(setting));
    }
    std::iter::once(data_home.to_path_buf())
        .chain(
            data_dirs
                .split(':')
                .filter(|dir| !dir.is_empty())
                .map(PathBuf::from),
        )
        .map(|dir| dir.join("megacmd-applet"))
        .find(|dir| dir.join("bin/megacmd-applet").is_file())
}

/// Runs `megacmd-applet ARGS` from the core in DIR, without a shell, and
/// returns its standard output, or its standard error (or why it could not
/// run) when it fails. The run is stopped, and the process killed, after
/// [`TIMEOUT`].
pub async fn run(dir: Option<PathBuf>, args: Vec<String>) -> Result<String, String> {
    run_within(dir, args, TIMEOUT).await
}

/// Does what [`run`] does, stopping the run after LIMIT.
async fn run_within(
    dir: Option<PathBuf>,
    args: Vec<String>,
    limit: Duration,
) -> Result<String, String> {
    let dir = dir.ok_or_else(|| "The MEGA applet's core is not installed".to_string())?;
    let child = tokio::process::Command::new("python3")
        .arg("-I")
        .arg(dir.join("bin/megacmd-applet"))
        .args(&args)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .kill_on_drop(true)
        .spawn()
        .map_err(|error| format!("Could not run the MEGA applet's core: {error}"))?;
    let output = tokio::time::timeout(limit, child.wait_with_output())
        .await
        .map_err(|_| "The MEGA applet's core did not answer in time".to_string())?
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

/// Runs `megacmd-applet ARGS` (a `status` command) and reads the view it
/// prints. The core prints a view also when MEGAcmd cannot be read, so an
/// error here means the core itself could not run or answer.
pub async fn status(dir: Option<PathBuf>, args: Vec<String>) -> Result<View, String> {
    let stdout = run(dir, args).await?;
    serde_json::from_str(&stdout).map_err(|_| "Unreadable MEGA status".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A fresh temporary folder for the test NAME holding data folders, one
    /// for each entry of WITH_CORE, with the core in those marked true.
    fn data_dirs(name: &str, with_core: &[bool]) -> (PathBuf, Vec<PathBuf>) {
        let base =
            env::temp_dir().join(format!("megacmd-applet-test-{}-{name}", std::process::id()));
        let _ = std::fs::remove_dir_all(&base);
        let dirs: Vec<PathBuf> = with_core
            .iter()
            .enumerate()
            .map(|(i, core)| {
                let dir = base.join(format!("data{i}"));
                std::fs::create_dir_all(dir.join("megacmd-applet/bin")).unwrap();
                if *core {
                    std::fs::write(dir.join("megacmd-applet/bin/megacmd-applet"), "").unwrap();
                }
                dir
            })
            .collect();
        (base, dirs)
    }

    /// DIRS joined with colons, as in `$XDG_DATA_DIRS`.
    fn joined(dirs: &[PathBuf]) -> String {
        dirs.iter()
            .map(|dir| dir.to_string_lossy())
            .collect::<Vec<_>>()
            .join(":")
    }

    #[test]
    fn the_setting_wins() {
        let (base, dirs) = data_dirs("setting", &[true]);
        assert_eq!(
            find_core("/opt/core", &dirs[0], ""),
            Some(PathBuf::from("/opt/core"))
        );
        std::fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn the_first_data_folder_holding_the_core_is_used() {
        let (base, dirs) = data_dirs("first", &[false, false, true, true]);
        let found = find_core("", &dirs[0], &joined(&dirs[1..]));
        assert_eq!(found, Some(dirs[2].join("megacmd-applet")));
        std::fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn no_core_anywhere_is_none() {
        let (base, dirs) = data_dirs("none", &[false, false]);
        assert_eq!(find_core("", &dirs[0], &joined(&dirs[1..])), None);
        std::fs::remove_dir_all(base).unwrap();
    }

    /// A fresh core folder for the test NAME whose `bin/megacmd-applet` is
    /// the Python SCRIPT.
    fn fake_core(name: &str, script: &str) -> PathBuf {
        let (base, _) = data_dirs(name, &[]);
        std::fs::create_dir_all(base.join("bin")).unwrap();
        std::fs::write(base.join("bin/megacmd-applet"), script).unwrap();
        base
    }

    /// Waits for FUTURE on a runtime of its own.
    fn block_on<T>(future: impl std::future::Future<Output = T>) -> T {
        tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap()
            .block_on(future)
    }

    #[test]
    fn a_missing_core_is_reported() {
        assert_eq!(
            block_on(run(None, vec!["status".into()])),
            Err("The MEGA applet's core is not installed".to_string())
        );
    }

    #[test]
    fn the_core_gets_the_arguments_and_its_view_is_read() {
        let dir = fake_core(
            "view",
            "import json, sys\nprint(json.dumps({'kind': 'paused', 'kindText': ' '.join(sys.argv[1:])}))\n",
        );
        let view = block_on(status(
            Some(dir.clone()),
            vec!["status".into(), "--preview".into(), "a b".into()],
        ))
        .unwrap();
        assert_eq!(view.kind, "paused");
        assert_eq!(view.kind_text, "status --preview a b");
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn a_refusal_returns_the_cores_reason() {
        let dir = fake_core("refusal", "import sys\nsys.exit('Not a folder: /x')\n");
        assert_eq!(
            block_on(run(
                Some(dir.clone()),
                vec!["open-folder".into(), "/x".into()]
            )),
            Err("Not a folder: /x".to_string())
        );
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn a_core_that_hangs_is_stopped() {
        let dir = fake_core("hang", "import time\ntime.sleep(30)\n");
        let started = std::time::Instant::now();
        let result = block_on(run_within(
            Some(dir.clone()),
            vec!["status".into()],
            Duration::from_millis(300),
        ));
        assert_eq!(
            result,
            Err("The MEGA applet's core did not answer in time".to_string())
        );
        assert!(started.elapsed() < Duration::from_secs(10));
        std::fs::remove_dir_all(dir).unwrap();
    }
}
