import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import qs.Commons
import qs.Services.Networking
import qs.Services.System
import qs.Services.UI
import qs.Widgets

Item {
  id: root

  property var pluginApi: null
  readonly property var mainInstance: pluginApi?.mainInstance
  readonly property var vpnRows: connectionRows()
  readonly property var ethernetRows: NetworkService.ethernetInterfaces || []
  readonly property var network: mainInstance?.networkTelemetry || ({})
  readonly property var totalTraffic: network.total || ({})
  readonly property var ethernetTraffic: network.ethernet || ({})
  readonly property var wifiTraffic: network.wifi || ({})
  readonly property var tailnetTraffic: network.tailnet || ({})

  readonly property var geometryPlaceholder: panelContainer
  property real contentPreferredWidth: Math.round(440 * Style.uiScaleRatio)
  property real contentPreferredHeight: Math.round(600 * Style.uiScaleRatio)
  readonly property bool allowAttach: true

  anchors.fill: parent

  Component.onCompleted: {
    VPNService.refresh();
    mainInstance?.refreshTailscale();
    mainInstance?.refreshNetwork();
  }

  function closePanel() {
    const activeScreen = pluginApi?.panelOpenScreen;
    if (activeScreen)
      pluginApi.closePanel(activeScreen);
  }

  function openNativePanel(name) {
    var activeScreen = pluginApi?.panelOpenScreen;
    var panel = PanelService.getPanel(name, activeScreen);
    root.closePanel();
    panel?.open();
  }

  function connectionRows() {
    var rows = [];
    var map = VPNService.connections || {};
    for (var key in map)
      rows.push(map[key]);
    rows.sort((a, b) => Number(b.active) - Number(a.active) || String(a.name).localeCompare(String(b.name)));
    return rows;
  }

  function trafficLabel(sample) {
    return "↓ " + (mainInstance?.formatBytesPerSecond(sample?.rxBps) || "0 B/s")
           + "   ↑ " + (mainInstance?.formatBytesPerSecond(sample?.txBps) || "0 B/s");
  }

  function historyMax(first, second, floor) {
    var maximum = Number(floor || 1);
    var values = (first || []).concat(second || []);
    for (var index = 0; index < values.length; index++)
      maximum = Math.max(maximum, Number(values[index] || 0));
    return maximum * 1.12;
  }

  component StatusRow: RowLayout {
    property string label: ""
    property string value: ""
    property string icon: "circle"
    Layout.fillWidth: true
    spacing: Style.marginS

    NIcon { icon: parent.icon; pointSize: Style.fontSizeM; color: Color.mPrimary }
    NText { text: parent.label; Layout.fillWidth: true; color: Color.mOnSurface; elide: Text.ElideRight }
    NText { text: parent.value; color: Color.mOnSurfaceVariant; pointSize: Style.fontSizeXS; elide: Text.ElideRight }
  }

  component TrafficGraph: NBox {
    id: graph
    property string icon: "chart-line"
    property string title: ""
    property string value: ""
    property var values: []
    property var values2: []
    property real maximum: 1024
    property color downloadColor: Color.mPrimary
    property color uploadColor: Color.mSecondary

    Layout.fillWidth: true
    Layout.preferredHeight: Math.round(118 * Style.uiScaleRatio)

    ColumnLayout {
      anchors.fill: parent
      anchors.margins: Style.marginS
      anchors.bottomMargin: Style.radiusM * 0.5
      spacing: Style.marginXXS

      RowLayout {
        Layout.fillWidth: true
        spacing: Style.marginXS
        NIcon { icon: graph.icon; pointSize: Style.fontSizeS; color: graph.downloadColor }
        NText { text: graph.title; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant; Layout.fillWidth: true }
        NText { text: graph.value; pointSize: Style.fontSizeXS; font.family: Settings.data.ui.fontFixed; color: Color.mOnSurface; elide: Text.ElideLeft }
      }

      NGraph {
        Layout.fillWidth: true
        Layout.fillHeight: true
        values: graph.values
        values2: graph.values2
        minValue: 0
        maxValue: graph.maximum
        minValue2: 0
        maxValue2: graph.maximum
        color: graph.downloadColor
        color2: graph.uploadColor
        strokeWidth: Math.max(1, Style.uiScaleRatio)
        fill: true
        fillOpacity: 0.14
        updateInterval: 2500
        animateScale: true
      }
    }
  }

  NBox {
    id: panelContainer
    anchors.fill: parent

    ColumnLayout {
      anchors.fill: parent
      anchors.margins: Style.marginL
      spacing: Style.marginM

      RowLayout {
        Layout.fillWidth: true
        spacing: Style.marginM

        NIcon { icon: "world"; pointSize: Style.fontSizeXL; color: Color.mPrimary }
        ColumnLayout {
          Layout.fillWidth: true
          spacing: 0
          NText { text: "Connection Center"; pointSize: Style.fontSizeM; font.weight: Style.fontWeightBold; color: Color.mOnSurface }
          NText { text: "Wi-Fi, Ethernet, Bluetooth, VPN, and Tailscale"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
        }
        NIconButton { icon: "refresh"; tooltipText: "Refresh"; onClicked: { VPNService.refresh(); NetworkService.scan(); root.mainInstance?.refresh(); } }
        NIconButton { icon: "close"; tooltipText: "Close"; onClicked: root.closePanel() }
      }

      NScrollView {
        id: scroll
        Layout.fillWidth: true
        Layout.fillHeight: true
        horizontalPolicy: ScrollBar.AlwaysOff
        verticalPolicy: ScrollBar.AsNeeded
        contentWidth: availableWidth
        reserveScrollbarSpace: true
        gradientColor: Color.mSurface

        ColumnLayout {
          width: scroll.availableWidth
          spacing: Style.marginM

          NBox {
            Layout.fillWidth: true
            implicitHeight: radioColumn.implicitHeight + Style.margin2M

            ColumnLayout {
              id: radioColumn
              anchors.fill: parent
              anchors.margins: Style.marginM
              spacing: Style.marginS

              NLabel { label: "Radios"; description: "Right-clicking the Connection Center icon also toggles airplane mode" }

              RowLayout {
                Layout.fillWidth: true
                NIcon { icon: NetworkService.airplaneModeEnabled ? "plane" : "plane-off"; color: NetworkService.airplaneModeEnabled ? Color.mTertiary : Color.mOnSurfaceVariant }
                NText { text: "Airplane mode"; Layout.fillWidth: true; color: Color.mOnSurface }
                NToggle { checked: NetworkService.airplaneModeEnabled; onToggled: checked => NetworkService.setAirplaneMode(checked) }
              }

              RowLayout {
                Layout.fillWidth: true
                NIcon { icon: NetworkService.wifiEnabled ? "wifi" : "wifi-off"; color: NetworkService.wifiEnabled ? Color.mPrimary : Color.mOnSurfaceVariant }
                NText { text: "Wi-Fi"; Layout.fillWidth: true; color: Color.mOnSurface }
                NText { text: NetworkService.getStatusText(false); pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant; elide: Text.ElideRight; Layout.maximumWidth: 150 * Style.uiScaleRatio }
                NToggle {
                  checked: NetworkService.wifiEnabled
                  enabled: !NetworkService.airplaneModeEnabled && NetworkService.wifiAvailable
                  onToggled: checked => NetworkService.setWifiEnabled(checked)
                }
              }

              RowLayout {
                Layout.fillWidth: true
                NIcon { icon: BluetoothService.enabled ? "bluetooth" : "bluetooth-off"; color: BluetoothService.enabled ? Color.mPrimary : Color.mOnSurfaceVariant }
                NText { text: "Bluetooth"; Layout.fillWidth: true; color: Color.mOnSurface }
                NText { text: (BluetoothService.connectedDevices?.length || 0) + " connected"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
                NToggle {
                  checked: BluetoothService.enabled
                  enabled: !NetworkService.airplaneModeEnabled && BluetoothService.bluetoothAvailable
                  onToggled: checked => BluetoothService.setBluetoothEnabled(checked)
                }
              }

              RowLayout {
                Layout.fillWidth: true
                spacing: Style.marginS
                NButton { Layout.fillWidth: true; icon: "wifi"; text: "Choose Wi-Fi network"; onClicked: root.openNativePanel("networkPanel") }
                NButton { Layout.fillWidth: true; icon: "bluetooth"; text: "Bluetooth devices"; onClicked: root.openNativePanel("bluetoothPanel") }
              }
            }
          }

          NBox {
            Layout.fillWidth: true
            implicitHeight: ethernetColumn.implicitHeight + Style.margin2M

            ColumnLayout {
              id: ethernetColumn
              anchors.fill: parent
              anchors.margins: Style.marginM
              spacing: Style.marginXS

              NLabel { label: "Ethernet"; description: NetworkService.ethernetConnected ? "Connected" : "No active wired connection" }
              Repeater {
                model: root.ethernetRows
                StatusRow {
                  required property var modelData
                  icon: modelData.connected ? "ethernet" : "ethernet-off"
                  label: modelData.connectionName || modelData.ifname || "Ethernet"
                  value: modelData.connected ? "Connected" : "Disconnected"
                }
              }
              StatusRow {
                visible: root.ethernetRows.length === 0
                icon: "ethernet-off"
                label: "No Ethernet interface"
                value: "Unavailable"
              }
            }
          }

          ColumnLayout {
            Layout.fillWidth: true
            spacing: Style.marginS

            RowLayout {
              Layout.fillWidth: true
              spacing: Style.marginS
              NLabel {
                Layout.fillWidth: true
                label: "Live network traffic"
                description: "Download / upload per link · 2.5 second samples"
              }
              Rectangle {
                width: 8 * Style.uiScaleRatio
                height: width
                radius: width / 2
                color: root.mainInstance?.networkError ? Color.mError : Color.mPrimary
                SequentialAnimation on opacity {
                  running: true
                  loops: Animation.Infinite
                  NumberAnimation { to: 0.28; duration: 700; easing.type: Easing.InOutSine }
                  NumberAnimation { to: 1; duration: 700; easing.type: Easing.InOutSine }
                }
              }
              NText {
                text: root.network.pingMs === null || root.network.pingMs === undefined
                      ? "ping —" : Number(root.network.pingMs).toFixed(1) + " ms"
                pointSize: Style.fontSizeXS
                font.family: Settings.data.ui.fontFixed
                color: Color.mOnSurface
              }
            }

            TrafficGraph {
              icon: "chart-arrows-vertical"
              title: "All links"
              value: root.trafficLabel(root.totalTraffic)
              values: root.mainInstance?.totalRxHistory || []
              values2: root.mainInstance?.totalTxHistory || []
              maximum: root.historyMax(values, values2, 1024)
              downloadColor: Color.mPrimary
              uploadColor: Color.mTertiary
            }

            RowLayout {
              Layout.fillWidth: true
              spacing: Style.marginS

              TrafficGraph {
                icon: "ethernet"
                title: "Ethernet total"
                value: root.trafficLabel(root.ethernetTraffic)
                values: root.mainInstance?.ethernetRxHistory || []
                values2: root.mainInstance?.ethernetTxHistory || []
                maximum: root.historyMax(values, values2, 1024)
              }

              TrafficGraph {
                icon: "world"
                title: "Tailnet tunnel"
                value: root.trafficLabel(root.tailnetTraffic)
                values: root.mainInstance?.tailnetRxHistory || []
                values2: root.mainInstance?.tailnetTxHistory || []
                maximum: root.historyMax(values, values2, 1024)
                downloadColor: Color.mTertiary
                uploadColor: Color.mPrimary
              }
            }

            TrafficGraph {
              visible: root.wifiTraffic.active === true
              icon: "wifi"
              title: "Wi-Fi"
              value: root.trafficLabel(root.wifiTraffic)
              values: root.mainInstance?.wifiRxHistory || []
              values2: root.mainInstance?.wifiTxHistory || []
              maximum: root.historyMax(values, values2, 1024)
              downloadColor: Color.mSecondary
              uploadColor: Color.mTertiary
            }

            TrafficGraph {
              icon: "activity"
              title: "Internet latency"
              value: root.network.pingMs === null || root.network.pingMs === undefined
                     ? "Unavailable" : Number(root.network.pingMs).toFixed(1) + " ms"
              values: root.mainInstance?.pingHistory || []
              values2: []
              maximum: root.historyMax(values, [], 20)
              downloadColor: Color.mSecondary
            }

            NText {
              text: root.network.note || "Ethernet is physical-link traffic and includes encrypted tailnet carriage."
              Layout.fillWidth: true
              wrapMode: Text.WordWrap
              pointSize: Style.fontSizeXS
              color: Color.mOnSurfaceVariant
            }

            NText {
              visible: (root.mainInstance?.networkError || "") !== ""
              text: root.mainInstance?.networkError || ""
              Layout.fillWidth: true
              wrapMode: Text.WordWrap
              pointSize: Style.fontSizeXS
              color: Color.mError
            }
          }

          NBox {
            Layout.fillWidth: true
            implicitHeight: vpnColumn.implicitHeight + Style.margin2M

            ColumnLayout {
              id: vpnColumn
              anchors.fill: parent
              anchors.margins: Style.marginM
              spacing: Style.marginS

              NLabel { label: "VPN"; description: root.vpnRows.length > 0 ? "NetworkManager profiles" : "No VPN profiles configured" }

              Repeater {
                model: root.vpnRows
                RowLayout {
                  required property var modelData
                  Layout.fillWidth: true
                  spacing: Style.marginS
                  NIcon { icon: modelData.active ? "shield-lock" : "shield"; color: modelData.active ? Color.mPrimary : Color.mOnSurfaceVariant }
                  NText { text: modelData.name; Layout.fillWidth: true; color: Color.mOnSurface; elide: Text.ElideRight }
                  NButton {
                    text: modelData.active ? "Disconnect" : "Connect"
                    enabled: !(VPNService.connecting || VPNService.disconnecting)
                    onClicked: VPNService.toggle(modelData.uuid)
                  }
                }
              }

              NText {
                visible: VPNService.lastError !== ""
                text: VPNService.lastError
                color: Color.mError
                pointSize: Style.fontSizeXS
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
              }
            }
          }

          NBox {
            Layout.fillWidth: true
            implicitHeight: tailscaleColumn.implicitHeight + Style.margin2M

            ColumnLayout {
              id: tailscaleColumn
              anchors.fill: parent
              anchors.margins: Style.marginM
              spacing: Style.marginS

              NLabel { label: "Tailscale"; description: root.mainInstance?.tailscaleState || "Unknown" }
              StatusRow {
                icon: root.mainInstance?.tailscaleOnline ? "world" : "world-off"
                label: root.mainInstance?.tailscaleOnline ? "Tailnet connected" : "Tailnet offline"
                value: (root.mainInstance?.tailscalePeersOnline || 0) + "/" + (root.mainInstance?.tailscalePeersTotal || 0) + " peers"
              }
              NButton {
                Layout.fillWidth: true
                text: root.mainInstance?.tailscaleChanging ? "Changing…" : ((root.mainInstance?.tailscaleState || "") === "Running" ? "Disconnect Tailscale" : "Connect Tailscale")
                enabled: !(root.mainInstance?.tailscaleChanging ?? false)
                onClicked: root.mainInstance?.toggleTailscale()
              }
              NText {
                visible: (root.mainInstance?.tailscaleError || "") !== ""
                text: root.mainInstance?.tailscaleError || ""
                color: Color.mError
                pointSize: Style.fontSizeXS
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
              }
            }
          }
        }
      }
    }
  }
}
