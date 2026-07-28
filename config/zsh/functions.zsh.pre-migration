# ==============================================================================
# CUSTOM FUNCTIONS
# ==============================================================================
# Shell functions for extended functionality

# ──────────────────────────────────────────────────────────────────────────────
# Terminal Color Testing
# ──────────────────────────────────────────────────────────────────────────────

# Display all terminal color combinations
all_colors() {
  for x in {0..8}; do
    for i in {30..37}; do
      for a in {40..47}; do
        echo -ne "\e[$x;$i;$a""m\\\e[$x;$i;$a""m\e[0;37;40m "
      done
      echo
    done
  done
  echo ""
}

# Display quick color palette reference
colors() {
  echo "\n\u001b[0m\u001b[31m\u001b[41m   \u001b[0m\u001b[31m\u001b[41m   \u001b[0m\u001b[32m\u001b[42m   \u001b[0m\u001b[32m\u001b[42m   \u001b[0m\u001b[33m\u001b[43m   \u001b[0m\u001b[33m\u001b[43m   \u001b[0m\u001b[34m\u001b[44m   \u001b[0m\u001b[34m\u001b[44m   \u001b[0m\u001b[35m\u001b[45m   \u001b[0m\u001b[35m\u001b[45m   \u001b[0m\u001b[36m\u001b[46m   \u001b[0m\u001b[36m\u001b[46m   \u001b[0m\u001b[37m\u001b[47m   \u001b[0m\u001b[37m\u001b[47m   \n"
}

# ──────────────────────────────────────────────────────────────────────────────
# macOS Specific Functions
# ──────────────────────────────────────────────────────────────────────────────

# Mount EFI partition (macOS only)
# Usage: efimount
efimount() {
  efidisk=$(diskutil list | grep "EFI EFI" | grep -o -E 'disk[0-9]*s[0-9]*')
  sudo mkdir /Volumes/efi && sudo mount -t msdos /dev/$efidisk /Volumes/efi && cd /Volumes/efi
}

# Adjust trackpad speed (macOS only)
# Usage: trackpad_speed <number>
# Example: trackpad_speed 2.5
trackpad_speed() {
  defaults write -g com.apple.mouse.scaling $1
}
