import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import Quickshell
import qs.Commons
import qs.Widgets

Item {
  id: root

  property var pluginApi: null

  readonly property var geometryPlaceholder: panelContainer
  property real contentPreferredWidth: 1320 * Style.uiScaleRatio
  property real contentPreferredHeight: 660 * Style.uiScaleRatio
  readonly property bool allowAttach: true

  readonly property var mainInstance: pluginApi?.mainInstance
  readonly property var outputs: mainInstance ? mainInstance.draftOutputs : []
  readonly property var selectedOutput: mainInstance ? mainInstance.getSelectedOutput() : null
  readonly property string selectedOutputId: mainInstance ? mainInstance.selectedOutputId : ""

  property int activeTab: 0 // 0 = Control, 1 = Configuration
  property string editPosX: ""
  property string editPosY: ""
  property string editScale: ""

  anchors.fill: parent




  function resolutionSummary(output) {
    if (!output) {
      return "";
    }

    var scaleText = output.scale && output.scale !== 1 ? "  |  " + pluginApi?.tr("panel.scale") + ": " + output.scale : "";
    return output.resolutionLabel + scaleText;
  }

  function syncPositionInputs() {
    if (!selectedOutput) {
      editPosX = "";
      editPosY = "";
      editScale = "";
      return;
    }

    editPosX = String(selectedOutput.x);
    editPosY = String(selectedOutput.y);
    editScale = String(selectedOutput.scale);
  }

  function parseCoordinate(text, fallbackValue) {
    var parsed = parseInt((text || "").trim());
    return isFinite(parsed) ? parsed : fallbackValue;
  }

  function applyTypedPosition() {
    if (!mainInstance || !selectedOutput) {
      return;
    }

    var nextX = parseCoordinate(editPosX, selectedOutput.x);
    var nextY = parseCoordinate(editPosY, selectedOutput.y);
    mainInstance.setOutputPosition(selectedOutput.outputId, nextX, nextY, true);
    editPosX = String(nextX);
    editPosY = String(nextY);
  }

  function parseScaleValue(text, fallbackValue) {
    var parsed = Number((text || "").trim());
    return isFinite(parsed) && parsed > 0 ? parsed : fallbackValue;
  }

  function applyTypedScale() {
    if (!mainInstance || !selectedOutput) {
      return;
    }

    var nextScale = parseScaleValue(editScale, selectedOutput.scale);
    mainInstance.setOutputScale(selectedOutput.outputId, nextScale);
    editScale = String(nextScale);
  }

  onSelectedOutputChanged: {
    syncPositionInputs();
  }

  function resolutionModel(output) {
    if (!output) {
      return [];
    }

    var model = [];
    var modes = output.availableModes || [];
    for (var index = 0; index < modes.length; index++) {
      var hz = Number(modes[index].refresh || 0).toFixed(2).replace(/\.00$/, "");
      var compactLabel = modes[index].width + "x" + modes[index].height + (hz === "0" ? "" : "@" + hz);
      model.push({
        "key": modes[index].id,
        "name": compactLabel
      });
    }
    return model;
  }

  function escapeForShell(text) {
    return String(text || "").replace(/'/g, "'\\''");
  }

  function copyToClipboard(text) {
    var escaped = escapeForShell(text);
    var cmd = `printf '%s' '${escaped}' | wl-copy || printf '%s' '${escaped}' | xclip -selection clipboard || printf '%s' '${escaped}' | xsel --clipboard --input`;
    Quickshell.execDetached(["sh", "-c", cmd]);
  }

  Item {
    id: panelContainer
    anchors.fill: parent

    ColumnLayout {
      anchors.fill: parent
      anchors.margins: Style.marginL
      spacing: Style.marginL

      // Tab bar
      RowLayout {
        Layout.fillWidth: true
        spacing: Style.marginM

        NButton {
          text: pluginApi?.tr("panel.tabControl")
          onClicked: root.activeTab = 0
        }

        NButton {
          text: pluginApi?.tr("panel.tabConfiguration")
          onClicked: root.activeTab = 1
        }

        Item {
          Layout.fillWidth: true
        }
      }

      // Control tab content
      Item {
        Layout.fillWidth: true
        Layout.fillHeight: true
        visible: root.activeTab === 0

        RowLayout {
          anchors.fill: parent
          spacing: Style.marginL

          NBox {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
              anchors.fill: parent
              anchors.margins: Style.marginM
              spacing: Style.marginM

              NText {
                text: pluginApi?.tr("panel.canvasTitle")
                pointSize: Style.fontSizeL
                font.weight: Style.fontWeightBold
                color: Color.mOnSurface
              }

              NText {
                text: pluginApi?.tr("panel.dragHint")
                pointSize: Style.fontSizeS
                color: Color.mOnSurfaceVariant
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
                maximumLineCount: 2
                elide: Text.ElideRight
              }

              MonitorArrangement {
                Layout.fillWidth: true
                Layout.fillHeight: true
                mainInstance: root.mainInstance
                emptyText: pluginApi?.tr("panel.empty") || "No displays available"
              }
            }
          }

          NBox {
            Layout.preferredWidth: 320 * Style.uiScaleRatio
            Layout.minimumWidth: 320 * Style.uiScaleRatio
            Layout.maximumWidth: 320 * Style.uiScaleRatio
            Layout.fillHeight: true

            ColumnLayout {
              anchors.fill: parent
              anchors.margins: Style.marginM
              spacing: Style.marginM

              NText {
                text: pluginApi?.tr("panel.inspectorTitle")
                pointSize: Style.fontSizeL
                font.weight: Style.fontWeightBold
                color: Color.mOnSurface
              }

              NText {
                visible: !selectedOutput
                text: pluginApi?.tr("panel.selectionHint")
                pointSize: Style.fontSizeS
                color: Color.mOnSurfaceVariant
                wrapMode: Text.WordWrap
              }

              NScrollView {
                id: inspectorScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                horizontalPolicy: ScrollBar.AlwaysOff
                verticalPolicy: ScrollBar.AsNeeded
                reserveScrollbarSpace: true
                visible: !!selectedOutput

                ColumnLayout {
                  width: parent.width
                  spacing: Style.marginM

                  NText {
                    text: selectedOutput ? selectedOutput.name : ""
                    pointSize: Style.fontSizeM
                    font.weight: Style.fontWeightBold
                    color: Color.mOnSurface
                  }

                  NText {
                    Layout.fillWidth: true
                    text: selectedOutput && selectedOutput.description !== "" ? selectedOutput.description : "-"
                    pointSize: Style.fontSizeS
                    color: Color.mOnSurfaceVariant
                    wrapMode: Text.NoWrap
                    elide: Text.ElideRight
                  }

                  NText {
                    text: pluginApi?.tr("panel.resolution")
                    pointSize: Style.fontSizeS
                    color: Color.mOnSurfaceVariant
                  }

                  Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: resolutionCombo.implicitHeight

                    NComboBox {
                      id: resolutionCombo
                      anchors.left: parent.left
                      anchors.right: parent.right
                      width: parent.width
                      model: root.resolutionModel(selectedOutput)
                      currentKey: selectedOutput ? selectedOutput.modeId : ""
                      onSelected: key => {
                        if (selectedOutput && mainInstance) {
                          mainInstance.setOutputResolution(selectedOutput.outputId, key);
                        }
                      }
                    }
                  }

                  NText {
                    text: root.resolutionSummary(selectedOutput)
                    pointSize: Style.fontSizeS
                    color: Color.mOnSurfaceVariant
                    wrapMode: Text.WordWrap
                  }

                  NText {
                    text: pluginApi?.tr("panel.position")
                    pointSize: Style.fontSizeS
                    color: Color.mOnSurfaceVariant
                  }

                  RowLayout {
                    Layout.fillWidth: true
                    spacing: Style.marginS

                    NTextInput {
                      Layout.fillWidth: true
                      label: pluginApi?.tr("panel.positionX")
                      text: root.editPosX
                      onTextChanged: root.editPosX = text
                      onEditingFinished: root.applyTypedPosition()
                    }

                    NTextInput {
                      Layout.fillWidth: true
                      label: pluginApi?.tr("panel.positionY")
                      text: root.editPosY
                      onTextChanged: root.editPosY = text
                      onEditingFinished: root.applyTypedPosition()
                    }
                  }

                  NButton {
                    text: pluginApi?.tr("panel.setPosition")
                    enabled: !!selectedOutput && !!mainInstance
                    onClicked: root.applyTypedPosition()
                  }

                  NText {
                    text: pluginApi?.tr("panel.scale")
                    pointSize: Style.fontSizeS
                    color: Color.mOnSurfaceVariant
                  }

                  RowLayout {
                    Layout.fillWidth: true
                    spacing: Style.marginS

                    NTextInput {
                      id: scaleInput
                      Layout.fillWidth: true
                      text: root.editScale
                      onTextChanged: root.editScale = text
                      onEditingFinished: root.applyTypedScale()
                    }

                    NButton {
                      text: pluginApi?.tr("panel.setScale")
                      enabled: !!selectedOutput && !!mainInstance
                      onClicked: root.applyTypedScale()
                    }
                  }

                  NText {
                    text: pluginApi?.tr("panel.scaleDesc")
                    pointSize: Style.fontSizeS
                    color: Color.mOnSurfaceVariant
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                  }

                  NText {
                    text: pluginApi?.tr("panel.transform") + ": " + (selectedOutput ? selectedOutput.transform : "")
                    pointSize: Style.fontSizeS
                    color: Color.mOnSurfaceVariant
                  }

                  NText {
                    text: pluginApi?.tr("panel.backend") + ": " + (mainInstance ? mainInstance.backendId : "")
                    pointSize: Style.fontSizeS
                    color: Color.mOnSurfaceVariant
                  }

                }
              }

              NText {
                visible: mainInstance && mainInstance.statusText !== ""
                text: mainInstance ? mainInstance.statusText : ""
                pointSize: Style.fontSizeS
                color: Color.mPrimary
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
              }

              NText {
                visible: mainInstance && mainInstance.errorText !== ""
                text: mainInstance ? mainInstance.errorText : ""
                pointSize: Style.fontSizeS
                color: Color.mError
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
              }

              NText {
                visible: mainInstance && mainInstance.hasPendingChanges
                text: pluginApi?.tr("panel.pendingChanges")
                pointSize: Style.fontSizeS
                color: Color.mPrimary
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
              }

              NButton {
                Layout.fillWidth: true
                text: pluginApi?.tr("actions.refresh")
                enabled: mainInstance && !mainInstance.isRefreshing && !mainInstance.isApplying
                onClicked: mainInstance.refreshOutputs()
              }

              NButton {
                Layout.fillWidth: true
                text: pluginApi?.tr("actions.reset")
                enabled: mainInstance && mainInstance.hasPendingChanges && !mainInstance.isApplying
                onClicked: mainInstance.resetDraftOutputs()
              }

              NButton {
                Layout.fillWidth: true
                text: pluginApi?.tr("actions.apply")
                enabled: mainInstance && mainInstance.hasPendingChanges && !mainInstance.isApplying
                onClicked: mainInstance.applyLayout()
              }
            }
          }
        }
      }

      // Configuration tab content
      Item {
        Layout.fillWidth: true
        Layout.fillHeight: true
        visible: root.activeTab === 1

        NBox {
          anchors.fill: parent

          ColumnLayout {
            anchors.fill: parent
            anchors.margins: Style.marginM
            spacing: Style.marginM

            NText {
              text: pluginApi?.tr("panel.configTitle")
              pointSize: Style.fontSizeL
              font.weight: Style.fontWeightBold
              color: Color.mOnSurface
            }

            NText {
              text: pluginApi?.tr("panel.configDescription")
              pointSize: Style.fontSizeS
              color: Color.mOnSurfaceVariant
              wrapMode: Text.WordWrap
              Layout.fillWidth: true
            }

            NText {
              visible: mainInstance && mainInstance.errorText !== ""
              text: mainInstance ? mainInstance.errorText : ""
              pointSize: Style.fontSizeS
              color: Color.mError
              wrapMode: Text.WordWrap
              Layout.fillWidth: true
            }

            Item {
              Layout.fillWidth: true
              Layout.fillHeight: true

              NScrollView {
                anchors.fill: parent
                horizontalPolicy: ScrollBar.AsNeeded
                verticalPolicy: ScrollBar.AsNeeded

                NBox {
                  width: parent.width - 12 * Style.uiScaleRatio
                  border.color: Color.mOutline
                  border.width: Style.borderS

                  ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Style.marginM
                    spacing: Style.marginS

                    NText {
                      text: {
                        if (!mainInstance) return "";
                        var cfg = mainInstance.getConfigurationScript();
                        if (cfg.error) return cfg.error;
                        return cfg.content || "";
                      }
                      pointSize: Style.fontSizeS
                      font.family: "Monospace"
                      color: Color.mOnSurfaceVariant
                      wrapMode: Text.Wrap
                      textFormat: Text.PlainText
                      Layout.fillWidth: true
                      Layout.fillHeight: true
                    }
                  }
                }
              }
            }

            RowLayout {
              Layout.fillWidth: true
              spacing: Style.marginM

              NButton {
                Layout.fillWidth: true
                text: pluginApi?.tr("actions.copyConfig")
                enabled: mainInstance && !mainInstance.getConfigurationScript().error
                onClicked: {
                  var cfg = mainInstance.getConfigurationScript();
                  if (!cfg.error) {
                    var backend = cfg.backend || "unknown";
                    var header = "# " + backend + " monitor configuration\n";
                    var fullText = header + cfg.content;

                    copyToClipboard(fullText);
                    mainInstance.statusText = pluginApi?.tr("status.configCopied");
                  }
                }
              }

              NButton {
                text: pluginApi?.tr("actions.refresh")
                enabled: mainInstance && !mainInstance.isRefreshing && !mainInstance.isApplying
                onClicked: mainInstance.refreshOutputs()
              }
            }
          }
        }
      }
    }
  }
}
