#!/bin/bash
set -euo pipefail
UID_VALUE="$(id -u)"
for label in com.triven.cinema.api com.triven.cinema.web com.triven.cinema.cleanup; do
  echo "===== $label ====="
  if launchctl print "gui/$UID_VALUE/$label" >/tmp/triven-launch-status 2>/dev/null; then
    grep -E 'state =|pid =|last exit code =|program =' /tmp/triven-launch-status || true
  elif sudo -n launchctl print "system/$label" >/tmp/triven-launch-status 2>/dev/null; then
    grep -E 'state =|pid =|last exit code =|program =' /tmp/triven-launch-status || true
  else
    echo "not loaded as a LaunchAgent (system daemon status may require sudo)"
  fi
done
rm -f /tmp/triven-launch-status

echo "===== API health ====="
curl -fsS http://127.0.0.1:8000/api/v1/health || true
echo
echo "===== API readiness ====="
curl -fsS http://127.0.0.1:8000/api/v1/health/ready || true
echo
