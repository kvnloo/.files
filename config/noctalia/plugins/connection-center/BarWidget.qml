import QtQuick
import QtQuick.Layouts
import Quickshell
import qs.Commons
import qs.Services.Networking
import qs.Services.UI
import qs.Widgets

Item {
  id: root

  property var pluginApi: null
  property ShellScreen screen
  property string widgetId: ""
  property string section: ""
  property int sectionWidgetIndex: -1
  property int sectionWidgetsCount: 0

  readonly property var mainInstance: pluginApi?.mainInstance
  readonly property var activeVpns: {
    const rows = [];
    const connections = VPNService.connections || {};
    for (const key in connections) {
      if (connections[key]?.active)
        rows.push(connections[key]);
    }
    return rows;
  }
  readonly property int bluetoothCount: BluetoothService.connectedDevices?.length || 0
  readonly property int activeCount: (NetworkService.wifiConnected ? 1 : 0)
                                      + (NetworkService.ethernetConnected ? 1 : 0)
                                      + activeVpns.length
                                      + (mainInstance?.tailscaleOnline ? 1 : 0)
                                      + (bluetoothCount > 0 ? 1 : 0)
  readonly property string statusIcon: NetworkService.airplaneModeEnabled ? "plane"
                                        : (activeVpns.length > 0 ? "shield-lock"
                                        : (NetworkService.wifiConnected ? NetworkService.getIcon()
                                        : (NetworkService.ethernetConnected ? "ethernet"
                                        : (mainInstance?.tailscaleOnline ? "world"
                                        : (bluetoothCount > 0 ? "bluetooth" : "world-off")))))
  readonly property real capsuleHeight: Style.getCapsuleHeightForScreen(screen?.name)

  implicitWidth: capsuleHeight
  implicitHeight: capsuleHeight

  function tooltipRows() {
    const rows = [];
    if (NetworkService.airplaneModeEnabled)
      rows.push(["Radios", "Airplane mode"]);
    if (NetworkService.wifiConnected)
      rows.push(["Wi-Fi", NetworkService.getStatusText(true)]);
    if (NetworkService.ethernetConnected) {
      const ethernet = NetworkService.activeEthernetDetails || {};
      rows.push(["Ethernet", String(ethernet.connectionName || NetworkService.activeEthernetIf || "Connected") + (ethernet.speed ? " · " + ethernet.speed : "")]);
    }
    for (let index = 0; index < activeVpns.length; index++)
      rows.push(["VPN", activeVpns[index].name || "Connected"]);
    if (mainInstance?.tailscaleOnline)
      rows.push(["Tailnet", mainInstance.tailscalePeersOnline + "/" + mainInstance.tailscalePeersTotal + " peers online"]);
    if (bluetoothCount > 0)
      rows.push(["Bluetooth", bluetoothCount + " device" + (bluetoothCount === 1 ? "" : "s") + " connected"]);
    if (rows.length === 0)
      rows.push(["Connections", "No active connections"]);
    const stats = mainInstance?.tooltipRows() || [];
    return rows.concat(stats);
  }

  Rectangle {
    id: capsule
    anchors.fill: parent
    radius: Style.radiusL
    color: pointer.containsMouse ? Color.mHover : Style.capsuleColor
    border.color: Style.capsuleBorderColor
    border.width: Style.capsuleBorderWidth

    NIcon {
      anchors.centerIn: parent
      icon: root.statusIcon
      pointSize: Style.getBarFontSizeForScreen(root.screen?.name) * 1.25
      applyUiScale: false
      color: root.activeCount > 0 ? Color.mPrimary : Color.mOnSurfaceVariant
    }

    Rectangle {
      visible: root.activeCount > 1
      anchors.right: parent.right
      anchors.top: parent.top
      anchors.rightMargin: -1
      anchors.topMargin: -2
      width: 12
      height: 12
      radius: 6
      color: Color.mPrimary

      NText {
        anchors.centerIn: parent
        text: root.activeCount > 9 ? "9+" : String(root.activeCount)
        pointSize: 7
        applyUiScale: false
        font.weight: Style.fontWeightBold
        color: Color.mOnPrimary
      }
    }
  }

  MouseArea {
    id: pointer
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    acceptedButtons: Qt.LeftButton | Qt.RightButton

    onClicked: function(mouse) {
      TooltipService.hide();
      if (mouse.button === Qt.LeftButton)
        pluginApi?.togglePanel(root.screen, root);
      else {
        VPNService.refresh();
        root.mainInstance?.refresh();
      }
    }
    onEntered: TooltipService.show(root, root.tooltipRows(), BarService.getTooltipDirection(root.screen?.name))
    onExited: TooltipService.hide()
  }
}
