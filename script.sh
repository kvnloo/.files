# install homebrew
/usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"

# install hyper
brew cask install hyper

# hide scrollbar in terminal
defaults write com.apple.Terminal AppleShowScrollBars -string WhenScrolling

# install zsh, oh-my-zsh, zsh-autosuggestions
brew install zsh
sh -c "$(curl -fsSL https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"
brew install zsh-autosuggestions

# install window manager
brew tap crisidev/homebrew-chunkwm
brew install chunkwm

# install random packages
brew install cowsay sl tmux archey z

# clone dotfiles
git clone https://github.com/lesseradmin/.files ~/.files

# create symlinks
rm ~/.zshrc
ln -s ~/.files/.zsh/.zshrc ~/.zshrc
rm ~/.oh-my-zsh
ln -s ~/.files/.oh-my-zsh ~/.oh-my-zsh
rm ~/.vim
ln -s ~/.files/.vim/ ~/.vim
rm ~/.vimrc
ln -s ~/.files/.vim/.vimrc ~/.vimrc
rm ~/.chunkwmrc
ln -s ~/.files/.chunkwm/.chunkwmrc ~/.chunkwmrc
rm ~/.khdrc
ln -s ~/.files/.khd/.khdrc-chunkwm ~/.khdrc
rm ~/.gitconfig
ln -s ~/.files/.gitconfig ~/.gitconfig
rm ~/.hyper.js
ln -s ~/.files/.hyper.js ~/.hyper.js
rm ~/.zsh
ln -s ~/.files/.zsh/zsh-autosuggestions ~/.zsh/zsh-autosuggestions
