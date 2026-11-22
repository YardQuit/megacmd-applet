# test_notices.py: tests for the once-per-problem notification bookkeeping.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for core/megacmd_applet/notices.py. Every test keeps its state file
in a temporary folder, never the user's.

Run from the repository root with:  python3 -m unittest discover -s tests
"""

import json
import pathlib
import tempfile
import threading
import unittest

from support import ROOT, CheckedTestCase, fenced_env, fixture, run_cli

from megacmd_applet import notices


def failing_syncs(count):
    """The sync-error state with COUNT syncs that stopped for different reasons."""
    status = fixture("sync-error.json")
    template = status["syncs"][0]
    status["syncs"] = [dict(template, id=f"s{i}", error=f"Reason {i}") for i in range(count)]
    return status


class NoticeTests(CheckedTestCase):
    """Reporting each problem once, across runs and applets."""

    def setUp(self):
        super().setUp()
        self.folder = tempfile.TemporaryDirectory()
        self.state = pathlib.Path(self.folder.name) / "notices.json"

    def tearDown(self):
        self.folder.cleanup()
        super().tearDown()

    def take(self, status, **options):
        """Takes the new notices for STATUS from the test state file."""
        return notices.take_notices(status, self.state, **options)

    def test_a_problem_is_reported_once(self):
        first = self.take(fixture("sync-error.json"))
        self.assertEqual([n["title"] for n in first], ["MEGA sync stopped"])
        self.assertEqual(first[0]["urgency"], "critical")
        self.assertEqual(self.take(fixture("sync-error.json")), [])

    def test_a_problem_that_cleared_and_came_back_is_reported_again(self):
        self.take(fixture("sync-error.json"))
        self.take(fixture("ok.json"))
        self.assertEqual(len(self.take(fixture("sync-error.json"))), 1)

    def test_the_engine_stopping_is_reported_once(self):
        self.take(fixture("ok.json"))
        stopped = self.take(fixture("stopped.json"))
        self.assertEqual([n["title"] for n in stopped], ["MEGAcmd stopped"])
        self.assertEqual(self.take(fixture("stopped.json")), [])

    def test_logging_out_is_reported(self):
        self.take(fixture("ok.json"))
        self.assertEqual([n["title"] for n in self.take(fixture("logged-out.json"))], ["MEGA logged out"])

    def test_storage_is_reported_when_it_crosses_90_and_95(self):
        self.take(fixture("ok.json"))
        at_90 = self.take(fixture("storage-90.json"))
        self.assertEqual(len(at_90), 1)
        self.assertEqual(at_90[0]["urgency"], "normal")
        at_95 = self.take(fixture("storage-95.json"))
        self.assertEqual(at_95[0]["urgency"], "critical")
        self.assertEqual(self.take(fixture("storage-95.json")), [])

    def test_fresh_forgets_what_was_reported(self):
        self.take(fixture("sync-error.json"))
        self.assertEqual(len(self.take(fixture("sync-error.json"), fresh=True)), 1)

    def test_an_unreadable_state_file_starts_over(self):
        self.state.write_text("not json")
        self.assertEqual(len(self.take(fixture("sync-error.json"))), 1)

    def test_many_problems_of_a_kind_give_one_notice(self):
        found = self.take(failing_syncs(3))
        self.assertEqual([n["title"] for n in found], ["MEGA: 3 syncs stopped"])
        self.assertEqual(self.take(failing_syncs(3)), [])
        self.assertEqual([n["title"] for n in self.take(failing_syncs(4))], ["MEGA sync stopped"])

    def test_syncs_that_could_not_be_read_keep_what_was_reported(self):
        self.take(fixture("sync-error.json"))
        self.assertEqual(self.take(dict(fixture("ok.json"), syncs=[], unread=["syncs"])), [])
        self.assertEqual(self.take(fixture("sync-error.json")), [])

    def test_storage_that_could_not_be_read_keeps_its_level(self):
        self.take(fixture("storage-95.json"))
        self.take(dict(fixture("ok.json"), usagePercent=0.0, totalBytes=0, unread=["storage"]))
        self.assertEqual(self.take(fixture("storage-95.json")), [])

    def test_storage_without_a_total_is_not_reported(self):
        self.assertEqual(self.take(dict(fixture("ok.json"), usagePercent=250.0, totalBytes=0)), [])

    def test_storage_beyond_the_range_is_reported_as_full(self):
        (notice,) = self.take(dict(fixture("ok.json"), usagePercent=250.0))
        self.assertEqual(notice["title"], "MEGA storage 100% full")

    def test_problems_are_not_repeated_after_an_engine_restart(self):
        # Syncs and backups cannot be read while the engine is stopped, so
        # their problems stay recorded rather than being reported again.
        self.take(fixture("sync-error.json"))
        self.take(fixture("stopped.json"))
        self.assertEqual(self.take(fixture("sync-error.json")), [])

    def test_megacmd_missing_reports_nothing(self):
        self.take(fixture("ok.json"))
        self.assertEqual(self.take(dict(fixture("logged-out.json"), installed=False)), [])

    def test_a_state_file_with_odd_bytes_or_types_starts_over(self):
        for text in (b"\xff\xfe{", json.dumps({"reported": 5, "wasRunning": "yes", "storageLevel": "x"}).encode(),
                     json.dumps({"reported": ["sync:x", 3], "storageLevel": True}).encode()):
            self.state.write_bytes(text)
            self.assertEqual(len(self.take(fixture("sync-error.json"))), 1, text)

    def test_a_new_preview_name_starts_afresh(self):
        self.assertEqual(len(self.take(fixture("sync-error.json"), preview="a")), 1)
        self.assertEqual(self.take(fixture("sync-error.json"), preview="a"), [])
        self.assertEqual(len(self.take(fixture("sync-error.json"), preview="b")), 1)

    def test_the_state_file_is_replaced_whole(self):
        self.take(fixture("sync-error.json"))
        self.assertEqual(sorted(p.name for p in self.state.parent.iterdir()), ["notices.json", "notices.json.lock"])
        self.assertEqual(json.loads(self.state.read_text())["reported"], ["sync:sync001:Local path not found"])

    def test_the_state_file_is_private(self):
        self.take(fixture("ok.json"))
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)

    def test_two_applets_at_once_report_a_problem_only_once(self):
        found = []
        start = threading.Barrier(8)

        def applet():
            start.wait()
            found.extend(self.take(fixture("sync-error.json")))

        threads = [threading.Thread(target=applet) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(found), 1)


class PreviewTests(CheckedTestCase):
    """Keeping the notices of previews apart from the live ones."""

    def test_a_preview_keeps_its_notices_apart_from_the_live_ones(self):
        with tempfile.TemporaryDirectory() as base:
            env = fenced_env(base)
            done = run_cli("status", "--fixture", str(ROOT / "fixtures" / "sync-error.json"), env=env)
            shown = json.loads(done.stdout)
            self.assertEqual(len(shown["notices"]), 1)
            self.assertTrue((pathlib.Path(env["XDG_RUNTIME_DIR"]) / "megacmd-applet" / "preview.json").exists())
            self.assertFalse((pathlib.Path(env["XDG_STATE_HOME"]) / "megacmd-applet").exists())

    def test_an_unreadable_state_takes_no_notices(self):
        with tempfile.TemporaryDirectory() as base:
            env = fenced_env(base)
            saved = pathlib.Path(base) / "busy.json"
            saved.write_text(json.dumps({"ok": False, "error": "MEGAcmd is busy"}))
            shown = json.loads(run_cli("status", "--fixture", str(saved), env=env).stdout)
            self.assertEqual((shown["kind"], shown["notices"]), ("unknown", []))
            self.assertFalse((pathlib.Path(env["XDG_RUNTIME_DIR"]) / "megacmd-applet").exists())


if __name__ == "__main__":
    unittest.main()
