# ==============================================================================
# STARTUP PROGRAMS
# ==============================================================================
# Visual programs that run on shell start (loaded last for performance)
# Only runs on first terminal of the session to avoid ~500ms overhead on every shell

if [[ ! -f "/tmp/.zsh-started-$UID" ]]; then
  # System Information Display
  # fastfetch (Linux/CachyOS) or archey (macOS)
  if command -v fastfetch &>/dev/null; then
    fastfetch
  elif command -v archey &>/dev/null; then
    archey -o
  fi

  # Welcome Message
  # Requires: cowsay, lolcat
  if command -v cowsay &>/dev/null && command -v lolcat &>/dev/null; then
    cowsay -f dragon "hello!" | lolcat
  fi

  # Color Palette Display
  command -v colors &>/dev/null && colors

  touch "/tmp/.zsh-started-$UID"
fi
