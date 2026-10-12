.pragma library

var ternAppIds = ["so.stencil.tern", "so.stencil.tern.open"];
var chordAliases = {
  control: "ctrl",
  option: "alt",
  opt: "alt",
  super: "cmd",
  meta: "cmd"
};

function isTernAppId(appId) {
  return typeof appId === "string" && ternAppIds.indexOf(appId) !== -1;
}

function canonicalChord(chord) {
  var parts = String(chord || "").trim().toLowerCase().split(">");
  if (!parts.length || parts.some(function(part) { return !part.trim(); }))
    return "";

  for (var i = 0; i < parts.length; i++) {
    var keys = parts[i].split("+");
    if (keys.some(function(key) { return !key.trim(); }))
      return "";
    parts[i] = keys.map(function(key) {
      var token = key.trim();
      return Object.prototype.hasOwnProperty.call(chordAliases, token) ? chordAliases[token] : token;
    }).join("+");
  }
  return parts.join(">");
}

function actionId(nativeAction) {
  var action = String(nativeAction || "").trim();
  var detail = action.lastIndexOf(" · ");
  return detail >= 0 ? action.substring(detail + 3).trim() : action;
}

function replacePrefix(chord, defaultPrefix, configuredPrefix) {
  var parts = String(chord || "").split(">");
  if (parts.length > 1 && canonicalChord(parts[0]) === canonicalChord(defaultPrefix))
    parts[0] = configuredPrefix;
  return parts.join(">");
}

function parseTernSettings(text, catalogs, version, commit) {
  var settings = JSON.parse(String(text || ""));
  if (!settings || typeof settings !== "object" || Array.isArray(settings))
    return { valid: false, supported: false, bindings: [], keymap: "", prefix: "", catalogVersion: "" };

  var keymap = typeof settings.keymap === "string" && settings.keymap.trim() ?
               settings.keymap.trim().toLowerCase() : "tern";
  var catalog = catalogs && catalogs[keymap];
  if (!catalog)
    return { valid: true, supported: false, bindings: [], keymap: keymap, prefix: "", catalogVersion: "" };

  var defaultPrefix = canonicalChord(catalog.defaultPrefix || "");
  var prefix = defaultPrefix;
  if (defaultPrefix && Object.prototype.hasOwnProperty.call(settings, "keymap_prefix")) {
    if (typeof settings.keymap_prefix !== "string")
      return { valid: false, supported: false, bindings: [], keymap: keymap, prefix: "", catalogVersion: "" };
    prefix = canonicalChord(settings.keymap_prefix);
    if (!prefix || prefix.indexOf(">") >= 0)
      return { valid: false, supported: false, bindings: [], keymap: keymap, prefix: "", catalogVersion: "" };
  }

  var actionsById = Object.create(null);
  var bindings = [];
  for (var groupIndex = 0; groupIndex < catalog.groups.length; groupIndex++) {
    var group = catalog.groups[groupIndex];
    var rows = group.bindings || [];
    for (var rowIndex = 0; rowIndex < rows.length; rowIndex++) {
      var row = rows[rowIndex];
      if (!row || row.length < 3)
        continue;
      var desc = String(row[0] || "").trim();
      var action = actionId(row[1]);
      var keys = replacePrefix(row[2], defaultPrefix, prefix);
      if (!desc || !action || !keys)
        continue;
      var actionKey = action.toLowerCase();
      if (!actionsById[actionKey])
        actionsById[actionKey] = { desc: desc, group: group.name };
      bindings.push({
        keys: keys,
        desc: desc,
        action: action,
        group: group.name,
      });
    }
  }

  var overrides = settings.keybinds;
  var suppressed = Object.create(null);
  var userBindings = [];
  if (overrides && typeof overrides === "object" && !Array.isArray(overrides)) {
    var chords = Object.keys(overrides).sort();
    for (var i = 0; i < chords.length; i++) {
      var chord = canonicalChord(chords[i]);
      var value = overrides[chords[i]];
      if (!chord)
        continue;
      if (value === "unbind" || (Array.isArray(value) && value.length === 0)) {
        suppressed[chord] = true;
        continue;
      }

      var actionNames;
      if (typeof value === "string") {
        actionNames = value.trim() ? [value.trim()] : [];
      } else if (Array.isArray(value) && value.every(function(actionName) {
        return typeof actionName === "string" && actionName.trim().length > 0;
      })) {
        actionNames = value.map(function(actionName) { return actionName.trim(); });
      } else {
        continue;
      }
      if (!actionNames.length)
        continue;

      suppressed[chord] = true;
      var labels = [];
      var groups = [];
      for (var actionIndex = 0; actionIndex < actionNames.length; actionIndex++) {
        var name = actionNames[actionIndex];
        var known = actionsById[name.toLowerCase()];
        labels.push(known ? known.desc : name);
        if (known && groups.indexOf(known.group) === -1)
          groups.push(known.group);
      }
      userBindings.push({
        keys: chord,
        desc: labels.join("  ›  "),
        action: actionNames.join("  ›  "),
        group: groups.length === 1 ? groups[0] : "User overrides",
        sourceLabel: "User override"
      });
    }
  }

  var effectiveBindings = [];
  for (var bindingIndex = 0; bindingIndex < bindings.length; bindingIndex++) {
    var binding = bindings[bindingIndex];
    if (!suppressed[canonicalChord(binding.keys)])
      effectiveBindings.push(binding);
  }
  for (var userIndex = 0; userIndex < userBindings.length; userIndex++)
    effectiveBindings.push(userBindings[userIndex]);

  return {
    valid: true,
    supported: true,
    bindings: effectiveBindings,
    keymap: keymap,
    prefix: prefix,
    catalogVersion: String(version || "") + (commit ? " (" + commit + ")" : "")
  };
}

function parseJsonCatalog(text) {
  var catalog = JSON.parse(String(text || ""));
  if (!catalog || typeof catalog !== "object" || Array.isArray(catalog) || !Array.isArray(catalog.shortcuts))
    return { valid: false, supported: false, bindings: [], keymap: "", prefix: "", catalogVersion: "" };

  var bindings = [];
  for (var i = 0; i < catalog.shortcuts.length; i++) {
    var entry = catalog.shortcuts[i];
    if (!entry || typeof entry !== "object" || Array.isArray(entry) || typeof entry.keys !== "string")
      continue;
    var keys = entry.keys.trim();
    var description = typeof entry.description === "string" ? entry.description.trim() :
                      (typeof entry.desc === "string" ? entry.desc.trim() : "");
    if (!keys || !description)
      continue;
    bindings.push({ keys: keys, desc: description, group: "", sourceLabel: "Configured shortcut" });
  }

  return { valid: true, supported: true, bindings: bindings, keymap: "", prefix: "", catalogVersion: "" };
}

