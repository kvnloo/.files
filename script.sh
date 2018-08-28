# install homebrew
/usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"

# install hyper
brew cask install hyper

# install zsh, oh-my-zsh, zsh-autosuggestions
brew install zsh
sh -c "$(curl -fsSL https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"
brew install zsh-autosuggestions

# install window manager
brew tap crisidev/homebrew-chunkwm
brew install chunkwm

# install random packages
brew install cowsay sl

# clone dotfiles
git clone https://github.com/lesseradmin/.files ~/.files

# create symlinks
ln -s ~/.files/.zsh/.zshrc ~/.zshrc
ln -s ~/.files/.oh-my-zsh ~/.oh-my-zsh
ln -s ~/.files/.vim/ ~/.vim
ln -s ~/.files/.vim/.vimrc ~/.vimrc
ln -s ~/.files/.chunkwm/.chunkwmrc ~/.chunkwmrc
ln -s ~/.files/.khd/.khdrc-chunkwm ~/.khdrc
ln -s ~/.files/.gitconfig ~/.gitconfig
ln -s ~/.files/.hyper.js ~/.hyper.js

