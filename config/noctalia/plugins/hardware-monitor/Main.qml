import QtQuick
import Quickshell.Io
import qs.Services.System

Item {
  id: root

  property var pluginApi: null
  property var telemetry: ({})
  property bool refreshing: false
  property string errorText: ""

  readonly property var gpu: telemetry.gpu || ({})
  readonly property var latency: telemetry.latency || ({})
  readonly property var pressure: telemetry.pressure || ({})
  readonly property var kernel: telemetry.kernel || ({})
  readonly property var temperatures: telemetry.temperatures || []
  readonly property var fans: telemetry.fans || []
  readonly property var swaps: telemetry.swaps || []
  readonly property bool gpuAvailable: gpu.available === true
  readonly property int historyLength: 40
  property var gpuUtilHistory: new Array(historyLength).fill(0)
  property var gpuTempHistory: new Array(historyLength).fill(40)
  property var gpuPowerHistory: new Array(historyLength).fill(0)
  property var gpuFanHistory: new Array(historyLength).fill(0)
  property var wakeLatencyHistory: new Array(historyLength).fill(0)
  property var ipcLatencyHistory: new Array(historyLength).fill(0)

  Component.onCompleted: {
    SystemStatService.registerComponent("plugin-hardware-monitor");
    refresh();
  }
  Component.onDestruction: SystemStatService.unregisterComponent("plugin-hardware-monitor")

  Timer {
    interval: 3000
    repeat: true
    running: true
    onTriggered: root.refresh()
  }

  Process {
    id: snapshotProcess
    command: ["/home/kvn/.config/noctalia/plugins/hardware-monitor/scripts/snapshot.py"]
    stdout: StdioCollector {}
    stderr: StdioCollector {}

    onExited: function(exitCode) {
      root.refreshing = false;
      if (exitCode !== 0) {
        root.errorText = String(stderr.text || "Hardware telemetry failed").trim();
        return;
      }
      try {
        const parsed = JSON.parse(String(stdout.text || "{}"));
        root.telemetry = parsed && typeof parsed === "object" ? parsed : {};
        root.pushGpuHistory();
        root.errorText = "";
      } catch (error) {
        root.errorText = "Invalid hardware telemetry: " + error;
      }
    }
  }

  function appendHistory(history, value) {
    const next = history.slice();
    next.push(Number(value || 0));
    if (next.length > historyLength)
      next.shift();
    return next;
  }

  function pushGpuHistory() {
    if (gpuAvailable) {
      gpuUtilHistory = appendHistory(gpuUtilHistory, gpu.utilization);
      gpuTempHistory = appendHistory(gpuTempHistory, gpu.temperature);
      gpuPowerHistory = appendHistory(gpuPowerHistory, gpu.powerWatts);
      gpuFanHistory = appendHistory(gpuFanHistory, gpu.fanPercent);
    }
    wakeLatencyHistory = appendHistory(wakeLatencyHistory, latency.wakeP95Us);
    ipcLatencyHistory = appendHistory(ipcLatencyHistory, latency.ipcP95Us);
  }

  function refresh() {
    if (snapshotProcess.running)
      return;
    refreshing = true;
    snapshotProcess.running = true;
  }

  function formatBytesPerSecond(value) {
    let amount = Number(value || 0);
    const units = ["B/s", "KiB/s", "MiB/s", "GiB/s"];
    let index = 0;
    while (amount >= 1024 && index < units.length - 1) {
      amount /= 1024;
      index++;
    }
    return (amount >= 100 || index === 0 ? Math.round(amount) : amount.toFixed(1)) + " " + units[index];
  }

  function formatRate(value) {
    const amount = Number(value || 0);
    if (amount >= 1000000)
      return (amount / 1000000).toFixed(1) + "M/s";
    if (amount >= 1000)
      return (amount / 1000).toFixed(1) + "K/s";
    return Math.round(amount) + "/s";
  }

  function diskPaths() {
    const sizes = SystemStatService.diskSizeGb || {};
    const paths = Object.keys(sizes).filter(path => {
      if (Number(sizes[path] || 0) < 1)
        return false;
      return path === "/" || path === "/workspace" || path.startsWith("/mnt/") || path.startsWith("/media/") || path.startsWith("/run/media/");
    });
    const preferred = ["/", "/workspace", "/mnt/zer0models"];
    return paths.sort((left, right) => {
      const li = preferred.indexOf(left);
      const ri = preferred.indexOf(right);
      if (li >= 0 || ri >= 0)
        return (li >= 0 ? li : preferred.length) - (ri >= 0 ? ri : preferred.length);
      return left.localeCompare(right);
    });
  }

  function tooltipRows() {
    const rows = [
      ["CPU", Math.round(SystemStatService.cpuUsage) + "% · " + Math.round(SystemStatService.cpuTemp) + "°C"],
      ["Memory", Math.round(SystemStatService.memPercent) + "% · " + Number(SystemStatService.memGb).toFixed(1) + " GiB"],
      ["Network", "↓ " + formatBytesPerSecond(SystemStatService.rxSpeed) + " · ↑ " + formatBytesPerSecond(SystemStatService.txSpeed)]
    ];
    if (gpuAvailable) {
      rows.splice(1, 0,
        ["GPU", Math.round(gpu.utilization || 0) + "% · " + Math.round(gpu.temperature || 0) + "°C"],
        ["GPU fan / power", Math.round(gpu.fanPercent || 0) + "% · " + Number(gpu.powerWatts || 0).toFixed(0) + " W"],
        ["VRAM", Number(gpu.vramUsedMiB || 0).toFixed(0) + " / " + Number(gpu.vramTotalMiB || 0).toFixed(0) + " MiB"]);
    }
    rows.push(
      ["Wake p95 / p99 / max", Number(latency.wakeP95Us || 0).toFixed(0) + " / " + Number(latency.wakeP99Us || 0).toFixed(0) + " / " + Number(latency.wakeMaxUs || 0).toFixed(0) + " µs"],
      ["IPC p95 / p99 / max", Number(latency.ipcP95Us || 0).toFixed(1) + " / " + Number(latency.ipcP99Us || 0).toFixed(1) + " / " + Number(latency.ipcMaxUs || 0).toFixed(1) + " µs"]);
    return rows;
  }
}
