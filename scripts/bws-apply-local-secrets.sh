#!/usr/bin/env bash
# Refresh only per-consumer runtime credentials. No persistent dotenv secrets.
set -euo pipefail
script_dir="$(CDPATH= cd -- "$(dirname -- "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
exec "$script_dir/bws-env-exec" --refresh
