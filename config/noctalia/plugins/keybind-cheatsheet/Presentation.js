.pragma library

var categoryOrder = [
  "Applications",
  "Window focus",
  "Window layout",
  "Workspaces",
  "Groups",
  "Media/audio",
  "System",
  "Screenshots",
  "Wallpaper",
  "Clipboard",
  "Cheatsheet controls",
  "Shortcut modes",
  "Other shortcuts"
];

var genericCategoryNames = {
  "": true,
  "all": true,
  "all shortcuts": true,
  "bindings": true,
  "default": true,
  "general": true,
  "key binds": true,
  "keybinds": true,
  "keyboard shortcuts": true,
  "misc": true,
  "miscellaneous": true,
  "other": true,
  "shortcuts": true
};

function copyFields(source) {
  var copy = {};
  for (var key in source) {
    if (Object.prototype.hasOwnProperty.call(source, key)) {
      copy[key] = source[key];
    }
  }
  return copy;
}

function reconstructedCommand(binding) {
  var verb = typeof binding._verb === "string" ? binding._verb.trim() : "";
  if (!verb) return "";

  var param = typeof binding._param === "string" ? binding._param.trim() : "";
  if (param) return verb + " " + param;

  var description = typeof binding.desc === "string" ? binding.desc.trim() : "";
  var plainVerb = verb.split("#")[0].trim();
  if (description && description.toLowerCase().indexOf(plainVerb.toLowerCase()) === 0 &&
      (description.length === plainVerb.length || /\s/.test(description.charAt(plainVerb.length)))) {
    return description;
  }
  if (binding._merged === true && binding._mainKey) {
    return verb + " " + String(binding._mainKey);
  }
  return verb;
}

function sourceDescription(binding) {
  if (typeof binding.rawDesc === "string") return binding.rawDesc;
  var description = typeof binding.desc === "string" ? binding.desc : "";
  var command = reconstructedCommand(binding);
  if (!command) return description;
  if (description.trim().replace(/\s+/g, " ") === command.trim().replace(/\s+/g, " ")) {
    return description;
  }
  return command;
}

function hasExplicitDescription(binding, rawDesc) {
  if (typeof binding.desc !== "string") return false;
  return binding.desc.trim().replace(/\s+/g, " ") !== String(rawDesc || "").trim().replace(/\s+/g, " ");
}

function normalizedCategoryTitle(title) {
  if (typeof title !== "string") return "";
  return title.trim().toLowerCase().replace(/[_-]+/g, " ").replace(/\s+/g, " ");
}

function meaningfulCategory(title) {
  if (typeof title !== "string") return "";
  var trimmed = title.trim();
  var normalized = normalizedCategoryTitle(trimmed);
  return Object.prototype.hasOwnProperty.call(genericCategoryNames, normalized) ? "" : trimmed;
}

function normalizedVerb(binding, rawDesc) {
  var verb = typeof binding._verb === "string" ? binding._verb : "";
  verb = verb.split("#")[0].trim().toLowerCase();
  if (verb) return verb.split(/\s+/)[0];

  var match = String(rawDesc || "").trim().match(/^([a-z][a-z0-9_-]*)\b/i);
  return match ? match[1].toLowerCase() : "";
}

function parameter(binding) {
  return typeof binding._param === "string" ? binding._param.trim() : "";
}

