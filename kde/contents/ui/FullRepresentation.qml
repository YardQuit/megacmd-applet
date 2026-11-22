// FullRepresentation.qml: the MEGA widget's popup.
// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.extras as PlasmaExtras
import org.kde.kirigami as Kirigami

// The overall state with a switch that pauses or resumes all syncing, the
// account's storage and transfers, the sync folders and backups with their
// buttons, and the actions to add more. Otherwise the state and, when the
// core offers one, a button that logs in or starts MEGAcmd.
PlasmaExtras.Representation {
    id: full

    Layout.minimumWidth: Kirigami.Units.gridUnit * 24
    Layout.preferredWidth: Kirigami.Units.gridUnit * 24
    Layout.minimumHeight: Kirigami.Units.gridUnit * 26
    collapseMarginsHint: true

    header: PlasmaExtras.PlasmoidHeading {
        RowLayout {
            anchors.fill: parent

            Kirigami.Icon {
                source: root.stateIcons[root.view.kind] || "state-information"
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
                    text: root.view.kindText || ""
                    textFormat: Text.PlainText
                    opacity: 0.7
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
            }
            PlasmaComponents3.Switch {
                visible: root.showAccount && root.view.syncs.length > 0
                checked: root.view.anyRunning === true
                text: i18n("Syncing")
                onToggled: {
                    root.toggleAll()
                    // Pressing the switch replaces the binding; the core's state decides.
                    checked = Qt.binding(() => root.view.anyRunning === true)
                }
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
        contentWidth: availableWidth

        ColumnLayout {
            id: content
            width: scroll.availableWidth - 2 * Kirigami.Units.largeSpacing
            x: Kirigami.Units.largeSpacing
            spacing: Kirigami.Units.smallSpacing

            PlasmaExtras.PlaceholderMessage {
                visible: !root.showAccount && root.view.offer !== ""
                Layout.fillWidth: true
                iconName: root.stateIcons[root.view.kind] || "state-information"
                text: root.view.offerText || ""
                explanation: root.view.offerHint || ""
                helpfulAction: Kirigami.Action {
                    icon.name: "network-connect"
                    text: root.view.offerText || ""
                    onTriggered: root.login()
                }
            }
            // The state in full when there is nothing to offer, e.g. why it
            // could not be read.
            PlasmaComponents3.Label {
                visible: !root.showAccount && root.view.offer === "" && text !== ""
                text: root.view.kindText || ""
                textFormat: Text.PlainText
                Layout.fillWidth: true
                wrapMode: Text.Wrap
            }

            PlasmaComponents3.Label {
                visible: root.showAccount
                text: root.view.email || ""
                textFormat: Text.PlainText
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
            PlasmaComponents3.Label {
                visible: root.showAccount && text !== ""
                text: root.view.usageText ? i18n("Stored: %1", root.view.usageText) : ""
                textFormat: Text.PlainText
                color: root.view.storageLevel > 0 ? Kirigami.Theme.neutralTextColor : Kirigami.Theme.textColor
                Layout.fillWidth: true
            }
            PlasmaComponents3.Label {
                visible: root.showAccount && text !== ""
                text: root.view.transfersText || ""
                textFormat: Text.PlainText
                opacity: 0.7
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }

            Kirigami.Heading {
                visible: root.showAccount
                level: 4
                text: i18n("Sync folders")
                Layout.topMargin: Kirigami.Units.largeSpacing
            }
            Repeater {
                model: root.showAccount ? root.view.syncs : []
                ItemRow {
                    required property var modelData
                    Layout.fillWidth: true
                    armed: modelData.key === root.armedKey
                    iconName: root.stateIcons[modelData.kind] || "state-information"
                    title: modelData.title
                    meta: modelData.meta
                    toggleIcon: modelData.paused ? "media-playback-start" : "media-playback-pause"
                    toggleText: modelData.paused ? i18n("Resume") : i18n("Pause")
                    onToggle: root.toggleSync(modelData)
                    onOpen: root.openFolder(modelData.local)
                    onRemove: root.removeSync(modelData)
                }
            }
            PlasmaComponents3.Button {
                visible: root.showAccount
                icon.name: "list-add"
                text: i18n("Add sync…")
                onClicked: root.addSync()
            }

            Kirigami.Heading {
                visible: root.showAccount
                level: 4
                text: i18n("Backups")
                Layout.topMargin: Kirigami.Units.largeSpacing
            }
            Repeater {
                model: root.showAccount ? root.view.backups : []
                ItemRow {
                    required property var modelData
                    Layout.fillWidth: true
                    armed: modelData.key === root.armedKey
                    iconName: root.stateIcons[modelData.kind] || "backup"
                    title: modelData.title
                    meta: modelData.meta
                    toggleIcon: "configure"
                    toggleText: i18n("Change schedule and versions")
                    onToggle: root.editBackup(modelData)
                    onOpen: root.openFolder(modelData.local)
                    onRemove: root.removeBackup(modelData)
                }
            }
            PlasmaComponents3.Button {
                visible: root.showAccount
                icon.name: "list-add"
                text: i18n("Add backup…")
                onClicked: root.addBackup()
            }

            PlasmaComponents3.Button {
                visible: root.showAccount
                icon.name: "internet-services"
                text: i18n("Open MEGA in the browser")
                onClicked: root.openWeb()
                Layout.topMargin: Kirigami.Units.largeSpacing
            }

            PlasmaComponents3.Label {
                visible: text !== ""
                text: root.actionStatus !== "" ? root.actionStatus : (root.view.ok === true ? root.view.error || "" : "")
                textFormat: Text.PlainText
                color: Kirigami.Theme.neutralTextColor
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }
        }
    }
}
