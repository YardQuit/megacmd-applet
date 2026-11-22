// ThemePalette.qml: the current Omarchy theme's named colours.
// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import Quickshell.Io
import qs.Commons

// Reads red, green, yellow, orange and blue from the current theme's
// colors.toml, which the shell does not expose by name, and reads them again
// when the file or the shell's colours change, as on a theme switch. Falls
// back to the shell's urgent and accent colours when the theme does not
// define them.
Item {
  id: root

  property color red: Color.urgent
  property color green: Color.accent
  property color yellow: Color.accent
  property color orange: Color.urgent
  property color blue: Color.accent

  // Takes the named colours from the colors.toml TEXT.
  function apply(text) {
    var values = {}
    var lines = String(text || "").split("\n")
    for (var i = 0; i < lines.length; i++) {
      // The same pattern as Commons.Color: quoted or bare hex values.
      var match = lines[i].match(/^\s*([A-Za-z0-9_-]+)\s*=\s*["']?(#[0-9A-Fa-f]{6})/)
      if (match) values[match[1]] = match[2]
    }
    red = values.red || Color.urgent
    green = values.green || Color.accent
    yellow = values.yellow || Color.accent
    orange = values.orange || values.yellow || Color.urgent
    blue = values.blue || Color.accent
  }

  FileView {
    id: colorsFile
    path: Color.currentThemePath + "/colors.toml"
    watchChanges: true
    onFileChanged: reload()
    onLoaded: root.apply(text())
  }

  Connections {
    target: Color
    function onForegroundChanged() { colorsFile.reload() }
    function onBackgroundChanged() { colorsFile.reload() }
    function onAccentChanged() { colorsFile.reload() }
  }
}