function cleanCommand(command) {
  return String(command || "").replace(/\s+#.*$/, "").replace(/\s+/g, " ").trim();
}

function hasExecutable(command, executable) {
  var text = String(command || "").toLowerCase();
  var name = executable.toLowerCase();
  var offset = 0;

  while ((offset = text.indexOf(name, offset)) !== -1) {
    var before = offset === 0 ? "" : text.charAt(offset - 1);
    var afterIndex = offset + name.length;
    var after = afterIndex >= text.length ? "" : text.charAt(afterIndex);
    var validBefore = offset === 0 || before === "/" || /\s|[|&;]/.test(before);
    var validAfter = afterIndex >= text.length || /\s|[|&;]/.test(after);
    if (validBefore && validAfter) return true;
    offset = afterIndex;
  }
  return false;
}

function directionName(value) {
  var direction = String(value || "").trim().toLowerCase();
  if (direction === "l" || direction === "left") return "left";
  if (direction === "r" || direction === "right") return "right";
  if (direction === "u" || direction === "up") return "up";
  if (direction === "d" || direction === "down") return "down";
  return "";
}

function readableFallback(rawDesc) {
  var text = String(rawDesc || "").trim();
  text = text.replace(/^exec\s+/i, "").replace(/\s+/g, " ");
  return text ? "Run: " + text : "Run command";
}

function describeExec(binding, rawDesc) {
  var command = parameter(binding);
  if (!command) command = String(rawDesc || "").replace(/^\s*exec\s+/i, "");
  command = cleanCommand(command);
  var lower = command.toLowerCase();

  if (hasExecutable(command, "workspace-copilot")) {
    if (/\bcommit-next\b/i.test(command)) {
      return { category: "Applications", desc: "Run Workspace Copilot: commit next" };
    }
    return { category: "Applications", desc: "Run Workspace Copilot" };
  }
  if (hasExecutable(command, "kitty")) {
    return { category: "Applications", desc: "Open Kitty terminal" };
  }
  if (hasExecutable(command, "nautilus")) {
    return { category: "Applications", desc: "Open Files" };
  }
  if (hasExecutable(command, "qs") && lower.indexOf("call launcher toggle") !== -1) {
    return { category: "Applications", desc: "Toggle Noctalia launcher" };
  }
  if (hasExecutable(command, "rofi") && lower.indexOf("-show window") !== -1) {
    return { category: "Window focus", desc: "Switch windows" };
  }
  if (hasExecutable(command, "rofi") && lower.indexOf("-show run") !== -1) {
    return { category: "Applications", desc: "Open application launcher" };
  }
  if (hasExecutable(command, "keybind-cheatsheet.py")) {
    return { category: "Applications", desc: "Open keyboard shortcuts" };
  }
  if (hasExecutable(command, "workspace-atlas.py")) {
    return { category: "Applications", desc: "Open workspace atlas" };
  }
  if (lower.indexOf("cliphist list") !== -1 && hasExecutable(command, "wl-copy")) {
    return { category: "Clipboard", desc: "Paste from clipboard history" };
  }

  if (hasExecutable(command, "grim")) {
    var selectedArea = lower.indexOf("-g ") !== -1;
    var toClipboard = hasExecutable(command, "wl-copy") || /\|\s*wl-copy\b/i.test(command);
    if (selectedArea && toClipboard) {
      return { category: "Screenshots", desc: "Capture selected area to clipboard" };
    }
    if (selectedArea) {
      return { category: "Screenshots", desc: "Capture selected area to a file" };
    }
    if (toClipboard) {
      return { category: "Screenshots", desc: "Capture full screen to clipboard" };
    }
    return { category: "Screenshots", desc: "Capture full screen to a file" };
  }

  if (hasExecutable(command, "wpctl")) {
    if (/\bset-volume\b/i.test(command) && /5%\+/i.test(command)) {
      return { category: "Media/audio", desc: "Increase output volume" };
    }
    if (/\bset-volume\b/i.test(command) && /5%-/i.test(command)) {
      return { category: "Media/audio", desc: "Decrease output volume" };
    }
    if (/\bset-mute\b/i.test(command)) {
      return { category: "Media/audio", desc: "Toggle output mute" };
    }
  }
  if (hasExecutable(command, "playerctl")) {
    if (/\bplay-pause\b/i.test(command)) {
      return { category: "Media/audio", desc: "Play or pause media" };
    }
    if (/\bnext\b/i.test(command)) {
      return { category: "Media/audio", desc: "Play next track" };
    }
    if (/\bprevious\b/i.test(command)) {
      return { category: "Media/audio", desc: "Play previous track" };
    }
  }
  if (hasExecutable(command, "audio-evolve")) {
    var preset = command.match(/\bselect\s+([^\s]+)/i);
    return {
      category: "Media/audio",
      desc: preset ? "Select audio preset " + preset[1] : "Select audio preset"
    };
  }
  if (hasExecutable(command, "audio-sink")) {
    var sink = command.match(/\baudio-sink\s+([^\s]+)/i);
    var sinkNames = {
      bitperfect: "Bit-perfect",
      bs2b: "BS2B crossfeed",
      room: "Room DSP",
      aural: "Aural Evolution"
    };
    var sinkLabel = sink ? sinkNames[sink[1].toLowerCase()] || sink[1] : "";
    return {
      category: "Media/audio",
      desc: sinkLabel ? "Select " + sinkLabel + " audio profile" : "Select audio profile"
    };
  }
  if (hasExecutable(command, "systemctl") && lower.indexOf("restart pipewire") !== -1) {
    return { category: "Media/audio", desc: "Restart the audio stack" };
  }
  if (hasExecutable(command, "speak-selection.sh")) {
    return { category: "Media/audio", desc: "Speak selected text" };
  }

  if (hasExecutable(command, "night-mode.sh")) {
    if (/\bon\b/i.test(command)) return { category: "System", desc: "Turn night mode on" };
    if (/\boff\b/i.test(command)) return { category: "System", desc: "Turn night mode off" };
    return { category: "System", desc: "Change night mode" };
  }
  if (hasExecutable(command, "hyprlock")) {
    return { category: "System", desc: "Lock the screen" };
  }
  if (hasExecutable(command, "systemctl")) {
    if (/\bsuspend\b/i.test(command)) return { category: "System", desc: "Suspend the computer" };
    if (/\breboot\b/i.test(command)) return { category: "System", desc: "Restart the computer" };
    if (/\bpoweroff\b/i.test(command)) return { category: "System", desc: "Shut down the computer" };
  }
  if (hasExecutable(command, "reload-desktop.sh")) {
    return { category: "System", desc: "Reload desktop configuration" };
  }
  if (hasExecutable(command, "bar-mode.sh")) {
    return { category: "System", desc: "Switch desktop panel" };
  }
  if (hasExecutable(command, "performance-mode")) {
    return { category: "System", desc: "Toggle performance mode" };
  }
  if (hasExecutable(command, "phone-display.sh")) {
    return { category: "System", desc: "Toggle phone display" };
  }

  if (hasExecutable(command, "hypr-gaps.sh")) {
    if (/\bincrease\b/i.test(command)) return { category: "Window layout", desc: "Increase window gaps" };
    if (/\bdecrease\b/i.test(command)) return { category: "Window layout", desc: "Decrease window gaps" };
    if (/\breset\b/i.test(command)) return { category: "Window layout", desc: "Reset window gaps" };
  }
  if (hasExecutable(command, "desktop-wallpaper-picker.sh")) {
    return { category: "Wallpaper", desc: "Choose a wallpaper" };
  }
  if (hasExecutable(command, "desktop-wallpaper-step.py")) {
    if (/\bprevious\b/i.test(command)) return { category: "Wallpaper", desc: "Show previous wallpaper" };
    if (/\bnext\b/i.test(command)) return { category: "Wallpaper", desc: "Show next wallpaper" };
  }
  if (hasExecutable(command, "wallpaper-mode.sh")) {
    if (/\bcycle\b/i.test(command)) return { category: "Wallpaper", desc: "Cycle wallpaper mode" };
    if (/\btoggle\b/i.test(command)) return { category: "Wallpaper", desc: "Pause or resume wallpaper engine" };
    var drawMode = command.match(/\bdraw\s+([^\s]+)/i);
    if (drawMode) return { category: "Wallpaper", desc: "Set wallpaper layout: " + drawMode[1] };
  }

  return { category: "Other shortcuts", desc: readableFallback(rawDesc || command) };
}

function classifyBinding(binding, rawDesc) {
  var verb = normalizedVerb(binding, rawDesc);
  var param = parameter(binding);
  var lowerParam = param.toLowerCase();

  if (verb === "exec") return describeExec(binding, rawDesc);

  if (verb === "global") {
    var globalAction = param.substring(param.lastIndexOf(":") + 1).toLowerCase();
    var globalLabels = {
      "down-left": "Notify shortcuts helper: left key down",
      "down-right": "Notify shortcuts helper: right key down",
      "show-left": "Show shortcuts on the left",
      "show-right": "Show shortcuts on the right"
    };
    return {
      category: "Cheatsheet controls",
      desc: globalLabels[globalAction] || (param ? "Global action: " + param : readableFallback(rawDesc))
    };
  }

  if (verb === "movefocus") {
    var focusDirection = directionName(param);
    return {
      category: "Window focus",
      desc: focusDirection ? "Focus window " + focusDirection : readableFallback(rawDesc)
    };
  }
  if (verb === "focuscurrentorlast") {
    return { category: "Window focus", desc: "Switch to previous window" };
  }
  if (verb === "killactive") {
    return { category: "Window focus", desc: "Close active window" };
  }
  if (verb === "movewindoworgroup") {
    var groupDirection = directionName(param);
    return {
      category: "Groups",
      desc: groupDirection ? "Move window or group " + groupDirection : "Move window or group"
    };
  }
  if (verb === "togglegroup") {
    return { category: "Groups", desc: "Toggle window group" };
  }
  if (verb === "changegroupactive") {
    return {
      category: "Groups",
      desc: lowerParam === "f" ? "Focus next group tab" : lowerParam === "b" ? "Focus previous group tab" : "Change active group tab"
    };
  }
  if (verb === "moveoutofgroup") {
    return { category: "Groups", desc: "Move window out of group" };
  }

  if (verb === "workspace") {
    return { category: "Workspaces", desc: param ? "Go to workspace " + param : "Go to workspace" };
  }
  if (verb === "movetoworkspace" || verb === "movetoworkspacesilent") {
    if (lowerParam === "special") {
      return { category: "Workspaces", desc: "Move window to special workspace" };
    }
    return { category: "Workspaces", desc: param ? "Move window to workspace " + param : "Move window to workspace" };
  }
  if (verb === "movecurrentworkspacetomonitor") {
    var monitorDirection = directionName(param);
    return {
      category: "Workspaces",
      desc: monitorDirection ? "Move workspace to monitor " + monitorDirection : "Move workspace to another monitor"
    };
  }
  if (verb === "togglespecialworkspace") {
    return {
      category: "Workspaces",
      desc: lowerParam === "scratch_term" ? "Toggle scratch terminal" : "Toggle special workspace"
    };
  }

  if (verb === "fullscreen") {
    return { category: "Window layout", desc: "Toggle fullscreen" };
  }
  if (verb === "togglefloating") {
    return { category: "Window layout", desc: "Toggle floating window" };
  }
  if (verb === "centerwindow") {
    return { category: "Window layout", desc: "Center window" };
  }
  if (verb === "resizewindowpixel") {
    var exactSize = param.match(/\bexact\s+(\S+)\s+(\S+)/i);
    return {
      category: "Window layout",
      desc: exactSize ? "Set window size to " + exactSize[1] + " × " + exactSize[2] + " px" : "Resize window: " + param
    };
  }
  if (verb === "resizeactive") {
    var delta = param.match(/^(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)/);
    if (delta) {
      var dx = Number(delta[1]);
      var dy = Number(delta[2]);
      var sizeChange = dx < 0 ? "narrower by " + Math.abs(dx) + " px" : dx > 0 ? "wider by " + dx + " px" : "";
      var heightChange = dy < 0 ? "shorter by " + Math.abs(dy) + " px" : dy > 0 ? "taller by " + dy + " px" : "";
      var changes = [];
      if (sizeChange) changes.push(sizeChange);
      if (heightChange) changes.push(heightChange);
      return {
        category: "Window layout",
        desc: changes.length ? "Resize active window: " + changes.join(" and ") : "Resize active window"
      };
    }
    return { category: "Window layout", desc: param ? "Resize active window: " + param : "Resize active window" };
  }
  if (verb === "layoutmsg") {
    if (/^preselect\s+l\b/i.test(param)) return { category: "Window layout", desc: "Preselect left split" };
    if (/^preselect\s+d\b/i.test(param)) return { category: "Window layout", desc: "Preselect bottom split" };
    if (/^togglesplit\b/i.test(param)) return { category: "Window layout", desc: "Toggle split direction" };
    return { category: "Window layout", desc: param ? "Arrange windows: " + param : "Arrange windows" };
  }
  if (verb === "movewindow") {
    return { category: "Window layout", desc: "Move window with mouse" };
  }
  if (verb === "resizewindow") {
    return { category: "Window layout", desc: "Resize window with mouse" };
  }

  if (verb === "submap") {
    if (lowerParam === "reset") {
      return { category: "Shortcut modes", desc: "Return to normal shortcuts" };
    }
    if (lowerParam.indexOf("wallpaper") === 0) {
      return { category: "Wallpaper", desc: "Open wallpaper layout shortcuts" };
    }
    if (lowerParam.indexOf("system") === 0) {
      return { category: "System", desc: "Open system actions" };
    }
    if (lowerParam === "resize") {
      return { category: "Window layout", desc: "Enter window resize mode" };
    }
    return { category: "Shortcut modes", desc: param ? "Open shortcut mode: " + param : "Open shortcut mode" };
  }

  if (verb === "exit") {
    return { category: "System", desc: "Exit Hyprland" };
  }

  return { category: "Other shortcuts", desc: readableFallback(rawDesc) };
}

function categoryRank(title) {
  for (var i = 0; i < categoryOrder.length; i++) {
    if (categoryOrder[i] === title) return i;
  }
  return -1;
}

function sourceCountFor(binding) {
  var count = binding.sourceCount;
  if (typeof count === "number" && isFinite(count) && count >= 1 && Math.floor(count) === count) {
    return count;
  }
  return 1;
}

function overrideForBinding(binding, bindOverrides) {
  if (!binding || typeof binding.bindId !== "string" || !binding.bindId ||
      !bindOverrides || typeof bindOverrides !== "object" ||
      !Object.prototype.hasOwnProperty.call(bindOverrides, binding.bindId)) {
    return null;
  }
  var override = bindOverrides[binding.bindId];
  return override && typeof override === "object" ? override : null;
}

function isExactSubmapReset(binding) {
  return !!binding && binding._verb === "submap" && binding._param === "reset";
}
function isSubmapResetLike(binding) {
  return !!binding && typeof binding._verb === "string" &&
    binding._verb.trim().toLowerCase() === "submap" &&
    typeof binding._param === "string" && binding._param.trim().toLowerCase() === "reset";
}


function hasDescribedCommand(binding, rawDesc) {
  if (!binding || binding.undescribed === true ||
      typeof binding.desc !== "string" || !binding.desc.trim() ||
      typeof binding._verb !== "string" || !binding._verb.trim() ||
      typeof rawDesc !== "string" || !rawDesc.trim()) {
    return false;
  }
  return !!reconstructedCommand(binding).trim();
}

function canFoldModeReset(previous, current) {
  var action = previous.sourceBind;
  var reset = current.sourceBind;
  if (!action || !reset || previous.categoryIndex !== current.categoryIndex ||
      previous.bindIndex + 1 !== current.bindIndex ||
      isSubmapResetLike(action) || !isExactSubmapReset(reset) ||
      action._merged === true || reset._merged === true ||
      (Object.prototype.hasOwnProperty.call(action, "sourceCount") && action.sourceCount !== 1) ||
      (Object.prototype.hasOwnProperty.call(reset, "sourceCount") && reset.sourceCount !== 1) ||
      typeof action._submap !== "string" || !action._submap ||
      action._submap !== reset._submap ||
      action.keys !== reset.keys || typeof action.keys !== "string" || !action.keys.trim() ||
      previous.title !== current.title ||
      !hasDescribedCommand(action, previous.rawDesc) ||
      !hasDescribedCommand(reset, current.rawDesc) ||
      hasExplicitDescription(reset, current.rawDesc) ||
      current.override) {
    return false;
  }
  return true;
}

function prepareCategories(rawCategories, bindOverrides) {
  if (!Array.isArray(rawCategories)) return [];

  var buckets = Object.create(null);
  var entries = [];
  var nextIndex = 0;

  for (var i = 0; i < rawCategories.length; i++) {
    var sourceCategory = rawCategories[i] || {};
    var sourceBinds = Array.isArray(sourceCategory.binds) ? sourceCategory.binds : [];
    var previousRecord = null;

    for (var j = 0; j < sourceBinds.length; j++) {
      var sourceBind = sourceBinds[j];
      if (!sourceBind || typeof sourceBind !== "object") {
        previousRecord = null;
        continue;
      }

      var override = overrideForBinding(sourceBind, bindOverrides);
      if (override && override.hidden === true) {
        previousRecord = null;
        continue;
      }

      var rawDesc = sourceDescription(sourceBind);
      var presentation = classifyBinding(sourceBind, rawDesc);
      var explicitTitle = meaningfulCategory(sourceBind.category) ||
        meaningfulCategory(sourceBind.group) || meaningfulCategory(sourceCategory.title);
      var title = explicitTitle || presentation.category;
      if (sourceBind._submap)
        title = "Mode: " + String(sourceBind._submap).split(" · ")[0];

      var bind = copyFields(sourceBind);
      var preserveDescription = hasExplicitDescription(sourceBind, rawDesc);
      var overrideDescription = override && typeof override.desc === "string" ? override.desc : "";
      bind.rawDesc = rawDesc;
      bind.desc = overrideDescription.trim() ? overrideDescription :
        preserveDescription ? sourceBind.desc : presentation.desc;
      bind.sourceCount = sourceCountFor(sourceBind);

      var record = {
        sourceBind: sourceBind,
        rawDesc: rawDesc,
        title: title,
        categoryIndex: i,
        bindIndex: j,
        override: override,
        bind: bind
      };

      if (previousRecord && canFoldModeReset(previousRecord, record)) {
        var folded = previousRecord.bind;
        folded.hint = "Returns to normal shortcuts";
        folded.rawDesc = previousRecord.rawDesc + "\n" + rawDesc;
        folded.sourceIds = [
          previousRecord.sourceBind.bindId === undefined ? null : previousRecord.sourceBind.bindId,
          sourceBind.bindId === undefined ? null : sourceBind.bindId
        ];
        folded.sourceCommands = [previousRecord.rawDesc, rawDesc];
        folded.sourceCount += bind.sourceCount;
        previousRecord = record;
        continue;
      }

      var bucket = buckets[title];
      if (!bucket) {
        bucket = { title: title, binds: [], firstIndex: nextIndex++ };
        buckets[title] = bucket;
        entries.push(bucket);
      }
      bucket.binds.push(bind);
      previousRecord = record;
    }
  }

  entries.sort(function (left, right) {
    var leftRank = categoryRank(left.title);
    var rightRank = categoryRank(right.title);
    if (leftRank >= 0 && rightRank >= 0) return leftRank - rightRank;
    if (leftRank >= 0) return -1;
    if (rightRank >= 0) return 1;
    return left.firstIndex - right.firstIndex;
  });

  var result = [];
  for (var k = 0; k < entries.length; k++) {
    result.push({ title: entries[k].title, binds: entries[k].binds });
  }
  return result;
}

function keyLabel(token) {
  if (token === undefined || token === null) return "";
  var original = String(token).trim();
  var key = original.toUpperCase().replace(/\s+/g, "_");
  var labels = {
    "SHIFT": "⇧",
    "CTRL": "Ctrl",
    "CONTROL": "Ctrl",
    "ALT": "Alt",
    "SUPER": "Super",
    "SUPER_L": "Super",
    "SUPER_R": "Super",
    "LEFT": "←",
    "RIGHT": "→",
    "UP": "↑",
    "DOWN": "↓",
    "RETURN": "↵",
    "ENTER": "↵",
    "ESC": "Esc",
    "ESCAPE": "Esc",
    "SPACE": "Space",
    "TAB": "Tab",
    "BACKSPACE": "Backspace",
    "DELETE": "Delete",
    "BRACKETLEFT": "[",
    "BRACKETRIGHT": "]",
    "MINUS": "−",
    "EQUAL": "=",
    "GRAVE": "`",
    "SLASH": "/",
    "COMMA": ",",
    "PERIOD": ".",
    "XF86AUDIORAISEVOLUME": "Vol Up",
    "XF86AUDIOLOWERVOLUME": "Vol Down",
    "XF86AUDIOMUTE": "Mute",
    "XF86AUDIOPLAY": "Play",
    "XF86AUDIOPAUSE": "Pause",
    "XF86AUDIONEXT": "Next",
    "XF86AUDIOPREV": "Prev",
    "MOUSE:272": "Left Click",
    "MOUSE:273": "Right Click"
  };
  return Object.prototype.hasOwnProperty.call(labels, key) ? labels[key] : original;
}

function categoryIcon(title) {
  var normalized = String(title || "").toLowerCase().replace(/[^a-z]/g, "");
  if (normalized === "applications" || normalized === "application") return "settings-launcher";
  if (normalized === "windowfocus") return "settings-display";
  if (normalized === "windowlayout") return "settings-user-interface";
  if (normalized === "workspaces" || normalized === "workspace") return "hyprland";
  if (normalized === "groups" || normalized === "group") return "users-group";
  if (normalized === "mediaaudio" || normalized === "audio" || normalized === "media") return "settings-audio";
  if (normalized === "system") return "settings-general";
  if (normalized === "screenshots" || normalized === "screenshot") return "image";
  if (normalized === "wallpaper") return "settings-wallpaper";
  if (normalized === "clipboard") return "filepicker-text";
  return "keyboard";
}
