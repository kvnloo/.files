" Vim Configuration
" Minimal but functional — Zed is the primary editor

" ── Essential Settings ──────────────────────────────────────────────
set nocompatible
filetype plugin indent on
syntax on

set encoding=utf-8
set number
set relativenumber
set tabstop=2
set softtabstop=2
set shiftwidth=2
set expandtab
set smarttab
set autoindent

set backspace=indent,eol,start
set hidden
set autoread
set mouse=a
set scrolloff=8
set sidescrolloff=8
set signcolumn=yes
set cursorline

" Search
set hlsearch
set incsearch
set ignorecase
set smartcase

" Command-line completion
set wildmenu
set wildmode=longest:full,full

" Persistent undo
set undofile
set undodir=~/.vim/undodir

" No swap/backup clutter
set noswapfile
set nobackup
set nowritebackup

" Splits open in natural direction
set splitbelow
set splitright

" ── Clipboard (Wayland) ────────────────────────────────────────────
if has('unnamedplus')
  set clipboard=unnamedplus
else
  " Fallback: use wl-copy/wl-paste for Wayland
  autocmd TextYankPost * if v:event.operator ==# 'y' | call system('wl-copy', @0) | endif
  nnoremap p :let @0=system('wl-paste --no-newline')<CR>"0p
endif

" ── Theme ──────────────────────────────────────────────────────────
if (has("termguicolors"))
  set termguicolors
endif
colorscheme onedark

" ── Leader Key ─────────────────────────────────────────────────────
let mapleader = " "

" Clear search highlight
nnoremap <leader><space> :nohlsearch<CR>

" Quick save/quit
nnoremap <leader>w :w<CR>
nnoremap <leader>q :q<CR>

" Split navigation
nnoremap <C-h> <C-w>h
nnoremap <C-j> <C-w>j
nnoremap <C-k> <C-w>k
nnoremap <C-l> <C-w>l
