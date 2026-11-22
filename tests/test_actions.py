# test_actions.py: tests for the actions the applets' panels run.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for core/megacmd_applet/actions.py and the command line around it.

The mega-* commands are stand-ins written to a temporary folder put first on
PATH; they log their arguments, so the tests see what would have run. No real
MEGAcmd command runs (see support.py).

Run from the repository root with:  python3 -m unittest discover -s tests
"""

import os
import unittest
from unittest import mock

from support import ROOT, CheckedTestCase, FakeMegaCmd, logged_in, write_script

from megacmd_applet import actions, megacmd

SYNC_LIST = "mega-sync --col-separator=\x1f --output-cols=" + ",".join(megacmd.SYNC_COLUMNS)


def sync_table(*rows):
    """MEGAcmd's sync table with rows of (id, run state)."""
    lines = [megacmd.SYNC_COLUMNS] + [[i, f"/home/user/{i}", f"/{i}", state, "Synced", "NO", "1 B", "1", "0"]
                                      for i, state in rows]
    return "\n".join(megacmd.SEPARATOR.join(line) for line in lines) + "\n"


class FakeTestCase(CheckedTestCase):
    """A test case with stand-in MEGAcmd commands in self.fake."""

    def setUp(self):
        super().setUp()
        self.fake = FakeMegaCmd()
        self.addCleanup(self.fake.close)


class CommandLineActionTests(FakeTestCase):
    """The command line runs the matching mega-* command for each action."""

    def test_pause_resume_and_remove_run_the_matching_mega_sync(self):
        for action in ("pause", "resume", "remove-sync"):
            self.assertEqual(self.fake.run_cli(action, "AbC_1").returncode, 0)
        self.assertEqual(self.fake.calls(), ["mega-sync --pause AbC_1", "mega-sync --enable AbC_1",
                                             "mega-sync --delete AbC_1"])

    def test_remove_backup_runs_mega_backup_delete(self):
        self.assertEqual(self.fake.run_cli("remove-backup", "7").returncode, 0)
        self.assertEqual(self.fake.calls(), ["mega-backup -d 7"])

    def test_values_that_could_pass_for_options_never_reach_megacmd(self):
        for args in (("pause", "--", "-x"), ("remove-sync", "--", "--all"), ("remove-backup", "1;rm"),
                     ("remove-backup", "--", "-d"), ("pause", "abc\n"), ("remove-backup", "7\n")):
            done = self.fake.run_cli(*args)
            self.assertEqual(done.returncode, 1, args)
        self.assertEqual(self.fake.calls(), [])

    def test_a_megacmd_error_is_reported_without_its_prefix(self):
        for output in ("[API:10:00:00 ERR Sync not found]", "[API:err: 10:00:00] Sync not found"):
            self.fake.set("mega-sync", output, 0)
            done = self.fake.run_cli("pause", "s1")
            self.assertEqual(done.returncode, 1, output)
            self.assertEqual(done.stderr.strip(), "Sync not found", output)

    def test_err_inside_a_message_is_not_an_error(self):
        self.fake.set("mega-sync", "Sync /home/user/ERR notes paused", 0)
        done = self.fake.run_cli("pause", "s1")
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_the_megacmd_folder_option_finds_commands_off_the_path(self):
        fake = FakeMegaCmd(on_path=False)
        self.addCleanup(fake.close)
        done = fake.run_cli(f"--megacmd-dir={fake.dir}", "pause", "SYNC1")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(fake.calls(), ["mega-sync --pause SYNC1"])

    def test_the_megacmd_folder_must_be_an_absolute_folder(self):
        for folder in ("relative/bin", str(self.fake.dir / "missing")):
            done = self.fake.run_cli(f"--megacmd-dir={folder}", "pause", "SYNC1")
            self.assertEqual(done.returncode, 1, folder)
            self.assertIn("Not a folder", done.stderr)
        self.assertEqual(self.fake.calls(), [])

    def test_a_megacmd_folder_with_a_colon_is_refused(self):
        folder = self.fake.base / "a:b"
        folder.mkdir()
        done = self.fake.run_cli(f"--megacmd-dir={folder}", "pause", "SYNC1")
        self.assertEqual(done.returncode, 1)
        self.assertIn("cannot go on the PATH", done.stderr)

    def test_a_failing_exit_status_is_an_error(self):
        self.fake.set("mega-sync", "", 3)
        done = self.fake.run_cli("resume", "s1")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stderr.strip(), "MEGA command failed")


