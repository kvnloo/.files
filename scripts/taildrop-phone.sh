#!/usr/bin/env bash
set -euo pipefail

if (($# == 0)); then
  printf 'usage: %s FILE [FILE ...]\n' "${0##*/}" >&2
  exit 2
fi
command -v tailscale >/dev/null 2>&1 || { printf 'tailscale is required\n' >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { printf 'jq is required\n' >&2; exit 1; }

for path in "$@"; do
  [[ -f $path ]] || { printf 'not a regular file: %s\n' "$path" >&2; exit 1; }
done

mapfile -t phones < <(
  tailscale status --json | jq -r '
    [.Peer[] | select(.OS == "android" and .Online == true)]
    | sort_by(.HostName // .DNSName // "")[]
    | [(.HostName // .DNSName // .TailscaleIPs[0]), .TailscaleIPs[0]]
    | @tsv
  '
)

case ${#phones[@]} in
  0)
    printf 'no Android phone is online in this tailnet\n' >&2
    exit 1
    ;;
  1)
    selection=${phones[0]}
    ;;
  *)
    command -v fzf >/dev/null 2>&1 || {
      printf 'multiple Android phones are online; install fzf to choose one\n' >&2
      exit 1
    }
    selection=$(printf '%s\n' "${phones[@]}" | fzf --delimiter=$'\t' --with-nth=1 --prompt='Taildrop to › ') || exit 0
    ;;
esac

target=${selection#*$'\t'}
printf 'Sending to %s…\n' "${selection%%$'\t'*}"
tailscale file cp -- "$@" "$target:"
