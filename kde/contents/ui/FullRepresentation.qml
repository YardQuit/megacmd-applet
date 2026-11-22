// FullRepresentation.qml: the MEGA widget's popup.
// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.extras as PlasmaExtras
import org.kde.kirigami as Kirigami

// The overall state with a switch that pauses or resumes all syncing, the
// account's storage and transfers, the sync folders and backups with their
// buttons, and the actions to add more. When logged out it offers to log in
// (or to start MEGAcmd).
PlasmaExtras.Representation {
    id: full

    Layout.minimumWidth: Kirigami.Units.gridUnit * 24
    Layout.minimumHeight: Kirigami.Units.gridUnit * 26
    collapseMarginsHint: true

    header: PlasmaExtras.PlasmoidHeading {
        RowLayout {
            anchors.fill: parent

            Kirigami.Icon {
                source: root.stateIcons[root.view.kind] || "state-ok"
                Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                Layout.preferredHeight: Kirigami.Units.iconSizes.medium
            }
            ColumnLayout {
                spacing: 0
                Layout.fillWidth: true
                Kirigami.Heading {
                    level: 3
                    text: i18n("MEGA")
                }
                PlasmaComponents3.Label {
                    text: root.view.installed === false ? i18n("MEGAcmd is not installed") : (root.view.kindText || "")
                    opacity: 0.7
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
            }
            PlasmaComponents3.Switch {
                visible: root.loggedIn && root.view.syncs.length > 0
                checked: root.view.anyRunning === true
                text: i18n("Syncing")
                onToggled: root.toggleAll()
            }
            PlasmaComponents3.ToolButton {
                icon.name: "view-refresh"
                display: PlasmaComponents3.AbstractButton.IconOnly
                text: i18n("Refresh")
                onClicked: root.refresh()
                PlasmaComponents3.ToolTip.text: text
                PlasmaComponents3.ToolTip.visible: hovered
            }
        }
    }

    PlasmaComponents3.ScrollView {
        id: scroll
        anchors.fill: parent
        PlasmaComponents3.ScrollBar.horizontal.policy: PlasmaComponents3.ScrollBar.AlwaysOff

        ColumnLayout {
            id: content
            width: scroll.availableWidth - 2 * Kirigami.Units.largeSpacing
            x: Kirigami.Units.largeSpacing
            spacing: Kirigami.Units.smallSpacing

            PlasmaExtras.PlaceholderMessage {
                visible: !root.loggedIn
                Layout.fillWidth: true
                iconName: "state-offline"
                text: root.view.running === false ? i18n("MEGAcmd is not running") : i18n("Not logged in")
                explanation: root.view.running === false
                             ? i18n("Starts the engine in a terminal; logs in too if needed.")
                             : i18n("Opens a terminal for your email, password and 2FA code.")
                helpfulAction: Kirigami.Action {
                    icon.name: "network-connect"
                    text: root.view.running === false ? i18n("Start MEGAcmd") : i18n("Log in to MEGA")
                    onTriggered: root.login()
                }
            }

            PlasmaComponents3.Label {
                visible: root.loggedIn
                text: root.view.email || ""
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
            PlasmaComponents3.Label {
                visible: root.loggedIn && text !== ""
                text: root.view.usageText ? i18n("Stored: %1", root.view.usageText) : ""
                color: root.view.storageLevel > 0 ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                Layout.fillWidth: true
            }
            PlasmaComponents3.Label {
                visible: root.loggedIn && text !== ""
                text: root.view.transfersText || ""
                opacity: 0.7
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }

            Kirigami.Heading {
                visible: root.loggedIn
                level: 4
                text: i18n("Sync folders")
                Layout.topMargin: Kirigami.Units.largeSpacing
            }
            Repeater {
                model: root.loggedIn ? root.view.syncs : []
                ItemRow {
                    required property var modelData
                    Layout.fillWidth: true
                    itemKey: modelData.key
                    iconName: root.stateIcons[modelData.kind] || "state-ok"
                    title: modelData.localDisplay + "  ↔  " + modelData.remote
                    meta: modelData.meta
                    toggleIcon: modelData.paused ? "media-playback-start" : "media-playback-pause"
                    toggleText: modelData.paused ? i18n("Resume") : i18n("Pause")
                    onToggle: root.toggleSync(modelData)
                    onOpen: root.openFolder(modelData.local)
                    onRemove: root.removeSync(modelData)
                }
            }
            PlasmaComponents3.Button {
                visible: root.loggedIn
                icon.name: "list-add"
                text: i18n("Add sync…")
                onClicked: root.addSync()
            }

            Kirigami.Heading {
                visible: root.loggedIn
                level: 4
                text: i18n("Backups")
                Layout.topMargin: Kirigami.Units.largeSpacing
            }
            Repeater {
                model: root.loggedIn ? root.view.backups : []
                ItemRow {
                    required property var modelData
                    Layout.fillWidth: true
                    itemKey: modelData.key
                    iconName: modelData.failed ? "state-error" : (modelData.lastStatus ? "state-ok" : "backup")
                    title: modelData.localDisplay + "  →  " + modelData.remote
                    meta: modelData.meta
                    toggleIcon: "configure"
                    toggleText: i18n("Change schedule and versions")
                    onToggle: root.editBackup(modelData)
                    onOpen: root.openFolder(modelData.local)
                    onRemove: root.removeBackup(modelData)
                }
            }
            PlasmaComponents3.Button {
                visible: root.loggedIn
                icon.name: "list-add"
                text: i18n("Add backup…")
                onClicked: root.addBackup()
            }

            PlasmaComponents3.Button {
                visible: root.loggedIn
                icon.name: "internet-services"
                text: i18n("Open MEGA in the browser")
                onClicked: root.openWeb()
                Layout.topMargin: Kirigami.Units.largeSpacing
            }

            PlasmaComponents3.Label {
                visible: text !== ""
                text: root.actionStatus !== "" ? root.actionStatus : root.lastError
                color: Kirigami.Theme.negativeTextColor
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }
        }
    }
}
