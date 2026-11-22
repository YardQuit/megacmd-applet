# test_megacmd.py: tests for reading MEGAcmd's output and state.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for core/megacmd_applet/megacmd.py: the MEGAcmd output parsers, the
engine check, and the saved states the command line prints.

Run from the repository root with:  python3 -m unittest discover -s tests
"""

import json
import os
import pathlib
import tempfile
import time
import unittest
from unittest import mock

from support import ROOT, CheckedTestCase, FakeMegaCmd, fenced_env, run_cli, write_script

from megacmd_applet import megacmd as status


class StorageTests(CheckedTestCase):
    """Reading the storage use from mega-df."""

    def test_used_bytes_come_from_percentage_and_total(self):
        text = ("Cloud drive:          1234...56789 in  10 file(s) and   2 folder(s)\n"
                "USED STORAGE:         1099...11776                  50.00% of 2199023255552\n")
        self.assertEqual(status.parse_storage(text), (1099511627776, 2199023255552, 50.0))

    def test_missing_storage_line_gives_zeroes(self):
        self.assertEqual(status.parse_storage("Not logged in."), (0, 0, 0.0))

    def test_an_exact_used_count_is_taken_as_it_is(self):
        text = "USED STORAGE:         1099511627777                  50.00% of 2199023255552\n"
        self.assertEqual(status.parse_storage(text)[0], 1099511627777)

    def test_a_bare_dot_for_the_percentage_does_not_break_the_status(self):
        self.assertEqual(status.parse_storage("USED STORAGE: 12 .% of 100\n"), (0, 0, 0.0))


def sync_table(*rows):
    """MEGAcmd's sync table with the given rows, in the columns megacmd.py asks for."""
    return "\n".join(status.SEPARATOR.join(row) for row in [status.SYNC_COLUMNS, *rows]) + "\n"


class SyncTests(CheckedTestCase):
    """Reading the sync table from mega-sync."""

    TEXT = sync_table(
        ["abc", "/home/user/My Notes", "/Sync/My Notes", "Running", "Synced", "NO", "1.50 MB", "12", "3"],
        ["d-f_9", "/home/user/Code", "/Sync/Code", "Disabled", "NONE", "Local path not found", "0.00   B", "0", "0"])

    def test_rows_keep_paths_with_spaces(self):
        syncs, unreadable = status.parse_syncs(self.TEXT)
        self.assertEqual([s["local"] for s in syncs], ["/home/user/My Notes", "/home/user/Code"])
        self.assertEqual(syncs[0]["remote"], "/Sync/My Notes")
        self.assertEqual(unreadable, 0)

    def test_no_error_is_empty_and_errors_are_kept(self):
        syncs, _ = status.parse_syncs(self.TEXT)
        self.assertEqual(syncs[0]["error"], "")
        self.assertEqual(syncs[1]["error"], "Local path not found")

    def test_sizes_and_counts_are_normalised(self):
        syncs, _ = status.parse_syncs(self.TEXT)
        self.assertEqual(syncs[1]["size"], "0.00 B")
        self.assertEqual((syncs[0]["files"], syncs[0]["dirs"]), (12, 3))

    def test_header_and_blank_lines_are_skipped(self):
        self.assertEqual(status.parse_syncs(sync_table() + "\n"), ([], 0))

    def test_a_pipe_in_a_folder_name_keeps_the_sync(self):
        syncs, unreadable = status.parse_syncs(sync_table(
            ["abc", "/home/user/A|B", "/Shared/A|B", "Running", "Synced", "NO", "1 B", "1", "0"]))
        self.assertEqual([s["local"] for s in syncs], ["/home/user/A|B"])
        self.assertEqual(unreadable, 0)

    def test_a_line_break_in_a_folder_name_cannot_pose_as_a_sync(self):
        # A shared folder named "x<newline>--delete..." splits its row in two;
        # neither half may become a sync whose ID reaches mega-sync as an option.
        name = "/Shared/x\n--delete" + status.SEPARATOR + "/home/user" + status.SEPARATOR + "/evil"
        syncs, unreadable = status.parse_syncs(sync_table(
            ["abc", "/home/user/Shared", name, "Running", "Failed", "fake error", "1 B", "0", "0"],
            ["ok1", "/home/user/A", "/A", "Running", "Synced", "NO", "1 B", "0", "0"]))
        self.assertEqual([s["id"] for s in syncs], ["ok1"])
        self.assertEqual(unreadable, 2)

    def test_an_id_or_local_path_that_could_be_an_option_is_refused(self):
        syncs, unreadable = status.parse_syncs(sync_table(
            ["--delete", "/home/user/A", "/A", "Running", "Synced", "NO", "1 B", "0", "0"],
            ["abc", "--help", "/A", "Running", "Synced", "NO", "1 B", "0", "0"]))
        self.assertEqual((syncs, unreadable), ([], 2))

    def test_counts_that_are_not_numbers_do_not_break_the_status(self):
        syncs, _ = status.parse_syncs(sync_table(
            ["abc", "/home/user/A", "/A", "Running", "Synced", "NO", "1 B", "many", "-"]))
        self.assertEqual((syncs[0]["files"], syncs[0]["dirs"]), (0, 0))


