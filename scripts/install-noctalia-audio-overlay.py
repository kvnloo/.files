#!/usr/bin/env python3
"""Build a user-local Noctalia config with audio and display overrides."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIGHTNESS_PANEL_SOURCE = ROOT / "config/noctalia/overlays/BrightnessPanel.qml"
SYSTEM_MONITOR_SOURCE = ROOT / "config/noctalia/overlays/SystemMonitorCard.qml"
SOURCE = Path("/etc/xdg/quickshell/noctalia-shell")
TARGET = Path.home() / ".config/quickshell/noctalia-shell"
AUDIO_OVERRIDE = Path("Modules/Panels/Audio/AudioPanel.qml")
DISPLAY_OVERRIDE = Path("Modules/Panels/Settings/Tabs/Display/DisplayTab.qml")
BRIGHTNESS_PANEL_OVERRIDE = Path("Modules/Panels/Brightness/BrightnessPanel.qml")
BRIGHTNESS_WIDGET_OVERRIDE = Path("Modules/Bar/Widgets/Brightness.qml")
SYSTEM_MONITOR_OVERRIDE = Path("Modules/Cards/SystemMonitorCard.qml")


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Noctalia overlay anchor matched {count} times:\n{old}")
    return text.replace(old, new, 1)


def customize_audio_panel(text: str) -> str:
    text = replace_once(
        text,
        "import Quickshell\nimport Quickshell.Services.Pipewire",
        "import Quickshell\nimport Quickshell.Io\nimport Quickshell.Services.Pipewire",
    )
    text = replace_once(
        text,
        "  preferredWidth: Math.round(440 * Style.uiScaleRatio)",
        "  preferredWidth: Math.round(840 * Style.uiScaleRatio)",
    )
    text = replace_once(
        text,
        "    // UI state (lazy-loaded with panelContent)\n"
        "    property int currentTabIndex: 0\n",
        """    // UI state (lazy-loaded with panelContent)
    property int currentTabIndex: 1
    property var filterChains: ({})

    function parseDspFilterChains(raw) {
      var chains = {};
      var sections = String(raw || "").split(/node\\.description\\s*=/);
      for (var i = 1; i < sections.length; i++) {
        var section = sections[i];
        var nodeMatch = section.match(/node\\.name\\s*=\\s*\"([^\"]+)\"/);
        var linksMatch = section.match(/links\\s*=\\s*\\[([\\s\\S]*?)\\]/);
        if (!nodeMatch || !linksMatch)
          continue;

        var links = linksMatch[1];
        var stages = [];
        if (/copyFC:|copyLFE:/.test(links)) stages.push("7.1");
        if (/eq_[lr]:/.test(links)) stages.push("EQ");
        if (/bs2b:/.test(links)) stages.push("Crossfeed");
        if (/brir_/.test(links)) stages.push("BRIR");
        if (/loudness:/.test(links)) stages.push("Loudness");
        if (/mbc:/.test(links)) stages.push("MBC");
        if (/limiter:/.test(links)) stages.push("Limiter");
        if (stages.length > 0)
          chains[nodeMatch[1]] = stages;
      }
      filterChains = chains;
    }

    function filterChainStagesFor(node) {
      if (!node)
        return ["Direct"];
      return filterChains[node.name || ""] || ["Direct"];
    }

    FileView {
      id: dspConfigFile
      path: "/home/kvn/workspace/.files/config/pipewire/pipewire.conf.d/10-headphone-dsp.conf"
      printErrors: false
      watchChanges: true
      onFileChanged: reload()
      onLoaded: panelContent.parseDspFilterChains(text())
    }
""",
    )
    text = replace_once(
        text,
        """                NText {
                  text: I18n.tr("panels.audio.devices-output-device-label")
                  pointSize: Style.fontSizeL
                  color: Color.mPrimary
                }

                Repeater {
                  model: AudioService.sinks
                  NRadioButton {
                    ButtonGroup.group: sinks
                    required property PwNode modelData
                    pointSize: Style.fontSizeS
                    text: modelData.description
                    checked: AudioService.sink?.id === modelData.id
                    onClicked: {
                      AudioService.setAudioSink(modelData);
                      localOutputVolume = AudioService.volume;
                    }
                    Layout.fillWidth: true
                  }
                }
""",
        """                RowLayout {
                  Layout.fillWidth: true

                  NText {
                    text: I18n.tr("panels.audio.devices-output-device-label")
                    pointSize: Style.fontSizeL
                    color: Color.mPrimary
                    Layout.fillWidth: true
                  }

                  NText {
                    text: "SIGNAL PATH"
                    pointSize: Style.fontSizeXS
                    font.weight: Style.fontWeightBold
                    color: Color.mOnSurfaceVariant
                    Layout.preferredWidth: 400 * Style.uiScaleRatio
                  }
                }

                Repeater {
                  model: AudioService.sinks
                  RowLayout {
                    required property PwNode modelData
                    Layout.fillWidth: true
                    spacing: Style.marginM

                    NRadioButton {
                      id: outputDeviceRadio
                      ButtonGroup.group: sinks
                      pointSize: Style.fontSizeS
                      text: modelData.description
                      checked: AudioService.sink?.id === modelData.id
                      onClicked: {
                        AudioService.setAudioSink(modelData);
                        localOutputVolume = AudioService.volume;
                      }
                      Layout.fillWidth: true
                    }

                    RowLayout {
                      id: outputSignalPath
                      readonly property var stages: panelContent.filterChainStagesFor(modelData)
                      Layout.preferredWidth: 400 * Style.uiScaleRatio
                      Layout.preferredHeight: 30 * Style.uiScaleRatio
                      Layout.alignment: Qt.AlignVCenter
                      spacing: Style.marginXS

                      Repeater {
                        model: outputSignalPath.stages

                        RowLayout {
                          required property string modelData
                          required property int index
                          spacing: Style.marginXS

                          Rectangle {
                            implicitWidth: outputStageLabel.implicitWidth + Style.margin2S
                            implicitHeight: 28 * Style.uiScaleRatio
                            radius: Style.radiusXS
                            color: outputDeviceRadio.checked ? Qt.alpha(Color.mPrimary, 0.12) : Qt.alpha(Color.mSurfaceVariant, 0.72)
                            border.width: Style.borderS
                            border.color: outputDeviceRadio.checked ? Qt.alpha(Color.mPrimary, 0.65) : Style.boxBorderColor

                            NText {
                              id: outputStageLabel
                              anchors.centerIn: parent
                              text: modelData
                              pointSize: Style.fontSizeXS
                              family: Settings.data.ui.fontFixed
                              font.weight: outputDeviceRadio.checked ? Style.fontWeightBold : Style.fontWeightRegular
                              color: outputDeviceRadio.checked ? Color.mPrimary : Color.mOnSurfaceVariant
                            }
                          }

                          NIcon {
                            visible: index < outputSignalPath.stages.length - 1
                            icon: "chevron-right"
                            pointSize: Style.fontSizeS
                            color: outputDeviceRadio.checked ? Color.mPrimary : Color.mOnSurfaceVariant
                          }
                        }
                      }
                    }
                  }
                }
""",
    )
    text = replace_once(
        text,
        """                NText {
                  text: I18n.tr("panels.audio.devices-input-device-label")
                  pointSize: Style.fontSizeL
                  color: Color.mPrimary
                }

                Repeater {
                  model: AudioService.sources
                  NRadioButton {
                    ButtonGroup.group: sources
                    required property PwNode modelData
                    pointSize: Style.fontSizeS
                    text: modelData.description
                    checked: AudioService.source?.id === modelData.id
                    onClicked: AudioService.setAudioSource(modelData)
                    Layout.fillWidth: true
                  }
                }
""",
        """                RowLayout {
                  Layout.fillWidth: true

                  NText {
                    text: I18n.tr("panels.audio.devices-input-device-label")
                    pointSize: Style.fontSizeL
                    color: Color.mPrimary
                    Layout.fillWidth: true
                  }

                  NText {
                    text: "SIGNAL PATH"
                    pointSize: Style.fontSizeXS
                    font.weight: Style.fontWeightBold
                    color: Color.mOnSurfaceVariant
                    Layout.preferredWidth: 400 * Style.uiScaleRatio
                  }
                }

                Repeater {
                  model: AudioService.sources
                  RowLayout {
                    required property PwNode modelData
                    Layout.fillWidth: true
                    spacing: Style.marginM

                    NRadioButton {
                      id: inputDeviceRadio
                      ButtonGroup.group: sources
                      pointSize: Style.fontSizeS
                      text: modelData.description
                      checked: AudioService.source?.id === modelData.id
                      onClicked: AudioService.setAudioSource(modelData)
                      Layout.fillWidth: true
                    }

                    RowLayout {
                      id: inputSignalPath
                      readonly property var stages: panelContent.filterChainStagesFor(modelData)
                      Layout.preferredWidth: 400 * Style.uiScaleRatio
                      Layout.preferredHeight: 30 * Style.uiScaleRatio
                      Layout.alignment: Qt.AlignVCenter
                      spacing: Style.marginXS

                      Repeater {
                        model: inputSignalPath.stages

                        RowLayout {
                          required property string modelData
                          required property int index
                          spacing: Style.marginXS

                          Rectangle {
                            implicitWidth: inputStageLabel.implicitWidth + Style.margin2S
                            implicitHeight: 28 * Style.uiScaleRatio
                            radius: Style.radiusXS
                            color: inputDeviceRadio.checked ? Qt.alpha(Color.mPrimary, 0.12) : Qt.alpha(Color.mSurfaceVariant, 0.72)
                            border.width: Style.borderS
                            border.color: inputDeviceRadio.checked ? Qt.alpha(Color.mPrimary, 0.65) : Style.boxBorderColor

                            NText {
                              id: inputStageLabel
                              anchors.centerIn: parent
                              text: modelData
                              pointSize: Style.fontSizeXS
                              family: Settings.data.ui.fontFixed
                              font.weight: inputDeviceRadio.checked ? Style.fontWeightBold : Style.fontWeightRegular
                              color: inputDeviceRadio.checked ? Color.mPrimary : Color.mOnSurfaceVariant
                            }
                          }

                          NIcon {
                            visible: index < inputSignalPath.stages.length - 1
                            icon: "chevron-right"
                            pointSize: Style.fontSizeS
                            color: inputDeviceRadio.checked ? Color.mPrimary : Color.mOnSurfaceVariant
                          }
                        }
                      }
                    }
                  }
                }
""",
    )
    return text


def customize_display_tab(text: str) -> str:
    text = replace_once(
        text,
        "import Quickshell.Io\n",
        "import Quickshell.Hyprland\nimport Quickshell.Io\n",
    )
    text = replace_once(
        text,
        """  spacing: 0

  // Time dropdown options""",
        """  spacing: 0
  property var monitors: []
  property string monitorSignature: ""
  property bool queryAgain: false
  property string pendingMonitorName: ""
  property string pendingMode: ""

  function modeResolution(mode) {
    var match = String(mode || "").match(/^(\\d+x\\d+)@/);
    return match ? match[1] : "";
  }

  function modeRefresh(mode) {
    var match = String(mode || "").match(/@([0-9.]+)Hz$/);
    return match ? Number(match[1]) : 0;
  }

  function currentResolution(monitor) {
    return monitor ? monitor.width + "x" + monitor.height : "";
  }

  function resolutionOptions(monitor) {
    var seen = {};
    var result = [];
    var modes = monitor && monitor.availableModes ? monitor.availableModes : [];
    for (var i = 0; i < modes.length; i++) {
      var resolution = modeResolution(modes[i]);
      if (resolution && !seen[resolution]) {
        seen[resolution] = true;
        result.push({
                      "key": resolution,
                      "name": resolution.replace("x", " × ")
                    });
      }
    }
    return result;
  }

  function refreshOptions(monitor) {
    var result = [];
    var resolution = currentResolution(monitor);
    var modes = monitor && monitor.availableModes ? monitor.availableModes : [];
    for (var i = 0; i < modes.length; i++) {
      if (modeResolution(modes[i]) === resolution) {
        result.push({
                      "key": modes[i],
                      "name": modeRefresh(modes[i]).toFixed(2) + " Hz"
                    });
      }
    }
    return result;
  }

  function currentModeKey(monitor) {
    var modes = monitor && monitor.availableModes ? monitor.availableModes : [];
    var resolution = currentResolution(monitor);
    var closest = "";
    var closestDifference = Number.MAX_VALUE;
    for (var i = 0; i < modes.length; i++) {
      if (modeResolution(modes[i]) !== resolution)
        continue;
      var difference = Math.abs(modeRefresh(modes[i]) - Number(monitor.refreshRate || 0));
      if (difference < closestDifference) {
        closest = modes[i];
        closestDifference = difference;
      }
    }
    return closest;
  }

  function bestModeForResolution(monitor, resolution) {
    var modes = monitor && monitor.availableModes ? monitor.availableModes : [];
    var closest = "";
    var closestDifference = Number.MAX_VALUE;
    for (var i = 0; i < modes.length; i++) {
      if (modeResolution(modes[i]) !== resolution)
        continue;
      var difference = Math.abs(modeRefresh(modes[i]) - Number(monitor.refreshRate || 0));
      if (difference < closestDifference) {
        closest = modes[i];
        closestDifference = difference;
      }
    }
    return closest;
  }

  function monitorBitDepth(monitor) {
    var format = String(monitor.currentFormat || "");
    return format.indexOf("2101010") >= 0 || format.indexOf("1010102") >= 0 ? 10 : 8;
  }

  function monitorRule(monitor, mode) {
    var position = Number(monitor.x || 0) + "x" + Number(monitor.y || 0);
    var rule = [
          monitor.name,
          String(mode).replace(/Hz$/, ""),
          position,
          Number(monitor.scale || 1),
          "transform",
          Number(monitor.transform || 0)
        ];
    if (monitor.mirrorOf && monitor.mirrorOf !== "none")
      rule.push("mirror", monitor.mirrorOf);
    rule.push("vrr", monitor.vrr ? 1 : 0);
    rule.push("bitdepth", monitorBitDepth(monitor));
    if (monitor.colorManagementPreset)
      rule.push("cm", monitor.colorManagementPreset);
    if (monitor.sdrBrightness !== undefined)
      rule.push("sdrbrightness", Number(monitor.sdrBrightness));
    if (monitor.sdrSaturation !== undefined)
      rule.push("sdrsaturation", Number(monitor.sdrSaturation));
    return rule.join(",");
  }

  function queryMonitors() {
    if (monitorQuery.running) {
      queryAgain = true;
      return;
    }
    monitorQuery.output = "";
    monitorQuery.running = true;
  }

  function applyMode(monitor, mode) {
    if (!monitor || !mode || monitorApply.running)
      return;
    pendingMonitorName = monitor.name;
    pendingMode = mode;
    monitorApply.command = ["hyprctl", "keyword", "monitor", monitorRule(monitor, mode)];
    monitorApply.running = true;
  }

  Process {
    id: monitorQuery
    running: false
    command: ["hyprctl", "-j", "monitors", "all"]
    property string output: ""

    stdout: SplitParser {
      onRead: line => monitorQuery.output += line
    }

    stderr: StdioCollector {}

    onExited: function (exitCode) {
      if (exitCode === 0 && output) {
        try {
          var parsed = JSON.parse(output);
          var active = [];
          for (var i = 0; i < parsed.length; i++) {
            if (!parsed[i].disabled && parsed[i].availableModes && parsed[i].availableModes.length > 0)
              active.push(parsed[i]);
          }
          var signature = JSON.stringify(active.map(monitor => ({
                                                                  "name": monitor.name,
                                                                  "width": monitor.width,
                                                                  "height": monitor.height,
                                                                  "refreshRate": monitor.refreshRate,
                                                                  "x": monitor.x,
                                                                  "y": monitor.y,
                                                                  "scale": monitor.scale,
                                                                  "transform": monitor.transform,
                                                                  "mirrorOf": monitor.mirrorOf,
                                                                  "vrr": monitor.vrr,
                                                                  "currentFormat": monitor.currentFormat,
                                                                  "colorManagementPreset": monitor.colorManagementPreset,
                                                                  "sdrBrightness": monitor.sdrBrightness,
                                                                  "sdrSaturation": monitor.sdrSaturation,
                                                                  "availableModes": monitor.availableModes
                                                                })));
          if (signature !== monitorSignature) {
            monitorSignature = signature;
            monitors = active;
          }
        } catch (error) {
          Logger.e("DisplayTab", "Failed to parse Hyprland monitors:", error);
        }
      } else {
        Logger.e("DisplayTab", "Failed to query Hyprland monitors, exit code:", exitCode);
      }
      output = "";
      if (queryAgain) {
        queryAgain = false;
        Qt.callLater(queryMonitors);
      }
    }
  }

  Process {
    id: monitorApply
    running: false
    command: []
    stderr: StdioCollector {
      id: monitorApplyErrors
    }

    onExited: function (exitCode) {
      if (exitCode === 0) {
        ToastService.showNotice("Display mode", pendingMonitorName + " set to " + pendingMode);
      } else {
        var detail = monitorApplyErrors.text ? ": " + monitorApplyErrors.text.trim() : "";
        ToastService.showError("Display mode", "Failed to update " + pendingMonitorName + detail);
      }
      refreshAfterApply.restart();
    }
  }

  Timer {
    id: refreshAfterApply
    interval: 250
    repeat: false
    onTriggered: queryMonitors()
  }

  Timer {
    interval: 3000
    repeat: true
    running: root.visible
    triggeredOnStart: true
    onTriggered: queryMonitors()
  }

  Connections {
    target: Hyprland
    function onRawEvent(event) {
      var monitorEvents = ["configreloaded", "monitoradded", "monitorremoved", "monitoraddedv2", "monitorremovedv2"];
      if (monitorEvents.includes(event.name))
        refreshAfterApply.restart();
    }
  }

  // Time dropdown options""",
    )
    text = replace_once(
        text,
        """  Component.onCompleted: {
    Qt.callLater(populateTimeOptions);
  }""",
        """  Component.onCompleted: {
    Qt.callLater(populateTimeOptions);
    queryMonitors();
  }""",
    )
    text = replace_once(
        text,
        """    NTabButton {
      text: I18n.tr("common.brightness")
      tabIndex: 0
      checked: subTabBar.currentIndex === 0
    }
    NTabButton {
      text: I18n.tr("common.night-light")
      tabIndex: 1
      checked: subTabBar.currentIndex === 1
    }""",
        """    NTabButton {
      text: "Display modes"
      tabIndex: 0
      checked: subTabBar.currentIndex === 0
    }
    NTabButton {
      text: I18n.tr("common.brightness")
      tabIndex: 1
      checked: subTabBar.currentIndex === 1
    }
    NTabButton {
      text: I18n.tr("common.night-light")
      tabIndex: 2
      checked: subTabBar.currentIndex === 2
    }""",
    )
    text = replace_once(
        text,
        """    BrightnessSubTab {}
    NightLightSubTab {""",
        """    ColumnLayout {
      Layout.fillWidth: true
      spacing: Style.marginL

      NText {
        visible: root.monitors.length === 0
        text: "No active Hyprland monitors found"
        pointSize: Style.fontSizeM
        color: Color.mOnSurfaceVariant
      }

      Repeater {
        model: root.monitors

        delegate: NBox {
          required property var modelData
          Layout.fillWidth: true
          implicitHeight: monitorContent.implicitHeight + Style.margin2L
          color: Color.mSurface

          ColumnLayout {
            id: monitorContent
            width: parent.width - Style.margin2L
            x: Style.marginL
            y: Style.marginL
            spacing: Style.marginM

            RowLayout {
              Layout.fillWidth: true

              NText {
                text: modelData.name
                pointSize: Style.fontSizeL
                font.weight: Style.fontWeightSemiBold
              }

              NText {
                Layout.fillWidth: true
                text: modelData.description || modelData.model || ""
                pointSize: Style.fontSizeS
                color: Color.mOnSurfaceVariant
                elide: Text.ElideRight
                horizontalAlignment: Text.AlignRight
              }
            }

            NText {
              Layout.fillWidth: true
              text: "Current: " + root.currentResolution(modelData).replace("x", " × ") + " @ " + Number(modelData.refreshRate).toFixed(2) + " Hz"
              pointSize: Style.fontSizeS
              color: Color.mOnSurfaceVariant
            }

            NComboBox {
              Layout.fillWidth: true
              label: "Resolution"
              description: "Select a mode advertised by this monitor"
              model: root.resolutionOptions(modelData)
              currentKey: root.currentResolution(modelData)
              enabled: !monitorApply.running
              onSelected: key => root.applyMode(modelData, root.bestModeForResolution(modelData, key))
            }

            NComboBox {
              Layout.fillWidth: true
              label: "Refresh rate"
              description: "Available rates for the current resolution"
              model: root.refreshOptions(modelData)
              currentKey: root.currentModeKey(modelData)
              enabled: !monitorApply.running
              onSelected: key => root.applyMode(modelData, key)
            }
          }
        }
      }
    }

    BrightnessSubTab {}
    NightLightSubTab {""",
    )
    return text


