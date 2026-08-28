import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qs.Commons
import qs.Widgets

Item {
  id: root
  property var pluginApi: null
  readonly property var mainInstance: pluginApi?.mainInstance
  readonly property var state: mainInstance?.snapshot || ({"overall": "idle", "lanes": ({}), "log": ""})
  property bool logsExpanded: false
  readonly property var geometryPlaceholder: panelContainer
  property real contentPreferredWidth: Math.round(520 * Style.uiScaleRatio)
  property real contentPreferredHeight: Math.round((logsExpanded ? 860 : 690) * Style.uiScaleRatio)
  readonly property bool allowAttach: true
  anchors.fill: parent

  function closePanel() {
    const screen = pluginApi?.panelOpenScreen;
    if (screen) pluginApi.closePanel(screen);
  }

  function colorFor(value) {
    if (value === "success") return Color.mPrimary;
    if (value === "failed") return Color.mError;
    if (value === "running") return Color.mTertiary;
    return Color.mOnSurfaceVariant;
  }

  component UpdateLane: NBox {
    required property string lane
    required property string title
    required property string iconName
    readonly property string laneState: String(root.state.lanes?.[lane] || "idle")
    Layout.fillWidth: true
    implicitHeight: Math.round(58 * Style.uiScaleRatio)

    RowLayout {
      anchors.fill: parent
      anchors.margins: Style.marginM
      spacing: Style.marginM
      NIcon {
        icon: parent.parent.iconName
        pointSize: Style.fontSizeL
        color: root.colorFor(parent.parent.laneState)
        rotation: parent.parent.laneState === "running" ? 360 : 0
        Behavior on rotation { NumberAnimation { duration: 900; loops: Animation.Infinite; easing.type: Easing.Linear } }
      }
      NText { text: parent.parent.title; Layout.fillWidth: true; color: Color.mOnSurface; font.weight: Style.fontWeightMedium }
      NText { text: parent.parent.laneState; color: root.colorFor(parent.parent.laneState); pointSize: Style.fontSizeXS }
    }
  }

  NBox {
    id: panelContainer
    anchors.fill: parent
    ColumnLayout {
      anchors.fill: parent
      anchors.margins: Style.marginL
      spacing: Style.marginM

      RowLayout {
        Layout.fillWidth: true
        NIcon { icon: "sparkles"; pointSize: Style.fontSizeXL; color: Color.mPrimary }
        ColumnLayout {
          Layout.fillWidth: true; spacing: 0
          NText { text: "Reforge Groot"; pointSize: Style.fontSizeM; font.weight: Style.fontWeightBold; color: Color.mOnSurface }
          NText { text: "Update every ecosystem in parallel"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
        }
        NIconButton { icon: "close"; tooltipText: "Close"; onClicked: root.closePanel() }
      }

      NBox {
        Layout.fillWidth: true
        implicitHeight: Math.round(78 * Style.uiScaleRatio)
        RowLayout {
          anchors.fill: parent; anchors.margins: Style.marginM; spacing: Style.marginM
          NIcon {
            icon: root.state.overall === "running" ? "loader-2" : (root.state.overall === "success" ? "circle-check" : "tree")
            pointSize: Style.fontSizeXL; color: root.colorFor(root.state.overall)
            rotation: root.state.overall === "running" ? 360 : 0
            Behavior on rotation { NumberAnimation { duration: 1000; loops: Animation.Infinite; easing.type: Easing.Linear } }
          }
          ColumnLayout {
            Layout.fillWidth: true; spacing: 0
            NText { text: root.state.overall === "running" ? "Reforging in progress" : (root.state.overall === "success" ? "Groot is fully reforged" : "Ready to reforge"); color: Color.mOnSurface; font.weight: Style.fontWeightBold }
            NText { text: "System · Flatpak · firmware · Rust · Python · Node"; pointSize: Style.fontSizeXS; color: Color.mOnSurfaceVariant }
          }
          NButton { text: root.state.overall === "running" ? "Running" : "Start"; icon: "player-play"; enabled: root.state.overall !== "running"; onClicked: root.mainInstance?.startUpdate() }
        }
      }

      GridLayout {
        Layout.fillWidth: true; columns: 1; columnSpacing: 0; rowSpacing: Style.marginS
        UpdateLane { lane: "system"; title: "System + AUR"; iconName: "packages" }
        UpdateLane { lane: "flatpak"; title: "Flatpak"; iconName: "box" }
        UpdateLane { lane: "firmware"; title: "Firmware"; iconName: "cpu" }
        UpdateLane { lane: "rust"; title: "Rust + Cargo"; iconName: "brand-rust" }
        UpdateLane { lane: "python"; title: "Python + pipx"; iconName: "brand-python" }
        UpdateLane { lane: "node"; title: "Node + npm"; iconName: "brand-nodejs" }
      }

      NButton {
        Layout.fillWidth: true
        text: root.logsExpanded ? "Hide live logs" : "Show live logs"
        icon: root.logsExpanded ? "chevron-up" : "chevron-down"
        onClicked: root.logsExpanded = !root.logsExpanded
      }

      NBox {
        visible: root.logsExpanded
        Layout.fillWidth: true
        Layout.fillHeight: true
        NScrollView {
          anchors.fill: parent; anchors.margins: Style.marginS
          horizontalPolicy: ScrollBar.AsNeeded; verticalPolicy: ScrollBar.AsNeeded
          TextArea {
            readOnly: true
            text: String(root.state.log || "No update logs yet.")
            color: Color.mOnSurface
            font.family: Settings.data.ui.fontFixed
            font.pixelSize: Style.fontSizeXS
            wrapMode: TextEdit.NoWrap
            background: null
          }
        }
      }
    }
  }
}
