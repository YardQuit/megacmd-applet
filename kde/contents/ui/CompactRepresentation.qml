// CompactRepresentation.qml: the MEGA widget's panel icon.
// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import org.kde.plasma.plasmoid
import org.kde.kirigami as Kirigami

// A cloud with the overall state's status icon in its lower-right corner.
// Left click opens the popup, middle click refreshes.
MouseArea {
    id: compact

    acceptedButtons: Qt.LeftButton | Qt.MiddleButton
    hoverEnabled: true
    onClicked: function(mouse) {
        if (mouse.button === Qt.MiddleButton) root.refresh()
        else root.expanded = !root.expanded
    }

    Kirigami.Icon {
        id: cloud
        anchors.fill: parent
        source: "cloudstatus"
        active: compact.containsMouse
    }

    Kirigami.Icon {
        width: Math.round(cloud.width * 0.55)
        height: width
        anchors.right: cloud.right
        anchors.bottom: cloud.bottom
        source: root.stateIcons[root.view.kind] || "state-ok"
    }
}
