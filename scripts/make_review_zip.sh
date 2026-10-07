#!/bin/bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT="${1:-$ROOT_DIR/triven-cinema-review.zip}"
cd "$ROOT_DIR"
rm -f "$OUTPUT"
zip -r "$OUTPUT" . \
  -x '.git/*' \
     '.venv/*' \
     '.env' \
     '.env.local' \
     'apps/web/.env*' \
     'node_modules/*' \
     'apps/web/node_modules/*' \
     '.next/*' \
     'apps/web/.next/*' \
     '__pycache__/*' \
     '*/__pycache__/*' \
     '*.pyc' \
     '*.pyo' \
     '*.orig' \
     '*.rej' \
     '*.rej.orig' \
     '.pytest_cache/*' \
     'storage/*' \
     '*.sqlite3' \
     '*.sqlite3-*' \
     '*.zip'
printf 'Created safe review ZIP: %s\n' "$OUTPUT"
