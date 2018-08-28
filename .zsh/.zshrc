# Outline of zshconfig:
# =====================
# 1. $PATH
# 2. OH-MY-ZSH
# 3. THEMES
# 4. RANDOM
# 5. PLUGINS
# 6. KEYBINDINGS
# 7. FUNCTIONS
# 8. ALIASES
# 9. STARTUP PROGRAMS
# =====================

# ----------------------------+
# $PATH: Configure your $PATH |
# ----------------------------+------------------------------------------------
# -- If you come from bash you might have to change your $PATH.
# -- export PATH=$HOME/bin:/usr/local/bin:$PATH

# ------------------------------------+
# OH-MY-ZSH: export oh-my-zsh changes |
# ------------------------------------+---------------------------------------
# -- Path to your oh-my-zsh installation.
export ZSH=~/.oh-my-zsh
export PATH="/usr/local/sbin:$PATH"
fpath=(/usr/local/share/zsh-completions $fpath)

# --------+
# THEMES: |
# --------+-------------------------------------------------------------------
# -- Set name of the theme to load. Optionally, if you set this to "random"
# -- it'll load a random theme each time that oh-my-zsh is loaded.
# -- See https://github.com/robbyrussell/oh-my-zsh/wiki/Themes
# ZSH_THEME="agnoster"
ZSH_THEME="robbyrussell"
# export TERM="xterm-256color"

# --------+
# RANDOM: |
# --------+-------------------------------------------------------------------
# -- Uncomment the following line to use case-sensitive completion.
# CASE_SENSITIVE="true"

# -- Uncomment the following line to use hyphen-insensitive completion. Case
# -- sensitive completion must be off. _ and - will be interchangeable.
HYPHEN_INSENSITIVE="true"

# -- Uncomment the following line to disable bi-weekly auto-update checks.
# DISABLE_AUTO_UPDATE="true"

# -- Uncomment the following line to change how often to auto-update (in days).
# export UPDATE_ZSH_DAYS=13

# -- Uncomment the following line to disable colors in ls.
# DISABLE_LS_COLORS="true"

# -- Uncomment the following line to disable auto-setting terminal title.
# DISABLE_AUTO_TITLE="true"

# -- Uncomment the following line to enable command auto-correction.
ENABLE_CORRECTION="true"

# -- Uncomment the following line to display red dots whilst waiting for completion.
COMPLETION_WAITING_DOTS="true"

# -- Instant keytimeout
export KEYTIMEOUT=1

# -- Uncomment the following line if you want to disable marking untracked files
# -- under VCS as dirty. This makes repository status check for large repositories
# -- much, much faster.
# DISABLE_UNTRACKED_FILES_DIRTY="true"

# -- Uncomment the following line if you want to change the command execution time
# -- stamp shown in the history command output.
# -- The optional three formats: "mm/dd/yyyy"|"dd.mm.yyyy"|"yyyy-mm-dd"
# HIST_STAMPS="mm/dd/yyyy"

# -- Would you like to use another custom folder than $ZSH/custom?
# ZSH_CUSTOM=/path/to/new-custom-folder

# ---------+
# PLUGINS: |
# ---------+------------------------------------------------------------------
# -- Which plugins would you like to load? (plugins can be found in ~/.oh-my-zsh/plugins/*)
# -- Custom plugins may be added to ~/.oh-my-zsh/custom/plugins/
# -- * Example format: plugins=(rails git textmate ruby lighthouse)
# -- ADD WISELY! (too many plugins slow down shell startup)

# -- User configuration:

# -- zsh-syntax-highlighting
plugins=(git zsh-syntax-highlighting)
source ~/.zsh/zsh-autosuggestions/zsh-autosuggestions.zsh
export ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE="fg=3"
# AUTOSUGGESTION_HIGHLIGHT_STYLE=''

# -- oh-my-zsh
source $ZSH/oh-my-zsh.sh

# -- z
source "$(brew --prefix)/etc/profile.d/z.sh"

# -------------+
# KEYBINDINGS: |
# -------------+--------------------------------------------------------------
# -- add custom keybindings to control your terminal!

bindkey -v
bindkey '^P' up-history
bindkey '^N' down-history
bindkey '^?' backward-delete-char
bindkey '^h' backward-delete-char
bindkey '^w' backward-kill-word
bindkey '^r' history-incremental-search-backward

# -----------+
# FUNCTIONS: |
# -----------+----------------------------------------------------------------
# -- Any user defined or plugin functions

# -- zle
precmd() { RPROMPT="" }
function zle-line-init zle-keymap-select {
  VIM_PROMPT="%{$fg_bold[yellow]%} [% NORMAL]%  %{$reset_color%}"
  RPS1="${${KEYMAP/vicmd/$VIM_PROMPT}/(main|viins)/} $EPS1"
  zle reset-prompt
}
zle -N zle-line-init
zle -N zle-keymap-select

