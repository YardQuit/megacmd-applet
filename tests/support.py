# support.py: shared helpers for the test suite: paths, fenced environments, stand-in commands.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Helpers shared by the tests.

Importing this module puts a folder of poison mega-* commands (and xdg-open
and gio) first on this process's PATH: if any test reaches one of them
instead of a stand-in, the call is logged and CheckedTestCase fails, and no
real MEGAcmd command runs. Every environment made here also points HOME and
the XDG folders into a temporary folder.
"""

import atexit
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLI = ROOT / "bin" / "megacmd-applet"
sys.path.insert(0, str(ROOT / "core"))

# Every command the core and the guided dialogs may run that must never be
# the real one during a test.
GUARDED = ("mega-whoami", "mega-df", "mega-sync", "mega-sync-issues", "mega-backup", "mega-transfers", "mega-ls",
           "mega-mkdir", "mega-mv", "mega-cmd", "mega-exec", "mega-cmd-server", "xdg-open", "gio")
XDG_NAMES = ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "XDG_RUNTIME_DIR")

POISON = """#!/bin/sh
printf '%s\\n' "$(basename "$0") $*" >> "$(dirname "$0")/calls"
exit 99
"""

# A stand-in command: logs its name and arguments to $FAKE_LOG, waits
# NAME.sleep seconds, prints NAME.out and exits with NAME.exit when those
# files exist next to it, else prints $FAKE_OUTPUT and exits with $FAKE_EXIT.
FAKE = """#!/bin/sh
name=$(basename "$0")
dir=$(dirname "$0")
printf '%s' "$name" >> "$FAKE_LOG"
for arg in "$@"; do printf ' %s' "$arg" >> "$FAKE_LOG"; done
printf '\\n' >> "$FAKE_LOG"
if [ -f "$dir/$name.sleep" ]; then sleep "$(cat "$dir/$name.sleep")"; fi
if [ -f "$dir/$name.out" ]; then cat "$dir/$name.out"; else printf '%s' "$FAKE_OUTPUT"; fi
if [ -f "$dir/$name.exit" ]; then exit "$(cat "$dir/$name.exit")"; fi
exit "${FAKE_EXIT:-0}"
"""


def write_script(path, text):
    """Write TEXT to PATH as an executable script; return PATH."""
    path = pathlib.Path(path)
    path.write_text(text)
    path.chmod(0o755)
    return path


POISON_DIR = pathlib.Path(tempfile.mkdtemp(prefix="megacmd-applet-poison-"))
atexit.register(shutil.rmtree, POISON_DIR, True)
for _name in GUARDED:
    write_script(POISON_DIR / _name, POISON)
os.environ["PATH"] = f"{POISON_DIR}{os.pathsep}{os.environ.get('PATH', '')}"


def poison_calls():
    """The poison commands run so far, one line each."""
    log = POISON_DIR / "calls"
    return log.read_text().splitlines() if log.exists() else []


class CheckedTestCase(unittest.TestCase):
    """A test case that fails when one of its tests reached a poison command."""

    def setUp(self):
        self.poisoned_before = len(poison_calls())

    def tearDown(self):
        self.assertEqual(poison_calls()[self.poisoned_before:], [], "a real command would have run")


def fixture(name):
    """The saved status in fixtures/NAME."""
    return json.loads((ROOT / "fixtures" / name).read_text())


def fenced_env(base, first=None, **extra):
    """This process's environment with HOME and the XDG folders inside BASE.

    FIRST, a folder, goes before the PATH (which starts with the poison
    folder); EXTRA adds or replaces variables.
    """
    base = pathlib.Path(base)
    path = os.environ["PATH"] if first is None else f"{first}{os.pathsep}{os.environ['PATH']}"
    env = {**os.environ, "PATH": path, "HOME": str(base / "home"),
           **{name: str(base / name.lower()) for name in XDG_NAMES}}
    for name in ("home",) + tuple(name.lower() for name in XDG_NAMES):
        (base / name).mkdir(exist_ok=True)
    env.update(extra)
    return env


def run_cli(*args, env):
    """Run the command line with ARGS in ENV; return the finished process."""
    return subprocess.run([sys.executable, "-I", str(CLI), *args], env=env, capture_output=True, text=True,
                          check=False)


class FakeMegaCmd:
    """Stand-in mega-* commands (and pgrep, xdg-open, gio) in a temporary folder, with a fenced environment.

    The folder goes first on PATH unless ON_PATH is false; then only the
    poison commands stand where the real ones would be. Each stand-in
    prints OUTPUT and exits with EXIT_CODE unless set() says otherwise.
    """

    NAMES = ("mega-whoami", "mega-df", "mega-sync", "mega-sync-issues", "mega-backup", "mega-transfers", "mega-ls",
             "mega-mkdir", "mega-mv", "mega-cmd", "pgrep", "xdg-open", "gio")

    def __init__(self, output="", exit_code=0, on_path=True):
        self.folder = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.folder.name)
        self.dir = self.base / "bin"
        self.dir.mkdir()
        for name in self.NAMES:
            write_script(self.dir / name, FAKE)
        for name in ("pgrep", "xdg-open"):
            self.set(name, "", 0)
        self.log = self.base / "log"
        self.env = fenced_env(self.base, self.dir if on_path else None, FAKE_LOG=str(self.log),
                              FAKE_OUTPUT=output, FAKE_EXIT=str(exit_code))

    def set(self, name, output=None, exit_code=None, sleep=None):
        """Make the stand-in NAME print OUTPUT, exit with EXIT_CODE or wait SLEEP seconds first."""
        for suffix, value in (("out", output), ("exit", exit_code), ("sleep", sleep)):
            if value is not None:
                (self.dir / f"{name}.{suffix}").write_text(str(value))

    def run_cli(self, *args):
        """Run the command line with ARGS against the stand-in commands; return the finished process."""
        return run_cli(*args, env=self.env)

    def calls(self):
        """The stand-in commands run so far, one line of arguments each."""
        return self.log.read_text().splitlines() if self.log.exists() else []

    def wait_for_calls(self, count, seconds=5):
        """The calls once there are COUNT of them, waiting up to SECONDS for detached commands."""
        deadline = time.monotonic() + seconds
        while len(self.calls()) < count and time.monotonic() < deadline:
            time.sleep(0.05)
        return self.calls()

    def close(self):
        """Remove the temporary folder."""
        self.folder.cleanup()


def logged_in(fake, syncs="", whoami="Account e-mail: user@example.com\n"):
    """Set up FAKE as a running MEGAcmd with someone logged in and the sync table SYNCS."""
    fake.set("mega-whoami", whoami)
    fake.set("mega-sync", syncs)


def issue_details(issue_id, sync_id, reason, *rows):
    """MEGAcmd's details of one sync issue, as `mega-sync-issues --detail` prints them with SEPARATOR.

    Each of ROWS is (path, problem, modified, uploaded, size), with "-" for
    nothing and cloud paths starting with "<CLOUD>".
    """
    separator = "\x1f"
    lines = [f"[Details on issue {issue_id}]", reason,
             f"Parent sync: {sync_id} (/home/user/Documents to <CLOUD>/Sync/Documents)", "",
             separator.join(["PATH", "PATH_ISSUE", "LAST_MODIFIED", "UPLOADED", "SIZE"])]
    return "\n".join(lines + [separator.join(row) for row in rows]) + "\n\n"


def tool_dir(base, names):
    """A folder in BASE with links to the system's NAMES only, for a PATH without anything else."""
    folder = pathlib.Path(base) / "tools"
    folder.mkdir(exist_ok=True)
    for name in names:
        (folder / name).symlink_to(shutil.which(name))
    return folder
