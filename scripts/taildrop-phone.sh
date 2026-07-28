#!/usr/bin/env bash
# Stage files in the tailnet portal by default; native Taildrop remains opt-in.
set -euo pipefail

mode=portal
case ${1:-} in
  --native) mode=native; shift ;;
  --portal) shift ;;
  --clear)
    outbox=$HOME/Downloads/Taildrop/To\ Phone
    mkdir -p "$outbox"
    find "$outbox" -mindepth 1 -maxdepth 1 -type f -delete
    find "$outbox" -mindepth 1 -maxdepth 1 -type l -delete
    printf 'Cleared PC-to-phone staging area.\n'
    exit 0
    ;;
esac

if (($# == 0)); then
  printf 'usage: %s [--portal|--native] FILE [FILE ...]\n' "${0##*/}" >&2
  printf '       %s --clear\n' "${0##*/}" >&2
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

phone_name=${selection%%$'\t'*}
target=${selection#*$'\t'}
if [[ $mode == native ]]; then
  printf 'Sending natively to %s…\n' "$phone_name"
  exec tailscale file cp -- "$@" "$target:"
fi

outbox=$HOME/Downloads/Taildrop/To\ Phone
mkdir -p "$outbox"
for source in "$@"; do
  source=$(realpath -- "$source")
  name=${source##*/}
  stem=${name%.*}
  suffix=
  [[ $name == *.* ]] && suffix=.${name##*.}
  [[ -n $suffix ]] || stem=$name
  destination=$outbox/$name
  index=1
  while [[ -e $destination || -L $destination ]]; do
    destination=$outbox/$stem\ \($index\)$suffix
    ((index++))
  done
  ln -- "$source" "$destination" 2>/dev/null || cp --reflink=auto --preserve=timestamps -- "$source" "$destination"
  printf 'Staged %s\n' "${destination##*/}"
done

dns_name=$(tailscale status --json | jq -r '.Self.DNSName // empty | rtrimstr(".")')
[[ -n $dns_name ]] || { printf 'this device has no Tailscale DNS name\n' >&2; exit 1; }
url=https://$dns_name/drop/
printf '\nOpen on %s:\n%s\n' "$phone_name" "$url"
if command -v notify-send >/dev/null 2>&1; then
  notify-send -a taildrop-phone "Files ready for $phone_name" "$url"
fi
