import QtQuick
import Quickshell
import qs.Widgets

NIconButtonHot {
  id: root

  property ShellScreen screen
  property var pluginApi: null
  readonly property var mainInstance: pluginApi?.mainInstance
  readonly property string updateState: String(mainInstance?.snapshot?.overall || "idle")

  icon: updateState === "running" ? "loader-2" : (updateState === "success" ? "circle-check" : "sparkles")
  hot: updateState === "running"
  tooltipText: updateState === "running" ? "Reforge Groot · updates running" : "Reforge Groot · update everything"

  onClicked: pluginApi?.togglePanel(screen, root)
}
