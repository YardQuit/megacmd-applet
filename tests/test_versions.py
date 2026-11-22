# test_versions.py: tests that every package states the same version.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The version is set in manifest.json; the KDE, GNOME and COSMIC packages
state it again in their own metadata, which must match."""

import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def manifest_version():
    """The version in manifest.json."""
    return json.loads((ROOT / "manifest.json").read_text())["version"]


class VersionTest(unittest.TestCase):
    def test_manifest_version_is_dotted_numbers(self):
        self.assertRegex(manifest_version(), r"^[0-9]+\.[0-9]+\.[0-9]+$")

    def test_kde_metadata_matches_manifest(self):
        metadata = json.loads((ROOT / "kde" / "metadata.json").read_text())
        self.assertEqual(metadata["KPlugin"]["Version"], manifest_version())

    def test_gnome_metadata_matches_manifest(self):
        metadata = json.loads((ROOT / "gnome" / "metadata.json").read_text())
        self.assertEqual(metadata["version-name"], manifest_version())

    def test_cargo_package_matches_manifest(self):
        cargo = (ROOT / "cosmic" / "Cargo.toml").read_text()
        match = re.search(r'^\[package\][^\[]*?^version = "([^"]+)"', cargo, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), manifest_version())


if __name__ == "__main__":
    unittest.main()
