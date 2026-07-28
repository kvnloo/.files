import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import qs.Commons
import qs.Services.System
import qs.Widgets

Item {
  id: root

  property var pluginApi: null
  readonly property var mainInstance: pluginApi?.mainInstance
  readonly property var gpu: mainInstance?.gpu || ({})
  readonly property var latency: mainInstance?.latency || ({})
  readonly property var pressure: mainInstance?.pressure || ({})
  readonly property var kernel: mainInstance?.kernel || ({})
  readonly property var diskPaths: mainInstance?.diskPaths() || []
  readonly property var auxiliaryTemperatures: (mainInstance?.temperatures || []).filter(item => item.chip !== "coretemp" && item.chip !== "nvidia").slice(0, 8)
  readonly property var hardwareFans: (mainInstance?.fans || []).slice(0, 8)

  readonly property var geometryPlaceholder: panelContainer
  property real contentPreferredWidth: Math.round(440 * Style.uiScaleRatio)
  property real contentPreferredHeight: Math.round(600 * Style.uiScaleRatio)
  readonly property bool allowAttach: true

  anchors.fill: parent

  function closePanel() {
    const screen = pluginApi?.panelOpenScreen;
    if (screen)
      pluginApi.closePanel(screen);
  }

  function gib(value) {
    return Number(value || 0).toFixed(1) + " GiB";
  }

  function pct(value) {
    return Math.round(Number(value || 0)) + "%";
  }

  component MetricRow: RowLayout {
    property string label: ""
    property string value: ""
    property color valueColor: Color.mOnSurface
    Layout.fillWidth: true
    spacing: Style.marginS
    NText { text: parent.label; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant; Layout.fillWidth: true; elide: Text.ElideRight }
    NText { text: parent.value; pointSize: Style.fontSizeXS; font.family: Settings.data.ui.fontFixed; color: parent.valueColor; horizontalAlignment: Text.AlignRight }
  }

  component GraphCard: NBox {
    id: graphCard
    property string icon: "device-analytics"
    property string title: ""
    property string value: ""
    property var values: []
    property var values2: []
    property real minValue: 0
    property real maxValue: 100
    property real minValue2: 0
    property real maxValue2: 100
    property color lineColor: Color.mPrimary
    property color lineColor2: Color.mSecondary
    property bool secondLine: values2 && values2.length > 0

    Layout.fillWidth: true
    Layout.preferredHeight: 132 * Style.uiScaleRatio

    ColumnLayout {
      anchors.fill: parent
      anchors.margins: Style.marginS
      anchors.bottomMargin: Style.radiusM * 0.5
      spacing: Style.marginXXS

      RowLayout {
        Layout.fillWidth: true
        spacing: Style.marginXS
        NIcon { icon: graphCard.icon; pointSize: Style.fontSizeS; color: graphCard.lineColor }
        NText { text: graphCard.value; pointSize: Style.fontSizeXS; font.family: Settings.data.ui.fontFixed; color: Color.mOnSurface; Layout.fillWidth: true; elide: Text.ElideRight }
        NText { text: graphCard.title; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
      }

      NGraph {
        Layout.fillWidth: true
        Layout.fillHeight: true
        values: graphCard.values
        values2: graphCard.values2
        minValue: graphCard.minValue
        maxValue: graphCard.maxValue
        minValue2: graphCard.minValue2
        maxValue2: graphCard.maxValue2
        color: graphCard.lineColor
        color2: graphCard.lineColor2
        strokeWidth: Math.max(1, Style.uiScaleRatio)
        fill: true
        fillOpacity: 0.15
        updateInterval: 3000
        animateScale: true
      }
    }
  }

  NBox {
    id: panelContainer
    anchors.fill: parent

    ColumnLayout {
      anchors.fill: parent
      anchors.margins: Style.marginL
      spacing: Style.marginS

      RowLayout {
        Layout.fillWidth: true
        spacing: Style.marginM
        NIcon { icon: "device-analytics"; pointSize: Style.fontSizeXL; color: Color.mPrimary }
        ColumnLayout {
          Layout.fillWidth: true
          spacing: 0
          NText { text: "Hardware Monitor"; pointSize: Style.fontSizeM; font.weight: Style.fontWeightBold; color: Color.mOnSurface }
          NText {
            text: root.mainInstance?.errorText || (root.mainInstance?.refreshing ? "Sampling…" : "Live system health")
            pointSize: Style.fontSizeXS
            color: root.mainInstance?.errorText ? Color.mError : Color.mOnSurfaceVariant
            elide: Text.ElideRight
            Layout.fillWidth: true
          }
        }
        NIconButton { icon: "refresh"; tooltipText: "Refresh"; baseSize: Style.baseWidgetSize * 0.72; onClicked: root.mainInstance?.refresh() }
        NIconButton { icon: "close"; tooltipText: "Close"; baseSize: Style.baseWidgetSize * 0.72; onClicked: root.closePanel() }
      }

      NScrollView {
        id: scroll
        Layout.fillWidth: true
        Layout.fillHeight: true
        horizontalPolicy: ScrollBar.AlwaysOff
        verticalPolicy: ScrollBar.AsNeeded
        contentWidth: availableWidth
        reserveScrollbarSpace: true
        gradientColor: Color.mSurface

        ColumnLayout {
          width: scroll.availableWidth
          spacing: Style.marginS

          GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: Style.marginS
            rowSpacing: Style.marginS
            uniformCellWidths: true

            GraphCard {
              icon: "cpu-usage"
              title: "CPU"
              value: root.pct(SystemStatService.cpuUsage) + " · " + Math.round(SystemStatService.cpuTemp) + "°"
              values: SystemStatService.cpuHistory
              values2: SystemStatService.cpuTempHistory
              minValue2: Math.max(0, SystemStatService.cpuTempHistoryMin - 5)
              maxValue2: Math.max(1, SystemStatService.cpuTempHistoryMax + 5)
            }

            GraphCard {
              icon: "gpu-temperature"
              title: "GPU"
              value: root.mainInstance?.gpuAvailable ? root.pct(root.gpu.utilization) + " · " + Math.round(root.gpu.temperature || 0) + "°" : "Unavailable"
              values: root.mainInstance?.gpuUtilHistory || []
              values2: root.mainInstance?.gpuTempHistory || []
            }

            GraphCard {
              icon: "memory"
              title: "RAM"
              value: root.pct(SystemStatService.memPercent) + " · " + root.gib(SystemStatService.memGb)
              values: SystemStatService.memHistory
              lineColor: Color.mPrimary
            }

            GraphCard {
              icon: "bolt"
              title: "GPU power"
              value: Math.round(root.gpu.powerWatts || 0) + "W · fan " + root.pct(root.gpu.fanPercent)
              values: root.mainInstance?.gpuPowerHistory || []
              values2: root.mainInstance?.gpuFanHistory || []
              maxValue: Math.max(1, Number(root.gpu.powerLimitWatts || 350))
              maxValue2: 100
              lineColor2: Color.mTertiary
            }

            GraphCard {
              icon: "network"
              title: "Network"
              value: "↓ " + (root.mainInstance?.formatBytesPerSecond(SystemStatService.rxSpeed) || "0 B/s") + " · ↑ " + (root.mainInstance?.formatBytesPerSecond(SystemStatService.txSpeed) || "0 B/s")
              values: SystemStatService.rxSpeedHistory
              values2: SystemStatService.txSpeedHistory
              maxValue: SystemStatService.rxMaxSpeed
              maxValue2: SystemStatService.txMaxSpeed
            }

            GraphCard {
              icon: "stopwatch"
              title: "Latency"
              value: Math.round(root.latency.wakeP95Us || 0) + "µs · " + Number(root.latency.ipcP95Us || 0).toFixed(1) + "µs"
              values: root.mainInstance?.wakeLatencyHistory || []
              values2: root.mainInstance?.ipcLatencyHistory || []
              maxValue: Math.max(100, ...(root.mainInstance?.wakeLatencyHistory || [100]))
              maxValue2: Math.max(10, ...(root.mainInstance?.ipcLatencyHistory || [10]))
            }
          }

          NBox {
            Layout.fillWidth: true
            implicitHeight: details.implicitHeight + Style.margin2M
            GridLayout {
              id: details
              anchors.fill: parent
              anchors.margins: Style.marginM
              columns: 1
              rowSpacing: Style.marginXXS
              MetricRow { label: "CPU clock · load 1/5/15"; value: SystemStatService.cpuFreq + " · " + SystemStatService.loadAvg1.toFixed(1) + "/" + SystemStatService.loadAvg5.toFixed(1) + "/" + SystemStatService.loadAvg15.toFixed(1) }
              MetricRow { label: "Swap total"; value: root.pct(SystemStatService.swapPercent) + " · " + root.gib(SystemStatService.swapGb) }
              MetricRow { label: "Swap in/out · major faults"; value: Number(root.kernel.swapInMiBPerSecond || 0).toFixed(1) + "/" + Number(root.kernel.swapOutMiBPerSecond || 0).toFixed(1) + " MiB/s · " + (root.mainInstance?.formatRate(root.kernel.majorFaultsPerSecond) || "0/s") }
              Repeater {
                model: root.mainInstance?.swaps || []
                MetricRow {
                  required property var modelData
                  label: "Swap · " + String(modelData.label) + " · p" + String(modelData.priority)
                  value: root.gib(modelData.usedGiB) + " / " + root.gib(modelData.sizeGiB) + " · " + root.pct(modelData.percent)
                }
              }
              MetricRow { label: "VRAM"; value: Math.round(root.gpu.vramUsedMiB || 0) + " / " + Math.round(root.gpu.vramTotalMiB || 0) + " MiB" }
              MetricRow { label: "GPU clocks · state · PCIe"; value: Math.round(root.gpu.coreClockMHz || 0) + "/" + Math.round(root.gpu.memoryClockMHz || 0) + " MHz · " + String(root.gpu.performanceState || "—") + " · G" + String(root.gpu.pcieGeneration || "—") + "×" + String(root.gpu.pcieWidth || "—") }
              MetricRow { label: "IRQ · softIRQ · context switches"; value: (root.mainInstance?.formatRate(root.kernel.interruptsPerSecond) || "0/s") + " · " + (root.mainInstance?.formatRate(root.kernel.softirqsPerSecond) || "0/s") + " · " + (root.mainInstance?.formatRate(root.kernel.contextSwitchesPerSecond) || "0/s") }
              MetricRow { label: "PSI CPU some · memory full · I/O full (10s)"; value: Number(root.pressure.cpuSome || 0).toFixed(1) + "% · " + Number(root.pressure.memoryFull || 0).toFixed(1) + "% · " + Number(root.pressure.ioFull || 0).toFixed(1) + "%" }
            }
          }

          NBox {
            Layout.fillWidth: true
            visible: root.diskPaths.length > 0
            implicitHeight: storage.implicitHeight + Style.margin2M
            ColumnLayout {
              id: storage
              anchors.fill: parent
              anchors.margins: Style.marginM
              spacing: Style.marginXXS
              MetricRow { label: "Mounted storage"; value: "used / total"; valueColor: Color.mPrimary }
              Repeater {
                model: root.diskPaths
                MetricRow {
                  required property string modelData
                  label: modelData
                  value: Math.round(SystemStatService.diskPercents[modelData] || 0) + "% · " + Number(SystemStatService.diskUsedGb[modelData] || 0).toFixed(1) + " / " + Number(SystemStatService.diskSizeGb[modelData] || 0).toFixed(1) + " GB"
                  valueColor: Number(SystemStatService.diskPercents[modelData] || 0) >= 90 ? Color.mError : Color.mOnSurface
                }
              }
            }
          }

          NBox {
            Layout.fillWidth: true
            visible: root.auxiliaryTemperatures.length > 0 || root.hardwareFans.length > 0
            implicitHeight: sensors.implicitHeight + Style.margin2M
            ColumnLayout {
              id: sensors
              anchors.fill: parent
              anchors.margins: Style.marginM
              spacing: Style.marginXXS
              MetricRow { label: "Board sensors"; value: "temperature / fan"; valueColor: Color.mPrimary }
              Repeater {
                model: root.auxiliaryTemperatures
                MetricRow {
                  required property var modelData
                  label: String(modelData.chip) + " · " + String(modelData.label)
                  value: Number(modelData.celsius || 0).toFixed(0) + " °C"
                }
              }
              Repeater {
                model: root.hardwareFans
                MetricRow {
                  required property var modelData
                  label: String(modelData.chip) + " · " + String(modelData.label)
                  value: Math.round(modelData.rpm || 0) + " RPM"
                }
              }
            }
          }
        }
      }
    }
  }
}
