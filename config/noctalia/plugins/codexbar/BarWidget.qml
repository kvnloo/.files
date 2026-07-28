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
  readonly property real capsuleHeight: Style.getCapsuleHeightForScreen(screen?.name)
  readonly property int usedPercent: mainInstance?.maxUsedPercent ?? 0
  readonly property color statusColor: usedPercent >= 90 ? Color.mError : (usedPercent >= 70 ? Color.mTertiary : Color.mPrimary)

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

    Behavior on color {
      enabled: !Color.isTransitioning
      ColorAnimation {
        duration: Style.animationFast
      }
    }

    RowLayout {
      id: content
      anchors.centerIn: parent
      spacing: Style.marginXS

      NIcon {
        icon: "brand-openai"
        pointSize: Style.getBarFontSizeForScreen(root.screen?.name) * 1.25
        applyUiScale: false
        color: root.statusColor
        Layout.alignment: Qt.AlignVCenter
      }

      NText {
        text: root.mainInstance?.hasData ? root.usedPercent + "%" : "--"
        pointSize: Style.getBarFontSizeForScreen(root.screen?.name)
        applyUiScale: false
        font.weight: Style.fontWeightSemiBold
        color: Color.mOnSurface
        Layout.alignment: Qt.AlignVCenter
      }
    }
  }

  MouseArea {
    id: pointer
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton

    onClicked: function(mouse) {
      TooltipService.hide();
      if (mouse.button === Qt.LeftButton) {
        pluginApi?.togglePanel(root.screen, root);
      } else if (mouse.button === Qt.RightButton) {
        root.mainInstance?.refresh();
      } else if (mouse.button === Qt.MiddleButton) {
        Quickshell.execDetached(["xdg-open", "https://codexbar.app"]);
      }
    }

    onEntered: TooltipService.show(root, root.mainInstance?.tooltipRows() || [["CodexBar", "Loading"]], BarService.getTooltipDirection(root.screen?.name))
    onExited: TooltipService.hide()
  }
}
