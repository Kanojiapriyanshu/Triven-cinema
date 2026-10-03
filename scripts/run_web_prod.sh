#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR/apps/web"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
export NODE_ENV=production
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-}"
export TRIVEN_INTERNAL_API_URL="${TRIVEN_INTERNAL_API_URL:-http://127.0.0.1:8000}"

if [ ! -d .next ]; then
  echo "Missing production build. Run: cd apps/web && NEXT_PUBLIC_API_URL='' npm run build" >&2
  exit 1
fi

exec npm run start -- --hostname 127.0.0.1 --port 3000
