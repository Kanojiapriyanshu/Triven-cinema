#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME="$(id -un)"
GROUP_NAME="$(id -gn)"
HOME_DIR="$HOME"
LOG_DIR="$ROOT_DIR/storage/logs"
PATH_VALUE="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
SYSTEM_DIR="/Library/LaunchDaemons"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

case "$ROOT_DIR" in
  */Desktop/*|*/Documents/*)
    echo "Refusing boot-time LaunchDaemon install from Desktop/Documents." >&2
    echo "Move the project first, e.g. ~/Services/triven-cinema, then rerun." >&2
    exit 1
    ;;
esac

mkdir -p "$LOG_DIR" "$ROOT_DIR/storage/jobs" "$ROOT_DIR/storage/metrics" "$ROOT_DIR/storage/backups" "$ROOT_DIR/storage/generated"
chmod 700 "$LOG_DIR" "$ROOT_DIR/storage/jobs" "$ROOT_DIR/storage/metrics" "$ROOT_DIR/storage/backups" || true
chmod 755 "$ROOT_DIR/storage/generated" || true
chmod 600 "$ROOT_DIR/.env"

"$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/scripts/production_preflight.py"

(
  cd "$ROOT_DIR/apps/web"
  NEXT_PUBLIC_API_URL="" TRIVEN_INTERNAL_API_URL="http://127.0.0.1:8000" npm run build
)

python3 - "$ROOT_DIR" "$TMP_DIR" "$LOG_DIR" "$PATH_VALUE" "$USER_NAME" "$GROUP_NAME" "$HOME_DIR" <<'PY'
import plistlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
out = Path(sys.argv[2])
logs = Path(sys.argv[3])
path_value, user, group, home = sys.argv[4:8]

def write(label, script, keep_alive, interval=None):
    payload = {
        "Label": label,
        "ProgramArguments": ["/bin/bash", str(root / "scripts" / script)],
        "WorkingDirectory": str(root),
        "UserName": user,
        "GroupName": group,
        "RunAtLoad": True,
        "KeepAlive": keep_alive,
        "EnvironmentVariables": {"PATH": path_value, "HOME": home},
        "StandardOutPath": str(logs / f"{label}.out.log"),
        "StandardErrorPath": str(logs / f"{label}.err.log"),
        "ProcessType": "Background",
        "ThrottleInterval": 10,
    }
    if interval is not None:
        payload["StartInterval"] = interval
        payload["RunAtLoad"] = False
        payload["KeepAlive"] = False
    target = out / f"{label}.plist"
    with target.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=False)

write("com.triven.cinema.api", "run_api_prod.sh", True)
write("com.triven.cinema.web", "run_web_prod.sh", True)
write("com.triven.cinema.cleanup", "cleanup_storage_prod.sh", False, 21600)
PY

for label in com.triven.cinema.api com.triven.cinema.web com.triven.cinema.cleanup; do
  sudo launchctl bootout system "$SYSTEM_DIR/$label.plist" >/dev/null 2>&1 || true
  sudo cp "$TMP_DIR/$label.plist" "$SYSTEM_DIR/$label.plist"
  sudo chown root:wheel "$SYSTEM_DIR/$label.plist"
  sudo chmod 644 "$SYSTEM_DIR/$label.plist"
  sudo launchctl bootstrap system "$SYSTEM_DIR/$label.plist"
done

sudo launchctl kickstart -k system/com.triven.cinema.api
sudo launchctl kickstart -k system/com.triven.cinema.web

echo "Installed boot-time LaunchDaemons. They run as $USER_NAME and start before login."
echo "Status: sudo launchctl print system/com.triven.cinema.api"
