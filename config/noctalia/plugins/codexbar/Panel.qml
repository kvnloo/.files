import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import qs.Commons
import qs.Services.UI
import qs.Widgets

Item {
  id: root

  property var pluginApi: null
  readonly property var mainInstance: pluginApi?.mainInstance
  readonly property var providers: mainInstance?.providers || []
  property int selectedIndex: 0
  readonly property var selectedEntry: providers.length > 0 ? providers[Math.min(selectedIndex, providers.length - 1)] : null
  readonly property var selectedWindows: selectedEntry ? mainInstance.windowsFor(selectedEntry) : []

  implicitWidth: Math.round(460 * Style.uiScaleRatio)
  implicitHeight: Math.round(570 * Style.uiScaleRatio)

  function closePanel() {
    const openScreen = pluginApi?.panelOpenScreen;
    if (openScreen)
      pluginApi.closePanel(openScreen);
  }

  function openUrl(url) {
    Quickshell.execDetached(["xdg-open", url]);
  }

  function firstNumber(source, keys) {
    if (!source || typeof source !== "object")
      return null;
    for (let i = 0; i < keys.length; i++) {
      const value = source[keys[i]];
      if (typeof value === "number")
        return value;
      if (typeof value === "string" && value.trim() !== "") {
        const parsed = Number(value.replace(/[$,]/g, ""));
        if (!isNaN(parsed))
          return parsed;
      }
    }
    return null;
  }

  function extraUsage(entry) {
    const usage = entry?.usage || {};
    const sources = [entry?.extraUsage, usage.extraUsage, usage.extra, entry?.credits];
    for (let i = 0; i < sources.length; i++) {
      const source = sources[i];
      const used = firstNumber(source, ["used", "usedUsd", "spent", "current", "usage"]);
      const limit = firstNumber(source, ["limit", "limitUsd", "budget", "maximum", "total"]);
      const remaining = firstNumber(source, ["remaining", "remainingUsd", "balance"]);
      if (used !== null || limit !== null) {
        const resolvedLimit = limit ?? 0;
        const resolvedUsed = used ?? (remaining !== null && resolvedLimit > 0 ? Math.max(0, resolvedLimit - remaining) : 0);
        return {
          available: true,
          used: resolvedUsed,
          limit: resolvedLimit,
          percent: resolvedLimit > 0 ? Math.min(100, Math.max(0, resolvedUsed / resolvedLimit * 100)) : 0
        };
      }
    }
    return { available: false, used: 0, limit: 0, percent: 0 };
  }

  function costUsage(entry) {
    const usage = entry?.usage || {};
    const cost = entry?.cost || usage.cost || usage.costs || {};
    const today = cost.today && typeof cost.today === "object" ? cost.today : {};
    const last30 = cost.last30Days || cost.last30 || cost.lastThirtyDays || {};
    const todayCost = firstNumber(today, ["cost", "usd", "amount"]) ?? firstNumber(cost, ["todayCost", "todayUsd", "costToday"]);
    const last30Cost = firstNumber(last30, ["cost", "usd", "amount"]) ?? firstNumber(cost, ["last30DaysCost", "last30Cost", "lastThirtyDaysCost"]);
    const todayTokens = today.tokens ?? today.tokenCount ?? cost.todayTokens ?? cost.tokensToday;
    const last30Tokens = last30.tokens ?? last30.tokenCount ?? cost.last30DaysTokens ?? cost.last30Tokens ?? cost.lastThirtyDaysTokens;
    return {
      available: todayCost !== null || last30Cost !== null || todayTokens !== undefined || last30Tokens !== undefined,
      todayCost: todayCost ?? 0,
      todayTokens: todayTokens ?? 0,
      last30Cost: last30Cost ?? 0,
      last30Tokens: last30Tokens ?? 0
    };
  }

  function formatMoney(value) {
    return "$" + Number(value || 0).toFixed(2);
  }

  function formatTokens(value) {
    if (typeof value === "string" && value.trim() !== "")
      return value.toLowerCase().indexOf("token") >= 0 ? value : value + " tokens";
    const amount = Number(value || 0);
    if (amount >= 1000000000)
      return (amount / 1000000000).toFixed(1).replace(/\.0$/, "") + "B tokens";
    if (amount >= 1000000)
      return (amount / 1000000).toFixed(1).replace(/\.0$/, "") + "M tokens";
    if (amount >= 1000)
      return (amount / 1000).toFixed(1).replace(/\.0$/, "") + "K tokens";
    return Math.round(amount) + " tokens";
  }

  function usageColor(percent) {
    return percent >= 90 ? Color.mError : (percent >= 70 ? Color.mTertiary : Color.mPrimary);
  }

  Connections {
    target: root.mainInstance
    function onProvidersChanged() {
      if (root.selectedIndex >= root.providers.length)
        root.selectedIndex = Math.max(0, root.providers.length - 1);
    }
  }

  NBox {
    anchors.fill: parent

    ColumnLayout {
      anchors.fill: parent
      anchors.margins: Style.marginL
      spacing: Style.marginM

      RowLayout {
        Layout.fillWidth: true
        spacing: Style.marginM

        NIcon {
          icon: "brand-openai"
          pointSize: Style.fontSizeXXL
          color: Color.mPrimary
        }

        ColumnLayout {
          Layout.fillWidth: true
          spacing: 0

          NText {
            text: "CodexBar"
            pointSize: Style.fontSizeL
            font.weight: Style.fontWeightBold
            color: Color.mOnSurface
          }

          NText {
            text: root.mainInstance?.refreshing ? "Refreshing provider usage…" : (root.mainInstance?.refreshError || "AI usage and rate limits")
            pointSize: Style.fontSizeXS
            color: root.mainInstance?.refreshError ? Color.mError : Color.mOnSurfaceVariant
            elide: Text.ElideRight
            Layout.fillWidth: true
          }
        }

        NIconButton {
          icon: root.mainInstance?.refreshing ? "loader-2" : "refresh"
          enabled: !(root.mainInstance?.refreshing ?? false)
          tooltipText: "Refresh usage"
          baseSize: Style.baseWidgetSize * 0.8
          onClicked: root.mainInstance?.refresh()
        }

        NIconButton {
          icon: "close"
          tooltipText: "Close"
          baseSize: Style.baseWidgetSize * 0.8
          onClicked: root.closePanel()
        }
      }

      RowLayout {
        Layout.fillWidth: true
        spacing: Style.marginS
        visible: root.providers.length > 0

        Repeater {
          model: root.providers

          NButton {
            required property int index
            required property var modelData
            text: root.mainInstance?.displayName(modelData.provider) || String(modelData.provider)
            icon: root.mainInstance?.providerIcon(modelData.provider) || "robot"
            outlined: index !== root.selectedIndex
            backgroundColor: index === root.selectedIndex ? Color.mPrimary : Color.mOutline
            textColor: index === root.selectedIndex ? Color.mOnPrimary : Color.mOnSurface
            fontSize: Style.fontSizeS
            Layout.fillWidth: true
            onClicked: root.selectedIndex = index
          }
        }
      }

      NScrollView {
        id: contentScroll
        Layout.fillWidth: true
        Layout.fillHeight: true
        horizontalPolicy: ScrollBar.AlwaysOff
        verticalPolicy: ScrollBar.AsNeeded
        contentWidth: availableWidth
        reserveScrollbarSpace: false
        gradientColor: Color.mSurface

        ColumnLayout {
          width: contentScroll.availableWidth
          spacing: Style.marginM

          NBox {
            Layout.fillWidth: true
            visible: root.providers.length === 0
            implicitHeight: emptyContent.implicitHeight + Style.margin2L

            ColumnLayout {
              id: emptyContent
              anchors.centerIn: parent
              spacing: Style.marginS

              NIcon {
                icon: root.mainInstance?.refreshing ? "loader-2" : "alert-circle"
                pointSize: Style.fontSizeXXL
                color: root.mainInstance?.errorText ? Color.mError : Color.mPrimary
                Layout.alignment: Qt.AlignHCenter
              }

              NText {
                text: root.mainInstance?.refreshing ? "Loading CodexBar usage…" : (root.mainInstance?.errorText || "No provider data available")
                color: Color.mOnSurfaceVariant
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
              }
            }
          }

          NBox {
            Layout.fillWidth: true
            visible: root.selectedEntry !== null
            implicitHeight: providerHeader.implicitHeight + Style.margin2L

            RowLayout {
              id: providerHeader
              anchors.fill: parent
              anchors.margins: Style.marginL
              spacing: Style.marginM

              NIcon {
                icon: root.selectedEntry ? root.mainInstance.providerIcon(root.selectedEntry.provider) : "robot"
                pointSize: Style.fontSizeXXL
                color: Color.mPrimary
              }

              ColumnLayout {
                Layout.fillWidth: true
                spacing: 0

                NText {
                  text: root.selectedEntry ? root.mainInstance.displayName(root.selectedEntry.provider) : ""
                  pointSize: Style.fontSizeXL
                  font.weight: Style.fontWeightBold
                  color: Color.mOnSurface
                }

                NText {
                  text: root.selectedEntry ? root.mainInstance.accountLabel(root.selectedEntry) : ""
                  visible: text !== ""
                  pointSize: Style.fontSizeS
                  color: Color.mOnSurfaceVariant
                  elide: Text.ElideRight
                  Layout.fillWidth: true
                }
              }

              Rectangle {
                visible: planText.text !== ""
                implicitWidth: planText.implicitWidth + Style.margin2M
                implicitHeight: planText.implicitHeight + Style.margin2S
                radius: Style.radiusL
                color: Color.mSecondaryContainer

                NText {
                  id: planText
                  anchors.centerIn: parent
                  text: root.selectedEntry ? root.mainInstance.planLabel(root.selectedEntry) : ""
                  pointSize: Style.fontSizeS
                  font.weight: Style.fontWeightSemiBold
                  color: Color.mOnSecondaryContainer
                }
              }
            }
          }

          NBox {
            Layout.fillWidth: true
            visible: root.selectedEntry?.error !== undefined && root.selectedEntry?.error !== null
            implicitHeight: providerError.implicitHeight + Style.margin2L

            NText {
              id: providerError
              anchors.fill: parent
              anchors.margins: Style.marginL
              text: root.selectedEntry?.error?.message || "Provider refresh failed"
              color: Color.mError
              wrapMode: Text.WordWrap
            }
          }

          Repeater {
            model: root.selectedWindows

            NBox {
              required property var modelData
              Layout.fillWidth: true
              implicitHeight: windowContent.implicitHeight + Style.margin2L

              ColumnLayout {
                id: windowContent
                anchors.fill: parent
                anchors.margins: Style.marginL
                spacing: Style.marginS

                RowLayout {
                  Layout.fillWidth: true

                  NText {
                    text: modelData.title
                    pointSize: Style.fontSizeM
                    font.weight: Style.fontWeightSemiBold
                    color: Color.mOnSurface
                    Layout.fillWidth: true
                  }

                  NText {
                    text: Math.round(modelData.usedPercent) + "% used"
                    pointSize: Style.fontSizeS
                    font.weight: Style.fontWeightBold
                    color: root.usageColor(modelData.usedPercent)
                  }
                }

                NLinearGauge {
                  Layout.fillWidth: true
                  Layout.preferredHeight: Math.max(6, Math.round(6 * Style.uiScaleRatio))
                  orientation: Qt.Horizontal
                  ratio: Math.max(0, Math.min(1, modelData.usedPercent / 100))
                  fillColor: root.usageColor(modelData.usedPercent)
                }

                RowLayout {
                  Layout.fillWidth: true
                  visible: modelData.resetDescription !== "" || modelData.paceDescription !== ""

                  NText {
                    text: modelData.paceDescription
                    visible: text !== ""
                    pointSize: Style.fontSizeXS
                    color: Color.mOnSurfaceVariant
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                  }

                  NText {
                    text: modelData.resetDescription === "" ? "" : "Resets " + modelData.resetDescription
                    visible: text !== ""
                    pointSize: Style.fontSizeXS
                    color: Color.mOnSurfaceVariant
                  }
                }
              }
            }
          }

          NBox {
            Layout.fillWidth: true
            visible: root.extraUsage(root.selectedEntry).available
            implicitHeight: extraContent.implicitHeight + Style.margin2L

            ColumnLayout {
              id: extraContent
              anchors.fill: parent
              anchors.margins: Style.marginL
              spacing: Style.marginS
              readonly property var summary: root.extraUsage(root.selectedEntry)

              RowLayout {
                Layout.fillWidth: true
                NText {
                  text: "Extra usage"
                  pointSize: Style.fontSizeM
                  font.weight: Style.fontWeightSemiBold
                  color: Color.mOnSurface
                  Layout.fillWidth: true
                }
                NText {
                  text: Math.round(extraContent.summary.percent) + "% used"
                  pointSize: Style.fontSizeS
                  color: root.usageColor(extraContent.summary.percent)
                }
              }

              NLinearGauge {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(6, Math.round(6 * Style.uiScaleRatio))
                orientation: Qt.Horizontal
                ratio: extraContent.summary.percent / 100
                fillColor: root.usageColor(extraContent.summary.percent)
              }

              NText {
                text: root.formatMoney(extraContent.summary.used) + " / " + root.formatMoney(extraContent.summary.limit) + " this month"
                pointSize: Style.fontSizeXS
                color: Color.mOnSurfaceVariant
              }
            }
          }

          NBox {
            Layout.fillWidth: true
            visible: root.costUsage(root.selectedEntry).available
            implicitHeight: costContent.implicitHeight + Style.margin2L

            ColumnLayout {
              id: costContent
              anchors.fill: parent
              anchors.margins: Style.marginL
              spacing: Style.marginS
              readonly property var summary: root.costUsage(root.selectedEntry)

              NText {
                text: "Cost"
                pointSize: Style.fontSizeM
                font.weight: Style.fontWeightSemiBold
                color: Color.mOnSurface
              }

              NText {
                text: "Today  " + root.formatMoney(costContent.summary.todayCost) + " · " + root.formatTokens(costContent.summary.todayTokens)
                pointSize: Style.fontSizeS
                color: Color.mOnSurfaceVariant
              }

              NText {
                text: "Last 30 days  " + root.formatMoney(costContent.summary.last30Cost) + " · " + root.formatTokens(costContent.summary.last30Tokens)
                pointSize: Style.fontSizeS
                color: Color.mOnSurfaceVariant
              }
            }
          }

          RowLayout {
            Layout.fillWidth: true
            visible: root.selectedEntry !== null
            spacing: Style.marginS

            NButton {
              text: "Usage dashboard"
              icon: "chart-bar"
              outlined: true
              Layout.fillWidth: true
              onClicked: root.openUrl("https://codexbar.app")
            }

            NButton {
              text: "Status"
              icon: "activity-heartbeat"
              outlined: true
              Layout.fillWidth: true
              onClicked: root.openUrl(root.mainInstance.statusUrl(root.selectedEntry.provider))
            }
          }
        }
      }
    }
  }
}
