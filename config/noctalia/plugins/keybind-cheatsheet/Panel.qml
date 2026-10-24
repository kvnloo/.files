import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Services.UI
import qs.Services.Compositor
import qs.Widgets
import "Presentation.js" as Presentation
import "AppShortcuts.js" as AppShortcuts

Item {
  id: root
  property var pluginApi: null
  readonly property bool exclusiveKeyboard: pluginApi?.mainInstance?.exclusiveKeyboard ?? true
  readonly property var appContextSource: pluginApi?.mainInstance ?? null
  readonly property string activeAppId: appContextSource?.activeAppId ?? ""
  readonly property string activeAppName: appContextSource?.activeAppName ?? activeAppId
  readonly property string activeAppShortcutOwnerAppId: appContextSource?.activeAppShortcutOwnerAppId ?? ""
  readonly property string activeAppShortcutStatus: appContextSource?.activeAppShortcutStatus ?? "no-app"
  readonly property string activeAppShortcutFormat: appContextSource?.activeAppShortcutFormat ?? ""
  readonly property string activeAppShortcutKeymap: appContextSource?.activeAppShortcutKeymap ?? ""
  readonly property string activeAppShortcutPrefix: appContextSource?.activeAppShortcutPrefix ?? ""
  readonly property string activeAppShortcutCatalogVersion: appContextSource?.activeAppShortcutCatalogVersion ?? ""
  readonly property var activeAppShortcutEntries: appContextSource?.activeAppShortcutEntries ?? []

  // Settings
  property var cfg: pluginApi?.pluginSettings || ({})
  property var defaults: pluginApi?.manifest?.metadata?.defaultSettings || ({})

  // Settings values
  property int settingsWidth: cfg.windowWidth ?? defaults.windowWidth ?? 1400
  property int settingsHeight: cfg.windowHeight ?? defaults.windowHeight ?? 0
  property bool autoHeight: cfg.autoHeight ?? defaults.autoHeight ?? true
  property int columnCount: cfg.columnCount ?? defaults.columnCount ?? 3
  readonly property real minimumColumnWidth: 280 * Style.uiScaleRatio
  readonly property real columnGutter: 28 * Style.uiScaleRatio
  readonly property real sectionHeaderHeight: 40 * Style.uiScaleRatio
  readonly property real bindRowHeight: 22 * Style.uiScaleRatio
  readonly property real categoryGap: 10 * Style.uiScaleRatio
  readonly property real applicationShortcutMaxHeight: Math.max(96 * Style.uiScaleRatio,
                                                                 Math.min(320 * Style.uiScaleRatio, maxScreenHeight * 0.32))
  readonly property real availableWidth: panelOpenScreen ? Math.max(1, panelOpenScreen.width - 40 * Style.uiScaleRatio) : settingsWidth
  readonly property int effectiveColumnCount: {
    var requested = Math.max(1, Math.min(4, columnCount));
    var columnGap = root.columnGutter;
    var horizontalPadding = 36 * Style.uiScaleRatio;
    var fitCount = Math.floor((Math.min(settingsWidth, availableWidth) - horizontalPadding + columnGap) /
                              (minimumColumnWidth + columnGap));
    if (requested === 1 || fitCount < 2)
      return 1;
    return Math.max(2, Math.min(requested, fitCount, 4));
  }

  // Bug 4 fix: re-evaluate rawCategories whenever Main.qml increments cheatsheetDataVersion
  property int _dataVersion: pluginApi?.mainInstance?.cheatsheetDataVersion ?? 0
  property var rawCategories: {
    var _v = _dataVersion; // force QML dependency on version counter
    return pluginApi?.pluginSettings?.cheatsheetData || [];
  }
  property var categories: []

  // Bug 5 fix: timeout if parsing never completes
  property bool loadingTimedOut: false

  Timer {
    id: loadingTimeoutTimer
    interval: 4000
    repeat: false
    running: false
    onTriggered: {
      if (root.isLoading) {
        root.loadingTimedOut = true;
      }
    }
  }

  Component.onCompleted: {
    categories = processCategories(Presentation.prepareCategories(rawCategories, pluginApi?.pluginSettings?.bindOverrides || ({})));
    applicationItems = buildApplicationItems();
    if (root.isLoading)
      loadingTimeoutTimer.start();
  }


  // Dynamic column items (up to 4 columns)
  property var columnItems: []
  property var applicationItems: []

  // Memory leak prevention: debounce column updates
  Timer {
    id: columnUpdateDebounce
    interval: 100
    repeat: false
    onTriggered: updateColumnItemsNow()
  }

  Component.onDestruction: {
    // Stop timer to prevent firing after destruction
    columnUpdateDebounce.stop();
    loadingTimeoutTimer.stop();

    // Clear column items
    columnItems = [];
  }

  onRawCategoriesChanged: {
    categories = processCategories(Presentation.prepareCategories(rawCategories, pluginApi?.pluginSettings?.bindOverrides || ({})));
    updateColumnItems();
  }

  onCategoriesChanged: {
    updateColumnItems();
    contentPreferredHeight = calculateDynamicHeight();
  }

  onColumnCountChanged: {
    updateColumnItems();
    contentPreferredHeight = calculateDynamicHeight();
  }
  onSettingsWidthChanged: {
    updateColumnItems();
    contentPreferredHeight = calculateDynamicHeight();
  }

  onEffectiveColumnCountChanged: {
    updateColumnItems();
    contentPreferredHeight = calculateDynamicHeight();
  }

  function updateSearchFocus() {
    if (!searchInput)
      return;
    const inputItem = searchInput.inputItem;
    if (!inputItem)
      return;

    if (root.pluginApi?.mainInstance?.manualVisible && root.pluginApi?.panelOpenScreen)
      inputItem.forceActiveFocus();
    else
      inputItem.focus = false;
  }

  Connections {
    target: root.pluginApi?.mainInstance
    function onManualVisibleChanged() { root.updateSearchFocus(); }
    function onActiveAppIdChanged() {
      if (applicationShortcutViewport)
        applicationShortcutViewport.contentY = 0;
      root.updateColumnItems();
    }
    function onActiveAppShortcutOwnerAppIdChanged() { root.updateColumnItems(); }
    function onActiveAppShortcutStatusChanged() { root.updateColumnItems(); }
    function onActiveAppShortcutEntriesChanged() { root.updateColumnItems(); }
    function onActiveAppShortcutKeymapChanged() { root.updateColumnItems(); }
    function onActiveAppShortcutPrefixChanged() { root.updateColumnItems(); }
    function onActiveAppShortcutCatalogVersionChanged() { root.updateColumnItems(); }
  }

  onPanelOpenScreenChanged: {
    // Recalculate height when screen becomes available (important for bar widget opening)
    contentPreferredHeight = calculateDynamicHeight();
    root.searchText = "";
    root.updateSearchFocus();
  }

  onMaxScreenHeightChanged: {
    contentPreferredHeight = calculateDynamicHeight();
  }

  function updateColumnItems() {
    columnUpdateDebounce.restart();
  }

  function updateColumnItemsNow() {
    columnItems = [];
    var assignments = distributeCategories();
    var items = [];
    for (var i = 0; i < effectiveColumnCount; i++)
      items.push(buildColumnItems(assignments[i] || []));
    columnItems = items;
    applicationItems = buildApplicationItems();
    contentPreferredHeight = calculateDynamicHeight();
  }

  // Screen height limit (90% of screen)
  property var panelOpenScreen: pluginApi?.panelOpenScreen
  property real maxScreenHeight: panelOpenScreen ? panelOpenScreen.height * 0.9 : 800

  property string searchText: ""
  onSearchTextChanged: {
    updateColumnItems();
    contentPreferredHeight = calculateDynamicHeight();
  }

  property real contentPreferredWidth: Math.min(settingsWidth, availableWidth)
  property real contentPreferredHeight: calculateDynamicHeight()
  readonly property var geometryPlaceholder: panelContainer
  readonly property bool allowAttach: false
  readonly property bool panelAnchorHorizontalCenter: true
  readonly property bool panelAnchorVerticalCenter: true
  anchors.fill: parent

  // Explicit key colors remain available as text tints; defaults use the theme.
  readonly property string keyColorAltOverride: cfg.keyColorAlt ?? ""
  readonly property string keyColorXF86Override: cfg.keyColorXF86 ?? ""
  readonly property string keyColorPrintOverride: cfg.keyColorPrint ?? ""
  readonly property string keyColorNumericOverride: cfg.keyColorNumeric ?? ""
  readonly property string keyColorMouseOverride: cfg.keyColorMouse ?? ""
  readonly property string keyColorSuperOverride: cfg.keyColorSuper ?? defaults.keyColorSuper ?? ""
  readonly property string keyColorCtrlOverride:  cfg.keyColorCtrl  ?? defaults.keyColorCtrl  ?? ""
  readonly property string keyColorShiftOverride: cfg.keyColorShift ?? defaults.keyColorShift ?? ""
  readonly property string keyColorDefaultOverride: cfg.keyColorDefault ?? ""
  readonly property string keyLabelColorOverride: cfg.keyLabelColor ?? ""
  // Empty string = theme-aware fallback (Color.mOnSurface).
  readonly property string descriptionColorOverride: cfg.descriptionTextColor || defaults.descriptionTextColor || ""
  readonly property color descriptionTextColor: descriptionColorOverride !== "" ? descriptionColorOverride : Color.mOnSurface

  // Per-key text colors; empty uses the global label tint or the key tint.
  readonly property string keyTextSuperOverride:   cfg.keyTextSuper   ?? defaults.keyTextSuper   ?? ""
  readonly property string keyTextCtrlOverride:    cfg.keyTextCtrl    ?? defaults.keyTextCtrl    ?? ""
  readonly property string keyTextShiftOverride:   cfg.keyTextShift   ?? defaults.keyTextShift   ?? ""
  readonly property string keyTextAltOverride:     cfg.keyTextAlt     ?? defaults.keyTextAlt     ?? ""
  readonly property string keyTextXF86Override:    cfg.keyTextXF86    ?? defaults.keyTextXF86    ?? ""
  readonly property string keyTextPrintOverride:   cfg.keyTextPrint   ?? defaults.keyTextPrint   ?? ""
  readonly property string keyTextNumericOverride: cfg.keyTextNumeric ?? defaults.keyTextNumeric ?? ""
  readonly property string keyTextMouseOverride:   cfg.keyTextMouse   ?? defaults.keyTextMouse   ?? ""
  readonly property string keyTextDefaultOverride: cfg.keyTextDefault ?? defaults.keyTextDefault ?? ""

  // Generic X11 modifiers also support text color and display-label overrides.
  // Empty color uses the subdued theme treatment; empty label keeps the raw token.
  readonly property string keyColorMod2Override: cfg.keyColorMod2 ?? defaults.keyColorMod2 ?? ""
  readonly property string keyColorMod3Override: cfg.keyColorMod3 ?? defaults.keyColorMod3 ?? ""
  readonly property string keyColorMod5Override: cfg.keyColorMod5 ?? defaults.keyColorMod5 ?? ""
  readonly property string keyTextMod2Override:  cfg.keyTextMod2  ?? defaults.keyTextMod2  ?? ""
  readonly property string keyTextMod3Override:  cfg.keyTextMod3  ?? defaults.keyTextMod3  ?? ""
  readonly property string keyTextMod5Override:  cfg.keyTextMod5  ?? defaults.keyTextMod5  ?? ""
  readonly property string keyLabelMod2Override: cfg.keyLabelMod2 ?? defaults.keyLabelMod2 ?? ""
  readonly property string keyLabelMod3Override: cfg.keyLabelMod3 ?? defaults.keyLabelMod3 ?? ""
  readonly property string keyLabelMod5Override: cfg.keyLabelMod5 ?? defaults.keyLabelMod5 ?? ""

  // Workspace category split tuning
  readonly property bool splitWorkspaces: cfg.splitLargeWorkspaceCategory ?? defaults.splitLargeWorkspaceCategory ?? true
  readonly property int workspaceSplitThreshold: cfg.workspaceSplitThreshold ?? defaults.workspaceSplitThreshold ?? 12

  // Data is loaded by Main.qml, we just display it
  property bool isLoading: rawCategories.length === 0

  function calculateDynamicHeight() {
    if (!autoHeight && settingsHeight > 0)
      return Math.min(settingsHeight, maxScreenHeight);

    var scale = Style.uiScaleRatio;
    if (categories.length === 0)
      return Math.min(400 * scale, maxScreenHeight);

    var assignments = distributeCategories();
    var maxColumnHeight = 0;
    for (var col = 0; col < effectiveColumnCount; col++) {
      var colHeight = 0;
      var sections = assignments[col] || [];
      for (var i = 0; i < sections.length; i++) {
        var section = sections[i];
        colHeight += root.sectionHeaderHeight;
        colHeight += Math.max(0, section.weight - 2) * root.bindRowHeight;
        if (i < sections.length - 1)
          colHeight += root.categoryGap;
      }
      maxColumnHeight = Math.max(maxColumnHeight, colHeight);
    }

    var applicationListHeight = Math.min(Math.max(1, applicationItems.length) * bindRowHeight,
                                          applicationShortcutMaxHeight);
    var applicationHeight = 74 * scale + applicationListHeight;
    if (activeAppShortcutStatus !== "ready")
      applicationHeight += 18 * scale;
    if (activeAppShortcutStatus === "ready" && AppShortcuts.isTernAppId(activeAppId))
      applicationHeight += 48 * scale;
    if (activeAppShortcutStatus === "ready" && activeAppShortcutFormat === "json")
      applicationHeight += 26 * scale;
    var totalHeight = 48 * scale + applicationHeight + categoryGap + maxColumnHeight + 34 * scale;
    return Math.max(300 * scale, Math.min(totalHeight, maxScreenHeight));
  }

  // ========== UI ==========
  Rectangle {
    id: panelContainer
    anchors.fill: parent
    color: "transparent"
    radius: Style.radiusL
    clip: true

    Rectangle {
      id: header
      anchors.top: parent.top
      anchors.left: parent.left
      anchors.right: parent.right
      height: 48 * Style.uiScaleRatio
      color: "transparent"
      radius: Style.radiusL

      RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Style.marginS
        anchors.rightMargin: Style.marginS
        spacing: 6 * Style.uiScaleRatio

        RowLayout {
          spacing: 6 * Style.uiScaleRatio

          NIcon {
            icon: "keyboard"
            pointSize: 15 * Style.uiScaleRatio
            color: Color.mOnSurfaceVariant
          }
          NText {
            text: CompositorService.isHyprland ? pluginApi?.tr("panel.title-hyprland") :
                  CompositorService.isNiri     ? pluginApi?.tr("panel.title-niri") :
                  CompositorService.isMango    ? pluginApi?.tr("panel.title-mango") :
                                                 pluginApi?.tr("panel.title")
            family: "Noto Sans"
            pointSize: 11.25
            font.weight: Font.DemiBold
            color: Color.mOnSurface
            Layout.maximumWidth: Math.min(210 * Style.uiScaleRatio,
                                          Math.max(68 * Style.uiScaleRatio, root.contentPreferredWidth * 0.22))
            elide: Text.ElideRight
          }
        }

        NText {
          visible: root.contentPreferredWidth > 1000 * Style.uiScaleRatio
          text: "Desktop shortcuts · ↩ returns to normal shortcuts"
          family: "Noto Sans"
          pointSize: 9
          font.italic: true
          color: Color.mOnSurfaceVariant
          opacity: 0.8
          Layout.leftMargin: 12 * Style.uiScaleRatio
        }

        Item { Layout.fillWidth: true }

        NTextInput {
          id: searchInput
          Layout.fillWidth: false
          Layout.preferredWidth: Math.min(340 * Style.uiScaleRatio,
                                          Math.max(92 * Style.uiScaleRatio, root.contentPreferredWidth * 0.26))
          Layout.minimumWidth: Math.min(110 * Style.uiScaleRatio, root.contentPreferredWidth * 0.24)
          Layout.maximumWidth: 340 * Style.uiScaleRatio
          placeholderText: pluginApi?.tr("panel.search-placeholder")
          text: root.searchText

          onTextChanged: {
            root.searchText = text;
            root.updateColumnItems();
          }
        }

        NIconButton {
          icon: "refresh"
          Layout.preferredWidth: 28 * Style.uiScaleRatio
          Layout.preferredHeight: 28 * Style.uiScaleRatio
          opacity: 0.72
          onClicked: {
            pluginApi?.mainInstance?.refresh();
          }
        }

        NIconButton {
          icon: "settings"
          Layout.preferredWidth: 28 * Style.uiScaleRatio
          Layout.preferredHeight: 28 * Style.uiScaleRatio
          opacity: 0.72
          onClicked: {
            var screen = pluginApi?.panelOpenScreen;
            if (screen && pluginApi?.manifest) {
              pluginApi.closePanel(screen);
              BarService.openPluginSettings(screen, pluginApi.manifest);
            }
          }
        }
      }
    }

    NText {
      id: loadingText
      anchors.centerIn: parent
      text: root.loadingTimedOut ? pluginApi?.tr("panel.loading-timeout") : pluginApi?.tr("panel.loading")
      visible: root.isLoading && !root.activeAppId
      font.pointSize: Style.fontSizeL
      color: Color.mOnSurface
    }

    NScrollView {
      id: scrollView
      visible: (!root.isLoading && root.categories.length > 0) || !!root.activeAppId
      anchors.top: header.bottom
      anchors.bottom: parent.bottom
      anchors.left: parent.left
      anchors.right: parent.right
      clip: true
      contentWidth: availableWidth
      leftPadding: 18 * Style.uiScaleRatio
      rightPadding: 18 * Style.uiScaleRatio
      topPadding: 12 * Style.uiScaleRatio
      bottomPadding: 14 * Style.uiScaleRatio

      ColumnLayout {
        width: Math.max(0, scrollView.availableWidth)
        spacing: root.categoryGap

        Rectangle {
          id: applicationShortcutSection
          Layout.fillWidth: true
          Layout.preferredHeight: implicitHeight
          Layout.minimumHeight: implicitHeight
          implicitHeight: applicationCardContent.implicitHeight + 24 * Style.uiScaleRatio
          radius: 10 * Style.uiScaleRatio
          color: Color.mSurface
          border.color: Color.mPrimary
          border.width: Style.uiScaleRatio

          ColumnLayout {
            id: applicationCardContent
            anchors.fill: parent
            anchors.margins: 12 * Style.uiScaleRatio
            spacing: 7 * Style.uiScaleRatio

            RowLayout {
              Layout.fillWidth: true
              spacing: 10 * Style.uiScaleRatio

              NIcon {
                icon: "keyboard"
                pointSize: 16 * Style.uiScaleRatio
                color: Color.mPrimary
              }

              ColumnLayout {
                Layout.fillWidth: true
                spacing: 2 * Style.uiScaleRatio

                NText {
                  text: root.localizedText("panel.application-shortcuts-title", "ACTIVE APPLICATION")
                  family: "Noto Sans"
                  pointSize: 8.5
                  font.weight: Font.DemiBold
                  color: Color.mOnSurfaceVariant
                }

                NText {
                  text: root.activeAppName || root.localizedText("panel.no-active-app", "No focused application")
                  family: "Noto Sans"
                  pointSize: 13
                  font.weight: Font.DemiBold
                  color: Color.mOnSurface
                  elide: Text.ElideRight
                  Layout.fillWidth: true
                }

                NText {
                  visible: !!root.activeAppId && root.activeAppName !== root.activeAppId
                  text: root.activeAppId
                  family: "Noto Sans"
                  pointSize: 8.5
                  color: Color.mOnSurfaceVariant
                  elide: Text.ElideRight
                  Layout.fillWidth: true
                }
              }
            }

            NText {
              visible: !!root.activeAppShortcutKeymap || !!root.activeAppShortcutPrefix
              text: root.applicationKeymapSummary()
              family: "Noto Sans"
              pointSize: 9
              color: Color.mOnSurfaceVariant
              Layout.fillWidth: true
            }

            NText {
              visible: root.activeAppShortcutStatus !== "ready"
              text: root.applicationStatusText()
              family: "Noto Sans"
              pointSize: 9
              color: Color.mOnSurfaceVariant
              wrapMode: Text.WordWrap
              Layout.fillWidth: true
            }

            Flickable {
              id: applicationShortcutViewport
              visible: root.applicationItems.length > 0
              clip: true
              boundsBehavior: Flickable.StopAtBounds
              contentWidth: width
              contentHeight: applicationShortcutList.implicitHeight
              Layout.fillWidth: true
              Layout.preferredHeight: Math.min(applicationShortcutList.implicitHeight,
                                               root.applicationShortcutMaxHeight)
              Layout.minimumHeight: Math.min(applicationShortcutList.implicitHeight,
                                             96 * Style.uiScaleRatio)
              Layout.maximumHeight: root.applicationShortcutMaxHeight

              GridLayout {
                id: applicationShortcutList
                width: applicationShortcutViewport.width
                columns: root.effectiveColumnCount
                columnSpacing: root.columnGutter
                rowSpacing: 2 * Style.uiScaleRatio
                uniformCellWidths: true

                Repeater {
                  model: root.applicationItems
                  delegate: Loader {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    Layout.columnSpan: modelData.type === "group" ? root.effectiveColumnCount : 1
                    Layout.preferredHeight: modelData.type === "group" ?
                                            Math.max(18 * Style.uiScaleRatio, item?.implicitHeight || 0) :
                                            Math.max(root.bindRowHeight, item?.implicitHeight || 0)
                    Layout.minimumHeight: Layout.preferredHeight
                    sourceComponent: modelData.type === "group" ? appGroupHeaderComponent : appBindingComponent
                    property var itemData: modelData
                  }
                }
              }

              ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
              }
            }

            NText {
              visible: AppShortcuts.isTernAppId(root.activeAppId) &&
                       root.activeAppShortcutStatus === "ready"
              text: root.localizedText(
                "panel.tern-shortcut-limit",
                "Native keyboard catalog from Tern Preferences → Keyboard; settings.json user overrides are applied. Plugin-added binds are not included. Context headings follow Tern's Keyboard preferences."
              )
              family: "Noto Sans"
              pointSize: 8.5
              color: Color.mOnSurfaceVariant
              wrapMode: Text.WordWrap
              Layout.fillWidth: true
            }

            NText {
              visible: root.activeAppShortcutFormat === "json" &&
                       root.activeAppShortcutStatus === "ready"
              text: root.localizedText(
                "panel.configured-shortcut-source",
                "This is a configured JSON shortcut list, not an application menu provided by Linux."
              )
              family: "Noto Sans"
              pointSize: 8.5
              color: Color.mOnSurfaceVariant
              wrapMode: Text.WordWrap
              Layout.fillWidth: true
            }

            NText {
              visible: root.activeAppShortcutStatus === "ready" &&
                       root.applicationItems.length === 0 &&
                       (root.activeAppShortcutFormat === "json" ||
                        AppShortcuts.isTernAppId(root.activeAppId))
              text: root.searchText ?
                    root.localizedText("panel.no-matching-app-shortcuts", "No matching application shortcuts.") :
                    root.localizedText("panel.no-configured-app-shortcuts", "No shortcuts are listed by this source.")
              family: "Noto Sans"
              pointSize: 9
              font.italic: true
              color: Color.mOnSurfaceVariant
              Layout.fillWidth: true
            }
          }
        }

        NText {
          visible: root.isLoading
          text: root.loadingTimedOut ? root.localizedText("panel.loading-timeout", "Loading timed out. Click Refresh to retry.") :
                                      root.localizedText("panel.loading", "Loading...")
          font.pointSize: Style.fontSizeL
          color: Color.mOnSurface
          Layout.alignment: Qt.AlignHCenter
        }

      RowLayout {
        id: mainLayout
        visible: root.categories.length > 0 && !root.isLoading
        width: Math.max(0, scrollView.availableWidth)
        spacing: root.columnGutter

        Repeater {
          model: root.columnItems.length

          ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            Layout.preferredWidth: Math.max(0, (mainLayout.width - mainLayout.spacing * (root.effectiveColumnCount - 1)) / root.effectiveColumnCount)
            Layout.alignment: Qt.AlignTop
            spacing: 0

            property var colItems: root.columnItems[index] || []

            Repeater {
              model: colItems
              Loader {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.preferredHeight: modelData.type === "header" ? root.sectionHeaderHeight :
                                        modelData.type === "spacer" ? root.categoryGap :
                                        Math.max(root.bindRowHeight, item?.implicitHeight || 0)
                Layout.minimumHeight: Layout.preferredHeight
                sourceComponent: modelData.type === "header" ? headerComponent :
                               (modelData.type === "spacer" ? spacerComponent : bindComponent)
                property var itemData: modelData

                Component.onDestruction: {
                  active = false;
                  sourceComponent = undefined;
                }
              }
            }
          }
        }
      }
      }
    }
  }

  Component {
    id: headerComponent
    ColumnLayout {
      Layout.fillWidth: true
      Layout.minimumWidth: 0
      implicitHeight: root.sectionHeaderHeight
      spacing: 3 * Style.uiScaleRatio

      Item {
        Layout.fillWidth: true
        Layout.preferredHeight: 10 * Style.uiScaleRatio
      }

      RowLayout {
        Layout.fillWidth: true
        Layout.preferredHeight: 15 * Style.uiScaleRatio
        spacing: 6 * Style.uiScaleRatio

        NIcon {
          icon: itemData.icon || "keyboard"
          pointSize: 11.5 * Style.uiScaleRatio
          color: Color.mOnSurfaceVariant
          opacity: 0.72
        }

        NText {
          Layout.fillWidth: true
          text: itemData.title
          family: "Noto Sans"
          pointSize: 10.25
          font.weight: Font.DemiBold
          color: Color.mPrimary
          elide: Text.ElideRight
        }
      }

      Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 1 * Style.uiScaleRatio
        color: Color.mOutline
        opacity: 0.34
      }

      Item {
        Layout.fillWidth: true
        Layout.preferredHeight: 5 * Style.uiScaleRatio
      }
    }
  }

  Component {
    id: spacerComponent
    Item {
      implicitHeight: root.categoryGap
      Layout.fillWidth: true
    }
  }
  Component {
    id: bindComponent
    RowLayout {
      id: bindRow
      Layout.fillWidth: true
      Layout.minimumWidth: 0
      implicitHeight: Math.max(root.bindRowHeight,
                               keyFlow.implicitHeight + 2 * Style.uiScaleRatio,
                               bindRow.editing ? Style.baseWidgetSize : 0)
      spacing: 10 * Style.uiScaleRatio

      property bool editing: false


      NText {
        visible: !itemData.undescribed
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        Layout.alignment: Qt.AlignVCenter
        text: itemData.desc || ""
        family: "Noto Sans"
        pointSize: 9.75
        color: root.descriptionTextColor
        elide: Text.ElideRight
        wrapMode: Text.NoWrap
        ToolTip.text: [itemData.desc, itemData.hint, itemData.rawDesc].filter(Boolean).join("\n")
        ToolTip.visible: descriptionHover.hovered && !!(itemData.rawDesc || itemData.desc)
        ToolTip.delay: 350

        HoverHandler {
          id: descriptionHover
        }
      }

      NText {
        visible: itemData.undescribed && !bindRow.editing
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        Layout.alignment: Qt.AlignVCenter
        text: pluginApi?.tr("panel.no-description")
        family: "Noto Sans"
        pointSize: 9.75
        font.italic: true
        color: Color.mOnSurfaceVariant
        elide: Text.ElideRight

        MouseArea {
          anchors.fill: parent
          cursorShape: Qt.PointingHandCursor
          onClicked: { bindRow.editing = true; descInput.text = ""; descInput.inputItem.forceActiveFocus(); }
        }
      }


      NTextInput {
        id: descInput
        visible: itemData.undescribed && bindRow.editing
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        Layout.preferredHeight: Style.baseWidgetSize
        placeholderText: pluginApi?.tr("panel.add-description-placeholder")
      }

      NIconButton {
        visible: itemData.undescribed && bindRow.editing
        Layout.preferredWidth: 20 * Style.uiScaleRatio
        Layout.preferredHeight: 20 * Style.uiScaleRatio
        opacity: 0.72
        icon: "check"
        tooltipText: pluginApi?.tr("panel.save-description")
        onClicked: {
          root.saveBindDescription(itemData.bindId, descInput.text);
          bindRow.editing = false;
        }
      }

      NIconButton {
        visible: itemData.undescribed && bindRow.editing
        Layout.preferredWidth: 20 * Style.uiScaleRatio
        Layout.preferredHeight: 20 * Style.uiScaleRatio
        opacity: 0.72
        icon: "close"
        tooltipText: pluginApi?.tr("panel.cancel")
        onClicked: { bindRow.editing = false; }
      }

      NIconButton {
        visible: itemData.undescribed && !bindRow.editing
        Layout.preferredWidth: 20 * Style.uiScaleRatio
        Layout.preferredHeight: 20 * Style.uiScaleRatio
        opacity: 0.72
        icon: "edit"
        tooltipText: pluginApi?.tr("panel.add-description")
        onClicked: { bindRow.editing = true; descInput.text = ""; descInput.inputItem.forceActiveFocus(); }
      }

      NIconButton {
        visible: itemData.undescribed && !bindRow.editing
        Layout.preferredWidth: 20 * Style.uiScaleRatio
        Layout.preferredHeight: 20 * Style.uiScaleRatio
        opacity: 0.72
        icon: "eye-off"
        tooltipText: pluginApi?.tr("panel.hide-bind")
        onClicked: { root.hideBind(itemData.bindId); }
      }
      Item {
        id: keyColumn
        Layout.preferredWidth: Math.min(166 * Style.uiScaleRatio,
                                       Math.max(88 * Style.uiScaleRatio, bindRow.width * 0.36))
        Layout.minimumWidth: keyFlow.implicitWidth
        Layout.alignment: Qt.AlignVCenter
        implicitHeight: keyFlow.implicitHeight

        Row {
          id: keyFlow
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          spacing: 3 * Style.uiScaleRatio
          property var tokens: String(itemData.keys || "").split(" + ")

          Repeater {
            model: keyFlow.tokens
            NText {
              text: {
                if (index === 0)
                  return root.formatKeyLabel(modelData);
                var previous = keyFlow.tokens[index - 1];
                var separator = root.isModifierKey(previous) && root.isModifierKey(modelData) ? " " : " + ";
                return separator + root.formatKeyLabel(modelData);
              }
              family: "Noto Sans"
              pointSize: 9.75
              font.weight: root.isModifierKey(modelData) ? Font.Normal : Font.DemiBold
              color: root.getKeyTextColor(modelData)
              opacity: root.isModifierKey(modelData) ? 0.7 : 1
            }
          }
        }
      }
      NText {
        visible: !!itemData.hint && !bindRow.editing
        Layout.alignment: Qt.AlignVCenter
        text: "↩"
        family: "Noto Sans"
        pointSize: 8.5
        font.weight: Font.Normal
        color: Color.mOnSurfaceVariant
        ToolTip.text: itemData.hint + (itemData.sourceCount > 1 && itemData.rawDesc ? "\n" + itemData.rawDesc : "")
        ToolTip.visible: hintHover.hovered
        ToolTip.delay: 350

        HoverHandler {
          id: hintHover
        }
      }
    }
  }

  Component {
    id: appGroupHeaderComponent
    RowLayout {
      Layout.fillWidth: true
      Layout.minimumWidth: 0
      implicitHeight: 18 * Style.uiScaleRatio
      spacing: 6 * Style.uiScaleRatio

      Rectangle {
        Layout.preferredWidth: 2 * Style.uiScaleRatio
        Layout.preferredHeight: 10 * Style.uiScaleRatio
        radius: Style.uiScaleRatio
        color: Color.mPrimary
      }

      NText {
        text: itemData.title || ""
        family: "Noto Sans"
        pointSize: 8.5
        font.weight: Font.DemiBold
        color: Color.mOnSurfaceVariant
        elide: Text.ElideRight
        Layout.fillWidth: true
      }
    }
  }

  Component {
    id: appBindingComponent
    RowLayout {
      id: appBindingRow
      Layout.fillWidth: true
      Layout.minimumWidth: 0
      implicitHeight: Math.max(root.bindRowHeight, appBindingDescription.implicitHeight + 2 * Style.uiScaleRatio)
      spacing: 10 * Style.uiScaleRatio

      ColumnLayout {
        id: appBindingDescription
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        spacing: 1 * Style.uiScaleRatio

        NText {
          text: itemData.desc || ""
          family: "Noto Sans"
          pointSize: 9.75
          color: root.descriptionTextColor
          elide: Text.ElideRight
          Layout.fillWidth: true
        }

        NText {
          visible: !!itemData.sourceLabel
          text: itemData.sourceLabel || ""
          family: "Noto Sans"
          pointSize: 7.5
          color: Color.mOnSurfaceVariant
          elide: Text.ElideRight
          Layout.fillWidth: true
        }
      }

      NText {
        text: root.formatApplicationKeys(itemData.keys)
        family: "Noto Sans"
        pointSize: 9.75
        font.weight: Font.DemiBold
        color: Color.mOnSurface
        elide: Text.ElideRight
        horizontalAlignment: Text.AlignRight
        Layout.maximumWidth: Math.min(260 * Style.uiScaleRatio, appBindingRow.width * 0.52)
      }
    }
  }

  function isModifierKey(keyName) {
    var key = String(keyName || "").toLowerCase();
    return key === "super" || key === "super_l" || key === "super_r" ||
           key === "ctrl" || key === "control" || key === "shift" || key === "alt" ||
           key === "mod2" || key === "mod3" || key === "mod5";
  }

  function defaultKeyColor(keyName) {
    return root.keyColorDefaultOverride ||
           (root.isModifierKey(keyName) ? Color.mOnSurfaceVariant : Color.mOnSurface);
  }

  function getKeyColor(keyName) {
    if (keyName === "Super") return root.keyColorSuperOverride || defaultKeyColor(keyName);
    if (keyName === "Ctrl") return root.keyColorCtrlOverride || defaultKeyColor(keyName);
    if (keyName === "Shift") return root.keyColorShiftOverride || defaultKeyColor(keyName);
    if (keyName === "Alt") return root.keyColorAltOverride || defaultKeyColor(keyName);
    if (keyName.startsWith("XF86")) return root.keyColorXF86Override || defaultKeyColor(keyName);
    if (keyName === "PRINT" || keyName === "Print") return root.keyColorPrintOverride || defaultKeyColor(keyName);
    if (keyName.match(/^[0-9]$/)) return root.keyColorNumericOverride || defaultKeyColor(keyName);
    if (keyName.includes("MOUSE") || keyName.includes("Wheel")) return root.keyColorMouseOverride || defaultKeyColor(keyName);
    if (keyName === "Mod2") return root.keyColorMod2Override || defaultKeyColor(keyName);
    if (keyName === "Mod3") return root.keyColorMod3Override || defaultKeyColor(keyName);
    if (keyName === "Mod5") return root.keyColorMod5Override || defaultKeyColor(keyName);
    return defaultKeyColor(keyName);
  }

  function getKeyTextColor(keyName) {
    if (keyName === "Super") return root.keyTextSuperOverride || root.keyLabelColorOverride || getKeyColor(keyName);
    if (keyName === "Ctrl") return root.keyTextCtrlOverride || root.keyLabelColorOverride || getKeyColor(keyName);
    if (keyName === "Shift") return root.keyTextShiftOverride || root.keyLabelColorOverride || getKeyColor(keyName);
    if (keyName === "Alt") return root.keyTextAltOverride || root.keyLabelColorOverride || getKeyColor(keyName);
    if (keyName.startsWith("XF86")) return root.keyTextXF86Override || root.keyLabelColorOverride || getKeyColor(keyName);
    if (keyName === "PRINT" || keyName === "Print") return root.keyTextPrintOverride || root.keyLabelColorOverride || getKeyColor(keyName);
    if (keyName.match(/^[0-9]$/)) return root.keyTextNumericOverride || root.keyLabelColorOverride || getKeyColor(keyName);
    if (keyName.includes("MOUSE") || keyName.includes("Wheel")) return root.keyTextMouseOverride || root.keyLabelColorOverride || getKeyColor(keyName);
    if (keyName === "Mod2") return root.keyTextMod2Override || root.keyLabelColorOverride || getKeyColor(keyName);
    if (keyName === "Mod3") return root.keyTextMod3Override || root.keyLabelColorOverride || getKeyColor(keyName);
    if (keyName === "Mod5") return root.keyTextMod5Override || root.keyLabelColorOverride || getKeyColor(keyName);
    return root.keyTextDefaultOverride || root.keyLabelColorOverride || getKeyColor(keyName);
  }

  // Display label for a key token. Lets users rename the generic X11 modifier
  // names (e.g. Mod3 -> "Hyper"); everything else renders as-is. Purely visual —
  // colour lookup and the cached bind still use the original token.
  function getKeyLabel(keyName) {
    if (keyName === "Mod2" && root.keyLabelMod2Override) return root.keyLabelMod2Override;
    if (keyName === "Mod3" && root.keyLabelMod3Override) return root.keyLabelMod3Override;
    if (keyName === "Mod5" && root.keyLabelMod5Override) return root.keyLabelMod5Override;
    return keyName;
  }
  function formatKeyLabel(keyName) {
    var label = Presentation.keyLabel(root.getKeyLabel(keyName));
    return label === "Return" ? "↵" : label;
  }

  // ===== Bind override helpers (shared keyed map in plugin settings) =====
  function _cloneOverrides() {
    if (!pluginApi || !pluginApi.pluginSettings) return ({});
    var src = pluginApi.pluginSettings.bindOverrides || ({});
    try { return JSON.parse(JSON.stringify(src)); } catch (e) { return ({}); }
  }

  function saveBindDescription(bindId, desc) {
    if (!pluginApi || !bindId) return;
    var o = _cloneOverrides();
    if (!o[bindId]) o[bindId] = ({});
    var trimmed = (desc || "").trim();
    if (trimmed.length === 0) {
      delete o[bindId].desc;
      if (Object.keys(o[bindId]).length === 0) delete o[bindId];
    } else {
      o[bindId].desc = trimmed;
    }
    pluginApi.pluginSettings.bindOverrides = o;
    pluginApi.saveSettings();
    pluginApi.mainInstance?.refresh();
  }

  function hideBind(bindId) {
    if (!pluginApi || !bindId) return;
    var o = _cloneOverrides();
    if (!o[bindId]) o[bindId] = ({});
    o[bindId].hidden = true;
    pluginApi.pluginSettings.bindOverrides = o;
    pluginApi.saveSettings();
    pluginApi.mainInstance?.refresh();
  }


  function localizedText(key, fallback) {
    const translated = pluginApi?.tr(key);
    return translated && translated !== key ? translated : fallback;
  }

  function applicationStatusText() {
    if (!activeAppId)
      return localizedText("panel.no-active-app-detail", "No focused application is available.");
    if (activeAppShortcutOwnerAppId !== activeAppId)
      return localizedText("panel.app-shortcuts-loading", "Reading this application's configured shortcut source...");
    if (activeAppShortcutStatus === "loading")
      return localizedText("panel.app-shortcuts-loading", "Reading this application's configured shortcut source...");
    if (activeAppShortcutStatus === "unconfigured")
      return localizedText("panel.app-shortcuts-unconfigured", "Application shortcuts are unavailable: no source is configured for this app.");
    if (activeAppShortcutStatus === "unsupported-keymap")
      return localizedText("panel.app-shortcuts-unsupported-keymap",
                           "Application shortcuts are unavailable: this Tern keymap has no native catalog in the plugin.");
    if (activeAppShortcutStatus === "unsupported")
      return localizedText("panel.app-shortcuts-unsupported", "Application shortcuts are unavailable: this source format is not supported.");
    if (activeAppShortcutStatus === "invalid")
      return localizedText("panel.app-shortcuts-invalid", "Application shortcuts are unavailable: the configured source is invalid.");
    if (activeAppShortcutStatus === "unavailable")
      return localizedText("panel.app-shortcuts-unavailable", "Application shortcut source could not be read.");
    return localizedText("panel.app-shortcuts-unavailable", "Application shortcut source is unavailable.");
  }

  function applicationKeymapSummary() {
    var parts = [];
    if (activeAppShortcutKeymap)
      parts.push(localizedText("panel.app-keymap", "Keymap") + ": " + activeAppShortcutKeymap);
    if (activeAppShortcutPrefix)
      parts.push(localizedText("panel.app-prefix", "Prefix") + ": " + formatApplicationKeys(activeAppShortcutPrefix));
    if (activeAppShortcutCatalogVersion)
      parts.push(localizedText("panel.app-catalog", "Catalog") + ": " + activeAppShortcutCatalogVersion);
    return parts.join("  ·  ");
  }

  function formatApplicationKeys(chord) {
    var labels = {
      "CTRL": "Ctrl", "CONTROL": "Ctrl", "ALT": "Alt", "OPT": "Alt",
      "SHIFT": "Shift", "CMD": "Super", "SUPER": "Super",
      "SPACE": "Space", "ENTER": "Enter", "RETURN": "Return",
      "ESC": "Esc", "ESCAPE": "Esc", "TAB": "Tab",
      "LEFT": "←", "RIGHT": "→", "UP": "↑", "DOWN": "↓",
      "PAGEUP": "PgUp", "PAGEDOWN": "PgDn", "INSERT": "Ins", "MINUS": "−"
    };
    return String(chord || "").split(">").map(function(sequence) {
      return sequence.split("+").map(function(part) {
        var token = part.trim();
        var upper = token.toUpperCase();
        if (Object.prototype.hasOwnProperty.call(labels, upper))
          return labels[upper];
        return token.length === 1 ? token.toUpperCase() :
               token.charAt(0).toUpperCase() + token.substring(1);
      }).join(" + ");
    }).join("  ›  ");
  }

  function applicationBindingMatches(binding) {
    var term = root.searchText.trim().toLowerCase();
    if (!term)
      return true;
    return String(binding.desc || "").toLowerCase().includes(term) ||
           String(binding.group || "").toLowerCase().includes(term) ||
           String(binding.keys || "").toLowerCase().includes(term) ||
           String(binding.sourceLabel || "").toLowerCase().includes(term);
  }

  function buildApplicationItems() {
    if (!activeAppId || activeAppShortcutOwnerAppId !== activeAppId ||
        activeAppShortcutStatus !== "ready")
      return [];

    var entries = activeAppShortcutEntries || [];
    var result = [];
    var currentGroup = "";
    for (var i = 0; i < entries.length; i++) {
      var entry = entries[i];
      if (!entry || typeof entry.keys !== "string" || !entry.keys ||
          typeof entry.desc !== "string" || !entry.desc ||
          !applicationBindingMatches(entry))
        continue;

      var group = String(entry.group || "").trim();
      if (group && group !== currentGroup) {
        result.push({ type: "group", title: group });
        currentGroup = group;
      } else if (!group) {
        currentGroup = "";
      }
      result.push({
        type: "binding",
        keys: entry.keys,
        desc: entry.desc,
        group: group,
        sourceLabel: entry.sourceLabel || ""
      });
    }
    return result;
  }

  function bindingMatches(binding) {
    var term = root.searchText.toLowerCase();
    if (!term) return true;
    var override = root.pluginApi?.pluginSettings?.bindOverrides?.[binding.bindId || ""];
    return String(override?.desc || binding.desc || "").toLowerCase().includes(term) ||
           String(binding.rawDesc || "").toLowerCase().includes(term) ||
           String(binding.hint || "").toLowerCase().includes(term) ||
           String(binding.keys || "").toLowerCase().includes(term);
  }

  function buildColumnItems(sections) {
    var result = [];
    if (!sections) return result;

    var bindOverrides = root.pluginApi?.pluginSettings?.bindOverrides || ({});
    for (var i = 0; i < sections.length; i++) {
      var section = sections[i];
      var cat = categories[section.index];
      if (!cat || !cat.binds) continue;

      var visibleBinds = [];
      var end = Math.min(section.end, cat.binds.length);
      for (var j = section.start; j < end; j++) {
        var bnd = cat.binds[j];
        var isUndesc = bnd.undescribed === true;
        var override = bindOverrides[bnd.bindId || ""];
        var desc = override?.desc || bnd.desc || "";
        var rawDesc = bnd.rawDesc || bnd.desc || "";
        var keys = String(bnd.keys || "");
        if (bindingMatches(bnd)) {
          visibleBinds.push({
            type: "bind",
            keys: keys,
            desc: desc,
            rawDesc: rawDesc,
            hint: bnd.hint || "",
            sourceCount: Number(bnd.sourceCount) || 1,
            bindId: bnd.bindId || "",
            undescribed: isUndesc
          });
        }
      }
      if (visibleBinds.length === 0) continue;

      if (result.length > 0)
        result.push({ type: "spacer" });
      result.push({
        type: "header",
        title: section.title,
        icon: Presentation.categoryIcon(cat.title)
      });
      for (var k = 0; k < visibleBinds.length; k++)
        result.push(visibleBinds[k]);
    }
    return result;
  }

  function processCategories(cats) {
    if (!cats || cats.length === 0) return [];
    if (!root.splitWorkspaces) return cats;

    var result = [];
    for (var i = 0; i < cats.length; i++) {
      var cat = cats[i];
      if (!cat.binds || cat.binds.length <= root.workspaceSplitThreshold) {
        result.push(cat);
        continue;
      }

      // Detect a category dominated by workspace verbs.
      // Hyprland verbs: workspace, movetoworkspace, movetoworkspacesilent, movecurrentworkspacetomonitor
      // Niri verbs:     focus-workspace, move-window-to-workspace, move-column-to-workspace
      var workspaceCount = 0;
      for (var k = 0; k < cat.binds.length; k++) {
        var v = cat.binds[k]._verb || "";
        if (v.indexOf("workspace") !== -1) workspaceCount++;
      }
      var workspaceDominated = workspaceCount >= Math.ceil(cat.binds.length * 0.6);
      if (!workspaceDominated) {
        result.push(cat);
        continue;
      }

      var switching = [], moving = [], mouse = [];
      for (var j = 0; j < cat.binds.length; j++) {
        var bind = cat.binds[j];
        var verb = bind._verb || "";
        var isMouse = (bind._mainKey || "").indexOf("MOUSE") !== -1 ||
                      (bind.keys || "").indexOf("MOUSE") !== -1 ||
                      (bind.keys || "").indexOf("Wheel") !== -1;

        if (isMouse) {
          mouse.push(bind);
        } else if (verb.indexOf("move") !== -1 || verb.indexOf("send") !== -1) {
          // Hyprland: movetoworkspace*, Niri: move-window-to-workspace, move-column-to-workspace
          moving.push(bind);
        } else {
          // Hyprland: workspace, Niri: focus-workspace
          switching.push(bind);
        }
      }

      if (switching.length > 0) result.push({ title: pluginApi?.tr("panel.workspace-switching"), binds: switching });
      if (moving.length > 0)    result.push({ title: pluginApi?.tr("panel.workspace-moving"), binds: moving });
      if (mouse.length > 0)     result.push({ title: pluginApi?.tr("panel.workspace-mouse"), binds: mouse });
    }
    return result;
  }

  function distributeCategories() {
    var numCols = Math.max(1, root.effectiveColumnCount);
    var columns = [];
    var columnWeights = [];
    for (var c = 0; c < numCols; c++) {
      columns.push([]);
      columnWeights.push(0);
    }

    var sections = [];
    var order = 0;
    for (var i = 0; i < categories.length; i++) {
      var cat = categories[i];
      var bindCount = cat.binds ? cat.binds.length : 0;
      var splitThreshold = Math.max(32, numCols * 8);
      var sliceCount = 1;
      if (bindCount > splitThreshold) {
        var slicesPerColumn = Math.max(1, Math.ceil(bindCount / (numCols * 24)));
        sliceCount = numCols * slicesPerColumn;
      }
      var sliceSize = bindCount > 0 ? Math.ceil(bindCount / sliceCount) : 1;

      for (var start = 0; start < Math.max(bindCount, 1); start += sliceSize) {
        var end = Math.min(bindCount, start + sliceSize);
        var matchingCount = 0;
        for (var matchIndex = start; matchIndex < end; matchIndex++)
          if (bindingMatches(cat.binds[matchIndex])) matchingCount++;
        if (matchingCount === 0) continue;
        sections.push({
          index: i,
          start: start,
          end: end,
          title: cat.title + (start > 0 ? " (continued)" : ""),
          weight: matchingCount + 2,
          order: order++
        });
      }
    }

    sections.sort(function(a, b) {
      return b.weight === a.weight ? a.order - b.order : b.weight - a.weight;
    });

    for (var i = 0; i < sections.length; i++) {
      var minCol = 0;
      for (var c = 1; c < numCols; c++) {
        if (columnWeights[c] < columnWeights[minCol])
          minCol = c;
      }
      columns[minCol].push(sections[i]);
      columnWeights[minCol] += sections[i].weight;
    }

    for (var c = 0; c < numCols; c++) {
      columns[c].sort(function(a, b) {
        return a.index === b.index ? a.start - b.start : a.index - b.index;
      });
    }
    return columns;
  }

}
