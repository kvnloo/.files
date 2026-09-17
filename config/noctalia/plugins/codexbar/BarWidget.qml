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
  readonly property var providers: mainInstance?.providers || []
  readonly property real capsuleHeight: Style.getCapsuleHeightForScreen(screen?.name)

  implicitWidth: capsule.implicitWidth
  implicitHeight: capsuleHeight

  function segmentFill(entry) {
    if (entry?.error)
      return Color.mError
    const id = String(entry?.provider || "").toLowerCase()
    if (id === "codex" || id === "openai")
      return Color.mPrimary
    if (id === "claude")
      return Color.mTertiary
    if (id === "cursor" || id === "gemini")
      return Color.mSecondary
    if (id === "grok")
      return Color.mOnSurface
    if (id === "groq")
      return Qt.rgba(Color.mTertiary.r, Color.mTertiary.g, Color.mTertiary.b, 0.72)
    if (id === "openrouter")
      return Qt.rgba(Color.mPrimary.r, Color.mPrimary.g, Color.mPrimary.b, 0.55)
    if (id === "cerebras")
      return Qt.rgba(Color.mSecondary.r, Color.mSecondary.g, Color.mSecondary.b, 0.55)
    if (id === "nous")
      return Qt.rgba(Color.mPrimary.r, Color.mPrimary.g, Color.mPrimary.b, 0.35)
    if (id === "vercel")
      return Qt.rgba(Color.mOnSurface.r, Color.mOnSurface.g, Color.mOnSurface.b, 0.5)
    return Color.mSecondary
  }

  function stackedProgress(entry) {
    if (entry?.error)
      return 1
    const remaining = mainInstance?.providerRemainingPercent(entry)
    if (remaining === undefined || remaining === null || isNaN(remaining))
      return 0
    return Math.max(0, Math.min(1, remaining / 100))
  }

  Rectangle {
    id: capsule
    anchors.centerIn: parent
    implicitWidth: Math.max(content.implicitWidth + Style.margin2M, Style.margin2M)
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

    Row {
      id: content
      objectName: "stackedBar"
      anchors.centerIn: parent
      spacing: 1
      height: Math.max(8, root.capsuleHeight * 0.36)

      Repeater {
        model: root.providers
        delegate: Rectangle {
          width: Math.max(6, Math.floor(160 / Math.max(root.providers.length, 1)))
          height: content.height
          radius: 4
          color: Qt.rgba(Color.mOnSurface.r, Color.mOnSurface.g, Color.mOnSurface.b, 0.16)

          Rectangle {
            width: parent.width * root.stackedProgress(modelData)
            height: parent.height
            radius: parent.radius
            color: root.segmentFill(modelData)
          }
        }
      }

      Rectangle {
        visible: root.providers.length === 0
        width: 160
        height: content.height
        radius: 6
        color: Qt.rgba(Color.mOnSurface.r, Color.mOnSurface.g, Color.mOnSurface.b, 0.16)
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