class BackupTests(CheckedTestCase):
    """Reading the backup list from mega-backup."""

    DETAILS = (
        "TAG   LOCALPATH                         REMOTEPARENTPATH            STATUS\n"
        "42    /home/user/Family Photos          /Backups                    ACTIVE\n"
        "  Max Backups:   7\n"
        '  Period:         "0 0 2 * * *"\n'
        "  Next backup scheduled for: Sun, 25 Oct 2026 02:00:00 +0100\n"
        "   -- CURRENT/LAST BACKUP --\n"
        "  FILES UP/TOT     FOLDERS CREATED           PROGRESS     \n"
        "       1/1                0            6.00/6.00  B  0.00%\n")
    LISTING = DETAILS + (
        "   -- HISTORY OF BACKUPS --\n"
        "  NAME                                         DATE                                  STATUS  FILES FOLDERS\n"
        "  Family Photos_bk_20261023020000              Fri, 23 Oct 2026 02:00:00 +0200     COMPLETE      9       1\n"
        "  Family Photos_bk_20261024020000              Sat, 24 Oct 2026 02:00:00 +0200   INCOMPLETE      4       1\n")

    def test_details_are_read(self):
        (backup,) = status.parse_backups(self.DETAILS)
        self.assertEqual(backup["tag"], "42")
        self.assertEqual(backup["local"], "/home/user/Family Photos")
        self.assertEqual(backup["remote"], "/Backups")
        self.assertEqual(backup["maxBackups"], 7)
        self.assertEqual(backup["period"], "0 0 2 * * *")
        self.assertEqual(backup["next"], "Sun, 25 Oct 2026 02:00:00 +0100")

    def test_details_are_kept_once_the_history_follows(self):
        (backup,) = status.parse_backups(self.LISTING)
        self.assertEqual((backup["maxBackups"], backup["period"]), (7, "0 0 2 * * *"))

    def test_newest_history_entry_wins(self):
        (backup,) = status.parse_backups(self.LISTING)
        self.assertEqual(backup["lastName"], "Family Photos_bk_20261024020000")
        self.assertEqual(backup["lastStatus"], "INCOMPLETE")

    def test_no_backups(self):
        self.assertEqual(status.parse_backups("No backup configured."), [])

    def test_max_backups_that_is_not_a_number_does_not_break_the_status(self):
        (backup,) = status.parse_backups(self.DETAILS.replace("Max Backups:   7", "Max Backups:   lots"))
        self.assertEqual(backup["maxBackups"], 0)

    def test_a_backup_whose_local_path_is_not_absolute_is_ignored(self):
        details = self.DETAILS.replace("/home/user/Family Photos", "-x Family Photos")
        self.assertEqual(status.parse_backups(details), [])


