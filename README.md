# .files
My dotfiles folder

Has my vim config, and fish config

    git clone https://github.com/lesseradmin/.files 

# Install all the submodules
    
    cd .files
    git submodule update --recursive --init

# Create symlinks!

    ln -s /pathTo/.files/.vim/ ~/.vim
    ln -s /pathTo/.files/.vim/.vimrc ~/.vimrc
    ln -s /pathTo/.files/.fish/ ~/.config/fish
    ln -s /pathTo/.files/.omf/ ~/.config/omf
    ln -s /pathTo/.files/.kwm ~/.config/.kwm
    ln -s /pathTo/.files/.khd/.khdrc ~/.config/.khdrc
    ln -s /pathTo/.files/.zsh/.zshrc ~/.zshrc
    ln -s /pathTo/.files/.oh-my-zsh ~/.oh-my-zsh
