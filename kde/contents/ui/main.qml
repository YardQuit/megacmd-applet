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
// saved state from fixtures/ instead; actions do nothing then.
PlasmoidItem {
    id: root

    property var view: ({ kind: "off", kindText: i18n("Not logged in"), syncs: [], backups: [] })
    property string lastError: ""
    property string actionStatus: ""
    property bool freshPreview: true

    readonly property string coreDir: decodeURIComponent(String(Qt.resolvedUrl("../megacmd")).replace(/^file:\/\//, ""))
    readonly property string previewName: String(Plasmoid.configuration.previewName || "").replace(/[^A-Za-z0-9_-]/g, "")
    readonly property bool loggedIn: view.loggedIn === true

    // The Breeze status icon of each state the core names.
    readonly property var stateIcons: ({
        stopped: "state-offline", off: "state-offline", error: "state-error", warning: "state-warning",
        paused: "state-pause", syncing: "state-sync", synced: "state-ok"
    })

    Plasmoid.icon: "cloudstatus"
    Plasmoid.status: view.kind === "error" || view.kind === "warning" ? PlasmaCore.Types.NeedsAttentionStatus
                                                                     : PlasmaCore.Types.ActiveStatus
    toolTipMainText: i18n("MEGA")
    toolTipSubText: view.kindText || ""
    compactRepresentation: CompactRepresentation {}
    fullRepresentation: FullRepresentation {}

    onExpandedChanged: if (expanded) refresh()
    onPreviewNameChanged: { freshPreview = true; refresh() }

    // ARG quoted for the shell the executable engine runs commands in.
    function shellQuote(arg) {
        return "'" + String(arg).replace(/'/g, "'\\''") + "'"
    }

    // Runs the core's command line with ARGS; DONE(exitCode, stdout, stderr) follows.
    function core(args, done) {
        var command = ["python3", "-I", coreDir + "/bin/megacmd-applet"].concat(args).map(shellQuote).join(" ")
        runner.callbacks[command] = done
        runner.connectSource(command)
    }

    function refresh() {
        var args = ["status", "--timeout", "20"]
        if (previewName !== "") {
            // The saved states in fixtures/ are written for the home folder /home/user.
            args = ["status", "--fixture", coreDir + "/fixtures/" + previewName + ".json", "--home", "/home/user"]
            if (freshPreview) args.push("--fresh")
            freshPreview = false
        }
        core(args, function(exitCode, stdout, stderr) {
            if (exitCode !== 0) {
                lastError = stderr.trim() || i18n("Could not read MEGA status")
                return
            }
            applyStatus(stdout)
        })
    }

    function applyStatus(raw) {
        var data
        try {
            data = JSON.parse(raw)
        } catch (e) {
            lastError = i18n("Unreadable MEGA status")
            return
        }
        if (!data || data.ok === false) {
            lastError = String(data && data.error || i18n("Could not read MEGA status"))
            return
        }
        view = data
        lastError = String(data.error || "")
        var notices = data.notices || []
        for (var i = 0; i < notices.length; i++) notify(notices[i])
    }

    // Shows a notice from the core; activating it opens the popup.
    function notify(notice) {
        var label = previewName !== "" ? i18n(" (preview)") : ""
        noticeComponent.createObject(root, {
            title: String(notice.title) + label,
            text: String(notice.body),
            iconName: notice.icon === "cloud" ? "cloudstatus" : "state-error",
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

    // Runs a core action, then refreshes twice: MEGAcmd applies changes a little later.
    function act(args) {
        if (!actionsAllowed()) return
        core(args, function(exitCode, stdout, stderr) {
            if (exitCode !== 0) showActionStatus(stderr.trim() || i18n("MEGA command failed"))
            refresh()
            settleTimer.restart()
        })
    }

    function toggleSync(sync) { act([sync.paused ? "resume" : "pause", sync.id]) }
    function toggleAll() { act(["toggle-all"]) }
    function removeSync(sync) { act(["remove-sync", sync.id]) }
    function removeBackup(backup) { act(["remove-backup", backup.tag]) }

    // Opens a guided dialog in the configured terminal, then keeps checking
    // for a while, as it runs on its own.
    function guided(name, args) {
        if (!actionsAllowed()) return
        act(["guided", name].concat(args || []).concat(["--terminal", Plasmoid.configuration.terminal]))
        guidedRefresh.ticks = 0
        guidedRefresh.restart()
    }

    function login() { guided("mega-account-login") }
    function addSync() { guided("mega-add-sync", [Plasmoid.configuration.syncFolder]) }
    function addBackup() { guided("mega-add-backup", [Plasmoid.configuration.backupFolder]) }
    function editBackup(backup) { guided("mega-edit-backup", [backup.tag, backup.period, String(backup.maxBackups)]) }

    function openFolder(path) {
        if (String(path).charAt(0) === "/" && actionsAllowed()) Qt.openUrlExternally("file://" + encodeURI(path))
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
        id: settleTimer
        interval: 1200
        onTriggered: root.refresh()
    }

    Timer {
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
}
