// Panel.qml: MEGA bar widget with sync and backup panel.
// SPDX-License-Identifier: GPL-3.0-or-later
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qs.Commons
import qs.Ui
import "Glyphs.js" as Glyphs

// Bar icon showing MEGAcmd's overall state, and a keyboard-navigable panel to
// pause, resume, add and remove syncs and backups. Left click opens the
// panel, right click pauses or resumes all syncing, middle click refreshes.
// In the panel, Enter or Space runs a row's main action; "o" opens its
// folder, "s" opens a backup's settings, Delete or "x" twice removes it, "p"
// pauses or resumes all syncing, "r" refreshes.
//
// Every bar's panel shows the one shared state of the plugin's service
// (Service.qml), which the shell loads once.
//
// IPC target "yardquit.mega": open, close, show, hide, toggle, refresh,
// status, and preview NAME / live to show a saved state from fixtures/.
Panel {
  id: root
  moduleName: "yardquit.mega"
  ipcTarget: "yardquit.mega"
  manageIpc: false

  property bool cursorActive: false
  property int cursorIndex: 0
  property string pendingRemove: ""

  // The plugin's service, or `offline` until the shell has loaded it.
  property var mega: offline

  // The panel's scrolling area, null until the panel first opens.
  readonly property Item panelFlick: panel.loadedContent ? panel.loadedContent.panelFlick : null

  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property string kind: mega.kind
  // Theme colours by name, for the state badges the shared core names.
  readonly property var stateColors: ({
    red: themeColors.red, orange: themeColors.orange, yellow: themeColors.yellow,
    blue: themeColors.blue, green: themeColors.green
  })
  readonly property color badgeColor: stateColors[mega.badgeColour] || foreground
  readonly property color panelBackground: Color.popups.background

  // Keyboard targets in display order: "header" (while there are syncs to
  // pause), "sync:N", "addSync", "backup:N", "addBackup", "web"; or "login"
  // when the view offers to log in or start MEGAcmd.
  readonly property var targets: {
    if (!mega.ready) return mega.offer !== "" ? ["login"] : []
    var list = mega.syncs.length > 0 ? ["header"] : []
    for (var i = 0; i < mega.syncs.length; i++) list.push("sync:" + i)
    list.push("addSync")
    for (var j = 0; j < mega.backups.length; j++) list.push("backup:" + j)
    list.push("addBackup", "web")
    return list
  }
  readonly property string cursorTarget: targets.length > 0 ? targets[Math.max(0, Math.min(cursorIndex, targets.length - 1))] : ""

  // True when the keyboard cursor is on TARGET.
  function hasCursor(target) {
    return cursorActive && cursorTarget === target
  }

  // Puts the keyboard cursor on TARGET, as when the mouse enters its row.
  function setCursor(target) {
    var index = targets.indexOf(target)
    if (index < 0) return
    cursorActive = true
    cursorIndex = index
  }

  // Moves the keyboard cursor DY rows and scrolls its row into view.
  function moveCursor(dy) {
    cursorActive = true
    cursorIndex = Math.max(0, Math.min(targets.length - 1, cursorIndex + dy))
    scrollItemIntoView(rowFor(cursorTarget, panelFlick ? panelFlick.contentItem : null))
  }

  // The visible row under ITEM whose target is TARGET, or null.
  function rowFor(target, item) {
    if (!item || !item.visible) return null
    if (item.target === target) return item
    for (var i = 0; i < item.children.length; i++) {
      var found = rowFor(target, item.children[i])
      if (found) return found
    }
    return null
  }

  // Scrolls the panel so that ITEM is fully shown.
  function scrollItemIntoView(item) {
    if (!panelFlick || !item) return
    Qt.callLater(function() {
      if (!item || !panelFlick) return
      var margin = Style.space(6)
      var top = item.mapToItem(panelFlick.contentItem, 0, 0).y
      var bottom = top + item.height
      var maxY = Math.max(0, panelFlick.contentHeight - panelFlick.height)
      if (top < panelFlick.contentY + margin) panelFlick.contentY = Math.max(0, top - margin)
      else if (bottom > panelFlick.contentY + panelFlick.height - margin) panelFlick.contentY = Math.min(maxY, bottom + margin - panelFlick.height)
    })
  }

  // The sync or backup TARGET names, or null for other rows.
  function itemFor(target) {
    var parts = String(target).split(":")
    if (parts[0] === "sync") return mega.syncs[Number(parts[1])]
    if (parts[0] === "backup") return mega.backups[Number(parts[1])]
    return null
  }

  // Runs the main action of the row TARGET names.
  function activate(target) {
    var parts = String(target).split(":")
    if (target === "login") mega.login()
    else if (target === "header") mega.toggleAll()
    else if (parts[0] === "sync") mega.toggleSync(itemFor(target))
    else if (parts[0] === "backup") editTarget(target)
    else if (target === "addSync") mega.addSync()
    else if (target === "addBackup") mega.addBackup()
    else if (target === "web") mega.openWeb()
  }

  // Opens the schedule and versions of the backup `target` names.
  function editTarget(target) {
    if (String(target).indexOf("backup:") === 0) mega.editBackup(itemFor(target))
  }

  // Opens the local folder of the sync or backup TARGET names.
  function openTarget(target) {
    var item = itemFor(target)
    if (item) mega.openFolder(item.local)
  }

  // Removing asks twice: the first request arms it, the second removes. The
  // sync or backup is armed by its key, so a list that changed between the
  // two requests arms the row's new item instead of removing it.
  function requestRemove(target) {
    var item = itemFor(target)
    var key = item ? item.key : ""
    if (key === "") return
    if (pendingRemove !== key) {
      pendingRemove = key
      removeDisarm.restart()
      return
    }
    pendingRemove = ""
    removeDisarm.stop()
    if (String(target).indexOf("sync:") === 0) mega.removeSync(item)
    else mega.removeBackup(item)
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onOpenedChanged: {
    if (opened && mega === offline) findService()
    mega.setPanelOpen(root, opened)
    if (!opened) return
    cursorActive = false
    cursorIndex = 0
    pendingRemove = ""
    if (panelFlick) panelFlick.contentY = 0
    Qt.callLater(function() { if (panel.loadedContent) panel.loadedContent.forceActiveFocus() })
  }
  onSettingsChanged: mega.configure(settings)
  Component.onCompleted: findService()
  Component.onDestruction: mega.setPanelOpen(root, false)

  // Looks up the plugin's service and hands it this widget's settings; until
  // the shell has loaded it, `serviceRetry` keeps looking, less and less often.
  function findService() {
    var service = bar && bar.shell ? bar.shell.serviceFor("yardquit.mega") : null
    if (!service) {
      serviceRetry.start()
      return
    }
    serviceRetry.stop()
    mega = service
    mega.configure(settings)
    if (opened) mega.setPanelOpen(root, true)
  }

  Timer {
    id: serviceRetry
    interval: 1000
    repeat: true
    onTriggered: {
      interval = Math.min(interval * 2, 60000)
      root.findService()
    }
  }

  // Stands in for the service until it is loaded: shows that, and does nothing.
  QtObject {
    id: offline
    readonly property bool ready: false
    readonly property string email: ""
    readonly property var syncs: []
    readonly property var backups: []
    readonly property string usageText: ""
    readonly property int storageLevel: 0
    readonly property string transfersText: ""
    readonly property bool ok: false
    readonly property string error: ""
    readonly property string actionStatus: ""
    readonly property string kind: "unknown"
    readonly property string kindText: "MEGA service not loaded"
    readonly property string badgeColour: "orange"
    readonly property string offer: ""
    readonly property string offerText: ""
    readonly property string offerHint: ""
    readonly property bool anyRunning: false
    readonly property bool busy: false
    function configure(settings) {}
    function setPanelOpen(panel, open) {}
    function refresh() {}
    function preview(name) {}
    function toggleAll() {}
    function toggleSync(sync) {}
    function removeSync(sync) {}
    function removeBackup(backup) {}
    function editBackup(backup) {}
    function addSync() {}
    function addBackup() {}
    function login() {}
    function openFolder(path) {}
    function openWeb() {}
  }

  ShellIpc {
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): string { mega.refresh(); return "ok" }
    function status(): string { return mega.kindText }
    function preview(name: string): string { mega.preview(name); return "preview " + name }
    function live(): string { mega.preview(""); return "live" }
  }

  Timer {
    id: removeDisarm
    interval: 4000
    onTriggered: root.pendingRemove = ""
  }

  ThemePalette { id: themeColors }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    // The cloud is the button's own glyph, so the bar sizes it like its other
    // icons; the badge sits on top and takes no part in that sizing.
    text: Glyphs.ICON_CLOUD
    tooltipText: mega.kindText !== "" ? "MEGA: " + mega.kindText : "MEGA"
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.RightButton) mega.toggleAll()
      else if (buttonCode === Qt.MiddleButton) mega.refresh()
      else root.toggle()
    }
  }

  StateBadge {
    width: Math.round(button.glyphPaintedHeight * 0.75)
    x: (button.width + button.glyphPaintedWidth) / 2 - width * 0.55
    y: (button.height + button.glyphPaintedHeight) / 2 - width * 0.6
    visible: button.glyphPaintedWidth > 0
    kind: root.kind
    badgeColor: root.badgeColor
    ringColor: root.bar ? root.bar.background : Color.bar.background
    fontFamily: root.fontFamily
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: panel.loadedContent
    contentWidth: panel.fittedContentWidth(Style.space(420))
    contentHeight: panel.fittedContentHeight(panel.loadedContentHeight, Style.space(620))

    content: PanelKeyCatcher {
      property alias panelFlick: panelFlick
      implicitHeight: column.implicitHeight
      anchors.fill: parent
      onMoveRequested: function(dx, dy) {
        if (!root.cursorActive) { root.cursorActive = true; return }
        if (dy !== 0) root.moveCursor(dy)
      }
      onActivateRequested: if (root.cursorActive) root.activate(root.cursorTarget)
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onDeleteRequested: if (root.cursorActive) root.requestRemove(root.cursorTarget)
      onTextKey: function(t, modifiers) {
        if (modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)) return
        if (t === "r" || t === "R") mega.refresh()
        else if (t === "o" || t === "O") root.openTarget(root.cursorTarget)
        else if (t === "s" || t === "S") root.editTarget(root.cursorTarget)
        else if (t === "p" || t === "P") mega.toggleAll()
      }

      Flickable {
        id: panelFlick
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: column
          width: panelFlick.width
          spacing: Style.space(12)

          Item {
            id: header
            width: parent.width
            implicitHeight: hero.implicitHeight
            readonly property string target: "header"
            readonly property bool ringVisible: root.hasCursor("header")

            PanelHero {
              id: hero
              width: parent.width
              title: "MEGA"
              meta: mega.kindText
              detail: mega.ready ? mega.email : ""
              foreground: root.foreground
              fontFamily: root.fontFamily
              iconComponent: Component {
                MegaIcon {
                  size: Style.font.display
                  kind: root.kind
                  color: root.foreground
                  badgeColor: root.badgeColor
                  ringColor: root.panelBackground
                  fontFamily: root.fontFamily
                }
              }
              trailingControl: Component {
                ToggleSwitch {
                  id: syncSwitch
                  visible: mega.ready && mega.syncs.length > 0
                  checked: mega.anyRunning
                  busy: mega.busy
                  hasCursor: header.ringVisible
                  foreground: hero.foreground
                  onHovered: function(on) { if (on) root.setCursor("header") }
                  onToggled: mega.toggleAll()

                  PanelToolTip {
                    visible: syncSwitch.containsMouse
                    text: mega.anyRunning ? "Pause all syncing" : "Resume all syncing"
                    fontFamily: hero.fontFamily
                  }
                }
              }
            }
          }

          // The panel's header shows the state upper-cased and cut short, so
          // an unreadable state's reason is repeated here in full.
          Text {
            readonly property string note: mega.actionStatus !== "" ? mega.actionStatus : mega.error
            textFormat: Text.PlainText
            visible: note !== ""
            width: parent.width
            text: note
            color: root.urgent
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.Wrap
          }

          ActionRow {
            visible: !mega.ready && mega.offer !== ""
            width: parent.width
            target: "login"
            glyph: "󰌆"
            title: mega.offerText
            meta: mega.offerHint
          }

          Column {
            visible: mega.ready
            width: parent.width
            spacing: Style.spacing.labelGap

            InfoPair {
              label: "Stored"
              value: mega.usageText
              valueColor: mega.storageLevel > 0 ? root.urgent : root.foreground
            }

            Text {
              textFormat: Text.PlainText
              visible: text !== ""
              width: parent.width
              text: mega.transfersText
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              elide: Text.ElideRight
            }
          }

          PanelSeparator { visible: mega.ready; foreground: root.foreground }

          Column {
            visible: mega.ready
            width: parent.width
            spacing: Style.space(6)

            PanelSectionHeader { text: "SYNC FOLDERS"; foreground: root.foreground; fontFamily: root.fontFamily }

            Repeater {
              model: mega.syncs
              ItemRow {
                required property var modelData
                required property int index
                width: parent.width
                target: "sync:" + index
                itemKey: modelData.key
                iconKind: modelData.kind
                iconColour: modelData.badgeColour
                title: modelData.title
                meta: modelData.meta
                toggleGlyph: modelData.paused ? "󰐊" : "󰏤"
                toggleTip: modelData.paused ? "Resume" : "Pause"
              }
            }

            ActionRow {
              width: parent.width
              target: "addSync"
              glyph: "󰐕"
              title: "Add sync…"
              meta: "Keep a local folder and a MEGA folder the same"
            }
          }

          PanelSeparator { visible: mega.ready; foreground: root.foreground }

          Column {
            visible: mega.ready
            width: parent.width
            spacing: Style.space(6)

            PanelSectionHeader { text: "BACKUPS"; foreground: root.foreground; fontFamily: root.fontFamily }

            Repeater {
              model: mega.backups
              ItemRow {
                required property var modelData
                required property int index
                width: parent.width
                target: "backup:" + index
                itemKey: modelData.key
                glyph: Glyphs.ICON_BACKUP
                glyphColor: root.stateColors[modelData.badgeColour] || root.foreground
                title: modelData.title
                meta: modelData.meta
                toggleGlyph: ""
              }
            }

            ActionRow {
              width: parent.width
              target: "addBackup"
              glyph: "󰐕"
              title: "Add backup…"
              meta: "Scheduled, versioned copies of a local folder in MEGA"
            }
          }

          PanelSeparator { visible: mega.ready; foreground: root.foreground }

          ActionRow {
            visible: mega.ready
            width: parent.width
            target: "web"
            glyph: "󰖟"
            title: "Open mega.nz"
            meta: "Files, shares and account settings in the browser"
          }
        }
      }
    }
  }

  // A row with a single action, such as "Add sync…".
  component ActionRow: CursorSurface {
    id: actionRow
    property string target: ""
    property string glyph: ""
    property string title: ""
    property string meta: ""

    hasCursor: root.hasCursor(target)
    foreground: root.foreground
    implicitHeight: actionContent.implicitHeight + Style.spacing.rowPaddingX

    MouseArea {
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onEntered: root.setCursor(actionRow.target)
      onClicked: root.activate(actionRow.target)
    }

    RowLayout {
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.leftMargin: Style.space(10)
      anchors.rightMargin: Style.space(10)
      spacing: Style.space(8)

      Text {
        textFormat: Text.PlainText
        text: actionRow.glyph
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.icon
        Layout.alignment: Qt.AlignVCenter
      }

      RowTexts {
        id: actionContent
        title: actionRow.title
        meta: actionRow.meta
      }
    }
  }

  // A sync or backup row with its own buttons.
  component ItemRow: CursorSurface {
    id: itemRow
    property string target: ""
    property string itemKey: ""
    property string iconKind: ""
    property string iconColour: ""
    property string glyph: ""
    property color glyphColor: root.foreground
    property string title: ""
    property string meta: ""
    property string toggleGlyph: ""
    property string toggleTip: ""
    readonly property bool armed: itemKey !== "" && root.pendingRemove === itemKey

    hasCursor: root.hasCursor(target)
    foreground: root.foreground
    implicitHeight: itemContent.implicitHeight + Style.spacing.rowPaddingX

    MouseArea {
      anchors.fill: parent
      hoverEnabled: true
      onEntered: root.setCursor(itemRow.target)
    }

    RowLayout {
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.leftMargin: Style.space(10)
      anchors.rightMargin: Style.space(6)
      spacing: Style.space(8)

      MegaIcon {
        visible: itemRow.iconKind !== ""
        size: Style.font.icon
        kind: itemRow.iconKind
        color: root.foreground
        badgeColor: root.stateColors[itemRow.iconColour] || root.foreground
        ringColor: root.panelBackground
        fontFamily: root.fontFamily
        Layout.alignment: Qt.AlignVCenter
      }

      Text {
        visible: itemRow.iconKind === ""
        textFormat: Text.PlainText
        text: itemRow.glyph
        color: itemRow.glyphColor
        font.family: root.fontFamily
        font.pixelSize: Style.font.icon
        Layout.alignment: Qt.AlignVCenter
      }

      RowTexts {
        id: itemContent
        title: itemRow.title
        titleElide: Text.ElideMiddle
        meta: itemRow.armed ? "Press remove again to stop it (files stay where they are)" : itemRow.meta
        metaColor: itemRow.armed ? root.urgent : root.dim
      }

      PanelActionButton {
        visible: itemRow.toggleGlyph !== ""
        iconText: itemRow.toggleGlyph
        tooltipText: itemRow.toggleTip
        foreground: root.foreground
        fontFamily: root.fontFamily
        Layout.alignment: Qt.AlignVCenter
        onClicked: root.activate(itemRow.target)
      }

      PanelActionButton {
        visible: String(itemRow.target).indexOf("backup:") === 0
        iconText: "󰒓"
        tooltipText: "Schedule and versions"
        foreground: root.foreground
        fontFamily: root.fontFamily
        Layout.alignment: Qt.AlignVCenter
        onClicked: root.editTarget(itemRow.target)
      }

      PanelActionButton {
        iconText: "󰉋"
        tooltipText: "Open folder"
        foreground: root.foreground
        fontFamily: root.fontFamily
        Layout.alignment: Qt.AlignVCenter
        onClicked: root.openTarget(itemRow.target)
      }

      PanelActionButton {
        iconText: "󰆴"
        tooltipText: itemRow.armed ? "Click again to remove" : "Remove"
        foreground: itemRow.armed ? root.urgent : root.foreground
        hoverColor: root.urgent
        fontFamily: root.fontFamily
        Layout.alignment: Qt.AlignVCenter
        onClicked: root.requestRemove(itemRow.target)
      }
    }
  }

  // A row's title with a smaller line below it.
  component RowTexts: ColumnLayout {
    property string title: ""
    property string meta: ""
    property int titleElide: Text.ElideRight
    property color metaColor: root.dim

    Layout.fillWidth: true
    spacing: Style.space(1)

    Text {
      textFormat: Text.PlainText
      Layout.fillWidth: true
      text: parent.title
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
      elide: parent.titleElide
    }

    Text {
      textFormat: Text.PlainText
      Layout.fillWidth: true
      text: parent.meta
      color: parent.metaColor
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
      elide: Text.ElideRight
    }
  }

  component InfoPair: Row {
    property string label: ""
    property string value: ""
    property color valueColor: root.foreground

    width: parent.width
    spacing: Style.space(8)

    Text {
      textFormat: Text.PlainText
      text: parent.label
      color: root.foreground
      opacity: 0.6
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
    }
    Item { width: Math.max(0, parent.width - parent.children[0].implicitWidth - parent.children[2].implicitWidth - parent.spacing * 2); height: 1 }
    Text {
      textFormat: Text.PlainText
      text: parent.value
      color: parent.valueColor
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
      elide: Text.ElideRight
    }
  }
}