# -- prints out all terminal colors
all_colors() {
  for x in {0..8}; do 
    for i in {30..37}; do 
      for a in {40..47}; do 
        echo -ne "\e[$x;$i;$a""m\\\e[$x;$i;$a""m\e[0;37;40m "
      done
      echo
    done
  done
  echo ""
}

# -- prints out certain terminal colors
colors() {
  echo "\n[0m[31m[41m   [0m[31m[41m   [0m[32m[42m   [0m[32m[42m   [0m[33m[43m   [0m[33m[43m   [0m[34m[44m   [0m[34m[44m   [0m[35m[45m   [0m[35m[45m   [0m[36m[46m   [0m[36m[46m   [0m[37m[47m   [0m[37m[47m   \n"
}


efimount(){
  efidisk=$(diskutil list | grep "EFI EFI" | grep -o -E 'disk[0-9]*s[0-9]*')
  sudo mkdir /Volumes/efi && sudo mount -t msdos /dev/$efidisk /Volumes/efi && cd /Volumes/efi
}

trackpad_speed() {
  defaults write -g com.apple.mouse.scaling $1
}

# export MANPATH="/usr/local/man:$MANPATH"

# You may need to manually set your language environment
# export LANG=en_US.UTF-8

# -- Preferred editor for local and remote sessions
# -- example: vim for remote mvim for local
# -- * if [[ -n $SSH_CONNECTION ]]; then
# -- *   export EDITOR='vim'
# -- * else
# -- *   export EDITOR='mvim'
# -- * fi
export EDITOR='vim'

# -- Compilation flags
# -- export ARCHFLAGS="-arch x86_64"

# ssh
# export SSH_KEY_PATH="~/.ssh/rsa_id"

# ---------+
# ALIASES: |
# ---------+------------------------------------------------------------------
# -- Set personal aliases, overriding those provided by oh-my-zsh libs,
# -- plugins, and themes. Aliases can be placed here, though oh-my-zsh
# -- users are encouraged to define aliases within the ZSH_CUSTOM folder.
# -- For a full list of active aliases, run `alias`.

# -- REQUIRES: "rmtrash" - this will move files to trash rather than piping to /dev/null
alias rm='rmtrash'
 
# -- REQUIRES: "kwm" - a tiling window manager on macos
alias 'rekwm'='brew services restart kwm'
alias 'rechunk'='brew services restart chunkwm'

# -- Shortcut for editing config files
alias zshconfig="vim ~/.zshrc"
alias vimconfig="vim ~/.vimrc"
alias gitconfig="vim ~/.gitconfig"
alias wmconfig="vim ~/.chunkwmrc"
alias hyperconfig="vim ~/.hyper.js"
alias khdconfig="vim ~/.khdrc"

# -- REQUIRES: "z" - jump around (https://github.com/rupa/z)
alias c='z'

# -- REQUIRES: "python", "python3", "pip", "pip3"
alias python='python3'
alias pip='pip3'

# -- cd aliases: these paths are specific to me, you'll probably want to change them
alias cdresume="cd ~/GoogleDrive/Jobs/resume"
alias cdrepos="cd ~/Desktop/repos"
alias cdprojects="cd ~/Desktop/Projects"
alias cdconfig="cd ~/GoogleDrive/Projects/.files"

# -- random aliases
alias timon='la | lolcat'
alias sl='sl | lolcat'
alias gits="find . -name '.git'"
alias reloadzsh="source ~/.zshrc"
alias chrome="/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome"
alias chrome-canary="/Applications/Google\ Chrome\ Canary.app/Contents/MacOS/Google\ Chrome\ Canary"

# ------------------+
# STARTUP PROGRAMS: |
# ------------------+---------------------------------------------------------
# -- Programs to open when zsh starts

# REQUIRES: "tmux" - terminal tiling and much more (https://tmux.github.io/)
# if [ "$TMUX" = "" ]; then tmux; fi

# all of the following are tools that display device information
# although neofetch looks the nicest, when I checked the execution
# times, archey was significantly faster than the other two
# REQUIRES:  "archey"
# if [ "$ARCHEY" = "" ]; then archey && colors && echo && echo; fi
# REQUIRES: "screenfetch"
# if [ "$SCREENFETCH" = "" ]; then screenfetch; fi
# REQUIRES: "neofetch"
# if [ "$NEOFETCH" = "" ]; then neofetch; fi

# echo "$PS1"
# export $PS1="echo $PS1 | cut -d '}' -f 2"

# Add RVM to PATH for scripting. Make sure this is the last PATH variable change.
cowsay -f dragon "hello\!" | lolcat
colors
export PATH="$PATH:$HOME/.rvm/bin"

