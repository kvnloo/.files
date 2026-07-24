import QtQuick
import QtQuick.Layouts
import Quickshell
import qs.Commons
import qs.Services.System
import qs.Services.UI
import qs.Widgets

// Unified system card: monitors CPU, temperature, memory, and every major mounted volume.
NBox {
  id: root

  Component.onCompleted: SystemStatService.registerComponent("card-sysmonitor")
  Component.onDestruction: SystemStatService.unregisterComponent("card-sysmonitor")

  readonly property string diskPath: Settings.data.controlCenter.diskPath || "/"
  readonly property real contentScale: 0.95 * Style.uiScaleRatio
  readonly property var diskPaths: {
    const sizes = SystemStatService.diskSizeGb || {};
    const paths = Object.keys(sizes).filter(path => {
      if (sizes[path] < 50)
        return false;
      return path === "/" || path === "/workspace" || path.startsWith("/mnt/") || path.startsWith("/media/") || path.startsWith("/run/media/");
    });
    const preferred = ["/", "/workspace", "/mnt/zer0models"];
    return paths.sort((left, right) => {
      const leftIndex = preferred.indexOf(left);
      const rightIndex = preferred.indexOf(right);
      if (leftIndex >= 0 || rightIndex >= 0)
        return (leftIndex >= 0 ? leftIndex : preferred.length) - (rightIndex >= 0 ? rightIndex : preferred.length);
      return left.localeCompare(right);
    });
  }

  function diskLabel(path) {
    if (path === "/")
      return "ROOT";
    if (path === "/workspace")
      return "WORK";
    const parts = path.split("/").filter(Boolean);
    const name = parts.length > 0 ? parts[parts.length - 1] : path;
    return name.length > 6 ? name.slice(0, 6).toUpperCase() : name.toUpperCase();
  }

  Item {
    id: content
    anchors.fill: parent
    anchors.margins: Style.marginS

    Column {
      anchors.fill: parent

      Item {
        width: parent.width
        height: parent.height / 4

        NCircleStat {
          id: cpuUsageGauge
          anchors.centerIn: parent
          ratio: SystemStatService.cpuUsage / 100
          icon: "cpu-usage"
          contentScale: root.contentScale
          fillColor: SystemStatService.cpuColor
          tooltipText: I18n.tr("system-monitor.cpu-usage") + `: ${Math.round(SystemStatService.cpuUsage)}%`
        }

        Connections {
          target: SystemStatService
          function onCpuUsageChanged() {
            if (TooltipService.activeTooltip && TooltipService.activeTooltip.targetItem === cpuUsageGauge)
              TooltipService.updateText(I18n.tr("system-monitor.cpu-usage") + `: ${Math.round(SystemStatService.cpuUsage)}%`);
          }
        }
      }

      Item {
        width: parent.width
        height: parent.height / 4

        NCircleStat {
          id: cpuTempGauge
          anchors.centerIn: parent
          ratio: SystemStatService.cpuTemp / 100
          suffix: "°C"
          icon: "cpu-temperature"
          contentScale: root.contentScale
          fillColor: SystemStatService.tempColor
          tooltipText: I18n.tr("system-monitor.cpu-temp") + `: ${Math.round(SystemStatService.cpuTemp)}°C`
        }

        Connections {
          target: SystemStatService
          function onCpuTempChanged() {
            if (TooltipService.activeTooltip && TooltipService.activeTooltip.targetItem === cpuTempGauge)
              TooltipService.updateText(I18n.tr("system-monitor.cpu-temp") + `: ${Math.round(SystemStatService.cpuTemp)}°C`);
          }
        }
      }

      Item {
        width: parent.width
        height: parent.height / 4

        NCircleStat {
          id: memPercentGauge
          anchors.centerIn: parent
          ratio: SystemStatService.memPercent / 100
          icon: "memory"
          contentScale: root.contentScale
          fillColor: SystemStatService.memColor
          tooltipText: I18n.tr("common.memory") + `: ${Math.round(SystemStatService.memPercent)}%`
        }

        Connections {
          target: SystemStatService
          function onMemPercentChanged() {
            if (TooltipService.activeTooltip && TooltipService.activeTooltip.targetItem === memPercentGauge)
              TooltipService.updateText(I18n.tr("common.memory") + `: ${Math.round(SystemStatService.memPercent)}%`);
          }
        }
      }

      Item {
        id: diskSection
        width: parent.width
        height: parent.height / 4

        Column {
          id: diskList
          anchors.fill: parent

          Repeater {
            model: root.diskPaths.length > 0 ? root.diskPaths : [root.diskPath]

            Item {
              id: diskRow
              required property string modelData
              readonly property string mountPath: modelData
              readonly property real usage: SystemStatService.diskPercents[mountPath] ?? 0
              width: diskList.width
              height: diskList.height / Math.max(1, root.diskPaths.length)

              RowLayout {
                anchors.fill: parent
                spacing: Style.marginXXS

                NText {
                  Layout.preferredWidth: 27 * Style.uiScaleRatio
                  text: root.diskLabel(diskRow.mountPath)
                  pointSize: Style.fontSizeXXS
                  font.weight: Style.fontWeightBold
                  color: SystemStatService.getDiskColor(diskRow.mountPath)
                  elide: Text.ElideRight
                }

                Rectangle {
                  Layout.fillWidth: true
                  Layout.preferredHeight: Math.max(4, 5 * Style.uiScaleRatio)
                  radius: height / 2
                  color: Qt.alpha(Color.mOnSurfaceVariant, 0.2)

                  Rectangle {
                    width: parent.width * Math.max(0, Math.min(1, diskRow.usage / 100))
                    height: parent.height
                    radius: parent.radius
                    color: SystemStatService.getDiskColor(diskRow.mountPath)
                  }
                }

                NText {
                  Layout.preferredWidth: 23 * Style.uiScaleRatio
                  text: `${Math.round(diskRow.usage)}%`
                  pointSize: Style.fontSizeXXS
                  font.weight: Style.fontWeightSemiBold
                  color: SystemStatService.getDiskColor(diskRow.mountPath)
                  horizontalAlignment: Text.AlignRight
                }
              }

              MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                onEntered: TooltipService.show(diskRow, `${root.diskLabel(diskRow.mountPath)}: ${Math.round(diskRow.usage)}%\n${diskRow.mountPath}`)
                onExited: TooltipService.hide()
              }
            }
          }
        }
      }
    }
  }
}
