return {
  {
    "folke/tokyonight.nvim",
    opts = {
      style = "moon",
      transparent = false,
      styles = {
        comments = { italic = true },
        keywords = { italic = true },
        sidebars = "dark",
        floats = "dark",
      },
    },
  },
  {
    "LazyVim/LazyVim",
    opts = { colorscheme = "tokyonight-moon" },
  },
  {
    "nvim-treesitter/nvim-treesitter",
    opts = {
      ensure_installed = {
        "bash",
        "css",
        "diff",
        "git_config",
        "git_rebase",
        "gitcommit",
        "html",
        "javascript",
        "json",
        "jsonc",
        "lua",
        "luadoc",
        "markdown",
        "markdown_inline",
        "python",
        "query",
        "regex",
        "rust",
        "toml",
        "tsx",
        "typescript",
        "vim",
        "vimdoc",
        "yaml",
      },
    },
  },
  {
    "mason-org/mason.nvim",
    opts = {
      ensure_installed = {
        "bash-language-server",
        "biome",
        "lua-language-server",
        "prettierd",
        "pyright",
        "ruff",
        "rust-analyzer",
        "shfmt",
        "stylua",
        "typescript-language-server",
        "yaml-language-server",
      },
    },
  },
  {
    "neovim/nvim-lspconfig",
    opts = {
      servers = {
        bashls = {},
        biome = {},
        lua_ls = {},
        pyright = {},
        qmlls = { cmd = { "/usr/lib/qt6/bin/qmlls" } },
        ruff = {},
        rust_analyzer = {},
        ts_ls = {},
        yamlls = {},
      },
    },
  },
  {
    "saghen/blink.cmp",
    opts = {
      keymap = { preset = "enter" },
      completion = {
        documentation = { auto_show = true, auto_show_delay_ms = 250 },
        menu = { border = "rounded" },
      },
      signature = { enabled = true, window = { border = "rounded" } },
    },
  },
  {
    "nvim-telescope/telescope.nvim",
    opts = {
      defaults = {
        layout_strategy = "horizontal",
        layout_config = { prompt_position = "top", preview_width = 0.55 },
        sorting_strategy = "ascending",
        borderchars = { "─", "│", "─", "│", "╭", "╮", "╯", "╰" },
      },
    },
  },
  {
    "christoomey/vim-tmux-navigator",
    lazy = false,
  },
  {
    "nvim-lualine/lualine.nvim",
    opts = function(_, opts)
      opts.options = opts.options or {}
      opts.options.globalstatus = true
      opts.options.component_separators = { left = "·", right = "·" }
      opts.options.section_separators = { left = "", right = "" }
    end,
  },
}
