#!/usr/bin/env bash
# Legacy entry point — forwards to the dual-path onboarding installer.
# See docs/SETUP.md and AGENTS.md.
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

cat <<'EOF'
script.sh is deprecated.
Launching the interactive onboarding installer (./install).
Docs: docs/SETUP.md
EOF

exec "$root/install" "$@"
