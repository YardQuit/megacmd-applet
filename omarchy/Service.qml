// Service.qml: MEGAcmd state and actions for the MEGA bar widget.
// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import "Glyphs.js" as Glyphs

// The plugin's service: one instance for the whole shell, whose state every
// bar's panel shows. Polls the shared core (bin/megacmd-applet status) for the
// account, syncs, backups, transfers and what they mean, shows the
// notifications the core hands it, and runs the core's actions for the
// panels. Refreshes quickly while a panel is open on any screen (see
// setPanelOpen) and every `refreshIntervalSec` otherwise. Setting
// `previewName` to a file name in fixtures/ shows that saved state instead;
// actions do nothing while a preview is shown.
Item {
  id: root

  // The widget's settings, handed over by the panels.
  property var settings: ({})
  readonly property bool fastRefresh: _openPanels.length > 0
  property string previewName: ""

  property bool installed: true
  property bool running: true
  property bool loggedIn: false
  property string email: ""
  property string kind: "synced"
  property string kindText: ""
  property string badgeColour: "green"
  property bool anyRunning: false
  property string usageText: ""
  property int storageLevel: 0
  property string transfersText: ""
  property var syncs: []
  property var backups: []
  property string lastError: ""
  property string actionStatus: ""
  property bool loaded: false

  // The repository: this file sits in its omarchy/ folder.
  readonly property string repoDir: decodeURIComponent(String(Qt.resolvedUrl("..")).replace(/^file:\/\//, "")).replace(/\/$/, "")
  readonly property string cli: repoDir + "/bin/megacmd-applet"
  readonly property int refreshIntervalSec: intSetting("refreshIntervalSec", 60, 10, 3600)
  readonly property string syncFolder: String(setting("syncFolder", "/"))
  readonly property string backupFolder: String(setting("backupFolder", "/Backups"))
  readonly property bool busy: controlProcess.running

  property var _queue: []
  property var _openPanels: []
  property bool _freshPreview: false

  function setting(name, fallback) {
    var value = settings ? settings[name] : undefined
    return value === undefined || value === null || value === "" ? fallback : value
  }

  function intSetting(name, fallback, min, max) {
    var n = parseInt(String(setting(name, fallback)), 10)
    return Util.clamp(isFinite(n) ? n : fallback, min, max)
  }

  // Records whether `panel` is open; refreshes at once when the first opens.
  function setPanelOpen(panel, open) {
    var others = _openPanels.filter(function(p) { return p !== panel })
    var wasFast = fastRefresh
    _openPanels = open ? others.concat([panel]) : others
    if (fastRefresh && !wasFast) refresh()
  }

  // The core's command line with ARGS.
  function core(args) {
    return ["python3", "-I", cli].concat(args)
  }

  function refresh() {
    if (statusProcess.running) return
    var args = ["status", "--timeout", "20"]
    if (previewName !== "") {
      // The saved states in fixtures/ are written for the home folder /home/user.
      args = ["status", "--fixture", repoDir + "/fixtures/" + previewName + ".json", "--home", "/home/user"]
      if (_freshPreview) args.push("--fresh")
      _freshPreview = false
    }
    statusProcess.command = core(args)
    statusProcess.running = true
  }

  function applyStatus(raw) {
    var data
    try {
      data = JSON.parse(String(raw || ""))
    } catch (e) {
      lastError = "Unreadable MEGA status: " + e
      return
    }
    if (!data || data.ok === false) {
      lastError = String(data && data.error || "Could not read MEGA status")
      return
    }
    installed = data.installed !== false
    running = data.running !== false
    loggedIn = data.loggedIn === true
    email = String(data.email || "")
    kind = String(data.kind || "synced")
    kindText = String(data.kindText || "")
    badgeColour = String(data.badgeColour || "green")
    anyRunning = data.anyRunning === true
    usageText = String(data.usageText || "")
    storageLevel = Number(data.storageLevel || 0)
    transfersText = String(data.transfersText || "")
    syncs = data.syncs || []
    backups = data.backups || []
    lastError = String(data.error || "")
    loaded = true
    var notices = data.notices || []
    for (var i = 0; i < notices.length; i++) notify(notices[i])
  }

  // Shows the MEGA status as of the saved state `name` (see fixtures/), or
  // the live state again when `name` is empty.
  function preview(name) {
    previewName = String(name || "").replace(/[^A-Za-z0-9_-]/g, "")
    _freshPreview = previewName !== ""
    refresh()
  }

  // False, with a note in the panel, while a preview is shown: its syncs and
  // backups are saved examples, not the account's.
  function actionsAllowed() {
    if (previewName === "") return true
    actionStatus = "Preview: actions are off"
    actionStatusTimer.restart()
    return false
  }

  // Shows a notice from the core; clicking it opens the panel.
  function notify(notice) {
    var label = previewName !== "" ? " (preview)" : ""
    Quickshell.execDetached(["omarchy-notification-send", "--app-name", "MEGA", "-u", String(notice.urgency || "normal"),
                             "-g", Glyphs.NOTICE[notice.icon] || Glyphs.ICON_CLOUD, String(notice.title) + label,
                             Glyphs.escapeMarkup(notice.body), "--exec", "omarchy-shell", "yardquit.mega", "open"])
  }

  // Runs the core's actions one after another, then refreshes.
  function runActions(actions) {
    if (!actionsAllowed()) return
    _queue = _queue.concat(actions)
    if (!controlProcess.running) runNext()
  }

  function runNext() {
    if (_queue.length === 0) {
      settleTimer.restart()
      return
    }
    controlProcess.command = core(_queue[0])
    _queue = _queue.slice(1)
    controlProcess.running = true
  }

  function pauseSync(sync) { if (sync) runActions([["pause", sync.id]]) }
  function resumeSync(sync) { if (sync) runActions([["resume", sync.id]]) }
  function toggleSync(sync) { if (sync && sync.paused) resumeSync(sync); else pauseSync(sync) }
  // Pauses every sync while any is running, otherwise resumes them all.
  function toggleAll() { runActions([["toggle-all"]]) }
  function removeSync(sync) { if (sync) runActions([["remove-sync", sync.id]]) }
  function removeBackup(backup) { if (backup) runActions([["remove-backup", backup.tag]]) }

  // Opens a local folder in the file manager; only absolute paths, so a
  // value can never pass for an option or a network address.
  function openFolder(path) {
    var folder = String(path || "")
    if (folder.charAt(0) === "/" && actionsAllowed()) Quickshell.execDetached(["uwsm-app", "--", "nautilus", folder])
  }

  function openWeb() {
    Qt.openUrlExternally("https://mega.nz/fm")
  }

  // Opens a guided dialog from bin/ in Omarchy's floating terminal.
  function runGuided(script, args) {
    if (!actionsAllowed()) return
    Quickshell.execDetached(["omarchy-launch-floating-terminal-with-presentation",
                             [repoDir + "/bin/" + script].concat(args || []).map(Util.shellQuote).join(" ")])
    guidedRefresh.ticks = 0
    guidedRefresh.restart()
  }

  function login() { runGuided("mega-account-login") }
  function addSync() { runGuided("mega-add-sync", [syncFolder]) }
  function addBackup() { runGuided("mega-add-backup", [backupFolder]) }
  function editBackup(backup) { if (backup) runGuided("mega-edit-backup", [backup.tag, backup.period, backup.maxBackups]) }

  Timer {
    interval: root.fastRefresh ? 3000 : root.refreshIntervalSec * 1000
    repeat: true
    running: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  Timer {
    // MEGAcmd applies pause/resume asynchronously; poll a little afterwards.
    id: settleTimer
    interval: 1200
    onTriggered: root.refresh()
  }

  Timer {
    // A guided step runs in its own terminal; keep checking while it is open.
    id: guidedRefresh
    property int ticks: 0
    interval: 5000
    repeat: true
    onTriggered: {
      ticks += 1
      root.refresh()
      if (ticks >= 60) { ticks = 0; stop() }
    }
  }

  Timer {
    id: actionStatusTimer
    interval: 4000
    onTriggered: root.actionStatus = ""
  }

  Process {
    id: statusProcess
    stdout: StdioCollector { id: statusOut; waitForEnd: true }
    stderr: StdioCollector { id: statusErr; waitForEnd: true }
    onExited: function(exitCode) {
      if (exitCode === 0) root.applyStatus(statusOut.text)
      else root.lastError = String(statusErr.text || "Could not read MEGA status").trim()
    }
  }

  Process {
    id: controlProcess
    stdout: StdioCollector { id: controlOut; waitForEnd: true }
    stderr: StdioCollector { id: controlErr; waitForEnd: true }
    onExited: function(exitCode) {
      if (exitCode !== 0) {
        root.actionStatus = String(controlErr.text || "").trim() || "MEGA command failed"
        actionStatusTimer.restart()
      }
      root.runNext()
    }
  }
}
