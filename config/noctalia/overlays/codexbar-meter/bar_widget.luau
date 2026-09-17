--!nonstrict
-- CodexBar provider usage bar widget.
--
-- CodexBar owns provider discovery, authentication, and quota fetching. The
-- top bar is one unnamed stacked progress bar: one color per provider, no
-- names. Hover and the attached panel list each provider's named windows.

local codexbarPath = noctalia.getConfig("codexbarPath") or "~/.local/bin/codexbar-noctalia"
local refreshIntervalSec = tonumber(noctalia.getConfig("refreshIntervalSec")) or 60
local cachePath = noctalia.expandPath("~/.cache/codexbar-waybar/full.json")

local providers = {}
local errorMsg = ""
local requestInFlight = false

-- Noctalia v5 panel surfaces have fixed manifest dimensions. Keep the
-- regular `panel` id as the compatibility/default entry, then choose a
-- nearby fixed tier when opening so the surface follows the current data
-- without relying on an unsupported runtime resize API.
local PANEL_IDS = {
    compact = "salemsayed/codexbar-meter:panel-compact",
    standard = "salemsayed/codexbar-meter:panel",
    tall = "salemsayed/codexbar-meter:panel-tall",
}

local PROVIDER_META = {
    codex = { label = "Codex", glyph = "brand-openai", color = "primary", fill = "primary" },
    openai = { label = "OpenAI", glyph = "brand-openai", color = "primary", fill = "primary" },
    azureopenai = { label = "Azure OpenAI", glyph = "brand-openai", color = "primary", fill = "primary" },
    claude = { label = "Claude", glyph = "message-chatbot", color = "tertiary", fill = "tertiary" },
    gemini = { label = "Gemini", glyph = "brand-google", color = "secondary", fill = "secondary" },
    copilot = { label = "Copilot", glyph = "brand-github", color = "secondary", fill = "on_surface/0.8" },
    cursor = { label = "Cursor", glyph = "cursor-text", color = "secondary", fill = "secondary" },
    opencode = { label = "OpenCode", glyph = "code", color = "secondary", fill = "tertiary/0.5" },
    opencodego = { label = "OpenCode Go", glyph = "code", color = "secondary", fill = "tertiary/0.5" },
    qwencloud = { label = "Qwen Cloud", glyph = "cloud", color = "secondary", fill = "secondary/0.7" },
    alibaba = { label = "Alibaba", glyph = "cloud", color = "secondary", fill = "secondary/0.7" },
    alibabatokenplan = { label = "Alibaba Token Plan", glyph = "cloud", color = "secondary", fill = "secondary/0.7" },
    antigravity = { label = "Antigravity", glyph = "sparkles", color = "tertiary", fill = "tertiary/0.65" },
    kilo = { label = "Kilo", glyph = "robot", color = "secondary", fill = "on_surface/0.65" },
    ollama = { label = "Ollama", glyph = "server", color = "secondary", fill = "on_surface/0.45" },
    openrouter = { label = "OpenRouter", glyph = "route", color = "secondary", fill = "primary/0.55" },
    grok = { label = "Grok", glyph = "letter-x", color = "secondary", fill = "on_surface" },
    groq = { label = "Groq", glyph = "bolt", color = "secondary", fill = "tertiary/0.72" },
    cerebras = { label = "Cerebras", glyph = "cpu", color = "secondary", fill = "secondary/0.55" },
    vercel = { label = "Vercel", glyph = "cloud", color = "secondary", fill = "on_surface/0.5" },
    nous = { label = "Nous", glyph = "brain", color = "secondary", fill = "primary/0.35" },
}

local FALLBACK_COLORS = { "secondary", "tertiary", "primary", "on_surface" }

local function shellQuote(value)
    return "'" .. string.gsub(tostring(value), "'", "'\\''") .. "'"
end

local function commandPath()
    local path = tostring(codexbarPath)
    if string.sub(path, 1, 1) == "~" then
        path = noctalia.expandPath(path)
    end
    return path
end

local function providerId(provider)
    return tostring(provider and (provider.provider or provider.id) or "unknown")
end

