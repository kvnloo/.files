import QtQuick
import QtQuick.Layouts
import Quickshell
import qs.Commons
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
  readonly property bool modeActive: mainInstance?.modeActive ?? false
  readonly property real capsuleHeight: Style.getCapsuleHeightForScreen(screen?.name)

  visible: modeActive
  implicitWidth: modeActive ? capsule.implicitWidth : 0
  implicitHeight: modeActive ? capsuleHeight : 0

  Rectangle {
    id: capsule
    anchors.centerIn: parent
    implicitWidth: content.implicitWidth + Style.margin2M
    width: implicitWidth
    height: root.capsuleHeight
    radius: Style.radiusL
    color: pointer.containsMouse ? Color.mHover : Qt.alpha(Color.mTertiary, 0.18)
    border.color: Color.mTertiary
    border.width: Math.max(1, Style.capsuleBorderWidth)

    RowLayout {
      id: content
      anchors.centerIn: parent
      spacing: Style.marginXS

      NIcon {
        icon: "command"
        pointSize: Style.getBarFontSizeForScreen(root.screen?.name) * 1.15
        applyUiScale: false
        color: Color.mTertiary
      }

      NText {
        text: "MODE · " + (root.mainInstance?.modeLabel || "")
        pointSize: Style.getBarFontSizeForScreen(root.screen?.name)
        applyUiScale: false
        font.family: Settings.data.ui.fontFixed
        font.weight: Style.fontWeightBold
        color: Color.mOnSurface
      }
    }
  }

  MouseArea {
    id: pointer
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    onClicked: root.mainInstance?.reset()
    onEntered: TooltipService.show(root, [["Hyprland mode", root.mainInstance?.activeSubmap || "default"], ["Action", "Click to exit mode"]], BarService.getTooltipDirection(root.screen?.name))
    onExited: TooltipService.hide()
  }
}