class TransferTests(CheckedTestCase):
    """Reading the transfer summary from mega-transfers."""

    def test_summary_is_read(self):
        text = ("   NUM DOWNLOADS  DOWNLOADED       TOTAL    %             NUM UPLOADS    UPLOADED       TOTAL    %   \n"
                "             120     1.20 GB     4.80 GB  25.00%                    3   10.00 MB    20.00 MB  50.00%\n")
        transfers = status.parse_transfers(text)
        self.assertEqual(transfers["downloads"], 120)
        self.assertEqual((transfers["downloaded"], transfers["downloadTotal"]), ("1.20 GB", "4.80 GB"))
        self.assertEqual(transfers["downloadPercent"], 25.0)
        self.assertEqual((transfers["uploads"], transfers["uploadPercent"]), (3, 50.0))

    def test_counts_that_are_not_finite_numbers_give_zero(self):
        text = ("   NUM DOWNLOADS  DOWNLOADED       TOTAL    %             NUM UPLOADS    UPLOADED       TOTAL    %   \n"
                "             nan     1.20 GB     4.80 GB  inf%                    inf   10.00 MB    20.00 MB  50.00%\n")
        transfers = status.parse_transfers(text)
        self.assertEqual((transfers["downloads"], transfers["downloadPercent"], transfers["uploads"]), (0, 0.0, 0))

    def test_no_transfers(self):
        transfers = status.parse_transfers("No transfers.")
        self.assertEqual((transfers["downloads"], transfers["uploads"]), (0, 0))


def collect_with(running=True, **answers):
    """Collects the state with MEGAcmd installed and RUNNING; returns it and the commands run.

    ANSWERS maps a command name with "_" for "-" (mega_whoami) to its
    (exit status, output); other commands answer (0, "").
    """
    calls = []

    def fake_run(args, timeout):
        calls.append(args[0])
        return answers.get(args[0].replace("-", "_"), (0, ""))

    with mock.patch.object(status.shutil, "which", return_value="/usr/bin/mega-whoami"), \
         mock.patch.object(status, "engine_running", return_value=running), \
         mock.patch.object(status, "run", side_effect=fake_run):
        data = status.collect()
    return data, calls


LOGGED_IN = (0, "Account e-mail: user@example.com\n")
STORAGE = (0, "USED STORAGE:         1099511627776                  50.00% of 2199023255552\n")


class EngineTests(CheckedTestCase):
    """Telling a stopped MEGAcmd engine from a running one."""

    def collect(self, running):
        """Collects the state with MEGAcmd installed; returns it and the commands run."""
        return collect_with(running)

    def test_a_stopped_engine_is_reported_and_not_started(self):
        # Every mega-* client starts the engine when it is not running, so
        # none may run while it is stopped.
        data, calls = self.collect(running=False)
        self.assertEqual(calls, [])
        self.assertFalse(data["running"])
        self.assertFalse(data["loggedIn"])

    def test_a_running_engine_is_asked_for_its_state(self):
        data, calls = self.collect(running=True)
        self.assertTrue(data["running"])
        self.assertEqual(calls[0], "mega-whoami")


