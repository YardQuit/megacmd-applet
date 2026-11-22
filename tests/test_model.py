# test_model.py: tests for the shared core's model and view.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for core/megacmd_applet/model.py and view.py: the overall state,
the problems worth a notification, and the texts every applet shows.

Run from the repository root with:  python3 -m unittest discover -s tests
"""

import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

from megacmd_applet import model, view  # noqa: E402

HOME = "/home/user"


def fixture(name):
    """The saved status in fixtures/NAME."""
    return json.loads((ROOT / "fixtures" / name).read_text())


def local_paths(status):
    """Every local folder a status names, absolute and in its ~/ form."""
    paths = [entry["local"] for entry in status.get("syncs", []) + status.get("backups", [])]
    return paths + ["~" + path[len(HOME):] for path in paths if path.startswith(HOME + "/")]


class ProblemTests(unittest.TestCase):
    def assert_no_local_path(self, found, status):
        for problem in found:
            for path in local_paths(status):
                self.assertNotIn(path, problem["title"])
                self.assertNotIn(path, problem["body"])

    def test_sync_error_is_reported_without_its_folder(self):
        status = fixture("sync-error.json")
        found = model.problems(status)
        failed = [s for s in status["syncs"] if s["error"]]
        self.assertEqual(len(found), len(failed))
        self.assertEqual(found[0]["title"], "MEGA sync stopped")
        self.assertIn(failed[0]["error"], found[0]["body"])
        self.assert_no_local_path(found, status)

    def test_failed_backup_is_reported_without_its_folder(self):
        status = fixture("backup-failed.json")
        found = model.problems(status)
        self.assertGreaterEqual(len(found), 1)
        self.assertTrue(all(p["title"].startswith("MEGA backup ") for p in found))
        self.assert_no_local_path(found, status)

    def test_healthy_status_reports_nothing(self):
        self.assertEqual(model.problems(fixture("ok.json")), [])


class StateTests(unittest.TestCase):
    def test_all_paused_with_storage_nearly_full_can_still_be_resumed(self):
        status = fixture("storage-95.json")
        for sync in status["syncs"]:
            sync["runState"] = "Disabled"
        self.assertEqual(model.overall_kind(status), "warning")
        self.assertFalse(model.any_running(status["syncs"]))

    def test_one_running_sync_means_pause_all(self):
        self.assertTrue(model.any_running(fixture("paused.json")["syncs"] + [{"runState": "Running"}]))

    def test_removal_is_keyed_by_id_not_by_row(self):
        syncs = fixture("ok.json")["syncs"]
        self.assertEqual(model.item_key("sync", syncs[1]), "sync:" + syncs[1]["id"])
        self.assertEqual(model.item_key("backup", {"tag": "7"}), "backup:7")
        self.assertEqual(model.item_key("sync", None), "")

    def test_transfers_are_summarised_per_direction(self):
        transfers = {"downloads": 1200, "downloaded": "1.20 GB", "downloadTotal": "4.80 GB", "downloadPercent": 25.0,
                     "uploads": 3, "uploaded": "10.00 MB", "uploadTotal": "20.00 MB", "uploadPercent": 50.4}
        self.assertEqual(model.transfers_text(transfers).split("\n"),
                         ["1,200 down · 1.20 GB of 4.80 GB (25%)", "3 up · 10.00 MB of 20.00 MB (50%)"])
        self.assertEqual(model.transfers_text(dict(transfers, downloads=0, uploads=0)), "")

    def test_a_stopped_engine_has_its_own_state(self):
        status = dict(fixture("ok.json"), running=False, loggedIn=False)
        self.assertEqual(model.overall_kind(status), "stopped")
        self.assertEqual(model.OVERALL_TEXT["stopped"], "MEGAcmd is not running")

    def test_byte_counts_round_as_javascript_did(self):
        self.assertEqual(model.format_bytes(0), "0 B")
        self.assertEqual(model.format_bytes(1536), "1.50 KB")
        self.assertEqual(model.format_bytes(2759989952000), "2.51 TB")


class ViewTests(unittest.TestCase):
    def test_view_carries_meaning_and_texts_for_every_row(self):
        shown = view.build_view(fixture("sync-error.json"), HOME)
        self.assertEqual((shown["kind"], shown["kindText"], shown["badgeColour"]),
                         ("error", "A sync needs attention", "red"))
        failed = [s for s in shown["syncs"] if s["kind"] == "error"]
        self.assertTrue(failed and failed[0]["meta"].startswith("Error: "))
        for sync in shown["syncs"]:
            self.assertEqual(sync["key"], "sync:" + sync["id"])
            self.assertEqual(sync["badgeColour"], model.BADGE_COLOUR[sync["kind"]])
            self.assertTrue(sync["localDisplay"].startswith("~") or not sync["local"].startswith(HOME))

    def test_backup_rows_say_when_they_failed(self):
        shown = view.build_view(fixture("backup-failed.json"), HOME)
        self.assertTrue(any(b["failed"] for b in shown["backups"]))
        self.assertTrue(all(b["meta"] for b in shown["backups"]))

    def test_view_keeps_the_notices_it_is_given(self):
        notice = {"title": "t", "body": "b", "urgency": "normal", "icon": "cloud"}
        self.assertEqual(view.build_view(fixture("ok.json"), HOME, [notice])["notices"], [notice])
        self.assertEqual(view.build_view(fixture("ok.json"), HOME)["notices"], [])


if __name__ == "__main__":
    unittest.main()