def customize_brightness_widget(text: str) -> str:
    text = replace_once(
        text,
        "import qs.Services.Hardware\nimport qs.Services.UI",
        "import qs.Services.Hardware\nimport qs.Services.Noctalia\nimport qs.Services.UI",
    )
    text = replace_once(
        text,
        """  readonly property bool reverseScroll: Settings.data.general.reverseScroll

  // Used to avoid opening the pill on Quickshell startup""",
        """  readonly property bool reverseScroll: Settings.data.general.reverseScroll
  property var monitorLayoutApi: null
  readonly property var monitorLayout: monitorLayoutApi?.mainInstance
  readonly property string displayTimeoutLabel: monitorLayout?.displayTimeoutLabel || "?"

  function syncMonitorLayoutApi() {
    monitorLayoutApi = PluginService.getPluginAPI("monitor-layout");
  }

  Component.onCompleted: syncMonitorLayoutApi()

  Connections {
    target: PluginService

    function onAllPluginsLoaded() {
      root.syncMonitorLayoutApi();
    }

    function onPluginLoaded(pluginId) {
      if (pluginId === "monitor-layout")
        root.syncMonitorLayoutApi();
    }

    function onPluginReloaded(pluginId) {
      if (pluginId === "monitor-layout")
        root.syncMonitorLayoutApi();
    }

    function onPluginUnloaded(pluginId) {
      if (pluginId === "monitor-layout")
        root.monitorLayoutApi = null;
    }
  }

  // Used to avoid opening the pill on Quickshell startup""",
    )
    text = replace_once(
        text,
        """    text: {
      var monitor = brightnessMonitor;
      if (!monitor || !monitor.brightnessControlAvailable || isNaN(monitor.brightness))
        return "";
      return Math.round(monitor.brightness * 100);
    }
    suffix: text.length > 0 ? "%" : "-" """.rstrip(),
        """    text: {
      var monitor = brightnessMonitor;
      if (!monitor || !monitor.brightnessControlAvailable || isNaN(monitor.brightness))
        return "";
      return Math.round(monitor.brightness * 100) + "% · " + root.displayTimeoutLabel;
    }
    suffix: "" """.rstrip(),
    )
    text = replace_once(
        text,
        """      return I18n.tr("tooltips.brightness-at", {
                       "brightness": Math.round(monitor.brightness * 100)
                     });""",
        """      var brightnessText = I18n.tr("tooltips.brightness-at", {
                       "brightness": Math.round(monitor.brightness * 100)
                     });
      var timeoutError = root.monitorLayout?.displayTimeoutError || "";
      var timeoutStatus = root.monitorLayout?.displayTimeoutInfinite
        ? "Display timeout: INF (automatic dimming and locking disabled)"
        : "Display timeout: " + root.displayTimeoutLabel;
      return brightnessText + "\\n" + (timeoutError !== "" ? timeoutError : timeoutStatus);""",
    )
    return text


