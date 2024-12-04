#!/bin/bash

# Get the directory of the script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Detect the operating system
OS="$(uname -s)"
echo "Detected OS: $OS"

# Define universal files to symlink
universal_files=(".gitconfig" ".zshrc" ".vim" ".vimrc" ".tmux.conf")

# Define OS-specific configurations
ubuntu_files=(".i3")
macos_files=(".yabai" ".skhd")

# Function to install Homebrew
install_homebrew() {
    if ! command -v brew &>/dev/null; then
        echo "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    else
        echo "Homebrew is already installed."
    fi
}

# Function to clone dotfiles repository
clone_dotfiles() {
    DOTFILES_REPO="$HOME/.files"
    if [[ ! -d "$DOTFILES_REPO" ]]; then
        echo "Cloning dotfiles repository..."
        git clone https://github.com/lesseradmin/.files "$DOTFILES_REPO"
    else
        echo "Dotfiles repository already exists at $DOTFILES_REPO."
    fi
}

# Function to install necessary packages
install_packages() {
    # Define global packages (common for macOS and Ubuntu)
    global_packages=("zsh" "zsh-autosuggestions" "cowsay" "sl" "tmux" "archey" "vim" "git")

    # Define Ubuntu-specific packages
    ubuntu_packages=("i3" "curl" "git-all" "gh")

    # Define macOS-specific casks
    macos_casks=("hyper" "spotify" "spotmenu" "cheatsheet" "google-chrome" "avibrazil-rdm" "sublime-text" "firefox-developer-edition" "slack")

    if [[ "$OS" == "Darwin" ]]; then
        echo "Installing macOS applications with Homebrew..."

        # Install global packages
        for package in "${global_packages[@]}"; do
            if brew list "$package" &>/dev/null; then
                echo "$package is already installed."
            else
                echo "Installing $package..."
                brew install "$package"
            fi
        done

        # Install macOS-specific casks
        for cask in "${macos_casks[@]}"; do
            if brew list --cask "$cask" &>/dev/null; then
                echo "$cask is already installed."
            else
                echo "Installing $cask..."
                brew install --cask "$cask"
            fi
        done
    elif [[ "$OS" == "Linux" ]]; then
        # Check if the system is Ubuntu
        if [[ -f /etc/os-release && "$(grep -i 'ubuntu' /etc/os-release)" ]]; then
            echo "Detected Ubuntu. Installing packages with apt..."
            sudo apt update

            # Install global packages
            for package in "${global_packages[@]}"; do
                if dpkg -l | grep -qw "$package"; then
                    echo "$package is already installed."
                else
                    echo "Installing $package..."
                    sudo apt install -y "$package"
                fi
            done

            # Install Ubuntu-specific packages
            for package in "${ubuntu_packages[@]}"; do
                if dpkg -l | grep -qw "$package"; then
                    echo "$package is already installed."
                else
                    echo "Installing $package..."
                    sudo apt install -y "$package"
                fi
            done

            # Additional custom installations
            echo "Installing additional Ubuntu-specific configurations..."
            # Install Liquorix kernel
            curl -s 'https://liquorix.net/install-liquorix.sh' | sudo bash

            # Install Codeium (Windsurf)
            curl -fsSL "https://windsurf-stable.codeiumdata.com/wVxQEIWkwPUEAGf3/windsurf.gpg" | sudo gpg --dearmor -o /usr/share/keyrings/windsurf-stable-archive-keyring.gpg
            echo "deb [signed-by=/usr/share/keyrings/windsurf-stable-archive-keyring.gpg arch=amd64] https://windsurf-stable.codeiumdata.com/wVxQEIWkwPUEAGf3/apt stable main" | sudo tee /etc/apt/sources.list.d/windsurf.list > /dev/null
            sudo apt-get update
            sudo apt-get upgrade -y windsurf

            # GitHub CLI Authentication
            gh auth login
        else
            echo "Linux detected, but not Ubuntu. Skipping package installation."
        fi
    fi
}


# Function to create symlinks
create_symlink() {
    local source="$1"
    local target="$2"

    if [[ -e "$target" || -L "$target" ]]; then
        # Existing file/folder/symlink detected
        read -p "An existing configuration at $target will be removed. Proceed? [y/N]: " confirm
    else
        # No existing file/folder/symlink
        read -p "Do you want to link $source to $target? [y/N]: " confirm
    fi

    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "Skipped $source"
        return
    fi

    # Remove existing target if it exists
    if [[ -e "$target" || -L "$target" ]]; then
        rm -rf "$target"
        echo "Removed existing $target"
    fi

    # Create the symlink
    ln -s "$source" "$target"
    echo "Linked $source to $target"
}

# Install Homebrew
install_homebrew

# Clone dotfiles repository
clone_dotfiles

# Install packages
install_packages

# Symlink universal files
for file in "${universal_files[@]}"; do
    if [[ -e "$SCRIPT_DIR/$file" ]]; then
        create_symlink "$SCRIPT_DIR/$file" "$HOME/$file"
    fi
done

# Symlink OS-specific files
if [[ "$OS" == "Linux" ]]; then
    # Check for Ubuntu
    if [[ -f /etc/os-release && "$(grep -i 'ubuntu' /etc/os-release)" ]]; then
        echo "Detected Ubuntu"
        for file in "${ubuntu_files[@]}"; do
            if [[ -e "$SCRIPT_DIR/$file" ]]; then
                create_symlink "$SCRIPT_DIR/$file" "$HOME/$file"
            fi
        done
    fi
elif [[ "$OS" == "Darwin" ]]; then
    echo "Detected macOS"
    for file in "${macos_files[@]}"; do
        if [[ -e "$SCRIPT_DIR/$file" ]]; then
            create_symlink "$SCRIPT_DIR/$file" "$HOME/$file"
        fi
    done
else
    echo "Unsupported operating system: $OS"
fi

echo "Symlinking completed."

# Final user reminders
echo "Make sure to configure git user name and email in .gitconfig."
if [[ "$OS" == "Darwin" ]]; then
    echo "For macOS: Remember to configure macOS Terminal settings as needed."
fi

