#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/services/api"

if [ ! -x "$ROOT_DIR/.venv/bin/python" ]; then
  echo "Missing .venv. Create it and install services/api/requirements.txt first." >&2
  exit 1
fi

exec "$ROOT_DIR/.venv/bin/python" -m uvicorn app.main:app \
  --app-dir "$ROOT_DIR/services/api" \
  --host 127.0.0.1 \
  --port 8000 \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips 127.0.0.1 \
  --no-server-header \
  --timeout-graceful-shutdown 600
