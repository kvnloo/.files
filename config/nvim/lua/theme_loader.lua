-- Follow the unified theme manager (scripts/theme, docs/theme-manager.md).
--
-- Inert until wired: `theme wire nvim` creates lua/plugins/theme.lua, a
-- one-line spec that requires this module.  It reads the palette file that
-- `theme apply` generates and returns LazyVim specs for it.  A theme with a
-- native colourscheme installed uses it; any other theme recolours tokyonight
-- from the palette.
local path = vim.fn.expand("~/.local/state/theme/generated/nvim.lua")
local ok, theme = pcall(dofile, path)
if not ok or type(theme) ~= "table" or type(theme.colorscheme) ~= "string" then
  return {}
end

vim.o.background = theme.background == "light" and "light" or "dark"

local specs = {
  { "LazyVim/LazyVim", opts = { colorscheme = theme.colorscheme } },
}

if not theme.native then
  table.insert(specs, {
    "folke/tokyonight.nvim",
    opts = {
      style = theme.background == "light" and "day" or "night",
      on_colors = function(colors)
        for key, value in pairs(theme.overrides or {}) do
          colors[key] = value
        end
      end,
    },
  })
end

return specs
