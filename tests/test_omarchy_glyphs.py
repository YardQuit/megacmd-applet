# test_omarchy_glyphs.py: tests for the Omarchy widget's Nerd Font glyphs.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests for omarchy/Glyphs.js: every state the shared core names has its
badge glyph, and every notice icon its glyph. Glyphs.js is a QML JavaScript
library; these tests load it in Node, so they are skipped where Node is not
installed.

Run from the repository root with:  python3 -m unittest discover -s tests
"""

import json
import pathlib
import shutil
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

from megacmd_applet import model  # noqa: E402

# Loads Glyphs.js without its ".pragma library" line and prints the badge
# glyph of each state named on standard input, and the notice glyphs.
RUNNER = """
const fs = require("fs");
const vm = require("vm");
const context = {};
vm.runInNewContext(fs.readFileSync(process.argv[1], "utf8").replace(/^\\.pragma library$/m, ""), context);
const kinds = JSON.parse(fs.readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify({
  badges: Object.fromEntries(kinds.map((kind) => [kind, context.badgeGlyph(kind)])),
  notices: context.NOTICE,
}));
"""

# The Font Awesome glyphs of Nerd Fonts the badges show.
BADGES = {"error": "", "warning": "", "off": "", "stopped": "",
          "paused": "", "syncing": "", "synced": ""}


@unittest.skipUnless(shutil.which("node"), "Node is not installed")
class GlyphTests(unittest.TestCase):
    def setUp(self):
        done = subprocess.run(["node", "-e", RUNNER, str(ROOT / "omarchy" / "Glyphs.js")],
                              input=json.dumps(list(model.KINDS)), capture_output=True, text=True, check=True)
        self.glyphs = json.loads(done.stdout)

    def test_every_state_has_its_badge_glyph(self):
        self.assertEqual(self.glyphs["badges"], BADGES)

    def test_every_notice_icon_has_a_glyph(self):
        for icon in ("error", "off", "cloud"):
            glyph = self.glyphs["notices"].get(icon, "")
            self.assertEqual(len(glyph), 1, icon)
            self.assertGreaterEqual(ord(glyph), 0xF0000, icon)


if __name__ == "__main__":
    unittest.main()