class UnreadableStateTests(CheckedTestCase):
    """A MEGAcmd that is busy or failing is not taken for logged out or for having nothing."""

    def test_a_busy_whoami_makes_the_state_unreadable(self):
        data, calls = collect_with(mega_whoami=(status.TIMED_OUT, ""))
        self.assertEqual((data["ok"], data["error"]), (False, "MEGAcmd is busy"))
        self.assertEqual(calls, ["mega-whoami"])

    def test_a_failing_whoami_makes_the_state_unreadable(self):
        data, _ = collect_with(mega_whoami=(1, "[API:err: 10:00:00] Internal error"))
        self.assertFalse(data["ok"])
        self.assertIn("Internal error", data["error"])

    def test_not_logged_in_is_read_as_logged_out(self):
        data, calls = collect_with(mega_whoami=(57, "[API:err: 10:00:00] Not logged in."))
        self.assertEqual((data["ok"], data["loggedIn"]), (True, False))
        self.assertEqual(calls, ["mega-whoami"])

    def test_parts_that_fail_are_named_and_noted(self):
        data, _ = collect_with(mega_whoami=LOGGED_IN, mega_df=STORAGE, mega_sync=(status.TIMED_OUT, ""),
                               mega_backup=(1, "[API:err: 10:00:00] Busy"))
        self.assertTrue(data["ok"] and data["loggedIn"])
        self.assertEqual(data["unread"], ["syncs", "backups"])
        self.assertEqual(data["error"], "Could not read the syncs and backups from MEGAcmd.")
        self.assertEqual(data["totalBytes"], 2199023255552)

    def test_storage_without_a_total_is_unread(self):
        data, _ = collect_with(mega_whoami=LOGGED_IN, mega_df=(0, "something else"))
        self.assertEqual(data["unread"], ["storage"])

    def test_a_plain_message_with_a_failing_status_still_counts_as_an_answer(self):
        data, _ = collect_with(mega_whoami=LOGGED_IN, mega_df=STORAGE, mega_backup=(1, "No backup configured."))
        self.assertEqual((data["unread"], data["backups"], data["error"]), ([], [], ""))


class RunTests(CheckedTestCase):
    """Running a command: timeouts, odd output and missing commands."""

    def setUp(self):
        super().setUp()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = pathlib.Path(folder.name)

    def test_a_timeout_kills_the_whole_process_group(self):
        # The background sleep keeps the output pipe open; killing only the
        # shell would leave the run waiting for it.
        script = write_script(self.dir / "slow", "#!/bin/sh\nsleep 8 &\necho $! > \"$0.pid\"\nsleep 8\n")
        start = time.monotonic()
        self.assertEqual(status.run([str(script)], 0.5), (status.TIMED_OUT, ""))
        self.assertLess(time.monotonic() - start, 4)
        pid = int((self.dir / "slow.pid").read_text())
        stat = pathlib.Path(f"/proc/{pid}/stat")
        self.assertTrue(not stat.exists() or stat.read_text().split()[2] == "Z", "the background child still runs")

    def test_output_that_is_not_utf8_is_decoded_with_replacements(self):
        script = write_script(self.dir / "odd", "#!/bin/sh\nprintf 'a\\377b'\n")
        self.assertEqual(status.run([str(script)], 5), (0, "a\ufffdb"))

    def test_a_missing_command_is_reported_not_raised(self):
        self.assertEqual(status.run([str(self.dir / "missing")], 5), (status.NOT_FOUND, ""))


def cli_status(path):
    """Runs `megacmd-applet status --fixture PATH --no-notices` in a fenced environment; returns the process."""
    with tempfile.TemporaryDirectory() as base:
        done = run_cli("status", "--fixture", str(path), "--no-notices", env=fenced_env(base))
    done.check_returncode()
    return done


