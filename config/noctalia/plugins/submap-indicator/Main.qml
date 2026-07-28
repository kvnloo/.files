import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io

Item {
  id: root

  property var pluginApi: null
  property string activeSubmap: "default"
  readonly property bool modeActive: activeSubmap !== "default"
  readonly property string modeLabel: modeActive ? activeSubmap.split(" ·")[0].trim().toUpperCase() : ""

  Component.onCompleted: queryProcess.running = true

  function normalizeSubmap(value) {
    const normalized = String(value || "").trim();
    if (normalized === "" || normalized === "default" || normalized === "reset")
      return "default";
    return normalized;
  }

  function updateSubmap(value) {
    activeSubmap = normalizeSubmap(value);
  }

  function reset() {
    if (!resetProcess.running)
      resetProcess.running = true;
  }

  Process {
    id: queryProcess
    command: ["hyprctl", "submap"]
    stdout: StdioCollector {}
    onExited: root.updateSubmap(stdout.text)
  }

  Process {
    id: resetProcess
    command: ["hyprctl", "dispatch", "submap", "reset"]
    stdout: StdioCollector {}
    stderr: StdioCollector {}
  }

  Connections {
    target: Hyprland
    function onRawEvent(event) {
      if (event.name === "submap")
        root.updateSubmap(event.data);
    }
  }

  IpcHandler {
    target: "plugin:submap-indicator"
    function get(): string { return root.activeSubmap; }
    function label(): string { return root.modeLabel; }
    function active(): bool { return root.modeActive; }
    function exit(): void { root.reset(); }
  }
}
