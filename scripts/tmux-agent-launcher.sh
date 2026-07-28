#!/usr/bin/env bash
set -euo pipefail

# tmux servers retain the environment they were started with. Include user
# agent install locations even when the server predates the current zsh PATH.
export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"

command -v tmux >/dev/null 2>&1 || exit 1
if ! command -v fzf >/dev/null 2>&1; then
    tmux display-message "agent launcher requires fzf"
    exit 1
fi

catalog=$'claude\tClaude Code\tAnthropic coding agent\nomp\tOh My Pi\tAgentic engineering harness\nhermes\tHermes\tPersistent autonomous agent\ncodex\tCodex CLI\tOpenAI coding agent\nopencode\tOpenCode\tProvider-agnostic coding agent\ngemini\tGemini CLI\tGoogle coding agent\nkimi\tKimi Code\tMoonshot coding agent\ngrok\tGrok CLI\txAI coding agent'
available=''
while IFS=$'\t' read -r command label description; do
    if executable="$(command -v "$command" 2>/dev/null)"; then
        available+="$command"$'\t'"$label"$'\t'"$description"$'\t'"$executable"$'\n'
    fi
done <<< "$catalog"

[[ -n "$available" ]] || {
    tmux display-message "no supported coding agents found"
    exit 1
}

selection="$(
    printf '%s' "$available" |
        fzf \
            --delimiter=$'\t' \
            --with-nth=2,3 \
            --no-multi \
            --layout=reverse \
            --border=rounded \
            --info=inline-right \
            --prompt='󰚩 launch › ' \
            --pointer='▶' \
            --header='enter: launch in a new project window  ·  esc: close' \
            --color='bg:#1a1b26,bg+:#24283b,fg:#a9b1d6,fg+:#c0caf5,hl:#7dcfff,hl+:#7aa2f7,border:#565f89,prompt:#7dcfff,pointer:#bb9af7,spinner:#e0af68,header:#565f89'
)" || exit 0

[[ -n "$selection" ]] || exit 0
IFS=$'\t' read -r command _label _description executable <<< "$selection"
if command -v systemd-run >/dev/null 2>&1; then
    printf -v launch_command \
        'exec systemd-run --user --scope --collect --quiet --slice=agent.slice -- %q' \
        "$executable"
else
    printf -v launch_command 'exec %q' "$executable"
fi
tmux new-window -c "$PWD" -n "$command" "$launch_command"
