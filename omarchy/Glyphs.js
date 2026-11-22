// Glyphs.js: Nerd Font glyphs and text escaping for the Omarchy bar widget.
// SPDX-License-Identifier: GPL-3.0-or-later
.pragma library

// Nerd Font glyphs (Material Design) for the bar icon and rows.
var ICON_CLOUD = "󰅟"
var ICON_ERROR = "󰧠"
var ICON_OFF = "󰅤"
var ICON_BACKUP = "󰁯"

// Glyph of each notice icon the shared core names (see notices.py).
var NOTICE = { error: ICON_ERROR, off: ICON_OFF, cloud: ICON_CLOUD }

// Small badge drawn on the cloud for a state the shared core names.
function badgeGlyph(kind) {
  if (kind === "error" || kind === "warning") return "\uf12a"
  if (kind === "off" || kind === "stopped") return "\uf00d"
  if (kind === "paused") return "\uf04c"
  if (kind === "syncing") return "\uf021"
  return "\uf00c"
}

// TEXT with "&", "<" and ">" escaped, for notification bodies, which the
// notification daemon renders as styled text.
function escapeMarkup(text) {
  return String(text || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}
