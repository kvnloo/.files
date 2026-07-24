import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import qs.Commons
import qs.Modules.MainScreen
import qs.Modules.Panels.Settings
import qs.Services.Hardware
import qs.Services.UI
import qs.Widgets

SmartPanel {
  id: root

  preferredWidth: Math.round(620 * Style.uiScaleRatio)
  preferredHeight: Math.round(720 * Style.uiScaleRatio)

  function openDisplaySettings() {
    var panel = PanelService.getPanel("settingsPanel", screen);
    panel.requestedTab = SettingsPanel.Tab.Display;
    panel.open();
    root.close();
  }

  function callPlugin(target, method) {
    Quickshell.execDetached(["qs", "-c", "noctalia-shell", "ipc", "call", target, method]);
    root.close();
  }

  function runDesktopScript(script, argument) {
    Quickshell.execDetached([Quickshell.env("HOME") + "/workspace/.files/scripts/" + script, argument]);
  }

  function setVibrance(portIndex, value) {
    var command = ["nvibrant"];
    for (var index = 0; index < portIndex; index++)
      command.push("0");
    command.push(String(Math.round(value)));

    Quickshell.execDetached(command);
  }


  panelContent: Item {
    id: panelContent

    property real globalBrightness: 0
    property bool globalBrightnessChanging: false
    property int globalBrightnessCapableMonitors: 0

    function getIcon(brightness) {
      return brightness <= 0.5 ? "brightness-low" : "brightness-high";
    }

    function getControllableMonitors() {
      var monitors = BrightnessService.monitors || [];
      return monitors.filter(monitor => monitor && monitor.brightnessControlAvailable);
    }

    function updateGlobalBrightness() {
      var monitors = getControllableMonitors();
      globalBrightnessCapableMonitors = monitors.length;
      if (globalBrightnessChanging || monitors.length === 0) {
        if (monitors.length === 0)
          globalBrightness = 0;
        return;
      }
      var total = 0;
      monitors.forEach(monitor => total += isNaN(monitor.brightness) ? 0 : monitor.brightness);
      globalBrightness = total / monitors.length;
    }

    function applyGlobalBrightness(value) {
      getControllableMonitors().forEach(monitor => monitor.setBrightness(value));
    }

    Component.onCompleted: updateGlobalBrightness()

    Connections {
      target: BrightnessService
      function onMonitorBrightnessChanged() { panelContent.updateGlobalBrightness(); }
      function onMonitorsChanged() { panelContent.updateGlobalBrightness(); }
      function onDdcMonitorsChanged() { panelContent.updateGlobalBrightness(); }
    }

    ColumnLayout {
      anchors.fill: parent
      anchors.margins: Style.marginL
      spacing: Style.marginM

      NBox {
        Layout.fillWidth: true
        implicitHeight: headerRow.implicitHeight + Style.margin2M

        RowLayout {
          id: headerRow
          anchors.fill: parent
          anchors.margins: Style.marginM
          spacing: Style.marginM

          NIcon {
            icon: "settings-display"
            pointSize: Style.fontSizeXXL
            color: Color.mPrimary
          }

          ColumnLayout {
            Layout.fillWidth: true
            spacing: 0

            NText {
              text: "Display Center"
              pointSize: Style.fontSizeL
              font.weight: Style.fontWeightBold
              color: Color.mOnSurface
            }

            NText {
              text: "Brightness, modes, layout, color, and wallpaper"
              pointSize: Style.fontSizeXS
              color: Color.mOnSurfaceVariant
            }
          }

          NIconButton {
            icon: "close"
            tooltipText: I18n.tr("common.close")
            baseSize: Style.baseWidgetSize * 0.8
            onClicked: root.close()
          }
        }
      }

      NScrollView {
        Layout.fillWidth: true
        Layout.fillHeight: true
        horizontalPolicy: ScrollBar.AlwaysOff
        verticalPolicy: ScrollBar.AsNeeded
        contentWidth: availableWidth
        reserveScrollbarSpace: false
        gradientColor: Color.mSurface

        ColumnLayout {
          width: parent.width
          spacing: Style.marginM

          NBox {
            Layout.fillWidth: true
            implicitHeight: brightnessColumn.implicitHeight + Style.margin2M

            ColumnLayout {
              id: brightnessColumn
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.top: parent.top
              anchors.margins: Style.marginM
              spacing: Style.marginS

              NLabel {
                label: "Brightness"
                description: panelContent.globalBrightnessCapableMonitors > 0
                  ? "Hardware-backed controls only"
                  : "No connected display exposes DDC brightness control"
              }

              RowLayout {
                visible: panelContent.globalBrightnessCapableMonitors > 1
                Layout.fillWidth: true
                spacing: Style.marginS

                NIcon {
                  icon: panelContent.getIcon(panelContent.globalBrightness)
                  pointSize: Style.fontSizeXL
                  color: Color.mOnSurface
                }

                NValueSlider {
                  from: 0
                  to: 1
                  value: panelContent.globalBrightness
                  stepSize: 0.01
                  enabled: panelContent.globalBrightnessCapableMonitors > 0
                  Layout.fillWidth: true
                  text: Math.round(panelContent.globalBrightness * 100) + "%"
                  onMoved: value => {
                    panelContent.globalBrightness = value;
                    panelContent.applyGlobalBrightness(value);
                  }
                  onPressedChanged: (pressed, value) => {
                    panelContent.globalBrightnessChanging = pressed;
                    panelContent.globalBrightness = value;
                    panelContent.applyGlobalBrightness(value);
                  }
                }
              }

              Repeater {
                model: Quickshell.screens || []

                RowLayout {
                  required property var modelData
                  property var brightnessMonitor: BrightnessService.getMonitorForScreen(modelData)
                  Layout.fillWidth: true
                  spacing: Style.marginS

                  NText {
                    text: modelData.name
                    color: Color.mOnSurface
                    Layout.preferredWidth: 105 * Style.uiScaleRatio
                    elide: Text.ElideRight
                  }

                  NValueSlider {
                    id: monitorBrightness
                    from: 0
                    to: 1
                    value: parent.brightnessMonitor ? parent.brightnessMonitor.brightness : 0
                    stepSize: 0.01
                    enabled: parent.brightnessMonitor ? parent.brightnessMonitor.brightnessControlAvailable : false
                    Layout.fillWidth: true
                    text: enabled ? Math.round(value * 100) + "%" : "Unavailable"
                    onMoved: value => {
                      if (parent.brightnessMonitor && parent.brightnessMonitor.brightnessControlAvailable)
                        parent.brightnessMonitor.setBrightness(value);
                    }
                  }
                }
              }
            }
          }

          NBox {
            Layout.fillWidth: true
            implicitHeight: displayTools.implicitHeight + Style.margin2M

            ColumnLayout {
              id: displayTools
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.top: parent.top
              anchors.margins: Style.marginM
              spacing: Style.marginS

              NLabel {
                label: "Displays"
                description: "Real advertised modes; layout changes apply only after confirmation"
              }

              RowLayout {
                Layout.fillWidth: true

                NButton {
                  Layout.fillWidth: true
                  icon: "settings-display"
                  text: "Resolution & refresh"
                  onClicked: root.openDisplaySettings()
                }

                NButton {
                  Layout.fillWidth: true
                  icon: "layout-grid"
                  text: "Arrange monitors"
                  onClicked: root.callPlugin("plugin:layout-mon", "toggle")
                }
              }
            }
          }

          NBox {
            Layout.fillWidth: true
            implicitHeight: vibranceColumn.implicitHeight + Style.margin2M

            ColumnLayout {
              id: vibranceColumn
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.top: parent.top
              anchors.margins: Style.marginM
              spacing: Style.marginS

              NLabel {
                label: "Digital vibrance"
                description: "NVIDIA hardware saturation; changes only when a slider moves"
              }

              RowLayout {
                Layout.fillWidth: true
                NText { text: "DP output A"; Layout.preferredWidth: 105 * Style.uiScaleRatio }
                NValueSlider {
                  from: 0
                  to: 1023
                  value: 0
                  stepSize: 16
                  text: Math.round(value)
                  Layout.fillWidth: true
                  onMoved: value => root.setVibrance(1, value)
                }
              }

              RowLayout {
                Layout.fillWidth: true
                NText { text: "DP output B"; Layout.preferredWidth: 105 * Style.uiScaleRatio }
                NValueSlider {
                  from: 0
                  to: 1023
                  value: 0
                  stepSize: 16
                  text: Math.round(value)
                  Layout.fillWidth: true
                  onMoved: value => root.setVibrance(3, value)
                }
              }
            }
          }

          NBox {
            Layout.fillWidth: true
            implicitHeight: appearanceTools.implicitHeight + Style.margin2M

            ColumnLayout {
              id: appearanceTools
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.top: parent.top
              anchors.margins: Style.marginM
              spacing: Style.marginS

              NLabel {
                label: "Wallpaper & theme"
                description: "Static, animated, performance, and palette controls"
              }

              RowLayout {
                Layout.fillWidth: true

                NButton {
                  Layout.fillWidth: true
                  icon: "image"
                  text: "Static wallpaper"
                  onClicked: {
                    var panel = PanelService.getPanel("wallpaperPanel", screen);
                    if (panel)
                      panel.toggle();
                    root.close();
                  }
                }

                NButton {
                  Layout.fillWidth: true
                  icon: "player-play"
                  text: "Wallpaper Engine"
                  onClicked: root.callPlugin("plugin:linux-wallpaperengine-controller", "toggle")
                }
              }

              RowLayout {
                Layout.fillWidth: true

                NButton {
                  Layout.fillWidth: true
                  icon: "refresh"
                  text: "Cycle performance mode"
                  onClicked: root.runDesktopScript("wallpaper-mode.sh", "cycle")
                }

                NButton {
                  Layout.fillWidth: true
                  icon: "moon"
                  text: "Light / dark"
                  onClicked: Quickshell.execDetached(["qs", "-c", "noctalia-shell", "ipc", "call", "darkMode", "toggle"])
                }

                NButton {
                  Layout.fillWidth: true
                  icon: "palette"
                  text: "Color editor"
                  onClicked: root.callPlugin("plugin:color-scheme-creator", "toggle")
                }
              }
            }
          }
        }
      }
    }
  }
}
