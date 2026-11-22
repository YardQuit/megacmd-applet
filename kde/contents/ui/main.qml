// main.qml: the MEGA Plasma widget: MEGAcmd's state and actions in the panel.
// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as P5Support
import org.kde.notification

// Polls the shared core (megacmd/bin/megacmd-applet status, bundled in the
// package) for the account, syncs, backups and what they mean, shows the
// notifications the core hands it, and runs the core's actions for the
// popup. Refreshes every 3 seconds while the popup is open and every
// `refreshIntervalSec` otherwise. The hidden setting `previewName` shows a
// saved state instead; actions are refused then.
PlasmoidItem {
    id: root

    // Shown until the first status arrives: nothing known yet, nothing offered.
    property var view: ({ ok: false, kind: "unknown", kindText: "", offer: "", syncs: [], backups: [] })
    property string shownJson: ""
    property string actionStatus: ""
    property string armedKey: ""
    property bool statusRunning: false
    property bool statusPending: false

    readonly property string coreDir: decodeURIComponent(String(Qt.resolvedUrl("../megacmd")).replace(/^file:\/\//, ""))
    readonly property string previewName: String(Plasmoid.configuration.previewName || "")
    readonly property bool showAccount: view.ok === true && view.loggedIn === true

    // The Breeze status icon of each state the core names, for the overall
    // state and the rows.
    readonly property var stateIcons: ({
        missing: "state-warning", unknown: "state-information",
        stopped: "state-offline", off: "state-offline", error: "state-error", warning: "state-warning",
        paused: "state-pause", syncing: "state-sync", synced: "state-ok", pending: "backup"
    })

    // The icon of each notice icon the core names.
    readonly property var noticeIcons: ({ error: "state-error", off: "state-offline", cloud: "cloudstatus" })

    Plasmoid.icon: "cloudstatus"
    Plasmoid.status: ["error", "warning", "missing"].indexOf(view.kind) >= 0 ? PlasmaCore.Types.NeedsAttentionStatus
                                                                             : PlasmaCore.Types.ActiveStatus
    toolTipMainText: i18n("MEGA")
    toolTipSubText: view.kindText || ""
    toolTipTextFormat: Text.PlainText
    compactRepresentation: CompactRepresentation {}
    fullRepresentation: FullRepresentation {}

    onExpandedChanged: if (expanded) refresh()

    Connections {
        target: Plasmoid.configuration
        function onMegacmdDirChanged() { settingsTimer.restart() }
        function onPreviewNameChanged() { settingsTimer.restart() }
        function onRefreshIntervalSecChanged() { settingsTimer.restart() }
    }

    // ARG quoted for the shell the executable engine runs commands in.
    function shellQuote(arg) {
        return "'" + String(arg).replace(/'/g, "'\\''") + "'"
    }

    // TEXT escaped, so the notification server shows it as plain text.
    function plainText(text) {
        return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    }

    // Runs the core's command line with ARGS; DONE(exitCode, stdout, stderr) follows.
    function core(args, done) {
        var dir = Plasmoid.configuration.megacmdDir
        var folder = dir ? ["--megacmd-dir=" + dir] : []
        var command = ["python3", "-I", coreDir + "/bin/megacmd-applet"].concat(folder, args).map(shellQuote).join(" ")
        runner.callbacks[command] = done
        runner.connectSource(command)
    }

    // The view shown when the core itself could not run or printed no view.
    function failedView(text) {
        return { ok: false, kind: "unknown", kindText: text, badgeColour: "orange", offer: "", syncs: [], backups: [] }
    }

    // The view from a finished status run, or a failed view when there is none.
    function readView(exitCode, stdout, stderr) {
        if (exitCode !== 0) return failedView(stderr.trim() || i18n("Could not read MEGA status"))
        try {
            return JSON.parse(stdout)
        } catch (e) {
            return failedView(i18n("Unreadable MEGA status"))
        }
    }

    // Reads the state from the core and shows it. One run at a time: a
    // refresh asked for meanwhile runs once when it ends, and a result for
    // a preview setting no longer in effect is not shown, though its
    // notices are.
    function refresh() {
        if (statusRunning) {
            statusPending = true
            return
        }
        statusRunning = true
        var preview = previewName
        var args = ["status", "--timeout", "20"]
        if (preview !== "") args.push("--preview=" + preview)
        core(args, function(exitCode, stdout, stderr) {
            statusRunning = false
            var data = readView(exitCode, stdout, stderr)
            var notices = data.notices || []
            delete data.notices
            if (preview === previewName) showView(data)
            for (var i = 0; i < notices.length; i++) notify(notices[i], preview !== "")
            if (statusPending) {
                statusPending = false
                refresh()
            }
        })
    }

    // Replaces the view only when it changed, so the popup is not rebuilt
    // on every refresh.
    function showView(data) {
        var json = JSON.stringify(data)
        if (json === shownJson) return
        shownJson = json
        view = data
    }

    // Shows a notice from the core; activating it opens the popup.
    function notify(notice, preview) {
        var title = String(notice.title)
        noticeComponent.createObject(root, {
            title: preview ? i18n("%1 (preview)", title) : title,
            text: plainText(String(notice.body)),
            iconName: noticeIcons[notice.icon] || noticeIcons.error,
            urgency: notice.urgency === "critical" ? Notification.HighUrgency : Notification.NormalUrgency
        }).sendEvent()
    }

    // False, with a note in the popup, while a preview is shown.
    function actionsAllowed() {
        if (previewName === "") return true
        showActionStatus(i18n("Preview: actions are off"))
        return false
    }

    function showActionStatus(text) {
        actionStatus = text
        actionStatusTimer.restart()
    }

    // Runs a core action unless a preview is shown.
    function act(args) {
        if (actionsAllowed()) run(args, true)
    }

    // Runs a core action and shows why it failed. SETTLE refreshes at once
    // and again a little later, as MEGAcmd applies changes after a moment.
    function run(args, settle) {
        core(args, function(exitCode, stdout, stderr) {
            if (exitCode !== 0) showActionStatus(stderr.trim() || i18n("MEGA command failed"))
            if (settle) {
                refresh()
                settleTimer.restart()
            }
        })
    }

    function toggleSync(sync) { act([sync.paused ? "resume" : "pause", "--", sync.id]) }
    function toggleAll() { act(["toggle-all"]) }
    function removeSync(sync) { confirmRemove(sync.key, ["remove-sync", "--", sync.id]) }
    function removeBackup(backup) { confirmRemove(backup.key, ["remove-backup", "--", backup.tag]) }

    // The first press arms the item KEY's remove button for a few seconds;
    // a second press while armed runs the core action ARGS.
    function confirmRemove(key, args) {
        if (armedKey === key) {
            disarm()
            act(args)
        } else {
            armedKey = key
            armTimer.restart()
        }
    }

    function disarm() {
        armTimer.stop()
        armedKey = ""
    }

    // Opens a guided dialog in a terminal, then keeps checking for a while,
    // as it runs on its own.
    function guided(name, args) {
        if (!actionsAllowed()) return
        var terminal = Plasmoid.configuration.terminal
        run(["guided"].concat(terminal ? ["--terminal=" + terminal] : [], [name, "--"], args || []), true)
        guidedRefresh.checks = 0
        guidedRefresh.restart()
    }

    function login() { guided("mega-account-login") }
    function addSync() { guided("mega-add-sync", [Plasmoid.configuration.syncFolder]) }
    function addBackup() { guided("mega-add-backup", [Plasmoid.configuration.backupFolder]) }
    function editBackup(backup) {
        guided("mega-edit-backup", [backup.tag, backup.period, backup.maxBackups ? String(backup.maxBackups) : ""])
    }

    function openFolder(path) {
        if (actionsAllowed()) run(["open-folder", path], false)
    }

    function openWeb() { Qt.openUrlExternally("https://mega.nz/fm") }

    P5Support.DataSource {
        id: runner
        engine: "executable"
        property var callbacks: ({})
        onNewData: function(source, data) {
            var done = callbacks[source]
            delete callbacks[source]
            disconnectSource(source)
            if (done) done(data["exit code"], String(data.stdout || ""), String(data.stderr || ""))
        }
    }

    Component {
        id: noticeComponent
        Notification {
            componentName: "plasma_workspace"
            eventId: "notification"
            autoDelete: true
            defaultAction: NotificationAction {
                label: i18n("Open")
                onActivated: root.expanded = true
            }
        }
    }

    Timer {
        interval: root.expanded ? 3000 : Math.max(10, Plasmoid.configuration.refreshIntervalSec) * 1000
        repeat: true
        running: true
        triggeredOnStart: true
        onTriggered: root.refresh()
    }

    Timer {
        id: settingsTimer
        interval: 1000
        onTriggered: root.refresh()
    }

    Timer {
        id: settleTimer
        interval: 2000
        onTriggered: root.refresh()
    }

    Timer {
        id: armTimer
        interval: 4000
        onTriggered: root.armedKey = ""
    }

    Timer {
        id: guidedRefresh
        property int checks: 0
        interval: 5000
        repeat: true
        onTriggered: {
            checks += 1
            root.refresh()
            if (checks >= 60) stop()
        }
    }

    Timer {
        id: actionStatusTimer
        interval: 4000
        onTriggered: root.actionStatus = ""
    }
}