class AllSyncCommandLineTests(FakeTestCase):
    """pause-all, resume-all and toggle-all through the command line."""

    def test_pause_all_reads_only_the_account_and_the_syncs(self):
        logged_in(self.fake, sync_table(("a", "Running"), ("b", "Disabled")))
        done = self.fake.run_cli("pause-all")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.fake.calls(), [f"pgrep -u {os.getuid()} -x mega-cmd-server", "mega-whoami",
                                             SYNC_LIST, "mega-sync --pause a"])

    def test_pause_all_fails_when_the_syncs_cannot_be_read(self):
        logged_in(self.fake)
        self.fake.set("mega-sync", "[API:err: 10:00:00] Busy", 1)
        done = self.fake.run_cli("pause-all")
        self.assertEqual(done.returncode, 1)
        self.assertIn("Could not read the syncs", done.stderr)

    def test_toggle_all_fails_when_nobody_is_logged_in(self):
        self.fake.set("mega-whoami", "[API:err: 10:00:00] Not logged in.", 57)
        done = self.fake.run_cli("toggle-all")
        self.assertEqual(done.returncode, 1)
        self.assertIn("Not logged in", done.stderr)
        self.assertNotIn(SYNC_LIST, self.fake.calls())


SYNCS = [{"id": "a", "runState": "Running"}, {"id": "b", "runState": "Disabled"}, {"id": "c", "runState": "Pending"}]


class AllSyncTests(CheckedTestCase):
    """Pausing and resuming every sync at once."""

    def run_all_with(self, paused, syncs=SYNCS):
        """Pauses (PAUSED true) or resumes SYNCS; returns the commands that would run."""
        ran = []
        with mock.patch.object(actions, "read_syncs_for_action", return_value=syncs), \
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

    def test_a_sync_in_the_paused_run_state_counts_as_paused(self):
        self.assertEqual(self.run_all_with(False, [{"id": "p", "runState": "Paused"}]),
                         [["mega-sync", "--enable", "p"]])

    def test_nothing_runs_while_the_engine_is_stopped(self):
        with mock.patch.object(actions.shutil, "which", return_value="/usr/bin/mega-whoami"), \
             mock.patch.object(actions.megacmd, "engine_running", return_value=False), \
             mock.patch.object(actions.megacmd, "run", side_effect=AssertionError("ran a command")), \
             self.assertRaises(actions.ActionError):
            actions.set_all_paused(True)


class MegacmdDirTests(CheckedTestCase):
    """The --megacmd-dir setting goes on the PATH once and cleanly."""

    def test_an_empty_path_gets_no_empty_entry(self):
        with mock.patch.dict(os.environ, {"PATH": ""}):
            actions.use_megacmd_dir("/")
            self.assertEqual(os.environ["PATH"], "/")

    def test_the_guided_dialog_gets_the_megacmd_folder_once(self):
        fake = FakeMegaCmd(on_path=False)
        self.addCleanup(fake.close)
        terminal = write_script(fake.base / "term", '#!/bin/sh\nprintf "%s\\n" "$@" >> "$FAKE_LOG"\n')
        done = fake.run_cli(f"--megacmd-dir={fake.dir}", "guided", f"--terminal={terminal}", "mega-account-login")
        self.assertEqual(done.returncode, 0, done.stderr)
        calls = fake.wait_for_calls(3)
        path = next(line for line in calls if line.startswith("PATH="))
        self.assertEqual(path[len("PATH="):].split(os.pathsep).count(str(fake.dir)), 1, path)
        self.assertEqual(calls[-1], str(ROOT / "bin" / "mega-account-login"))


class OpenFolderTests(FakeTestCase):
    """open-folder opens existing absolute folders only."""

    def test_an_existing_folder_is_opened(self):
        done = self.fake.run_cli("open-folder", str(self.fake.base))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.fake.wait_for_calls(1), [f"xdg-open {self.fake.base}"])

    def test_files_missing_and_relative_paths_are_refused(self):
        script = self.fake.dir / "mega-sync"
        for path in (str(script), str(self.fake.base / "missing"), "bin", "--help=x"):
            done = self.fake.run_cli("open-folder", "--", path)
            self.assertEqual(done.returncode, 1, path)
            self.assertIn("Not a folder", done.stderr)
        self.assertEqual(self.fake.calls(), [])


