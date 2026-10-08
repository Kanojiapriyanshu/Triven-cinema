#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
COMPOSE=(docker compose -f docker-compose.production.yml)
health_failed=0

check_endpoint() {
  printf '\n%s:\n' "$1"
  if ! curl -fsS --connect-timeout 5 --max-time 15 --output /dev/null \
      --write-out 'HTTP %{http_code}\n' "$2"; then
    health_failed=1
  fi
}

"${COMPOSE[@]}" ps
check_endpoint "Local API readiness" "http://127.0.0.1:3337/api/v1/health/ready"
check_endpoint "Local frontend readiness" "http://127.0.0.1:3336/"
check_endpoint "Public HTTPS API readiness" "https://cinema.devansh.info/api/v1/health/ready"
check_endpoint "Public HTTPS frontend readiness" "https://cinema.devansh.info/"

printf '\n\nStorage:\n'
df -h storage 2>/dev/null || df -h .
du -sh storage/generated storage/backups 2>/dev/null || true

printf '\nRecent logs:\n'
"${COMPOSE[@]}" logs --tail=50 api web maintenance
printf '\nHost Nginx status:\n'
systemctl is-active nginx 2>/dev/null || true
exit "$health_failed"
