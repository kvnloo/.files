#!/usr/bin/env bash
# Shared helpers for dual-path onboarding (interactive script + LLM harness).
# shellcheck disable=SC2034

onboard_repo_root() {
  local here
  here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
  printf '%s\n' "$here"
}

onboard_state_dir() {
  printf '%s\n' "${XDG_STATE_HOME:-$HOME/.local/state}/dotfiles"
}

onboard_state_file() {
  printf '%s\n' "$(onboard_state_dir)/onboard.json"
}

onboard_ensure_state_dir() {
  mkdir -p "$(onboard_state_dir)"
}

onboard_now_iso() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

# Returns: cursor|claude|codex|opencode|gemini|omp|hermes|kimi|grok|unknown
onboard_detect_harness() {
  local harness="unknown"

  if [[ -n "${CURSOR_AGENT:-}" || -n "${CURSOR_TRACE_ID:-}" || -n "${CURSOR_SESSION_ID:-}" ]]; then
    harness="cursor"
  elif [[ -n "${CLAUDECODE:-}" || -n "${CLAUDE_CODE:-}" || -n "${CLAUDE_AGENT:-}" ]]; then
    harness="claude"
  elif [[ -n "${CODEX_HOME:-}" || -n "${CODEX_THREAD_ID:-}" || -n "${OPENAI_CODEX:-}" ]]; then
    harness="codex"
  elif [[ -n "${OPENCODE:-}" || -n "${OPENCODE_SESSION:-}" ]]; then
    harness="opencode"
  elif [[ -n "${GEMINI_CLI:-}" || -n "${GEMINI_API_KEY:-}" ]] && [[ -n "${TERM_PROGRAM:-}" ]]; then
    # Gemini CLI often leaves few markers; prefer process hints below.
    :
  fi

  if [[ "$harness" == "unknown" ]]; then
    local parent
    parent="$(ps -o comm= -p "${PPID:-0}" 2>/dev/null || true)"
    case "$parent" in
      cursor|Cursor*) harness="cursor" ;;
      claude|claude-code) harness="claude" ;;
      codex) harness="codex" ;;
      opencode) harness="opencode" ;;
      gemini) harness="gemini" ;;
      omp|oh-my-pi) harness="omp" ;;
      hermes) harness="hermes" ;;
      kimi|kimi-code) harness="kimi" ;;
      grok) harness="grok" ;;
    esac
  fi

  # Path / argv hints from common agent wrappers
  if [[ "$harness" == "unknown" ]]; then
    local tree
    tree="$(ps -o args= -p "${PPID:-0}" 2>/dev/null || true)"
    case "$tree" in
      *cursor*agent*|*Cursor*) harness="cursor" ;;
      *claude*) harness="claude" ;;
      *codex*) harness="codex" ;;
      *opencode*) harness="opencode" ;;
      *gemini*) harness="gemini" ;;
    esac
  fi

  printf '%s\n' "$harness"
}

onboard_prompt_yn() {
  # usage: onboard_prompt_yn "Question?" default_y|default_n
  local question="$1"
  local default="${2:-default_y}"
  local reply prompt

  if [[ "${ONBOARD_ASSUME_YES:-0}" == "1" ]]; then
    return 0
  fi
  if [[ "${ONBOARD_NONINTERACTIVE:-0}" == "1" ]]; then
    [[ "$default" == "default_y" ]]
    return $?
  fi

  if [[ "$default" == "default_y" ]]; then
    prompt="[Y/n]"
  else
    prompt="[y/N]"
  fi

  if ! read -r -p "$question $prompt: " reply; then
    return 1
  fi
  reply="${reply:-}"
  if [[ -z "$reply" ]]; then
    [[ "$default" == "default_y" ]]
    return $?
  fi
  [[ "$reply" == "y" || "$reply" == "Y" || "$reply" == "yes" || "$reply" == "YES" ]]
}

onboard_link() {
  local src="$1"
  local dst="$2"
  local dst_dir

  if [[ ! -e "$src" ]]; then
    printf '  skip (missing source): %s\n' "$src"
    return 0
  fi

  dst_dir="$(dirname "$dst")"
  mkdir -p "$dst_dir"

  if [[ -L "$dst" ]]; then
    rm -f "$dst"
  elif [[ -e "$dst" ]]; then
    if onboard_prompt_yn "Backup and replace existing $dst?" default_y; then
      mv "$dst" "${dst}.bak.$(date +%Y%m%d-%H%M%S)"
    else
      printf '  skipped %s\n' "$dst"
      return 0
    fi
  fi

  ln -sfn "$src" "$dst"
  printf '  linked %s -> %s\n' "$dst" "$src"
}

onboard_mark_module() {
  local module="$1"
  local status="${2:-done}"
  local state_file harness
  state_file="$(onboard_state_file)"
  harness="$(onboard_detect_harness)"
  onboard_ensure_state_dir

  python3 - "$state_file" "$module" "$status" "$harness" <<'PY'
import json, pathlib, sys
from datetime import datetime, timezone

path = pathlib.Path(sys.argv[1])
module, status, harness = sys.argv[2], sys.argv[3], sys.argv[4]
data = {}
if path.exists():
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        data = {}
modules = data.setdefault("modules", {})
modules[module] = {
    "status": status,
    "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "harness": harness,
}
data["updated_at"] = modules[module]["updated_at"]
data["last_harness"] = harness
path.write_text(json.dumps(data, indent=2) + "\n")
PY
}

onboard_module_status() {
  local module="$1"
  local state_file
  state_file="$(onboard_state_file)"
  if [[ ! -f "$state_file" ]]; then
    printf 'pending\n'
    return
  fi
  python3 - "$state_file" "$module" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
module = sys.argv[2]
try:
    data = json.loads(path.read_text())
except Exception:
    print("pending")
    raise SystemExit(0)
print(data.get("modules", {}).get(module, {}).get("status", "pending"))
PY
}

onboard_is_tty() {
  [[ -t 0 && -t 1 ]]
}
