local enabled = true
tern.command({id="enable", title="Phone controls: enable", run=function(cx)
    enabled = true
    cx.settings:set_many({font_size=15, status_bar=true})
    cx:command("chat:reader")
    tern.chrome.refresh()
end})
tern.command({id="hide", title="Phone controls: hide", run=function(_cx)
    enabled = false
    tern.chrome.refresh()
end})
tern.command({id="esc", title="Phone: Escape", run=function(cx) cx:action("key:Escape") end})
tern.command({id="tab", title="Phone: Tab", run=function(cx) cx:action("key:Tab") end})
tern.command({id="interrupt", title="Phone: interrupt focused agent", run=function(cx)
    local pane = cx.session:focused()
    if not pane then return end
    for _, agent in cx.agents:list() do
        if agent.pane == pane then cx.agents:interrupt(pane); return end
    end
    cx:toast("info", "Focused pane is not an agent")
end})
tern.chrome.status(function(_pane)
    if not enabled then return nil end
    return {
        {text="Hosts", command="switch_host"},
        {text="Sessions", command="switch_session"},
        {text="Prev", command="previous_tab"},
        {text="Next", command="next_tab"},
        {text="More", command="show_commands"},
    }
end)
tern.css("phone", [[
#statusline .sl-plugin[data-plugin='phone-controls'] { min-height:48px; padding:12px 8px; }
]])
