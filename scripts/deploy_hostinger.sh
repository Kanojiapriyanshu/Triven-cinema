#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
COMPOSE=(docker compose -f docker-compose.production.yml)
PUBLIC_URL="https://cinema.devansh.info"
SKIP_PUBLIC_CHECK=false

case "${1:-}" in
  "") ;;
  --skip-public-check) SKIP_PUBLIC_CHECK=true ;;
  *) echo "Usage: $0 [--skip-public-check]" >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then
  echo "Usage: $0 [--skip-public-check]" >&2
  exit 2
fi

if [ ! -f .env ]; then
  echo "Missing .env. Copy .env.production.example to .env and configure it first." >&2
  exit 1
fi

mkdir -p storage/generated storage/jobs storage/metrics storage/backups storage/logs
if [ -O storage/backups ]; then
  chmod 700 storage/backups
fi

python3 scripts/production_preflight.py

# Build before touching the running stack. A failed build leaves it running.
"${COMPOSE[@]}" build --pull

# Run with the container's storage ownership. Fresh installations exit successfully
# without a snapshot; a real backup failure must stop an upgrade.
"${COMPOSE[@]}" run --rm --no-deps api python /app/scripts/backup_state.py

echo "Waiting for API and frontend readiness..."
if ! "${COMPOSE[@]}" up -d --remove-orphans --wait --wait-timeout 300; then
  echo "The production services did not become healthy." >&2
  "${COMPOSE[@]}" ps >&2
  "${COMPOSE[@]}" logs --tail=160 api web maintenance >&2
  exit 1
fi

# These probes also catch broken host port mappings, which container probes cannot.
for url in \
  "http://127.0.0.1:3337/api/v1/health/ready" \
  "http://127.0.0.1:3336/"; do
  if ! curl -fsS --connect-timeout 5 --max-time 15 "$url" >/dev/null; then
    echo "Local readiness check failed: $url" >&2
    exit 1
  fi
done
"${COMPOSE[@]}" ps

if [ "$SKIP_PUBLIC_CHECK" = true ]; then
  echo "Local services are healthy. Public HTTPS checks were explicitly skipped."
  echo "After DNS/TLS setup, run ./scripts/status_hostinger.sh to verify public readiness."
  exit 0
fi

for path in /api/v1/health/ready /; do
  echo "Checking public HTTPS endpoint: $PUBLIC_URL$path"
  if ! curl -fsS --connect-timeout 8 --max-time 20 "$PUBLIC_URL$path" >/dev/null; then
    echo "Public HTTPS readiness failed; deployment is not ready for public traffic." >&2
    echo "Check DNS A/AAAA records, the VPS firewall, reverse proxy, and TLS certificate." >&2
    exit 1
  fi
done
echo "Deployment ready: $PUBLIC_URL (frontend 127.0.0.1:3336, API 127.0.0.1:3337)."
