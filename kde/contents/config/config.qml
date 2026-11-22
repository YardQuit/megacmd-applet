// config.qml: the MEGA Plasma widget's settings pages.
// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import org.kde.plasma.configuration

ConfigModel {
    ConfigCategory {
        name: i18n("General")
        icon: "cloudstatus"
        source: "ConfigGeneral.qml"
    }
}
