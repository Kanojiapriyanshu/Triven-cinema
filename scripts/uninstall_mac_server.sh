#!/bin/bash
set -euo pipefail
UID_VALUE="$(id -u)"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
for label in com.triven.cinema.api com.triven.cinema.web com.triven.cinema.cleanup; do
  launchctl bootout "gui/$UID_VALUE" "$LAUNCH_DIR/$label.plist" >/dev/null 2>&1 || true
  rm -f "$LAUNCH_DIR/$label.plist"
done
echo "Removed Triven Cinema launchd services. Project files and generated media were not deleted."
