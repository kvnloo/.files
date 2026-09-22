import QtQuick
import Quickshell
import Quickshell.Io

Item {
  id: root
  property var pluginApi: null
  property var snapshot: ({"overall": "idle", "lanes": ({}) , "log": ""})
  property bool refreshing: false

  Component.onCompleted: root.refresh()

  Timer {
    interval: 1000
    repeat: true
    running: !!root.pluginApi?.panelOpenScreen || root.snapshot.overall === "running"
    onTriggered: root.refresh()
  }

  Process {
    id: snapshotProcess
    command: [root.pluginApi?.pluginDir + "/scripts/snapshot.py"]
    stdout: StdioCollector {}
    onExited: function(exitCode) {
      root.refreshing = false;
      if (exitCode === 0) {
        try { root.snapshot = JSON.parse(String(stdout.text || "{}")); } catch (_) {}
      }
    }
  }

  Process {
    id: updateTerminal
    command: ["alacritty", "--class", "reforge-groot", "-e", "/workspace/.files/scripts/update-all-ui-runner.sh"]
  }

  function refresh() {
    if (!snapshotProcess.running) {
      refreshing = true;
      snapshotProcess.running = true;
    }
  }

  function startUpdate() {
    if (!updateTerminal.running)
      updateTerminal.running = true;
  }

  IpcHandler {
    target: "plugin:reforge-groot"
    function toggle() { root.pluginApi?.withCurrentScreen(screen => root.pluginApi.togglePanel(screen)); }
    function open() { root.pluginApi?.withCurrentScreen(screen => root.pluginApi.openPanel(screen)); }
    function start() { root.startUpdate(); }
  }
}
