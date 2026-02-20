# ==============================================================================
# STARTUP PROGRAMS
# ==============================================================================
# Visual programs that run on shell start (loaded last for performance)
# Only runs on first terminal of the session to avoid ~500ms overhead on every shell

if [[ ! -f "/tmp/.zsh-started-$UID" ]]; then
  # System Information Display
  # Requires: fastfetch (pacman -S fastfetch)
  fastfetch

  # Welcome Message
  # Requires: cowsay, lolcat
  # cowsay -f dragon "hello!" | lolcat

  # Color Palette Display
  colors

  touch "/tmp/.zsh-started-$UID"
fi
