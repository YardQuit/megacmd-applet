# test_notices.py: tests for the once-per-problem notification bookkeeping.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for core/megacmd_applet/notices.py. Every test keeps its state file
in a temporary folder, never the user's.

Run from the repository root with:  python3 -m unittest discover -s tests
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

from megacmd_applet import notices  # noqa: E402


def fixture(name):
    """The saved status in fixtures/NAME."""
    return json.loads((ROOT / "fixtures" / name).read_text())


class NoticeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.state = pathlib.Path(self.folder.name) / "notices.json"

    def tearDown(self):
        self.folder.cleanup()

    def take(self, status, **options):
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


class PreviewTests(unittest.TestCase):
    def test_a_preview_keeps_its_notices_apart_from_the_live_ones(self):
        with tempfile.TemporaryDirectory() as state, tempfile.TemporaryDirectory() as runtime:
            env = {**os.environ, "XDG_STATE_HOME": state, "XDG_RUNTIME_DIR": runtime}
            command = [sys.executable, "-I", str(ROOT / "bin" / "megacmd-applet"), "status",
                       "--fixture", str(ROOT / "fixtures" / "sync-error.json")]
            shown = json.loads(subprocess.run(command, env=env, capture_output=True, text=True, check=True).stdout)
            self.assertEqual(len(shown["notices"]), 1)
            self.assertTrue((pathlib.Path(runtime) / "megacmd-applet" / "preview.json").exists())
            self.assertFalse((pathlib.Path(state) / "megacmd-applet").exists())


if __name__ == "__main__":
    unittest.main()
