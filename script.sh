# install homebrew
/usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"

# clone dotfiles
git clone https://github.com/lesseradmin/.files ~/.files

# symlink new gitconfig
rm ~/.gitconfig
ln -s ~/.files/.gitconfig ~/.gitconfig
echo "Remember to change your email and name."

# install apps
brew cask install hyper spotify spotmenu cheatsheet google-chrome avibrazil-rdm sublime-text firefox-developer-edition
echo "Make sure to sign into Spotify and Google Chrome to pull user preferences"

# symlink new hyper config
rm ~/.hyper.js
ln -s ~/.files/.hyper.js ~/.hyper.js

# hide scrollbar in terminal
defaults write com.apple.Terminal AppleShowScrollBars -string WhenScrolling
echo "Open terminal -> Preferences (CMD + ',') -> Profiles -> Settings Cog -> Import... -> Select ~/.files/Chesterish.terminal"

# create symlinks for vim
echo "Removing default vim config files and symlinking new config files."
rm ~/.vim
rm ~/.vimrc
ln -s ~/.files/.vim/ ~/.vim
ln -s ~/.files/.vim/.vimrc ~/.vimrc

# install zsh, oh-my-zsh, zsh-autosuggestions
brew install zsh
sh -c "$(curl -fsSL https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"
brew install zsh-autosuggestions
echo "Removing default zsh config files and symlinking new config files."
rm ~/.zsh
rm ~/.zshrc
rm ~/.oh-my-zsh
ln -s ~/.files/.zsh/.zshrc ~/.zshrc
ln -s ~/.files/.oh-my-zsh ~/.oh-my-zsh

ln -s ~/.files/.zsh/zsh-autosuggestions ~/.zsh/zsh-autosuggestions

# install window manager
brew tap crisidev/homebrew-chunkwm
brew install chunkwm skhd
rm ~/.chunkwmrc
rm ~/.skhdrc
ln -s ~/.files/.chunkwm/.chunkwmrc ~/.chunkwmrc
ln -s ~/.files/.khd/.khdrc-chunkwm ~/.skhdrc

# install random packages
brew install cowsay sl tmux archey z
