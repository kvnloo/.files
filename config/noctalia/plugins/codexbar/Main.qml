import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons

Item {
  id: root

  property var pluginApi: null
  property var providers: []
  property bool refreshing: false
  property string errorText: ""
  property string refreshError: ""

  readonly property int maxUsedPercent: computeMaxUsedPercent()
  readonly property bool hasData: providers.length > 0

  Component.onCompleted: {
    loadSnapshot();
    refresh();
  }

  Timer {
    interval: 60000
    repeat: true
    running: true
    onTriggered: root.refresh()
  }

  Process {
    id: snapshotProcess
    command: ["/home/kvn/.config/noctalia/plugins/codexbar/scripts/snapshot.sh", "read"]
    stdout: StdioCollector {}
    stderr: StdioCollector {}

    onExited: function(exitCode) {
      if (exitCode !== 0) {
        root.errorText = String(stderr.text || "Unable to read CodexBar cache").trim();
        return;
      }
      try {
        const parsed = JSON.parse(String(stdout.text || "[]"));
        root.providers = Array.isArray(parsed) ? parsed : [];
        root.errorText = "";
      } catch (error) {
        root.errorText = "Invalid CodexBar data: " + error;
      }
    }
  }

  Process {
    id: refreshProcess
    command: ["/home/kvn/.config/noctalia/plugins/codexbar/scripts/snapshot.sh", "refresh"]
    stdout: StdioCollector {}
    stderr: StdioCollector {}

    onExited: function(exitCode) {
      root.refreshing = false;
      root.refreshError = exitCode === 0 ? "" : String(stderr.text || "CodexBar refresh failed").trim();
      root.loadSnapshot();
    }
  }

  function loadSnapshot() {
    if (!snapshotProcess.running)
      snapshotProcess.running = true;
  }

  function refresh() {
    if (refreshing || refreshProcess.running)
      return;
    refreshing = true;
    refreshError = "";
    refreshProcess.running = true;
  }

  function displayName(providerId) {
    const names = {
      codex: "Codex",
      claude: "Claude",
      gemini: "Gemini",
      cursor: "Cursor",
      copilot: "Copilot",
      grok: "Grok",
      kimi: "Kimi",
      minimax: "MiniMax",
      openrouter: "OpenRouter",
      zai: "Z.ai"
    };
    return names[providerId] || String(providerId || "Provider");
  }

  function providerIcon(providerId) {
    const icons = {
      codex: "brand-openai",
      claude: "brain",
      gemini: "brand-google",
      cursor: "cursor-text",
      copilot: "brand-github-copilot",
      grok: "letter-x",
      kimi: "moon-stars",
      minimax: "sparkles",
      openrouter: "router",
      zai: "sparkles"
    };
    return icons[providerId] || "robot";
  }

  function planLabel(entry) {
    const usage = entry?.usage || {};
    const identity = usage.identity || {};
    const keys = ["planName", "plan", "subscription", "tier", "accountType"];
    for (let i = 0; i < keys.length; i++) {
      const value = usage[keys[i]] || identity[keys[i]];
      if (value)
        return titleCase(value);
    }
    if (entry?.provider === "claude")
      return "Max";
    const login = identity.loginMethod || usage.loginMethod;
    return login ? titleCase(login) : "";
  }

  function accountLabel(entry) {
    const usage = entry?.usage || {};
    const identity = usage.identity || {};
    return String(identity.accountEmail || usage.accountEmail || entry?.source || "");
  }

  function titleCase(value) {
    return String(value || "").replace(/(^|[-_\s])([a-z])/g, function(_, prefix, letter) {
      return (prefix ? " " : "") + letter.toUpperCase();
    });
  }

  function windowLabel(providerId, key, window) {
    const explicit = window?.title || window?.name || window?.label || window?.model;
    if (explicit)
      return titleCase(explicit);
    if (providerId === "claude" && key === "tertiary")
      return "Sonnet";
    const labels = { primary: "Session", secondary: "Weekly", tertiary: "Model" };
    return labels[key] || titleCase(key);
  }

  function periodLabel(window) {
    const title = String(window?.title || "");
    if (/month/i.test(title))
      return title;
    if (/week/i.test(title))
      return title;
    const minutes = Number(window?.windowMinutes || 0);
    if (minutes >= 40000)
      return "Monthly";
    if (minutes >= 10000)
      return "Weekly";
    return title || "Rate limit";
  }

  function windowsFor(entry) {
    const usage = entry?.usage || {};
    const result = [];
    const keys = ["primary", "secondary", "tertiary"];
    for (let i = 0; i < keys.length; i++) {
      const key = keys[i];
      const window = usage[key];
      if (window && typeof window === "object") {
        result.push({
          key: key,
          title: windowLabel(entry.provider, key, window),
          usedPercent: Number(window.usedPercent || 0),
          windowMinutes: Number(window.windowMinutes || 0),
          resetDescription: String(window.resetDescription || ""),
          paceDescription: String(window.paceDescription || window.paceText || window.paceLabel || "")
        });
      }
    }
    const extras = Array.isArray(usage.extraRateWindows) ? usage.extraRateWindows : [];
    for (let j = 0; j < extras.length; j++) {
      const extra = extras[j] || {};
      const extraWindow = extra.window || extra;
      result.push({
        key: String(extra.id || "extra-" + j),
        title: String(extra.title || extra.name || "Additional window"),
        usedPercent: Number(extraWindow.usedPercent || 0),
        windowMinutes: Number(extraWindow.windowMinutes || extra.windowMinutes || 0),
        resetDescription: String(extraWindow.resetDescription || ""),
        paceDescription: String(extraWindow.paceDescription || "")
      });
    }
    return result;
  }

  function providerMax(entry) {
    const windows = windowsFor(entry);
    let maximum = 0;
    for (let i = 0; i < windows.length; i++)
      maximum = Math.max(maximum, Number(windows[i].usedPercent || 0));
    return Math.round(maximum);
  }

  function computeMaxUsedPercent() {
    let maximum = 0;
    for (let i = 0; i < providers.length; i++)
      maximum = Math.max(maximum, providerMax(providers[i]));
    return Math.round(maximum);
  }

  function tooltipRows() {
    const rows = [];
    for (let i = 0; i < providers.length; i++) {
      const entry = providers[i];
      const name = displayName(entry.provider);
      if (entry.error) {
        rows.push([name, "Usage unavailable"]);
        continue;
      }
      const windows = windowsFor(entry);
      const longWindows = windows.filter(window => window.windowMinutes >= 10000 || /week|month/i.test(window.title));
      if (longWindows.length === 0) {
        rows.push([name, "Weekly/monthly data unavailable"]);
        continue;
      }
      for (let j = 0; j < longWindows.length; j++) {
        const window = longWindows[j];
        let value = Math.round(window.usedPercent) + "%";
        if (window.resetDescription)
          value += " · " + window.resetDescription;
        rows.push([name + " " + periodLabel(window), value]);
      }
    }
    if (rows.length === 0)
      rows.push([refreshing ? "Refreshing CodexBar" : "CodexBar", errorText || "No usage data"]);
    return rows;
  }

  function statusUrl(providerId) {
    const urls = {
      codex: "https://status.openai.com",
      claude: "https://status.anthropic.com",
      gemini: "https://status.cloud.google.com",
      cursor: "https://status.cursor.com",
      copilot: "https://www.githubstatus.com"
    };
    return urls[providerId] || "https://codexbar.app";
  }

  IpcHandler {
    target: "plugin:codexbar"

    function toggle() {
      if (pluginApi) {
        pluginApi.withCurrentScreen(function(screen) {
          pluginApi.togglePanel(screen);
        });
      }
    }

    function refresh() {
      root.refresh();
    }
  }
}
