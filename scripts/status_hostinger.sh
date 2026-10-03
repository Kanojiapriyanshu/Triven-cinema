#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
COMPOSE=(docker compose -f docker-compose.production.yml)

"${COMPOSE[@]}" ps
printf '\nAPI health (inside Docker network):\n'
"${COMPOSE[@]}" exec -T api \
  curl -fsS http://127.0.0.1:8000/api/v1/health/ready || true

if [ -f .env ]; then
  domain="$(python3 - <<'PY'
from pathlib import Path
for raw in Path('.env').read_text(encoding='utf-8').splitlines():
    line = raw.strip()
    if line.startswith('TRIVEN_DOMAIN='):
        print(line.split('=', 1)[1].strip().strip('"').strip("'"))
        break
PY
)"
  if [ -n "$domain" ]; then
    printf '\n\nPublic HTTPS health:\n'
    curl -fsS --connect-timeout 5 --max-time 10 \
      "https://$domain/api/v1/health/ready" || true
  fi
fi

printf '\n\nStorage:\n'
df -h storage 2>/dev/null || df -h .
du -sh storage/generated storage/backups 2>/dev/null || true

printf '\nRecent logs:\n'
"${COMPOSE[@]}" logs --tail=50 api web caddy maintenance
