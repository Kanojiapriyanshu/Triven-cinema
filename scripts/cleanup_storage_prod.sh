#!/bin/bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
"$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/scripts/backup_state.py"
exec "$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/scripts/cleanup_storage.py" --apply
