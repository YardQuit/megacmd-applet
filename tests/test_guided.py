# test_guided.py: tests for the guided terminal dialogs in bin/.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for bin/mega-add-sync, mega-add-backup, mega-edit-backup and guided.sh.

gum and the mega-* commands are stand-ins: gum gives the answers queued for
it, one per call, and every command logs its arguments. No real MEGAcmd
command runs (see support.py).

Run from the repository root with:  python3 -m unittest discover -s tests
"""

import pathlib
import subprocess
import unittest

from support import ROOT, CheckedTestCase, FakeMegaCmd, logged_in, tool_dir, write_script

# A stand-in gum: logs its arguments; "gum style" prints its text to standard
# error; any other call takes the first "STATUS|OUTPUT" line of
# $GUM_ANSWERS, prints OUTPUT and exits with STATUS (1 when none is left).
GUM = """#!/bin/sh
printf 'gum' >> "$FAKE_LOG"
for arg in "$@"; do printf ' %s' "$arg" >> "$FAKE_LOG"; done
printf '\\n' >> "$FAKE_LOG"
if [ "$1" = style ]; then shift; printf '%s\\n' "$*" >&2; exit 0; fi
[ -s "$GUM_ANSWERS" ] || exit 1
line=$(head -n 1 "$GUM_ANSWERS")
tail -n +2 "$GUM_ANSWERS" > "$GUM_ANSWERS.rest" && mv "$GUM_ANSWERS.rest" "$GUM_ANSWERS"
out=${line#*|}
[ -n "$out" ] && printf '%s\\n' "$out"
exit "${line%%|*}"
"""


class GuidedDialogTests(CheckedTestCase):
    """The dialogs stop on a cancel or a wrong answer and pass on only checked values."""

    def setUp(self):
        super().setUp()
        self.fake = FakeMegaCmd()
        self.addCleanup(self.fake.close)
        logged_in(self.fake)
        write_script(self.fake.dir / "gum", GUM)
        self.answers = self.fake.base / "answers"
        self.fake.env["GUM_ANSWERS"] = str(self.answers)
        self.folder = pathlib.Path(self.fake.env["HOME"]) / "Pictures"
        self.folder.mkdir()

    def dialog(self, name, answers, *args, env=None):
        """Runs the dialog NAME with ARGS, gum answering ANSWERS in turn; returns the finished process."""
        self.answers.write_text("".join(f"{line}\n" for line in answers))
        return subprocess.run([str(ROOT / "bin" / name), *args], env=env or self.fake.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=30, check=False)

    def mega_calls(self, name):
        """The logged runs of the mega-* command NAME."""
        return [line for line in self.fake.calls() if line.split(" ", 1)[0] == name]

    def test_a_sync_is_added_with_a_clean_mega_folder(self):
        done = self.dialog("mega-add-sync", [f"0|{self.folder}", "0|/Sync/Pictures//", "0|"], "/Sync")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.mega_calls("mega-sync"), [f"mega-sync {self.folder} /Sync/Pictures"])

    def test_cancelling_the_folder_stops_adding_a_sync(self):
        done = self.dialog("mega-add-sync", ["1|", "0|/Sync/x", "0|"])
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(self.mega_calls("mega-sync"), [])
        self.assertEqual(self.mega_calls("mega-mkdir"), [])

    def test_cancelling_the_schedule_stops_adding_a_backup(self):
        done = self.dialog("mega-add-backup", [f"0|{self.folder}", "0|/Backups", "130|", "0|3", "0|"])
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(self.mega_calls("mega-backup"), [])

    def test_a_custom_period_megacmd_would_not_take_stops_the_dialog(self):
        done = self.dialog("mega-add-backup", [f"0|{self.folder}", "0|/Backups", "0|Other…", "0|every tuesday",
                                               "0|3", "0|"])
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("Not a backup period", done.stderr)
        self.assertEqual(self.mega_calls("mega-backup"), [])

    def test_a_custom_period_is_passed_on(self):
        done = self.dialog("mega-add-backup", [f"0|{self.folder}", "0|/Backups", "0|Other…", "0|1m12d3h",
                                               "0|3", "0|"])
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.mega_calls("mega-backup"),
                         [f"mega-backup {self.folder} /Backups --period=1m12d3h --num-backups=3"])

    def test_a_wrong_number_kept_stops_editing_a_backup(self):
        done = self.dialog("mega-edit-backup", ["0|Keep current (1d)", "0|x", "0|"], "7", "1d", "")
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(self.mega_calls("mega-backup"), [])

    def test_an_empty_number_kept_suggests_the_default(self):
        done = self.dialog("mega-edit-backup", ["0|Keep current (1d)", "0|14", "0|"], "7", "1d", "")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("--value=14", next(line for line in self.fake.calls() if line.startswith("gum input")))
        self.assertEqual(self.mega_calls("mega-backup"), ["mega-backup 7 --period=1d --num-backups=14"])

    def test_without_gum_the_dialogs_say_so_and_stop(self):
        tools = tool_dir(self.fake.base, ("dirname", "realpath", "basename", "cat", "sleep", "sed"))
        bare = self.fake.base / "bare"
        bare.mkdir()
        for name in ("mega-whoami", "mega-sync"):
            (bare / name).symlink_to(self.fake.dir / name)
        env = dict(self.fake.env, PATH=f"{bare}:{tools}")
        for name in ("mega-account-login", "mega-add-sync", "mega-add-backup", "mega-edit-backup"):
            done = self.dialog(name, [], "7", env=env)
            self.assertEqual(done.returncode, 1, name)
            self.assertIn("gum is not installed", done.stderr, name)
        self.assertEqual(self.mega_calls("mega-sync"), [])


if __name__ == "__main__":
    unittest.main()
