#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"
export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/services/api"

echo "[1/4] Python syntax"
python -m compileall -q services/api/app inference modal scripts tests

echo "[2/4] Unit tests"
python -m unittest discover -s tests -p 'test_*.py' -v

echo "[3/4] Shell scripts"
for file in scripts/*.sh; do
  sh -n "$file"
done

echo "[4/4] Frontend build"
if [ -d apps/web/node_modules ]; then
  (cd apps/web && npm run build)
else
  echo "Skipping frontend build: run 'cd apps/web && npm ci' first."
fi

echo "Verification complete."
