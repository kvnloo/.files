import QtQuick
import QtQuick.Layouts
import Quickshell
import qs.Commons
import qs.Services.System
import qs.Services.UI
import qs.Widgets

Item {
  id: root

  property var pluginApi: null
  property ShellScreen screen
  property string widgetId: ""
  property string section: ""
  property int sectionWidgetIndex: -1
  property int sectionWidgetsCount: 0

  readonly property var mainInstance: pluginApi?.mainInstance
  readonly property var gpu: mainInstance?.gpu || ({})
  readonly property real capsuleHeight: Style.getCapsuleHeightForScreen(screen?.name)
  readonly property color gpuColor: Number(gpu.temperature || 0) >= 85 ? Color.mError : (Number(gpu.temperature || 0) >= 75 ? Color.mTertiary : Color.mPrimary)

  implicitWidth: capsule.implicitWidth
  implicitHeight: capsuleHeight

  Rectangle {
    id: capsule
    anchors.centerIn: parent
    implicitWidth: content.implicitWidth + Style.margin2M
    width: implicitWidth
    height: root.capsuleHeight
    radius: Style.radiusL
    color: pointer.containsMouse ? Color.mHover : Style.capsuleColor
    border.color: Style.capsuleBorderColor
    border.width: Style.capsuleBorderWidth

    RowLayout {
      id: content
      anchors.centerIn: parent
      spacing: Style.marginXS

      NIcon {
        icon: "device-analytics"
        pointSize: Style.getBarFontSizeForScreen(root.screen?.name) * 1.2
        applyUiScale: false
        color: root.gpuColor
      }

      NText {
        text: "C " + Math.round(SystemStatService.cpuUsage) + "%"
        pointSize: Style.getBarFontSizeForScreen(root.screen?.name)
        applyUiScale: false
        font.family: Settings.data.ui.fontFixed
        color: Color.mOnSurface
      }

      NText {
        visible: root.mainInstance?.gpuAvailable ?? false
        text: "G " + Math.round(root.gpu.utilization || 0) + "% " + Math.round(root.gpu.temperature || 0) + "° " + Math.round(root.gpu.powerWatts || 0) + "W"
        pointSize: Style.getBarFontSizeForScreen(root.screen?.name)
        applyUiScale: false
        font.family: Settings.data.ui.fontFixed
        color: root.gpuColor
      }

      NText {
        text: "M " + Math.round(SystemStatService.memPercent) + "%"
        pointSize: Style.getBarFontSizeForScreen(root.screen?.name)
        applyUiScale: false
        font.family: Settings.data.ui.fontFixed
        color: Color.mOnSurface
      }
    }
  }

  MouseArea {
    id: pointer
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    acceptedButtons: Qt.LeftButton | Qt.RightButton

    onClicked: function(mouse) {
      TooltipService.hide();
      if (mouse.button === Qt.LeftButton)
        pluginApi?.togglePanel(root.screen, root);
      else
        root.mainInstance?.refresh();
    }
    onEntered: TooltipService.show(root, root.mainInstance?.tooltipRows() || [["Hardware", "Loading"]], BarService.getTooltipDirection(root.screen?.name))
    onExited: TooltipService.hide()
  }
}