class FixtureTests(CheckedTestCase):
    """The saved states in fixtures/ read and turn into views."""

    def test_every_fixture_keeps_its_fields_in_the_view(self):
        for path in sorted((ROOT / "fixtures").glob("*.json")):
            with self.subTest(fixture=path.name):
                saved = json.loads(path.read_text())
                shown = json.loads(cli_status(path).stdout)
                for key, value in saved.items():
                    if key in ("syncs", "backups"):
                        for row, saved_row in zip(shown[key], value, strict=True):
                            self.assertEqual({k: row[k] for k in saved_row}, saved_row)
                    else:
                        self.assertEqual(shown[key], value, key)

    def test_a_fixture_must_be_an_object(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
            handle.write("[1, 2]")
            handle.flush()
            shown = json.loads(cli_status(handle.name).stdout)
        self.assertFalse(shown["ok"])
        self.assertIn("not a JSON object", shown["error"])
        self.assertEqual((shown["kind"], shown["kindText"]), ("unknown", shown["error"]))

    def test_every_fixture_says_whether_megacmd_runs(self):
        for path in sorted((ROOT / "fixtures").glob("*.json")):
            self.assertIn("running", json.loads(path.read_text()), path.name)


class StatusCommandTests(CheckedTestCase):
    """`status` always prints a whole view."""

    def setUp(self):
        super().setUp()
        self.fake = FakeMegaCmd()
        self.addCleanup(self.fake.close)

    def status(self, *args):
        """Runs `status ARGS` against the stand-ins; returns the view after checking the exit status is 0."""
        done = self.fake.run_cli(*args)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_a_bad_megacmd_folder_gives_an_unreadable_view(self):
        shown = self.status("--megacmd-dir=relative", "status")
        self.assertEqual((shown["ok"], shown["kind"], shown["loggedIn"], shown["offer"]),
                         (False, "unknown", False, ""))
        self.assertEqual(shown["kindText"], "Not a folder: relative")

    def test_a_busy_megacmd_gives_an_unreadable_view_and_no_notices(self):
        self.fake.set("mega-whoami", "", 0, sleep=5)
        shown = self.status("status", "--timeout", "0.3")
        self.assertEqual((shown["ok"], shown["kind"], shown["kindText"]), (False, "unknown", "MEGAcmd is busy"))
        self.assertEqual(shown["notices"], [])
        self.assertFalse((pathlib.Path(self.fake.env["XDG_STATE_HOME"]) / "megacmd-applet").exists())

    def test_megacmd_not_installed_offers_nothing(self):
        env = dict(self.fake.env, PATH=os.pathsep.join(p for p in self.fake.env["PATH"].split(os.pathsep)
                                                      if not (pathlib.Path(p) / "mega-whoami").exists()))
        shown = json.loads(run_cli("status", env=env).stdout)
        self.assertEqual((shown["kind"], shown["badgeColour"], shown["offer"]), ("missing", "orange", ""))

    def test_a_preview_shows_a_saved_state_for_the_preview_home(self):
        shown = self.status("status", "--preview", "sync-error")
        self.assertEqual(shown["kind"], "error")
        self.assertTrue(all(row["localDisplay"].startswith("~/") for row in shown["syncs"]))
        self.assertEqual(len(shown["notices"]), 1)
        self.assertTrue((pathlib.Path(self.fake.env["XDG_RUNTIME_DIR"]) / "megacmd-applet" / "preview.json").exists())
        self.assertEqual(self.fake.calls(), [])

    def test_a_preview_ignores_the_megacmd_folder(self):
        shown = self.status("--megacmd-dir=relative", "status", "--preview", "ok")
        self.assertEqual((shown["ok"], shown["kind"]), (True, "synced"))

    def test_a_bad_or_unknown_preview_name_gives_an_unreadable_view(self):
        for name in ("no-such-state", "../fixtures/ok", "ok.json", ""):
            shown = self.status("status", "--preview", name)
            self.assertEqual((shown["ok"], shown["kind"]), (False, "unknown"), name)
            self.assertEqual(shown["error"], f"No saved state named {name}")

    def test_an_unwritable_state_file_is_a_note_not_a_failure(self):
        # A folder under a regular file cannot be made, even by root.
        blocker = pathlib.Path(self.fake.base) / "blocker"
        blocker.write_text("")
        shown = self.status("status", "--fixture", str(ROOT / "fixtures" / "sync-error.json"),
                            "--state", str(blocker / "sub" / "notices.json"))
        self.assertEqual(shown["notices"], [])
        self.assertIn("Could not keep the notification state", shown["error"])


if __name__ == "__main__":
    unittest.main()
