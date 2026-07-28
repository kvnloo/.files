import QtQuick
import Quickshell
import qs.Commons
import qs.Services.Networking
import qs.Widgets

NIconButtonHot {
  id: root

  property ShellScreen screen
  property var pluginApi: null

  readonly property var mainInstance: pluginApi?.mainInstance

  icon: NetworkService.airplaneModeEnabled ? "plane" : (mainInstance?.tailscaleOnline ? "world" : NetworkService.getIcon())
  hot: NetworkService.internetConnectivity || (mainInstance?.tailscaleOnline ?? false)
  tooltipText: "Connection Center"

  onClicked: pluginApi?.togglePanel(screen, root)
  onRightClicked: NetworkService.setAirplaneMode(!NetworkService.airplaneModeEnabled)
}
