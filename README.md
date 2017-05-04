# .files
Welcome to my dot files! If you have any sugguestions or cool configurations feel free to contact me at lesseradmin@ek.vin

This repo has my configuration for the following "tools"
  * Universal
    * Custom Shells:
      * tmux config
      * zsh (zsh is cool)
        * oh-my-zsh (gotta theme up my zsh)
      * fish (I prefer zsh)
        * oh-my-fish (gotta theme up my fish)
    * vim (I don't emacs)
    * gitconfig (cuz whatthecommit.com)
  * MacOS Specific:
    * Tiling Window Managers:
      * chunkwm (still in alpha stage but I like it better)
      * kwm
    * Terminal Skins
      * iTermColors
      * Hyper Terminal Config
  * Linux / Arch
    * i3 config coming soon
  * Android (if you don't customize your phone life gets boring):
    * Nova backup (nova master race)
    * Zooper widget

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
