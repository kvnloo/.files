#!/usr/bin/env bash
set -uo pipefail

action=${1:-status}
hypridle_config=${HYPRIDLE_CONFIG:-$HOME/.config/hypr/hypridle.conf}
hyprcaffeine_bin=${HYPRCAFFEINE_BIN:-hyprcaffeine}

timeout_seconds=0
infinite=false
available=true
error=""

append_error() {
  if [[ -n $error ]]; then
    error+="; $1"
  else
    error=$1
  fi
}

read_dpms_timeout() {
  [[ -r $hypridle_config ]] || return 1

  local line=""
  local listener_block=""
  local in_listener=false
  local action_pattern='on-timeout[[:space:]]*=[^;}]*hyprctl[[:space:]]+dispatch[[:space:]]+dpms[[:space:]]+off'
  local timeout_pattern='timeout[[:space:]]*=[[:space:]]*([0-9]+)'
  while IFS= read -r line || [[ -n $line ]]; do
    line=${line%%#*}
    if [[ $in_listener == false ]]; then
      if [[ ! $line =~ ^[[:space:]]*listener[[:space:]]*\{ ]]; then
        continue
      fi
      in_listener=true
      listener_block=$line
    else
      listener_block+=" $line"
    fi

    if [[ $listener_block != *"}"* ]]; then
      continue
    fi

    if [[ $listener_block =~ $action_pattern ]] &&
       [[ $listener_block =~ $timeout_pattern ]]; then
      timeout_seconds=${BASH_REMATCH[1]}
      return 0
    fi

    in_listener=false
    listener_block=""
  done < "$hypridle_config"
  return 1
}

format_timeout() {
  local seconds=$1
  if (( seconds > 0 && seconds % 3600 == 0 )); then
    printf '%dh' "$((seconds / 3600))"
  elif (( seconds > 0 && seconds % 60 == 0 )); then
    printf '%dm' "$((seconds / 60))"
  else
    printf '%ds' "$seconds"
  fi
}

resolve_hyprcaffeine() {
  if [[ $hyprcaffeine_bin == */* ]]; then
    [[ -x $hyprcaffeine_bin ]] || return 1
    printf '%s' "$hyprcaffeine_bin"
    return 0
  fi
  command -v "$hyprcaffeine_bin" 2>/dev/null
}

if ! read_dpms_timeout; then
  append_error "DPMS timeout not found in $hypridle_config"
fi

caffeine_command=""
if ! caffeine_command=$(resolve_hyprcaffeine); then
  available=false
  append_error "HyprCaffeine is not installed"
fi

case "$action" in
  status)
    ;;
  enable)
    if [[ $available == true ]] && ! "$caffeine_command" monitor on >/dev/null 2>&1; then
      append_error "HyprCaffeine failed to enable monitor inhibition"
    fi
    ;;
  disable)
    if [[ $available == true ]] && ! "$caffeine_command" monitor off >/dev/null 2>&1; then
      append_error "HyprCaffeine failed to disable monitor inhibition"
    fi
    ;;
  *)
    append_error "Unknown action: $action"
    ;;
esac

if [[ $available == true ]]; then
  waybar_json=$("$caffeine_command" waybar 2>/dev/null) || {
    waybar_json=""
    append_error "HyprCaffeine status is unavailable"
  }
  if [[ -z $waybar_json ]]; then
    append_error "HyprCaffeine returned empty status"
  else
    state_class=$(jq -r '.class // ""' <<< "$waybar_json" 2>/dev/null) || {
      state_class=""
      append_error "HyprCaffeine returned invalid status"
    }
    if [[ $state_class == *monitor* || $state_class == hc-all ]]; then
      infinite=true
    fi
  fi
fi

if [[ $infinite == true ]]; then
  label=INF
elif (( timeout_seconds > 0 )); then
  label=$(format_timeout "$timeout_seconds")
else
  label='?'
fi

jq -cn \
  --argjson available "$available" \
  --argjson infinite "$infinite" \
  --argjson timeoutSeconds "$timeout_seconds" \
  --arg label "$label" \
  --arg error "$error" \
  '{available:$available,infinite:$infinite,timeoutSeconds:$timeoutSeconds,label:$label,error:$error}'

[[ -z $error ]]
