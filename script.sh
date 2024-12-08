
#!/bin/bash

# Desired repository URL
DOTFILES_REPO_URL="git@github.com:kvnloo/.files"

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

#######################################
# Functions
#######################################

normalize_repo_url() {
    local url="$1"
    # Strip protocols and '.git' suffix, leaving 'author/repo'
    echo "$url" \
        | sed -E 's#^(git@|https://|ssh://git@)?github.com[:/]+##' \
        | sed -E 's#.git$##'
}

install_homebrew() {
    if ! command -v brew &>/dev/null; then
        echo "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    else
        echo "Homebrew is already installed."
    fi
}

already_in_repo() {
    if git -C "$SCRIPT_DIR" rev-parse --is-inside-work-tree &>/dev/null; then
        remote_url=$(git -C "$SCRIPT_DIR" remote get-url origin 2>/dev/null)
        normalized_remote=$(normalize_repo_url "$remote_url")
        normalized_target=$(normalize_repo_url "$DOTFILES_REPO_URL")

        if [[ "$normalized_remote" == "$normalized_target" ]]; then
            return 0  # True: already in the correct repo
        fi
    fi
    return 1  # False: not in the correct repo
}

clone_dotfiles() {
    if already_in_repo; then
        echo "You are already inside the dotfiles repository ($(normalize_repo_url "$DOTFILES_REPO_URL"))."
        echo "Skipping cloning..."
        DOTFILES_REPO="$SCRIPT_DIR"
        return
    fi

    echo "Please specify where you'd like to clone the dotfiles repository."
    read -p "Press Enter for default [$HOME/.files]: " DOTFILES_REPO
    DOTFILES_REPO="${DOTFILES_REPO:-$HOME/.files}"

    if [[ ! -d "$DOTFILES_REPO" ]]; then
        echo "Cloning dotfiles repository into $DOTFILES_REPO..."
        git clone "$DOTFILES_REPO_URL" "$DOTFILES_REPO"
    else
        echo "Dotfiles repository already exists at $DOTFILES_REPO."
    fi
}

is_installed() {
    command -v "$1" &>/dev/null
}

