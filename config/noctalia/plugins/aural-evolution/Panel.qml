import QtQuick
import QtQuick.Layouts
import Quickshell.Io
import qs.Commons
import qs.Widgets

Item {
  id: root

  property var pluginApi: null
  property var state: ({
    device: "—", mode: "native", generation: 0, active: 1,
    calibration: false, intensity: 1, variant_labels: [],
    smoke: false, smoke_profile: null
  })
  property bool busy: false
  readonly property var geometryPlaceholder: panel
  readonly property bool allowAttach: true
  property real contentPreferredWidth: 520 * Style.uiScaleRatio
  property real contentPreferredHeight: 310 * Style.uiScaleRatio
  anchors.fill: parent

  function refresh() {
    if (!busy && !status.running)
      status.running = true;
  }

  function act(args) {
    if (busy)
      return;
    busy = true;
    action.command = ["audio-evolve"].concat(args);
    action.running = true;
  }

  function variantText(index) {
    const labels = root.state.variant_labels || [];
    const prefix = String(index + 1);
    if (!root.state.calibration || !labels[index])
      return prefix;
    const intensity = root.state.active === index + 1 && root.state.intensity > 1
      ? " ×2" : "";
    return `${prefix} ${labels[index]}${intensity}`;
  }

  Component.onCompleted: refresh()

  Timer {
    interval: 1000
    repeat: true
    running: true
    onTriggered: root.refresh()
  }

  Process {
    id: status
    command: ["audio-evolve", "json"]
    stdout: StdioCollector {}
    onExited: function(exitCode) {
      if (exitCode === 0) {
        try {
          root.state = JSON.parse(stdout.text);
        } catch (_) {}
      }
    }
  }

  Process {
    id: action
    stdout: StdioCollector {}
    onExited: function(_) {
      root.busy = false;
      root.refresh();
    }
  }

  Rectangle {
    id: panel
    anchors.fill: parent
    color: "transparent"

    ColumnLayout {
      anchors {
        fill: parent
        margins: Style.marginL
      }
      spacing: Style.marginM

      RowLayout {
        Layout.fillWidth: true

        NIcon {
          icon: "wave-sine"
          pointSize: Style.fontSizeXL
          color: Color.mPrimary
        }
        NText {
          text: "Aural Evolution"
          pointSize: Style.fontSizeL
          font.weight: Font.Bold
          color: Color.mOnSurface
        }
        Item { Layout.fillWidth: true }
        NText {
          text: root.state.calibration
            ? `Calibration Smoke Test · ${root.state.mode}`
            : `${root.state.device} · ${root.state.mode} · gen ${root.state.generation}`
          pointSize: Style.fontSizeS
          color: Color.mOnSurfaceVariant
        }
        NIconButton {
          icon: "x"
          tooltipText: "Close"
          onClicked: {
            const screen = pluginApi?.panelOpenScreen;
            if (screen)
              pluginApi.closePanel(screen);
          }
        }
      }

      NText {
        text: root.state.calibration
          ? "Alt+1…0 selects · press the selected profile again for safe ×2 intensity"
          : root.state.smoke_profile === "tone"
          ? "Tone test: 1 ref · 2/3 bass ± · 4/5 body ± · 6/7 presence ± · 8/9 clarity ± · 0 warm"
          : root.state.smoke
            ? "Smoke test: 1 = reference; 2…0 get progressively quieter."
            : "Choose by sound. Revisit freely before advancing."
        pointSize: Style.fontSizeS
        color: Color.mOnSurfaceVariant
      }

      GridLayout {
        Layout.fillWidth: true
        columns: 5
        columnSpacing: Style.marginS
        rowSpacing: Style.marginS

        Repeater {
          model: 10

          NButton {
            required property int index
            readonly property bool selected: root.state.active === index + 1
            Layout.fillWidth: true
            text: root.variantText(index)
            enabled: !root.busy
            backgroundColor: selected ? Color.mPrimary : Color.mSurfaceVariant
            textColor: selected ? Color.mOnPrimary : Color.mOnSurface
            onClicked: root.act(["select", String(index + 1)])
          }
        }
      }

      NDivider {
        Layout.fillWidth: true
        opacity: 0.4
      }

      RowLayout {
        Layout.fillWidth: true
        spacing: Style.marginS

        NButton {
          Layout.fillWidth: true
          text: "Native"
          enabled: !root.busy && !root.state.smoke
          outlined: root.state.mode !== "native"
          onClicked: root.act(["mode", "native"])
        }
        NButton {
          Layout.fillWidth: true
          text: "Room"
          enabled: !root.busy && !root.state.smoke
          outlined: root.state.mode !== "room"
          onClicked: root.act(["mode", "room"])
        }
        NButton {
          Layout.fillWidth: true
          text: "Spectrum"
          enabled: !root.busy && !root.state.smoke
          outlined: root.state.mode !== "spectrum"
          onClicked: root.act(["mode", "spectrum"])
        }
        NButton {
          Layout.fillWidth: true
          text: "Colors"
          enabled: !root.busy && !root.state.smoke
          outlined: root.state.mode !== "colors"
          onClicked: root.act(["mode", "colors"])
        }
        NButton {
          Layout.fillWidth: true
          text: "Imaging"
          enabled: !root.busy && !root.state.smoke
          outlined: root.state.mode !== "imaging"
          onClicked: root.act(["mode", "imaging"])
        }
      }

      NButton {
          Layout.fillWidth: true
          text: root.state.smoke ? "Exit Smoke Test" : "Favorite → Next"
          icon: root.state.smoke ? "x" : "star"
          enabled: !root.busy
          visible: root.state.smoke || !root.state.calibration
          onClicked: root.act(root.state.smoke ? ["smoke", "stop"] : ["favorite"])
      }
    }
  }
}