def customize_brightness_panel(_: str) -> str:
    return BRIGHTNESS_PANEL_SOURCE.read_text()


def customize_system_monitor(_: str) -> str:
    return SYSTEM_MONITOR_SOURCE.read_text()


CUSTOMIZERS = {
    BRIGHTNESS_WIDGET_OVERRIDE: customize_brightness_widget,
    AUDIO_OVERRIDE: customize_audio_panel,
    DISPLAY_OVERRIDE: customize_display_tab,
    BRIGHTNESS_PANEL_OVERRIDE: customize_brightness_panel,
    SYSTEM_MONITOR_OVERRIDE: customize_system_monitor,
}


def mirror_overlay(source: Path, target: Path, relative: Path = Path()) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        child_relative = relative / child.name
        destination = target / child.name
        customizer = CUSTOMIZERS.get(child_relative)
        if customizer is not None:
            destination.write_text(customizer(child.read_text()))
            continue
        if child.is_dir() and any(
            child_relative in override.parents for override in CUSTOMIZERS
        ):
            mirror_overlay(child, destination, child_relative)
            continue
        destination.symlink_to(child, target_is_directory=child.is_dir())


def main() -> None:
    missing = [SOURCE / override for override in CUSTOMIZERS if not (SOURCE / override).is_file()]
    if missing:
        raise SystemExit("Noctalia source not found: " + ", ".join(map(str, missing)))
    if TARGET.exists() or TARGET.is_symlink():
        if TARGET.is_symlink() or TARGET.is_file():
            TARGET.unlink()
        else:
            shutil.rmtree(TARGET)
    mirror_overlay(SOURCE, TARGET)
    for override in CUSTOMIZERS:
        print(TARGET / override)


if __name__ == "__main__":
    main()