local function providerAccount(provider)
    if type(provider) ~= "table" then return "" end
    if provider.account ~= nil and tostring(provider.account) ~= "" then
        return tostring(provider.account)
    end
    local usage = provider.usage
    local identity = type(usage) == "table" and usage.identity or nil
    if type(identity) == "table" then
        if identity.accountEmail ~= nil and tostring(identity.accountEmail) ~= "" then
            return tostring(identity.accountEmail)
        end
        if identity.accountOrganization ~= nil and tostring(identity.accountOrganization) ~= "" then
            return tostring(identity.accountOrganization)
        end
    end
    return ""
end

local function titleFromId(value)
    local text = string.gsub(tostring(value or "unknown"), "[_%-]+", " ")
    text = string.gsub(text, "(%a)([%w]*)", function(first, rest)
        return string.upper(first) .. string.lower(rest)
    end)
    return text
end

local function metaFor(provider, index)
    local id = providerId(provider)
    local known = PROVIDER_META[string.lower(id)]
    if known ~= nil then return known end
    local colorIndex = ((index - 1) % #FALLBACK_COLORS) + 1
    return {
        label = titleFromId(id),
        glyph = "chart-donut-3",
        color = FALLBACK_COLORS[colorIndex],
        fill = FALLBACK_COLORS[colorIndex],
    }
end

local function providerLabel(provider, index)
    local meta = metaFor(provider, index)
    local account = providerAccount(provider)
    if account ~= "" then
        return meta.label .. " · " .. account
    end
    return meta.label
end

local function providerError(provider)
    if type(provider) ~= "table" or provider.error == nil then return "" end
    if type(provider.error) == "string" then return provider.error end
    if type(provider.error) == "table" then
        return tostring(provider.error.message or provider.error.description or provider.error.kind or "Provider unavailable")
    end
    return "Provider unavailable"
end

local function windowLabel(window, fallback)
    if type(window) ~= "table" then return fallback or "Limit" end
    local named = window.title or window.name or window.label
    if named ~= nil and tostring(named) ~= "" then return tostring(named) end
    local minutes = tonumber(window.windowMinutes) or 0
    if minutes == 300 then return "5h" end
    if minutes == 1440 then return "24h" end
    if minutes == 10080 then return "7d" end
    if minutes == 43200 then return "30d" end
    if minutes >= 1440 then return string.format("%dd", math.floor(minutes / 1440)) end
    if minutes >= 60 then return string.format("%dh", math.floor(minutes / 60)) end
    if minutes > 0 then return string.format("%dm", minutes) end
    return fallback or "limit"
end

local function isGrokBotWindow(item)
    if type(item) ~= "table" then return false end
    local id = string.lower(tostring(item.id or ""))
    if id == "cursor-grok-bot" then return true end
    local title = string.lower(tostring(item.title or item.name or ""))
    if string.find(title, "grok bot", 1, true) then return true end
    local window = item.window
    if type(window) == "table" then
        local label = string.lower(tostring(window.title or window.name or window.label or ""))
        if string.find(label, "grok bot", 1, true) then return true end
    end
    return false
end

local function usedPercent(window)
    if type(window) ~= "table" then return nil end
    local used = tonumber(window.usedPercent)
    if used == nil then return nil end
    return math.max(0, math.min(100, used))
end

local function remainingPercent(window)
    if type(window) ~= "table" or window.usedPercent == nil then return nil end
    local used = tonumber(window.usedPercent)
    if used == nil then return nil end
    return math.max(0, math.min(100, 100 - used))
end

local function addWindow(windows, title, window, rank, extraId)
    if type(window) ~= "table" or tonumber(window.usedPercent) == nil then return end
    for _, item in ipairs(windows) do
        if item.window == window then return end
    end
    windows[#windows + 1] = {
        id = extraId,
        title = title or windowLabel(window),
        window = window,
        rank = rank or 99,
    }
end

local function windowsFor(provider)
    local result = {}
    local usage = type(provider) == "table" and provider.usage or nil
    if type(usage) ~= "table" then return result end
    local cursor = string.lower(providerId(provider)) == "cursor"
    addWindow(result, windowLabel(usage.primary, cursor and "Included" or "Session"), usage.primary, 1)
    addWindow(result, windowLabel(usage.secondary, cursor and "Cursor Models" or "Weekly"), usage.secondary, 2)
    addWindow(result, windowLabel(usage.tertiary, cursor and "Other Models" or "Monthly"), usage.tertiary, 3)

    if type(usage.extraRateWindows) == "table" then
        for index, extra in ipairs(usage.extraRateWindows) do
            if type(extra) == "table" then
                addWindow(result, extra.title or extra.name or "Additional window", extra.window or extra, 10 + index, extra.id)
            end
        end
    end

    if type(usage.windows) == "table" then
        for index, item in ipairs(usage.windows) do
            if type(item) == "table" then
                addWindow(result, item.title or item.name or "Usage window", item.window or item, 20 + index, item.id)
            end
        end
    end

    -- Future providers may add another named rate window. Pick up any table
    -- that carries the standard usedPercent field without treating identity,
    -- status, or provider-specific metadata as a quota row.
    for key, value in pairs(usage) do
        if type(value) == "table" and tonumber(value.usedPercent) ~= nil then
            addWindow(result, windowLabel(value, titleFromId(key)), value, 40)
        end
    end

    table.sort(result, function(a, b)
        if a.rank ~= b.rank then return a.rank < b.rank end
        return a.title < b.title
    end)
    return result
end

local function creditsFor(provider)
    if type(provider) ~= "table" then return nil end
    if type(provider.credits) == "table" then return provider.credits end
    if type(provider.usage) == "table" and type(provider.usage.credits) == "table" then
        return provider.usage.credits
    end
    return nil
end

local function summaryFor(provider)
    local windows = windowsFor(provider)
    if #windows > 0 then
        local window = windows[1].window
        return {
            window = window,
            label = windows[1].title .. " " .. string.format("%d%%", math.floor((remainingPercent(window) or 0) + 0.5)),
            remaining = remainingPercent(window),
        }
    end

    local credits = creditsFor(provider)
    if credits ~= nil and credits.remaining ~= nil then
        local creditPercent = tonumber(credits.remainingPercent)
        return {
            label = tostring(credits.remaining),
            remaining = creditPercent,
            credits = true,
        }
    end
    return { label = "—", remaining = nil }
end

local function providerByIndex(index)
    return providers[index]
end

local function percentText(value)
    if value == nil then return "—" end
    return string.format("%d%%", math.floor(value + 0.5))
end

local function tooltipFor(provider, index)
    local meta = metaFor(provider, index)
    local issue = providerError(provider)
    if issue ~= "" then
        return { key = providerLabel(provider, index), value = "Unavailable · " .. issue }
    end

    local windows = windowsFor(provider)
    local lines = {}
    local cursor = string.lower(providerId(provider)) == "cursor"
    for _, item in ipairs(windows) do
        local used = usedPercent(item.window)
        if cursor and used ~= nil then
            lines[#lines + 1] = item.title .. ": " .. percentText(used) .. " used"
        else
            lines[#lines + 1] = item.title .. ": " .. percentText(remainingPercent(item.window)) .. " left"
        end
        if cursor and isGrokBotWindow(item) then
            local reset = item.window and item.window.resetDescription
            if reset ~= nil and tostring(reset) ~= "" then
                lines[#lines] = lines[#lines] .. " · " .. tostring(reset)
            end
        end
    end

    local credits = creditsFor(provider)
    if credits ~= nil and credits.remaining ~= nil then
        lines[#lines + 1] = "Credits: " .. tostring(credits.remaining)
    end
    if #lines == 0 then lines[#lines + 1] = "No usage window reported" end
    if provider.stale == true then lines[#lines + 1] = "Showing last known data" end

    return { key = meta.label, value = table.concat(lines, "\n") }
end

local function hasProviderErrors()
    for _, provider in ipairs(providers) do
        if providerError(provider) ~= "" then return true end
    end
    return false
end

local function hasProviderStatus(provider)
    local status = type(provider) == "table" and provider.status or nil
    return type(status) == "table"
        and status.description ~= nil
        and tostring(status.indicator or "none") ~= "none"
end

local function hasPaceSummary(provider)
    local pace = type(provider) == "table" and provider.pace or nil
    if type(pace) ~= "table" then return false end
    for _, key in ipairs({ "primary", "secondary", "tertiary" }) do
        if type(pace[key]) == "table" and pace[key].summary ~= nil then return true end
    end
    for _, value in pairs(pace) do
        if type(value) == "table" and value.summary ~= nil then return true end
    end
    return false
end

local function estimatedProviderHeight(provider)
    -- Approximate the panel card from semantic content, not provider names.
    -- This deliberately errs upward; the scroll view remains the safety net
    -- for providers with unusually verbose or future-specific payloads.
    local height = 104
    height = height + (#windowsFor(provider) * 82)
    if providerError(provider) ~= "" then height = height + 44 end
    if hasPaceSummary(provider) then height = height + 34 end
    if provider.stale == true then height = height + 34 end

    local credits = creditsFor(provider)
    if credits ~= nil and credits.remaining ~= nil then height = height + 30 end
    if hasProviderStatus(provider) then height = height + 34 end
    return height
end


local function parseCreditAmount(value)
    if value == nil then return nil end
    if type(value) == "number" then return value end
    local text = string.gsub(tostring(value), "[$%s,]", "")
    return tonumber(text)
end

local function isConnectivityWindow(window)
    if type(window) ~= "table" then return false end
    if window.quota == false then return true end
    local label = string.lower(tostring(window.resetDescription or window.label or ""))
    return string.find(label, "connected", 1, true) ~= nil and string.find(label, "model", 1, true) ~= nil
end

local function providerRemainingPercent(provider)
    if providerError(provider) ~= "" then return nil end

    local credits = creditsFor(provider)
    local creditPercent = nil
    local creditAmount = nil
    if type(credits) == "table" then
        creditPercent = tonumber(credits.remainingPercent)
        creditAmount = parseCreditAmount(credits.remaining)
    end

    local maxUsed = nil
    for _, item in ipairs(windowsFor(provider)) do
        local window = item.window
        if not isConnectivityWindow(window) then
            local remaining = remainingPercent(window)
            if remaining ~= nil then
                local used = 100 - remaining
                if maxUsed == nil or used > maxUsed then
                    maxUsed = used
                end
            end
        end
    end

    if creditPercent ~= nil then
        return math.max(0, math.min(100, creditPercent))
    end
    if creditAmount ~= nil and creditAmount <= 0 then
        if maxUsed ~= nil and maxUsed > 0 then
            return math.max(0, 100 - maxUsed)
        end
        return 0
    end
    if maxUsed ~= nil then
        return math.max(0, 100 - maxUsed)
    end
    return nil
end

local function averageRemainingPercent()
    local values = {}
    for _, provider in ipairs(providers) do
        local remaining = providerRemainingPercent(provider)
        if remaining ~= nil then
            values[#values + 1] = remaining
        end
    end
    if #values == 0 then return nil end
    local sum = 0
    for _, value in ipairs(values) do
        sum = sum + value
    end
    return math.floor((sum / #values) + 0.5)
end

local function aggregateColor(remaining)
    if remaining == nil then return "on_surface_variant" end
    if remaining <= 10 then return "error" end
    if remaining <= 30 then return "tertiary" end
    return "primary"
end

local function segmentFill(provider, index)
    if providerError(provider) ~= "" then return "error" end
    local meta = metaFor(provider, index)
    return meta.fill or meta.color
end

local function stackedBar()
    local children = {}
    if #providers == 0 then
        children[1] = ui.progress({
            progress = 0,
            fill = "primary",
            track = "on_surface/0.16",
            radius = 6,
            width = 160,
            height = 8,
        })
    else
        local slot = math.max(8, math.floor(160 / #providers))
        for index, provider in ipairs(providers) do
            local remaining = providerRemainingPercent(provider)
            local progress = 0
            if providerError(provider) ~= "" then
                progress = 1
            elseif remaining ~= nil then
                progress = remaining / 100
            end
            children[#children + 1] = ui.progress({
                progress = progress,
                fill = segmentFill(provider, index),
                track = "on_surface/0.16",
                radius = 2,
                width = slot,
                height = 8,
            })
        end
    end
    return ui.row({ key = "codexbar-segments", align = "center", gap = 1 }, children)
end

local function render()
    barWidget.render(ui.row({ key = "codexbar-all", gap = 0, align = "center" }, {
        stackedBar(),
    }))

    local tooltip = {}
    for index, provider in ipairs(providers) do
        tooltip[#tooltip + 1] = tooltipFor(provider, index)
    end
    if #tooltip == 0 then
        tooltip[#tooltip + 1] = { key = "CodexBar", value = "Waiting for provider data" }
    end
    if errorMsg ~= "" then
        tooltip[#tooltip + 1] = { key = "Status", value = errorMsg }
    end
    barWidget.setTooltip(tooltip)
end

local function decodeProviders(stdout)
    local decoded = noctalia.json.decode(stdout or "")
    if type(decoded) ~= "table" then return nil end
    if type(decoded.providers) == "table" then return decoded.providers end
    if decoded.provider ~= nil or decoded.error ~= nil then return { decoded } end

    local result = {}
    for _, provider in ipairs(decoded) do
        if type(provider) == "table" then result[#result + 1] = provider end
    end
    return result
end

local function applyProviders(decoded, errText)
    if decoded ~= nil and #decoded > 0 then
        providers = decoded
        errorMsg = errText or ""
        noctalia.state.set("providers", providers)
        noctalia.state.set("error", errorMsg)
        noctalia.state.set("lastRefresh", os.time())
        render()
        return true
    end
    return false
end

local function loadCache(callback)
    noctalia.runAsync("cat " .. shellQuote(cachePath), function(result)
        callback(result)
    end, 5000)
end

local function refresh()
    if requestInFlight then return end
    requestInFlight = true

    local command = "timeout 120s " .. shellQuote(commandPath())
        .. " usage --format json --json-only"

    noctalia.runAsync(command, function(result)
        requestInFlight = false
        local decoded = result ~= nil and decodeProviders(result.stdout) or nil
        if applyProviders(decoded, "") then return end

        loadCache(function(cacheResult)
            local cached = cacheResult ~= nil and decodeProviders(cacheResult.stdout) or nil
            if applyProviders(cached, "") then return end

            errorMsg = result ~= nil and result.exitCode ~= 0
                and "CodexBar could not refresh"
                or "CodexBar returned no provider data"
            noctalia.state.set("error", errorMsg)
            render()
        end)
    end, 120000)
end

noctalia.state.watch("command", function(value)
    if type(value) == "table" and value.action == "refresh" then refresh() end
end)

noctalia.state.watch("providers", function(value)
    if type(value) == "table" then
        providers = value
        render()
    end
end)

noctalia.state.watch("error", function(value)
    if type(value) == "string" then
        errorMsg = value
        render()
    end
end)

local function panelEntryIdForCurrentData()
    local height = 90
    for _, provider in ipairs(providers) do
        height = height + estimatedProviderHeight(provider)
    end
    if height <= 390 then return PANEL_IDS.compact end
    if height <= 560 then return PANEL_IDS.standard end
    return PANEL_IDS.tall
end

function update()
    noctalia.setUpdateInterval(refreshIntervalSec * 1000)
    refresh()
end

function onClick()
    noctalia.togglePanel(panelEntryIdForCurrentData())
end

function onRightClick()
    refresh()
end

function onIpc(event, _payload)
    if event == "refresh" then refresh() end
end

local existing = noctalia.state.get("providers")
if type(existing) == "table" then providers = existing end
local existingError = noctalia.state.get("error")
if type(existingError) == "string" then errorMsg = existingError end

loadCache(function(result)
    local decoded = result ~= nil and decodeProviders(result.stdout) or nil
    applyProviders(decoded, "")
end)

noctalia.setUpdateInterval(refreshIntervalSec * 1000)
render()
refresh()
