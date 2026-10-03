#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/3] Python syntax"
python -m compileall -q services/api/app inference modal scripts

echo "[2/3] Shell scripts"
bash -n scripts/run_api.sh scripts/run_web.sh scripts/check_mvp.sh scripts/setup_modal.sh

echo "[3/3] Frontend build"
if [ -d apps/web/node_modules ]; then
  (cd apps/web && npm run build)
else
  echo "Skipping frontend build: run 'cd apps/web && npm ci' first."
fi

echo "Verification complete."
