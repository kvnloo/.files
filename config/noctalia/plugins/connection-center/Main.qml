import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons

Item {
  id: root

  property var pluginApi: null
  property string tailscaleState: "Unknown"
  property bool tailscaleOnline: false
  property int tailscalePeersOnline: 0
  property int tailscalePeersTotal: 0
  property bool tailscaleRefreshing: false
  property bool tailscaleChanging: false
  property string tailscaleError: ""
  property var networkTelemetry: ({})
  property bool networkRefreshing: false
  property string networkError: ""
  readonly property int historyLength: 40
  property var totalRxHistory: new Array(historyLength).fill(0)
  property var totalTxHistory: new Array(historyLength).fill(0)
  property var tailnetRxHistory: new Array(historyLength).fill(0)
  property var tailnetTxHistory: new Array(historyLength).fill(0)
  property var ethernetRxHistory: new Array(historyLength).fill(0)
  property var ethernetTxHistory: new Array(historyLength).fill(0)
  property var wifiRxHistory: new Array(historyLength).fill(0)
  property var wifiTxHistory: new Array(historyLength).fill(0)
  property var pingHistory: new Array(historyLength).fill(0)

  Component.onCompleted: {
    refreshTailscale();
    refreshNetwork();
  }

  Timer {
    interval: 10000
    running: true
    repeat: true
    onTriggered: root.refreshTailscale()
  }

  Timer {
    interval: 2500
    running: true
    repeat: true
    onTriggered: root.refreshNetwork()
  }

  Process {
    id: networkStats
    running: false
    command: ["/home/kvn/.config/noctalia/plugins/connection-center/scripts/network-stats.py"]
    stdout: StdioCollector {}
    stderr: StdioCollector {}

    onExited: function(exitCode) {
      root.networkRefreshing = false;
      if (exitCode !== 0) {
        root.networkError = String(stderr.text || "Network telemetry failed").trim();
        return;
      }
      try {
        const parsed = JSON.parse(String(stdout.text || "{}"));
        root.networkTelemetry = parsed && typeof parsed === "object" ? parsed : {};
        root.pushNetworkHistory();
        root.networkError = "";
      } catch (error) {
        root.networkError = "Invalid network telemetry: " + error;
      }
    }
  }

  Process {
    id: tailscaleStatus
    running: false
    command: ["tailscale", "status", "--json"]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          var status = JSON.parse(text || "{}");
          root.tailscaleState = String(status.BackendState || "Unknown");
          root.tailscaleOnline = !!status.Self?.Online;
          var peers = status.Peer || {};
          var total = 0;
          var online = 0;
          for (var key in peers) {
            total += 1;
            if (peers[key]?.Online)
              online += 1;
          }
          root.tailscalePeersTotal = total;
          root.tailscalePeersOnline = online;
          root.tailscaleError = "";
        } catch (error) {
          root.tailscaleError = "Unable to parse Tailscale status";
        }
      }
    }
    stderr: StdioCollector {
      onStreamFinished: {
        if (text.trim() !== "")
          root.tailscaleError = text.trim().split("\n")[0];
      }
    }
    onExited: root.tailscaleRefreshing = false
  }

  Process {
    id: tailscaleToggle
    running: false
    stdout: StdioCollector {}
    stderr: StdioCollector {
      onStreamFinished: {
        if (text.trim() !== "")
          root.tailscaleError = text.trim().split("\n")[0];
      }
    }
    onExited: {
      root.tailscaleChanging = false;
      root.refreshTailscale();
    }
  }

  function appendHistory(history, value) {
    const next = history.slice();
    next.push(Number(value || 0));
    if (next.length > historyLength)
      next.shift();
    return next;
  }

  function pushNetworkHistory() {
    const sample = networkTelemetry || {};
    totalRxHistory = appendHistory(totalRxHistory, sample.total?.rxBps);
    totalTxHistory = appendHistory(totalTxHistory, sample.total?.txBps);
    tailnetRxHistory = appendHistory(tailnetRxHistory, sample.tailnet?.rxBps);
    tailnetTxHistory = appendHistory(tailnetTxHistory, sample.tailnet?.txBps);
    ethernetRxHistory = appendHistory(ethernetRxHistory, sample.ethernet?.rxBps);
    ethernetTxHistory = appendHistory(ethernetTxHistory, sample.ethernet?.txBps);
    wifiRxHistory = appendHistory(wifiRxHistory, sample.wifi?.rxBps);
    wifiTxHistory = appendHistory(wifiTxHistory, sample.wifi?.txBps);
    pingHistory = appendHistory(pingHistory, sample.pingMs);
  }

  function refreshNetwork() {
    if (networkStats.running)
      return;
    networkRefreshing = true;
    networkStats.running = true;
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

  function tooltipRows() {
    const sample = networkTelemetry || {};
    const rows = [];
    rows.push(["Internet ping", sample.pingMs === null || sample.pingMs === undefined ? "Unavailable" : Number(sample.pingMs).toFixed(1) + " ms"]);
    if (sample.ethernet?.active)
      rows.push(["Ethernet ↓ / ↑", formatBytesPerSecond(sample.ethernet.rxBps) + " / " + formatBytesPerSecond(sample.ethernet.txBps)]);
    if (sample.wifi?.active)
      rows.push(["Wi-Fi ↓ / ↑", formatBytesPerSecond(sample.wifi.rxBps) + " / " + formatBytesPerSecond(sample.wifi.txBps)]);
    if (tailscaleOnline || sample.tailnet?.active)
      rows.push(["Tailnet ↓ / ↑", formatBytesPerSecond(sample.tailnet?.rxBps) + " / " + formatBytesPerSecond(sample.tailnet?.txBps)]);
    rows.push(["Tailscale", tailscaleState + " · " + tailscalePeersOnline + "/" + tailscalePeersTotal + " peers"]);
    return rows;
  }

  function refreshTailscale() {
    if (tailscaleStatus.running)
      return;
    tailscaleRefreshing = true;
    tailscaleStatus.running = true;
  }

  function toggleTailscale() {
    if (tailscaleToggle.running)
      return;
    tailscaleChanging = true;
    tailscaleError = "";
    tailscaleToggle.command = tailscaleState === "Running" ? ["tailscale", "down"] : ["tailscale", "up"];
    tailscaleToggle.running = true;
  }

  IpcHandler {
    target: "plugin:connection-center"
    function toggle() {
      pluginApi?.withCurrentScreen(screen => pluginApi.togglePanel(screen));
    }
    function refresh() {
      root.refreshTailscale();
      root.refreshNetwork();
    }
  }
}
