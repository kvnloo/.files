# .files
Welcome to my dot files! If you have any sugguestions or cool configurations feel free to contact me at lesseradmin@ek.vin

This repo has my configuration for the following "tools"
  * Universal
    * Custom Shells:
      * [tmux](https://tmux.github.io/)
      * [zsh](zsh.org)
        * [oh-my-zsh](https://github.com/robbyrussell/oh-my-zsh)
      * [fish](https://fishshell.com/)
        * [oh-my-fish](https://github.com/oh-my-fish/oh-my-fish)
    * [vim](http://www.vim.org/) (I don't emacs)
    * [gitconfig](https://git-scm.com/docs/git-config)
  * MacOS Specific:
    * Tiling Window Managers:
      * [chunkwm](https://github.com/koekeishiya/chunkwm)
      * [kwm](https://github.com/koekeishiya/kwm)
    * Terminal Skins
      * [iTerm](https://www.iterm2.com/)
      * [Hyper Terminal](hyper.is)
  * Linux / Arch
    * [i3 coming soon!](https://i3wm.org/)
  * Android
    * [Nova](http://novalauncher.com/) (nova master race)
    * [Zooper widget](https://play.google.com/store/apps/details?id=org.zooper.zwfree&hl=en)

# Clone the repo

    git clone https://github.com/lesseradmin/.files 

# Install all the submodules
    
    cd .files
    git submodule update --recursive --init

# Create symlinks
    
    # zsh
    ln -s /pathTo/.files/.zsh/.zshrc ~/.zshrc
    ln -s /pathTo/.files/.oh-my-zsh ~/.oh-my-zsh
    # fish
    ln -s /pathTo/.files/.fish/ ~/.config/fish
    ln -s /pathTo/.files/.omf/ ~/.config/omf
    # vim
    ln -s /pathTo/.files/.vim/ ~/.vim
    ln -s /pathTo/.files/.vim/.vimrc ~/.vimrc
    # window managers (choose either chunkwm or kwm) -> MacOS only
    # chunkwm
    ln -s /pathTo/.files/.chunkwm/.chunkwmrc ~/.chunkwmrc
    ln -s /pathTo/.files/.chunkwm/.chunkwm_plugins ~/.chunkwm_plugins
    ln -s /pathTo/.files/.khd/.khdrc-chunkwm ~/.config/.khdrc
    # kwm
    ln -s /pathTo/.files/.kwm ~/.config/.kwm
    ln -s /pathTo/.files/.khd/.khdrc-kwm ~/.config/.khdrc
    # git
    ln -s /pathTo/.files/.gitconfig ~/.gitconfig
