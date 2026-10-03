#!/bin/bash
set -euo pipefail
SYSTEM_DIR="/Library/LaunchDaemons"
for label in com.triven.cinema.api com.triven.cinema.web com.triven.cinema.cleanup; do
  sudo launchctl bootout system "$SYSTEM_DIR/$label.plist" >/dev/null 2>&1 || true
  sudo rm -f "$SYSTEM_DIR/$label.plist"
done
echo "Removed Triven Cinema boot-time LaunchDaemons. Project files and media were not deleted."
