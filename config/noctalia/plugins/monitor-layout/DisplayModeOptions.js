.pragma library

function resolutionKey(mode) {
  if (!mode)
    return "";
  var width = Number(mode.width || 0);
  var height = Number(mode.height || 0);
  return width > 0 && height > 0 ? width + "x" + height : "";
}

function resolutionOptions(modes) {
  var rows = [];
  var seen = {};
  modes = modes || [];
  for (var index = 0; index < modes.length; index++) {
    var key = resolutionKey(modes[index]);
    if (key === "" || seen[key])
      continue;
    seen[key] = true;
    rows.push({
      "key": key,
      "name": Number(modes[index].width) + " × " + Number(modes[index].height)
    });
  }
  return rows;
}

function refreshOptions(modes, selectedResolution) {
  var rows = [];
  modes = modes || [];
  for (var index = 0; index < modes.length; index++) {
    var mode = modes[index];
    if (resolutionKey(mode) !== selectedResolution)
      continue;
    rows.push({
      "key": String(mode.id || ""),
      "name": Number(mode.refresh || 0).toFixed(2) + " Hz"
    });
  }
  return rows;
}

function closestModeId(modes, selectedResolution, preferredRefresh) {
  var bestId = "";
  var bestDifference = Number.MAX_VALUE;
  var targetRefresh = Number(preferredRefresh || 0);
  modes = modes || [];
  for (var index = 0; index < modes.length; index++) {
    var mode = modes[index];
    if (resolutionKey(mode) !== selectedResolution)
      continue;
    var difference = Math.abs(Number(mode.refresh || 0) - targetRefresh);
    if (difference < bestDifference) {
      bestId = String(mode.id || "");
      bestDifference = difference;
    }
  }
  return bestId;
}
