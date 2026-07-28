import QtQuick 2.15
import QtTest 1.2
import "../DisplayModeOptions.js" as DisplayModeOptions

TestCase {
  name: "DisplayModeOptions"

  readonly property var modes: [
    { "id": "1920x1080@239.96", "width": 1920, "height": 1080, "refresh": 239.96 },
    { "id": "1920x1080@144", "width": 1920, "height": 1080, "refresh": 144 },
    { "id": "2560x1440@144", "width": 2560, "height": 1440, "refresh": 144 },
    { "id": "1920x1080@60", "width": 1920, "height": 1080, "refresh": 60 }
  ]

  function test_resolutionOptionsDeduplicateAdvertisedModes() {
    compare(JSON.stringify(DisplayModeOptions.resolutionOptions(modes)), JSON.stringify([
      { "key": "1920x1080", "name": "1920 × 1080" },
      { "key": "2560x1440", "name": "2560 × 1440" }
    ]));
  }

  function test_refreshOptionsOnlyIncludeSelectedResolution() {
    compare(JSON.stringify(DisplayModeOptions.refreshOptions(modes, "1920x1080")), JSON.stringify([
      { "key": "1920x1080@239.96", "name": "239.96 Hz" },
      { "key": "1920x1080@144", "name": "144.00 Hz" },
      { "key": "1920x1080@60", "name": "60.00 Hz" }
    ]));
  }

  function test_closestModePreservesPreferredRefresh() {
    compare(DisplayModeOptions.closestModeId(modes, "2560x1440", 239.96), "2560x1440@144");
    compare(DisplayModeOptions.closestModeId(modes, "1920x1080", 142), "1920x1080@144");
  }

  function test_emptyAndUnknownModesAreSafe() {
    compare(JSON.stringify(DisplayModeOptions.resolutionOptions([])), "[]");
    compare(JSON.stringify(DisplayModeOptions.refreshOptions(null, "1920x1080")), "[]");
    compare(DisplayModeOptions.closestModeId(modes, "3840x2160", 60), "");
  }
}
