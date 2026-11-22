# test_actions.py: tests for the actions the applets' panels run.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for core/megacmd_applet/actions.py and the command line around it.

The mega-* commands are stand-ins written to a temporary folder put first on
PATH; they log their arguments, so the tests see what would have run. No real
MEGAcmd command runs.

Run from the repository root with:  python3 -m unittest discover -s tests
"""

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLI = ROOT / "bin" / "megacmd-applet"
sys.path.insert(0, str(ROOT / "core"))

from megacmd_applet import actions  # noqa: E402

# A stand-in mega-* command: logs its name and arguments, prints $FAKE_OUTPUT
# and exits with $FAKE_EXIT.
FAKE = """#!/bin/sh
printf '%s' "$(basename "$0")" >> "$FAKE_LOG"
for arg in "$@"; do printf ' %s' "$arg" >> "$FAKE_LOG"; done
printf '\\n' >> "$FAKE_LOG"
printf '%s' "$FAKE_OUTPUT"
exit "${FAKE_EXIT:-0}"
"""


class FakeMegaCmd:
    """Stand-in mega-* commands in a temporary folder, first on PATH."""

    def __init__(self, output="", exit_code=0):
        self.folder = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.folder.name)
        for name in ("mega-sync", "mega-backup"):
            path = base / name
            path.write_text(FAKE)
            path.chmod(0o755)
        self.log = base / "log"
        self.env = {**os.environ, "PATH": f"{base}:{os.environ['PATH']}", "FAKE_LOG": str(self.log),
                    "FAKE_OUTPUT": output, "FAKE_EXIT": str(exit_code)}

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-I", str(CLI), *args], env=self.env, capture_output=True, text=True)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def close(self):
        self.folder.cleanup()


class CommandLineActionTests(unittest.TestCase):
    def test_pause_resume_and_remove_run_the_matching_mega_sync(self):
        fake = FakeMegaCmd()
        self.addCleanup(fake.close)
        for action in ("pause", "resume", "remove-sync"):
            self.assertEqual(fake.run_cli(action, "AbC_1").returncode, 0)
        self.assertEqual(fake.calls(), ["mega-sync --pause AbC_1", "mega-sync --enable AbC_1",
                                        "mega-sync --delete AbC_1"])

    def test_remove_backup_runs_mega_backup_delete(self):
        fake = FakeMegaCmd()
        self.addCleanup(fake.close)
        self.assertEqual(fake.run_cli("remove-backup", "7").returncode, 0)
        self.assertEqual(fake.calls(), ["mega-backup -d 7"])

    def test_values_that_could_pass_for_options_never_reach_megacmd(self):
        fake = FakeMegaCmd()
        self.addCleanup(fake.close)
        for args in (("pause", "--", "-x"), ("remove-sync", "--", "--all"), ("remove-backup", "1;rm"),
                     ("remove-backup", "--", "-d")):
            done = fake.run_cli(*args)
            self.assertEqual(done.returncode, 1, args)
        self.assertEqual(fake.calls(), [])

    def test_a_megacmd_error_is_reported_without_its_prefix(self):
        fake = FakeMegaCmd(output="[API:10:00:00 ERR Sync not found]", exit_code=0)
        self.addCleanup(fake.close)
        done = fake.run_cli("pause", "s1")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stderr.strip(), "Sync not found")

    def test_a_failing_exit_status_is_an_error(self):
        fake = FakeMegaCmd(output="", exit_code=3)
        self.addCleanup(fake.close)
        done = fake.run_cli("resume", "s1")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stderr.strip(), "MEGA command failed")


SYNCS = [{"id": "a", "runState": "Running"}, {"id": "b", "runState": "Disabled"}, {"id": "c", "runState": "Pending"}]


class AllSyncTests(unittest.TestCase):
    def run_all_with(self, paused, syncs=SYNCS, running=True):
        ran = []
        status = {"running": running, "syncs": syncs}
        with mock.patch.object(actions.megacmd, "collect", return_value=status), \
             mock.patch.object(actions, "run_all", side_effect=ran.extend):
            actions.set_all_paused(paused)
        return ran

    def test_pause_all_pauses_only_running_syncs(self):
        self.assertEqual(self.run_all_with(True), [["mega-sync", "--pause", "a"], ["mega-sync", "--pause", "c"]])

    def test_resume_all_resumes_only_paused_syncs(self):
        self.assertEqual(self.run_all_with(False), [["mega-sync", "--enable", "b"]])

    def test_toggle_all_pauses_while_any_runs(self):
        self.assertEqual(self.run_all_with(None), self.run_all_with(True))

    def test_toggle_all_resumes_when_all_are_paused(self):
        paused = [dict(s, runState="Disabled") for s in SYNCS]
        self.assertEqual(len(self.run_all_with(None, paused)), 3)

    def test_nothing_runs_while_the_engine_is_stopped(self):
        with self.assertRaises(actions.ActionError):
            self.run_all_with(True, running=False)


class GuidedTests(unittest.TestCase):
    def test_the_given_terminal_runs_the_dialog_with_its_arguments(self):
        command = actions.guided_command("mega-add-sync", ["/Sync"], terminal="foot --app-id=mega")
        self.assertEqual(command[:2], ["foot", "--app-id=mega"])
        self.assertEqual(command[2:], [str(ROOT / "bin" / "mega-add-sync"), "/Sync"])

    def test_xdg_terminal_exec_is_the_default_terminal(self):
        with mock.patch.object(actions.shutil, "which", side_effect=lambda name: "/usr/bin/" + name):
            self.assertEqual(actions.guided_command("mega-account-login", [])[0], "xdg-terminal-exec")

    def test_a_desktops_own_terminal_is_found_without_a_setting(self):
        for name, start in (("konsole", ["konsole", "-e"]), ("ptyxis", ["ptyxis", "--"])):
            with mock.patch.object(actions.shutil, "which", side_effect=lambda found, n=name: found == n and found):
                self.assertEqual(actions.guided_command("mega-account-login", [])[:2], start)

    def test_no_terminal_at_all_is_an_error(self):
        with mock.patch.object(actions.shutil, "which", return_value=None), \
             mock.patch.dict(actions.os.environ, {"TERMINAL": ""}):
            with self.assertRaises(actions.ActionError):
                actions.guided_command("mega-account-login", [])

    def test_editing_a_backup_checks_its_tag_and_count(self):
        command = actions.guided_command("mega-edit-backup", ["7", "0 0 2 * * *", "14"], terminal="term")
        self.assertEqual(command[-3:], ["7", "0 0 2 * * *", "14"])
        for args in (["-7", "1d", "3"], ["7", "1d", "x"]):
            with self.assertRaises(actions.ActionError):
                actions.guided_command("mega-edit-backup", args, terminal="term")

    def test_only_the_known_dialogs_can_be_opened(self):
        with self.assertRaises(actions.ActionError):
            actions.guided_command("../../bin/sh", [], terminal="term")


if __name__ == "__main__":
    unittest.main()
