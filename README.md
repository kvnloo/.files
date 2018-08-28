# .files
Welcome to my dot files! If you have any sugguestions or cool configurations feel free to contact me at dev@ek.vin

This repo has my configuration for the following programs:
  * [tmux](https://tmux.github.io/)
  * [zsh](zsh.org)
  * [oh-my-zsh](https://github.com/robbyrussell/oh-my-zsh)
  * [fish](https://fishshell.com/)
  * [oh-my-fish](https://github.com/oh-my-fish/oh-my-fish)
  * [vim](http://www.vim.org/) (I don't emacs)
  * [gitconfig](https://git-scm.com/docs/git-config)
  * [Hyper](hyper.is)
  
Then for MacOS I've got a custom config for the following:
  * [chunkwm](https://github.com/koekeishiya/chunkwm)
      
Then on Android I've got the following config files:
  * [Nova](http://novalauncher.com/) (nova master race)
  * [Zooper widget](https://play.google.com/store/apps/details?id=org.zooper.zwfree&hl=en)

On MacOS script.sh can be run to automatically install all my favorite programs and link my dotfiles (**be careful as this will destroy your existing dotfiles**).

Otherwise clone the repository, initialize the submodules, then create symlinks!


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