class GuidedCommandLineTests(FakeTestCase):
    """The guided command: options before the dialog's name, "--" before its arguments."""

    def guided(self, *args):
        """Runs `guided --terminal=<stand-in> ARGS`; returns (finished process, logged terminal arguments)."""
        terminal = write_script(self.fake.base / "term", '#!/bin/sh\nprintf "%s\\n" "$@" >> "$FAKE_LOG"\n')
        done = self.fake.run_cli("guided", f"--terminal={terminal}", *args)
        return done, (self.fake.wait_for_calls(1, 2) if done.returncode == 0 else self.fake.calls())

    def test_arguments_after_dashes_reach_the_dialog(self):
        done, calls = self.guided("mega-add-sync", "--", "/Sync")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(calls, [str(ROOT / "bin" / "mega-add-sync"), "/Sync"])

    def test_arguments_without_dashes_are_refused(self):
        done, calls = self.guided("mega-add-sync", "/Sync")
        self.assertEqual(done.returncode, 1)
        self.assertIn("--", done.stderr)
        self.assertEqual(calls, [])

    def test_a_value_like_an_option_cannot_replace_the_terminal(self):
        done, calls = self.guided("mega-add-sync", "--", "--terminal=sh -c id")
        self.assertEqual(done.returncode, 1)
        self.assertIn("Not a MEGA folder", done.stderr)
        self.assertEqual(calls, [])

    def test_a_bad_terminal_setting_is_an_error_not_a_traceback(self):
        done = self.fake.run_cli("guided", '--terminal=foot "unclosed', "mega-account-login")
        self.assertEqual(done.returncode, 1)
        self.assertIn("Not a terminal command", done.stderr)
        done = self.fake.run_cli("guided", f"--terminal={self.fake.base}/no-such-terminal", "mega-account-login")
        self.assertEqual(done.returncode, 1)
        self.assertIn("Could not start", done.stderr)


class GuidedTests(CheckedTestCase):
    """Building the command that opens a guided dialog in a terminal."""

    def test_the_given_terminal_runs_the_dialog_with_its_arguments(self):
        command = actions.guided_command("mega-add-sync", ["/Sync"], terminal="foot --app-id=mega")
        self.assertEqual(command[:2], ["foot", "--app-id=mega"])
        self.assertEqual(command[2:], [str(ROOT / "bin" / "mega-add-sync"), "/Sync"])

    def test_the_search_path_reaches_the_dialog_through_env(self):
        command = actions.guided_command("mega-add-sync", ["/Sync"], terminal="foot", path="/opt/megacmd/bin:/usr/bin")
        self.assertEqual(command[1:3], ["env", "PATH=/opt/megacmd/bin:/usr/bin"])
        self.assertEqual(command[3:], [str(ROOT / "bin" / "mega-add-sync"), "/Sync"])

    def test_xdg_terminal_exec_is_the_default_terminal(self):
        with mock.patch.object(actions.shutil, "which", side_effect=lambda name: "/usr/bin/" + name):
            self.assertEqual(actions.guided_command("mega-account-login", [])[0], "xdg-terminal-exec")

    def test_a_desktops_own_terminal_is_found_without_a_setting(self):
        for name, start in (("konsole", ["konsole", "-e"]), ("ptyxis", ["ptyxis", "--"])):
            with mock.patch.object(actions.shutil, "which", side_effect=lambda found, n=name: found == n and found):
                self.assertEqual(actions.guided_command("mega-account-login", [])[:2], start)

    def test_no_terminal_at_all_is_an_error(self):
        with mock.patch.object(actions.shutil, "which", return_value=None), \
             mock.patch.dict(actions.os.environ, {"TERMINAL": ""}), \
             self.assertRaises(actions.ActionError):
            actions.guided_command("mega-account-login", [])

    def test_editing_a_backup_checks_its_tag_and_count(self):
        command = actions.guided_command("mega-edit-backup", ["7", "0 0 2 * * *", "14"], terminal="term")
        self.assertEqual(command[-3:], ["7", "0 0 2 * * *", "14"])
        for args in (["-7", "1d", "3"], ["7", "1d", "x"], ["7\n", "1d", "3"], ["7", "1d", "3", "4"]):
            with self.assertRaises(actions.ActionError, msg=args):
                actions.guided_command("mega-edit-backup", args, terminal="term")

    def test_an_unknown_number_kept_is_left_to_the_dialog(self):
        for keep in ("", "0"):
            command = actions.guided_command("mega-edit-backup", ["7", "1d", keep], terminal="term")
            self.assertEqual(command[-3:], ["7", "1d", ""], keep)

    def test_a_period_megacmd_would_not_take_is_dropped(self):
        for period in ("--terminal=sh", "0 0 * *", "1x"):
            command = actions.guided_command("mega-edit-backup", ["7", period, "3"], terminal="term")
            self.assertEqual(command[-3:], ["7", "", "3"], period)
        command = actions.guided_command("mega-edit-backup", ["7", "1m12d3h", "3"], terminal="term")
        self.assertEqual(command[-2], "1m12d3h")

    def test_each_dialog_takes_only_its_own_arguments(self):
        for name, args in (("mega-account-login", ["x"]), ("mega-add-sync", ["Sync"]),
                           ("mega-add-backup", ["/a", "/b"])):
            with self.assertRaises(actions.ActionError, msg=name):
                actions.guided_command(name, args, terminal="term")
        self.assertEqual(actions.guided_command("mega-add-backup", [""], terminal="term")[1:],
                         [str(ROOT / "bin" / "mega-add-backup")])

    def test_only_the_known_dialogs_can_be_opened(self):
        with self.assertRaises(actions.ActionError):
            actions.guided_command("../../bin/sh", [], terminal="term")


if __name__ == "__main__":
    unittest.main()
