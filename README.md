# .files
Welcome to my dot files! If you have any sugguestions or cool configurations feel free to contact me at lesseradmin@ek.vin

This repo has my configuration for the following "tools"
  * vim (I don't emacs)
  * fish (I prefer zsh)
  * oh-my-fish (gotta theme up my fish)
  * zsh (zsh is cool)
  * oh-my-zsh (gotta theme up my zsh)
  * gitconfig (cuz whatthecommit.com)
  * Android stuff (if you don't customize your phone life gets boring)
    * Nova backup (nova master race)
    * Zooper widget

# Clone the repo

    git clone https://github.com/lesseradmin/.files 

# Install all the submodules
    
    cd .files
    git submodule update --recursive --init

# Create symlinks

    ln -s /pathTo/.files/.vim/ ~/.vim
    ln -s /pathTo/.files/.vim/.vimrc ~/.vimrc
    ln -s /pathTo/.files/.fish/ ~/.config/fish
    ln -s /pathTo/.files/.omf/ ~/.config/omf
    ln -s /pathTo/.files/.kwm ~/.config/.kwm
    ln -s /pathTo/.files/.khd/.khdrc ~/.config/.khdrc
    ln -s /pathTo/.files/.zsh/.zshrc ~/.zshrc
    ln -s /pathTo/.files/.oh-my-zsh ~/.oh-my-zsh
