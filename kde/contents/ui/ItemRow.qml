// ItemRow.qml: one sync folder or backup in the MEGA widget's popup.
// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

// A status icon, the folder pair and its second line, and buttons for the
// row's main action (`toggle`), opening its local folder and removing it.
// `remove` is signalled on every press of the remove button; `armed` shows
// that button asking for confirmation.
RowLayout {
    id: row

    property string iconName: ""
    property string title: ""
    property string meta: ""
    property string toggleIcon: ""
    property string toggleText: ""
    property bool armed: false

    signal toggle()
    signal open()
    signal remove()

    spacing: Kirigami.Units.smallSpacing

    Kirigami.Icon {
        source: row.iconName
        Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
        Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
        Layout.alignment: Qt.AlignVCenter
    }
    ColumnLayout {
        spacing: 0
        Layout.fillWidth: true
        PlasmaComponents3.Label {
            text: row.title
            textFormat: Text.PlainText
            Layout.fillWidth: true
            elide: Text.ElideMiddle
        }
        PlasmaComponents3.Label {
            text: row.meta
            textFormat: Text.PlainText
            opacity: 0.7
            font: Kirigami.Theme.smallFont
            Layout.fillWidth: true
            elide: Text.ElideRight
        }
    }
    PlasmaComponents3.ToolButton {
        icon.name: row.toggleIcon
        display: PlasmaComponents3.AbstractButton.IconOnly
        text: row.toggleText
        onClicked: row.toggle()
        PlasmaComponents3.ToolTip.text: text
        PlasmaComponents3.ToolTip.visible: hovered
    }
    PlasmaComponents3.ToolButton {
        icon.name: "folder-open"
        display: PlasmaComponents3.AbstractButton.IconOnly
        text: i18n("Open folder")
        onClicked: row.open()
        PlasmaComponents3.ToolTip.text: text
        PlasmaComponents3.ToolTip.visible: hovered
    }
    PlasmaComponents3.ToolButton {
        icon.name: row.armed ? "dialog-ok-apply" : "edit-delete"
        display: row.armed ? PlasmaComponents3.AbstractButton.TextBesideIcon : PlasmaComponents3.AbstractButton.IconOnly
        text: row.armed ? i18n("Remove?") : i18n("Remove (files stay)")
        onClicked: row.remove()
        PlasmaComponents3.ToolTip.text: text
        PlasmaComponents3.ToolTip.visible: hovered
    }
}
