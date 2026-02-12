#!/usr/bin/env bash
# Setup AutoEQ Python venv for on-the-fly FIR filter generation
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$PROJECT_DIR/.venv/autoeq"

if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python" ]; then
  echo "✓ AutoEQ venv already exists at $VENV_DIR"
  "$VENV_DIR/bin/python" -m autoeq --help >/dev/null 2>&1 && echo "✓ autoeq package is installed" || {
    echo "→ Reinstalling autoeq package..."
    "$VENV_DIR/bin/pip" install --quiet autoeq
    echo "✓ autoeq installed"
  }
  exit 0
fi

echo "→ Creating Python venv at $VENV_DIR..."
python3 -m venv "$VENV_DIR"

echo "→ Installing autoeq package..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet autoeq

echo "✓ AutoEQ venv ready at $VENV_DIR"
echo "  Python: $VENV_DIR/bin/python"
echo "  AutoEQ: $("$VENV_DIR/bin/python" -c 'import autoeq; print(autoeq.__version__)' 2>/dev/null || echo 'installed')"
