import QtQuick
import qs.Commons
import qs.Widgets

Item {
  id: root

  property var mainInstance: null
  property string emptyText: "No displays available"
  readonly property var outputs: mainInstance?.draftOutputs || []
  readonly property string selectedOutputId: mainInstance?.selectedOutputId || ""
  readonly property real padding: 20 * Style.uiScaleRatio
  readonly property var bounds: sceneBounds()
  readonly property real sceneScale: Math.max(0.0001, Math.min((width - 2 * padding) / bounds.width, (height - 2 * padding) / bounds.height))
  readonly property real originX: (width - bounds.width * sceneScale) / 2
  readonly property real originY: (height - bounds.height * sceneScale) / 2
  enabled: mainInstance !== null && !mainInstance.isApplying && !mainInstance.isRefreshing
  clip: true

  function sceneBounds() {
    if (outputs.length === 0)
      return { minX: 0, minY: 0, width: 1920, height: 1080 };
    var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (var output of outputs) {
      minX = Math.min(minX, output.x);
      minY = Math.min(minY, output.y);
      maxX = Math.max(maxX, output.x + (output.logicalWidth || output.width));
      maxY = Math.max(maxY, output.y + (output.logicalHeight || output.height));
    }
    return { minX: minX, minY: minY, width: Math.max(1, maxX - minX), height: Math.max(1, maxY - minY) };
  }

  NBox {
    anchors.fill: parent
    border.color: Color.mOutline
    border.width: Style.borderS
    color: Qt.alpha(Color.mSurfaceVariant, 0.45)
  }

  NText {
    anchors.centerIn: parent
    visible: root.outputs.length === 0
    text: root.emptyText
    color: Color.mOnSurfaceVariant
  }

  Repeater {
    model: root.outputs

    delegate: Item {
      id: tile
      required property var modelData
      readonly property var output: modelData
      property point pressScene: Qt.point(0, 0)
      property point pressPosition: Qt.point(0, 0)
      property point offset: Qt.point(0, 0)
      property real pressScale: 1
      property bool dragging: false
      objectName: "monitorTile-" + output.outputId
      x: root.originX + (output.x - root.bounds.minX) * root.sceneScale + offset.x
      y: root.originY + (output.y - root.bounds.minY) * root.sceneScale + offset.y
      width: Math.max(18, (output.logicalWidth || output.width) * root.sceneScale)
      height: Math.max(16, (output.logicalHeight || output.height) * root.sceneScale)
      z: dragging ? 3 : output.outputId === root.selectedOutputId ? 2 : 1
      clip: true

      NBox {
        anchors.fill: parent
        color: output.outputId === root.selectedOutputId ? Qt.alpha(Color.mPrimary, 0.22) : Color.mSurface
        border.color: output.outputId === root.selectedOutputId ? Color.mPrimary : Color.mOutline
        border.width: output.outputId === root.selectedOutputId ? 2 : 1
      }

      Column {
        anchors.centerIn: parent
        width: Math.max(0, parent.width - 8)
        spacing: 3
        NText {
          width: parent.width
          text: tile.output.name
          color: Color.mOnSurface
          font.weight: Style.fontWeightBold
          pointSize: Style.fontSizeS
          horizontalAlignment: Text.AlignHCenter
          elide: Text.ElideRight
        }
        NText {
          width: parent.width
          visible: tile.height > 52 * Style.uiScaleRatio
          text: tile.output.x + ", " + tile.output.y
          color: Color.mOnSurfaceVariant
          pointSize: Style.fontSizeXXS
          horizontalAlignment: Text.AlignHCenter
          elide: Text.ElideRight
        }
      }

      MouseArea {
        id: mouseArea
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        preventStealing: true
        hoverEnabled: true
        cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        onPressed: mouse => {
          tile.pressScene = mapToItem(root, mouse.x, mouse.y);
          tile.pressPosition = Qt.point(tile.output.x, tile.output.y);
          tile.pressScale = root.sceneScale;
          tile.offset = Qt.point(0, 0);
          tile.dragging = true;
          root.mainInstance.selectOutput(tile.output.outputId);
        }
        onPositionChanged: mouse => {
          if (!tile.dragging || !(mouse.buttons & Qt.LeftButton)) return;
          var point = mapToItem(root, mouse.x, mouse.y);
          tile.offset = Qt.point(point.x - tile.pressScene.x, point.y - tile.pressScene.y);
        }
        onReleased: mouse => {
          if (!tile.dragging) return;
          var point = mapToItem(root, mouse.x, mouse.y);
          var id = tile.output.outputId;
          var x = tile.pressPosition.x + (point.x - tile.pressScene.x) / tile.pressScale;
          var y = tile.pressPosition.y + (point.y - tile.pressScene.y) / tile.pressScale;
          tile.dragging = false;
          tile.offset = Qt.point(0, 0);
          // A selection click must not snap an existing off-grid position.
          if (Math.hypot(point.x - tile.pressScene.x, point.y - tile.pressScene.y) < mouseArea.drag.threshold)
            return;
          if (root.mainInstance)
            root.mainInstance.setOutputPosition(id, x, y, true);
        }
        onCanceled: {
          tile.dragging = false;
          tile.offset = Qt.point(0, 0);
        }
      }
    }
  }
}
