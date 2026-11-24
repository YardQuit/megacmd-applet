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
// panels. Polling starts once a panel has handed over the widget's settings
// (see configure); it is quick while a panel is open on any screen (see
// setPanelOpen) and every `refreshIntervalSec` otherwise. Setting
// `previewName` to the name of a saved state in fixtures/ shows that state
// instead; actions do nothing while a preview is shown.
Item {
  id: root

  // The widget's settings, handed over by the panels through configure().
  property var settings: ({})
  property bool configured: false
  readonly property bool fastRefresh: _openPanels.length > 0
  property string previewName: ""

  // The core's view (see "megacmd-applet status"); until the first one
  // arrives the state is unknown, with nothing offered.
  property bool ok: false
  property bool loggedIn: false
  property string email: ""
  property string kind: "unknown"
  property string kindText: ""
  property string badgeColour: "orange"
  property string offer: ""
  property string offerText: ""
  property string offerHint: ""
  property bool anyRunning: false
  property string usageText: ""
  property int storageLevel: 0
  property string transfersText: ""
  property var syncs: []
  property var backups: []
  property var issues: []
  property string issuesMoreText: ""
  property string error: ""
  property string actionStatus: ""
  // True when the account and its syncs and backups can be shown.
  readonly property bool ready: ok && loggedIn

  // The repository: this file sits in its omarchy/ folder.
  readonly property string repoDir: decodeURIComponent(String(Qt.resolvedUrl("..")).replace(/^file:\/\//, "")).replace(/\/$/, "")
  readonly property string cli: repoDir + "/bin/megacmd-applet"
  readonly property int refreshIntervalSec: intSetting("refreshIntervalSec", 60, 10, 3600)
  readonly property string syncFolder: String(setting("syncFolder", "/"))
  readonly property string backupFolder: String(setting("backupFolder", "/Backups"))
  readonly property string megacmdDir: String(setting("megacmdDir", ""))
  readonly property bool busy: controlProcess.running

  // The terminal the core opens guided dialogs in: Omarchy's floating
  // terminal. That launcher joins its arguments into one line for bash, so
  // bash's printf quotes each argument the core hands over first.
  readonly property string guidedTerminal: "bash -c 'omarchy-launch-floating-terminal-with-presentation \"$(printf \"%q \" \"$@\")\"' guided"

  property var _queue: []
  property var _openPanels: []
  property bool _refreshPending: false
  property string _statusPreview: ""

  // The setting NAME, or FALLBACK when it is unset or empty.
  function setting(name, fallback) {
    var value = settings ? settings[name] : undefined
    return value === undefined || value === null || value === "" ? fallback : value
  }

  // The setting NAME as a whole number between MIN and MAX.
  function intSetting(name, fallback, min, max) {
    var n = parseInt(String(setting(name, fallback)), 10)
    return Util.clamp(isFinite(n) ? n : fallback, min, max)
  }

  // Takes the widget's SETTINGS from a panel; a refresh follows once they
  // have stopped changing, and the first one starts polling.
  function configure(newSettings) {
    settings = newSettings || ({})
    settingsSettle.restart()
  }

  // Records whether `panel` is open; refreshes at once when the first opens.
  function setPanelOpen(panel, open) {
    var others = _openPanels.filter(function(p) { return p !== panel })
    var wasFast = fastRefresh
    _openPanels = open ? others.concat([panel]) : others
    if (fastRefresh && !wasFast) refresh()
  }

  // The core's command line with ARGS, with the MEGAcmd folder set.
  function core(args) {
    return ["python3", "-I", cli].concat(megacmdDir !== "" ? ["--megacmd-dir=" + megacmdDir] : [], args)
  }

  // Asks the core for the current view; while a run is going, one more run
  // follows when it ends.
  function refresh() {
    if (statusProcess.running) {
      _refreshPending = true
      return
    }
    _refreshPending = false
    _statusPreview = previewName
    var args = ["status", "--timeout", "20"]
    if (previewName !== "") args = ["status", "--preview", previewName]
    statusProcess.command = core(args)
    statusProcess.running = true
  }

  // The view in the core's output TEXT, or null when it is not one.
  function parseView(text) {
    try {
      var data = JSON.parse(String(text || ""))
      return data && typeof data === "object" ? data : null
    } catch (e) {
      return null
    }
  }

  // Takes over the view DATA from the core and shows its notices.
  function applyView(data) {
    ok = data.ok === true
    loggedIn = data.loggedIn === true
    email = String(data.email || "")
    kind = String(data.kind || "unknown")
    kindText = String(data.kindText || "")
    badgeColour = String(data.badgeColour || "")
    offer = String(data.offer || "")
    offerText = String(data.offerText || "")
    offerHint = String(data.offerHint || "")
    anyRunning = data.anyRunning === true
    usageText = String(data.usageText || "")
    storageLevel = Number(data.storageLevel || 0)
    transfersText = String(data.transfersText || "")
    syncs = data.syncs || []
    backups = data.backups || []
    issues = data.issues || []
    issuesMoreText = String(data.issuesMoreText || "")
    error = String(data.error || "")
    var notices = data.notices || []
    for (var i = 0; i < notices.length; i++) notify(notices[i])
  }

  // Shows the state as unknown because the core could not run; TEXT says why.
  function applyFailure(text) {
    applyView({ ok: false, kind: "unknown", kindText: text, error: text, badgeColour: "orange" })
  }

  // Shows the MEGA status as of the saved state `name` (see fixtures/), or
  // the live state again when `name` is empty.
  function preview(name) {
    previewName = String(name || "")
    refresh()
  }

  // False, with a note in the panel, while a preview is shown: its syncs and
  // backups are saved examples, not the account's.
  function actionsAllowed() {
    if (previewName === "") return true
    showActionStatus("Preview: actions are off")
    return false
  }

  // Shows TEXT as the panel's action status for a few seconds.
  function showActionStatus(text) {
    actionStatus = text
    actionStatusTimer.restart()
  }

  // Shows a notice from the core; clicking it opens the panel. Omarchy shows
  // the title as plain text and the body as markup, so only the body is escaped.
  function notify(notice) {
    var title = String(notice.title || "")
    if (previewName !== "") title = "%1 (preview)".arg(title)
    Quickshell.execDetached(["omarchy-notification-send", "--app-name", "MEGA", "-u", String(notice.urgency || "normal"),
                             "-g", Glyphs.NOTICE[notice.icon] || Glyphs.ICON_CLOUD, title,
                             Glyphs.escapeMarkup(notice.body), "--exec", "omarchy-shell", "yardquit.mega", "open"])
  }

  // Runs the core's actions one after another, then refreshes.
  function runActions(actions) {
    if (!actionsAllowed()) return
    _queue = _queue.concat(actions)
    if (!controlProcess.running) runNext()
  }

  // Starts the next queued action, or refreshes when none is left.
  function runNext() {
    if (_queue.length === 0) {
      refresh()
      settleTimer.restart()
      return
    }
    controlProcess.command = core(_queue[0])
    _queue = _queue.slice(1)
    controlProcess.running = true
  }

  // Pauses SYNC.
  function pauseSync(sync) { if (sync) runActions([["pause", sync.id]]) }
  // Resumes SYNC.
  function resumeSync(sync) { if (sync) runActions([["resume", sync.id]]) }
  // Resumes SYNC when it is paused, otherwise pauses it.
  function toggleSync(sync) { if (sync && sync.paused) resumeSync(sync); else pauseSync(sync) }
  // Pauses every sync while any is running, otherwise resumes them all.
  function toggleAll() { runActions([["toggle-all"]]) }
  // Stops SYNC; its files stay where they are.
  function removeSync(sync) { if (sync) runActions([["remove-sync", sync.id]]) }
  // Stops BACKUP; the copies made so far stay in MEGA.
  function removeBackup(backup) { if (backup) runActions([["remove-backup", backup.tag]]) }
  // Runs the core command line ARGS that a button of a sync issue names.
  function runIssueAction(args) { if (args && args.length > 0) runActions([args.map(String)]) }
  // Opens the local folder PATH in the file manager.
  function openFolder(path) { if (path) runActions([["open-folder", String(path)]]) }

  // Opens MEGA's web app in the browser.
  function openWeb() {
    Quickshell.execDetached(["omarchy-launch-browser", "https://mega.nz/fm"])
  }

  // Opens the guided dialog NAME from bin/ with ARGS in Omarchy's floating
  // terminal, and keeps refreshing while it may be open.
  function runGuided(name, args) {
    if (!actionsAllowed()) return
    runActions([["guided", "--terminal=" + guidedTerminal, name, "--"].concat(args || [])])
    guidedRefresh.ticks = 0
    guidedRefresh.restart()
  }

  // Opens the dialog the view's offer names: log in, or start MEGAcmd.
  function login() { runGuided("mega-account-login") }
  // Opens the dialog that adds a sync.
  function addSync() { runGuided("mega-add-sync", [syncFolder]) }
  // Opens the dialog that adds a backup.
  function addBackup() { runGuided("mega-add-backup", [backupFolder]) }
  // Opens the dialog that changes BACKUP's schedule and number of copies kept.
  function editBackup(backup) {
    if (backup) runGuided("mega-edit-backup", [String(backup.tag), String(backup.period ?? ""), String(backup.maxBackups ?? "")])
  }

  Timer {
    interval: root.fastRefresh ? 3000 : root.refreshIntervalSec * 1000
    repeat: true
    running: root.configured
    onTriggered: root.refresh()
  }

  Timer {
    // Settings arrive from the panels one after another and change as they are
    // typed; refresh once they have settled.
    id: settingsSettle
    interval: 500
    onTriggered: {
      root.configured = true
      root.refresh()
    }
  }

  Timer {
    // MEGAcmd applies pause/resume asynchronously; check again a little later.
    id: settleTimer
    interval: 2000
    onTriggered: root.refresh()
  }

  Timer {
    // A guided dialog runs in its own terminal; keep checking while it is open.
    id: guidedRefresh
    property int ticks: 0
    interval: 5000
    repeat: true
    onTriggered: {
      ticks += 1
      root.refresh()
      if (ticks >= 60) stop()
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
      var view = exitCode === 0 ? root.parseView(statusOut.text) : null
      if (root._statusPreview !== root.previewName) root._refreshPending = true
      else if (view) root.applyView(view)
      else root.applyFailure(String(statusErr.text || "").trim() || "Could not run the MEGA status check")
      if (root._refreshPending) Qt.callLater(root.refresh)
    }
  }

  Process {
    id: controlProcess
    stdout: StdioCollector { id: controlOut; waitForEnd: true }
    stderr: StdioCollector { id: controlErr; waitForEnd: true }
    onExited: function(exitCode) {
      if (exitCode !== 0) root.showActionStatus(String(controlErr.text || "").trim() || "MEGA command failed")
      root.runNext()
    }
  }
}
