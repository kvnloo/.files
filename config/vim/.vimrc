" # Outline of vimconfig:
" # =====================
" # 1. BASIC SETTINGS
" # 2. PLUGINS
" # 3. THEMES
" # =====================



" # -----------------+
" # BASIC SETTINGS:  |
" # -----------------+-----------------------------------------------------------

" # -- Compatible (http://vimdoc.sourceforge.net/htmldoc/options.html#'compatible')
"set nocompatible 

" # -- Filetypes (http://vimdoc.sourceforge.net/htmldoc/filetype.html#filetype)
filetype on      

" # -- Soft Tab Stop (http://vimdoc.sourceforge.net/htmldoc/options.html#'softtabstop')
set softtabstop=2

" # -- Shift Width (http://vimdoc.sourceforge.net/htmldoc/options.html#'shiftwidth')
set shiftwidth=2

" # -- Expand Tab (http://vimdoc.sourceforge.net/htmldoc/options.html#'expandtab')
set expandtab

" # -- Encoding (http://vimdoc.sourceforge.net/htmldoc/options.html#'fileencoding')
set encoding=utf-8




set number


set tabstop=2

"set smarttab



" # ---------+
" # PLUGINS: |
" # ---------+-------------------------------------------------------------------

" # -- pathogen (https://github.com/tpope/vim-pathogen)
call pathogen#infect('bundle/{}')
syntax on
filetype plugin indent on


" # --------+
" # THEMES: |
" # --------+--------------------------------------------------------------------

" # -- ONE DARK (https://github.com/joshdick/onedark.vim)

" # (1) SETUP:
" # --------------------------
if (empty($TMUX))
  if (has("nvim")) "For Neovim 0.1.3 and 0.1.4 < https://github.com/neovim/neovim/pull/2198 >
    let $NVIM_TUI_ENABLE_TRUE_COLOR=1
  endif
  "For Neovim > 0.1.5 and Vim > patch 7.4.1799 < https://github.com/vim/vim/commit/61be73bb0f965a895bfb064ea3e55476ac175162 >
  "Based on Vim patch 7.4.1770 (`guicolors` option) < https://github.com/vim/vim/commit/8a633e3427b47286869aa4b96f2bfc1fe65b25cd >
  " < https://github.com/neovim/neovim/wiki/Following-HEAD#20160511 >
  if (has("termguicolors"))
    set termguicolors
  endif
endif

let g:onedark_termcolors=256

" # (2) OPTIONS:
" # --------------------------
" let g:lightline = {
"       \ 'colorscheme': 'wombat',
"       \ 'component': {
"       \   'readonly': '%{&readonly?"⭤":""}',
"       \ },
"       \ 'separator': { 'left': '⮀', 'right': '⮂' },
"       \ 'subseparator': { 'left': '⮁', 'right': '⮃' }
"       \ }
" let g:onedark_terminal_italics
"let g:lightline = {
"  \ 'colorscheme': 'onedark',
"  \ }

" # (3) ENABLE COLOR SCHEME:
" # --------------------------
syntax on
colorscheme onedark
colorscheme atom-dark-256
