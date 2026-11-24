# test_model.py: tests for the shared core's model and view.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for core/megacmd_applet/model.py and view.py: the overall state,
the problems worth a notification, and the texts every applet shows.

Run from the repository root with:  python3 -m unittest discover -s tests
"""

import json
import unittest

from support import CheckedTestCase, fixture

from megacmd_applet import model, view

HOME = "/home/user"


def local_paths(status):
    """Every local folder a status names, absolute and in its ~/ form."""
    paths = [entry["local"] for entry in status.get("syncs", []) + status.get("backups", [])]
    return paths + ["~" + path[len(HOME):] for path in paths if path.startswith(HOME + "/")]


class ProblemTests(CheckedTestCase):
    """Finding the problems to notify about."""

    def assert_no_local_path(self, found, status):
        """Fails if any problem in FOUND names a local folder of STATUS."""
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


class StateTests(CheckedTestCase):
    """Working out the overall state."""

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

    def test_megacmd_missing_or_unreadable_has_its_own_state(self):
        self.assertEqual(model.overall_kind(dict(fixture("ok.json"), installed=False)), "missing")
        self.assertEqual(model.overall_kind(dict(fixture("ok.json"), ok=False)), "unknown")
        self.assertEqual(model.overall_kind(dict(fixture("ok.json"), syncs=[], unread=["syncs"])), "unknown")

    def test_every_state_has_a_text_and_a_colour(self):
        for kind in model.KINDS:
            self.assertTrue(model.OVERALL_TEXT[kind] and model.BADGE_COLOUR[kind], kind)

    def test_the_paused_run_state_counts_as_paused(self):
        self.assertTrue(model.sync_paused({"runState": "Paused"}))
        self.assertEqual(model.sync_kind({"runState": "Paused", "status": "Synced"}), "paused")

    def test_numbers_that_are_not_finite_are_zero(self):
        for value in ("nan", "inf", float("inf"), "-inf", None, "x"):
            self.assertEqual(model.number(value), 0.0, value)

    def test_byte_counts_round_as_javascript_did(self):
        self.assertEqual(model.format_bytes(0), "0 B")
        self.assertEqual(model.format_bytes(1536), "1.50 KB")
        self.assertEqual(model.format_bytes(2759989952000), "2.51 TB")


class StorageTests(CheckedTestCase):
    """The storage line and warning level."""

    def test_storage_beyond_the_range_is_clamped(self):
        status = dict(fixture("ok.json"), usagePercent=250.0)
        self.assertEqual(model.storage_percent(status), 100.0)
        self.assertTrue(model.usage_text(status).endswith("(100%)"))
        self.assertEqual(model.storage_percent(dict(status, usagePercent=-5)), 0.0)

    def test_storage_without_a_total_has_no_line_and_no_warning(self):
        status = dict(fixture("ok.json"), usagePercent=97.0, totalBytes=0)
        self.assertEqual((model.usage_text(status), model.storage_percent(status)), ("", 0.0))
        self.assertEqual(model.overall_kind(status), "synced")


class PeriodTests(CheckedTestCase):
    """Backup schedules in words."""

    def test_cron_lines(self):
        for period, text in (("0 0 2 * * *", "Daily at 02:00 UTC"), ("0 30 4 * * 1", "Weekly on Monday at 04:30 UTC"),
                             ("0 0 3 * * 7", "Weekly on Sunday at 03:00 UTC"),
                             ("0 0 3 * * sat", "Weekly on Saturday at 03:00 UTC"),
                             ("15 30 4 * * *", "Daily at 04:30:15 UTC"), ("0 5 * * * *", "Hourly at :05")):
            self.assertEqual(model.period_text(period), text, period)

    def test_cron_lines_that_are_not_simple_stay_as_they_are(self):
        for period in ("0 0 * * * 1", "0 0 0 15 * *", "0 0 */2 * * *", "0 0 2 * * 1-5", "0 0 25 * * *"):
            self.assertEqual(model.period_text(period), period)

    def test_times_use_megacmds_units(self):
        for period, text in (("1d", "Every day"), ("6h", "Every 6 hours"), ("1m", "Every month"),
                             ("30M", "Every 30 minutes"), ("1m12d3h", "Every 1 month, 12 days, 3 hours"),
                             ("weird", "weird")):
            self.assertEqual(model.period_text(period), text, period)


class OfferTests(CheckedTestCase):
    """What an applet offers when nobody is logged in."""

    def test_each_state_offers_what_helps(self):
        for status, offer in ((fixture("stopped.json"), "start"), (fixture("logged-out.json"), "login"),
                              (fixture("ok.json"), ""), (dict(fixture("logged-out.json"), installed=False), ""),
                              (dict(fixture("logged-out.json"), ok=False), "")):
            self.assertEqual(model.offer(status), offer)


class ViewTests(CheckedTestCase):
    """Building the view the desktops draw."""

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

    def test_rows_have_titles_and_backup_rows_their_state(self):
        shown = view.build_view(fixture("backup-failed.json"), HOME)
        self.assertEqual(shown["syncs"][0]["title"], "~/Documents ↔ /Sync/Documents")
        self.assertEqual(shown["backups"][0]["title"], "~/Pictures → /Backups")
        self.assertEqual((shown["backups"][0]["kind"], shown["backups"][0]["badgeColour"]), ("error", "red"))
        ok = view.build_view(fixture("ok.json"), HOME)["backups"][0]
        self.assertEqual((ok["kind"], ok["badgeColour"]), ("synced", "green"))
        pending = view.backup_row(dict(fixture("ok.json")["backups"][0], lastStatus=""), HOME)
        self.assertEqual((pending["kind"], pending["badgeColour"]), ("pending", ""))

    def test_an_unreadable_state_shows_why_and_offers_nothing(self):
        shown = view.build_view({"ok": False, "error": "MEGAcmd is busy", "loggedIn": True}, HOME)
        self.assertEqual((shown["kind"], shown["kindText"], shown["error"]), ("unknown", "MEGAcmd is busy",
                                                                             "MEGAcmd is busy"))
        self.assertEqual((shown["loggedIn"], shown["offer"], shown["offerText"], shown["badgeColour"]),
                         (False, "", "", "orange"))
        self.assertEqual((shown["syncs"], shown["usageText"]), ([], ""))

    def test_offers_come_with_their_text_and_hint(self):
        shown = view.build_view(fixture("stopped.json"), HOME)
        self.assertEqual((shown["offer"], shown["offerText"]), ("start", "Start MEGAcmd"))
        self.assertTrue(shown["offerHint"])
        shown = view.build_view(fixture("logged-out.json"), HOME)
        self.assertEqual((shown["offer"], shown["offerText"]), ("login", "Log in to MEGA"))

    def test_view_keeps_the_notices_it_is_given(self):
        notice = {"title": "t", "body": "b", "urgency": "normal", "icon": "cloud"}
        self.assertEqual(view.build_view(fixture("ok.json"), HOME, [notice])["notices"], [notice])
        self.assertEqual(view.build_view(fixture("ok.json"), HOME)["notices"], [])


class SyncIssueTests(CheckedTestCase):
    """Files that are not syncing: their state, texts, notices and buttons."""

    def setUp(self):
        super().setUp()
        self.status = fixture("sync-issues.json")
        self.conflict, self.unreadable = self.status["issues"]

    def test_a_sync_with_issues_is_a_warning_not_a_stopped_sync(self):
        sync = self.status["syncs"][0]
        self.assertEqual((model.issue_count(sync), model.sync_kind(sync)), (2, "warning"))
        self.assertTrue(model.sync_meta(sync).startswith("2 files not syncing · "))
        self.assertEqual(model.overall_kind(self.status), "warning")
        self.assertEqual(model.overall_text(self.status, "warning"), model.ISSUES_TEXT)

    def test_storage_running_out_keeps_its_own_warning_text(self):
        status = fixture("storage-90.json")
        self.assertEqual(model.overall_text(status, model.overall_kind(status)), "Storage almost full")

    def test_a_paused_sync_with_issues_shows_as_paused(self):
        self.status["syncs"][0]["runState"] = "Disabled"
        self.assertEqual(model.sync_kind(self.status["syncs"][0]), "paused")

    def test_only_two_copies_of_one_file_make_a_conflict(self):
        self.assertIsNotNone(model.issue_conflict(self.conflict))
        self.assertIsNone(model.issue_conflict(self.unreadable))
        local, cloud = self.conflict["paths"]
        for paths in ([local, dict(local)], [dict(cloud, size=""), local], [dict(local, problem="Locked"), cloud],
                      [local, dict(cloud, path="/Sync/Documents/Other.ods")], [local, cloud, cloud]):
            self.assertIsNone(model.issue_conflict(dict(self.conflict, paths=paths)), paths)

    def test_the_fingerprint_changes_with_any_date_or_size(self):
        changed = json.loads(json.dumps(self.conflict))
        changed["paths"][0]["modified"] = "2026-10-20 09:14:03"
        self.assertEqual(model.issue_version(self.conflict), model.issue_version(json.loads(json.dumps(self.conflict))))
        self.assertNotEqual(model.issue_version(self.conflict), model.issue_version(changed))

    def test_a_conflict_shows_both_copies_and_which_is_newer(self):
        self.assertEqual(model.issue_lines(self.conflict, HOME), ["On this computer: 2026-10-20 09:14 · 48.20 KB",
                                                                   "On MEGA: 2026-10-22 18:40 · 47.95 KB · newer"])
        self.assertEqual(model.issue_lines(self.unreadable, HOME),
                         ["On this computer: ~/Documents/Notes.txt (Permission denied)"])

    def test_each_issue_is_reported_once_without_its_name_or_folder(self):
        found = [problem for problem in model.problems(self.status) if problem["kind"] == "issue"]
        self.assertEqual([problem["key"] for problem in found], ["issue:issue001", "issue:issue002"])
        self.assertEqual(found[0]["title"], "MEGA: a file has two different copies")
        for problem in found:
            for word in ("Budget", "Notes", "Documents"):
                self.assertNotIn(word, problem["title"] + problem["body"])
        self.assertFalse(any(problem["kind"] == "sync" for problem in model.problems(self.status)))

    def test_a_conflict_gets_a_button_for_each_choice(self):
        shown = view.build_view(self.status, HOME)
        row = shown["issues"][0]
        self.assertEqual((row["key"], row["title"], row["syncTitle"]),
                         ("issue:issue001", "Budget.ods", "~/Documents ↔ /Sync/Documents"))
        version = model.issue_version(self.conflict)
        self.assertEqual([action["args"] for action in row["actions"]],
                         [["resolve", "issue001", choice, version] for choice in ("both", "local", "cloud")])
        self.assertTrue(all(action["label"] and action["hint"] for action in row["actions"]))
        self.assertEqual((shown["kindText"], shown["issuesMoreText"]), (model.ISSUES_TEXT, ""))

    def test_another_issue_gets_a_button_that_opens_its_folder(self):
        row = view.build_view(self.status, HOME)["issues"][1]
        self.assertEqual([action["args"] for action in row["actions"]], [["open-folder", "/home/user/Documents"]])
        self.assertEqual(row["text"], self.unreadable["reason"])

    def test_issues_beyond_those_shown_are_counted(self):
        self.status["issues"] = [dict(self.conflict, id=f"i{n}") for n in range(view.ISSUES_SHOWN + 2)]
        self.status["syncs"][0]["error"] = "Sync Issues (9)"
        shown = view.build_view(self.status, HOME)
        self.assertEqual(len(shown["issues"]), view.ISSUES_SHOWN)
        self.assertTrue(shown["issuesMoreText"].startswith(f"{9 - view.ISSUES_SHOWN} more files not syncing"))


if __name__ == "__main__":
    unittest.main()