install_packages() {
    global_packages=("zsh" "zsh-autosuggestions" "cowsay" "sl" "tmux" "archey" "vim" "git")
    ubuntu_packages=("i3" "curl" "git-all" "gh")
    macos_casks=("hyper" "spotify" "spotmenu" "cheatsheet" "google-chrome" "avibrazil-rdm" "sublime-text" "firefox-developer-edition" "slack")

    if [[ "$OS" == "Darwin" ]]; then
        echo "Installing macOS applications with Homebrew..."
        for package in "${global_packages[@]}"; do
            if is_installed "$package"; then
                echo "$package is already installed."
            else
                echo "Installing $package..."
                brew install "$package"
            fi
        done

        for cask in "${macos_casks[@]}"; do
            if brew list --cask "$cask" &>/dev/null; then
                echo "$cask is already installed."
            else
                echo "Installing $cask..."
                brew install --cask "$cask"
            fi
        done
    elif [[ "$OS" == "Linux" ]]; then
        if [[ -f /etc/os-release && "$(grep -i 'ubuntu' /etc/os-release)" ]]; then
            echo "Detected Ubuntu. Installing packages with apt..."
            sudo apt update
            for package in "${global_packages[@]}"; do
                if is_installed "$package"; then
                    echo "$package is already installed."
                else
                    echo "Installing $package..."
                    sudo apt install -y "$package"
                fi
            done

            for package in "${ubuntu_packages[@]}"; do
                if is_installed "$package"; then
                    echo "$package is already installed."
                else
                    echo "Installing $package..."
                    sudo apt install -y "$package"
                fi
            done

            echo "Installing additional Ubuntu-specific configurations..."
            if ! is_installed "liquorix"; then
                curl -s 'https://liquorix.net/install-liquorix.sh' | sudo bash
            fi

            if ! grep -q "windsurf" /etc/apt/sources.list.d/*; then
                curl -fsSL "https://windsurf-stable.codeiumdata.com/wVxQEIWkwPUEAGf3/windsurf.gpg" | sudo gpg --dearmor -o /usr/share/keyrings/windsurf-stable-archive-keyring.gpg
                echo "deb [signed-by=/usr/share/keyrings/windsurf-stable-archive-keyring.gpg arch=amd64] https://windsurf-stable.codeiumdata.com/wVxQEIWkwPUEAGf3/apt stable main" | sudo tee /etc/apt/sources.list.d/windsurf.list > /dev/null
                sudo apt-get update
                sudo apt-get upgrade -y windsurf
            else
                echo "Windsurf is already configured."
            fi

            if is_installed "gh"; then
                echo "GitHub CLI is already installed."
            else
                gh auth login
            fi
        else
            echo "Linux detected, but not Ubuntu. Skipping package installation."
        fi
    fi
}

create_symlink() {
    local source="$1"
    local target="$2"
    local filename="$(basename "$target")"

    # Check if target already exists
    if [[ -e "$target" || -L "$target" ]]; then
        # File exists
        echo "THIS WILL DELETE EXISTING REPO FILE: $filename"
        read -p "Proceed? [y/N]: " confirm
        if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
            echo "Skipped $filename"
            return
        fi
        rm -rf "$target"
        echo "Removed existing $target"
    else
        # File does not exist
        echo "Do you want to link $filename?"
        read -p "[y/N]: " confirm
        if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
            echo "Skipped $filename"
            return
        fi
    fi

    ln -s "$source" "$target"
    echo "Linked $source to $target"
}

setup_symlinks() {
    if [[ -z "$DOTFILES_REPO" || ! -d "$DOTFILES_REPO" ]]; then
        echo "You haven't cloned the dotfiles repository yet in this session."
        echo "Please specify the directory where dotfiles are cloned."
        read -p "Press Enter for default [$HOME/.files]: " DOTFILES_REPO
        DOTFILES_REPO="${DOTFILES_REPO:-$HOME/.files}"
        if [[ ! -d "$DOTFILES_REPO" ]]; then
            echo "Directory $DOTFILES_REPO does not exist. Please clone the repository first."
            return
        fi
    fi

    # Collect all files to symlink
    files_to_link=("${universal_files[@]}")
    if [[ "$OS" == "Linux" && -f /etc/os-release && "$(grep -i 'ubuntu' /etc/os-release)" ]]; then
        files_to_link+=("${ubuntu_files[@]}")
    elif [[ "$OS" == "Darwin" ]]; then
        files_to_link+=("${macos_files[@]}")
    fi

    # Create symlinks with per-file prompts
    for file in "${files_to_link[@]}"; do
        if [[ -e "$DOTFILES_REPO/$file" ]]; then
            create_symlink "$DOTFILES_REPO/$file" "$HOME/$file"
        else
            echo "Skipping $file because it does not exist in the repo."
        fi
    done

    echo "Symlinking completed."
}

#######################################
# Intro Menu
#######################################

clear
echo "=========================================="
echo "  Welcome to the Dotfiles Setup Script!  "
echo "=========================================="
echo "Please select an option from the menu:"
echo "1) Do everything (install Homebrew, clone dotfiles, install packages, and setup symlinks)"
echo "2) Install packages only"
echo "3) Setup dotfile symlinks only"
echo "4) Quit"
echo

read -p "Enter your choice [1-4]: " choice

case $choice in
    1)
        # Do everything
        install_homebrew
        clone_dotfiles
        install_packages
        setup_symlinks
        ;;
    2)
        # Install packages only
        install_homebrew
        clone_dotfiles
        install_packages
        ;;
    3)
        # Setup symlinks only
        if [[ -z "$DOTFILES_REPO" || ! -d "$DOTFILES_REPO" ]]; then
            clone_dotfiles
        fi
        setup_symlinks
        ;;
    4)
        echo "Exiting..."
        exit 0
        ;;
    *)
        echo "Invalid choice, exiting..."
        exit 1
        ;;
esac

echo "Make sure to configure git user name and email in .gitconfig."
if [[ "$OS" == "Darwin" ]]; then
    echo "For macOS: Remember to configure macOS Terminal settings as needed."
fi

