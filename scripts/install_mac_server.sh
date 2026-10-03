#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UID_VALUE="$(id -u)"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
LOG_DIR="$ROOT_DIR/storage/logs"
PATH_VALUE="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

mkdir -p "$LAUNCH_DIR" "$LOG_DIR" "$ROOT_DIR/storage/jobs" "$ROOT_DIR/storage/metrics" "$ROOT_DIR/storage/backups" "$ROOT_DIR/storage/generated"
chmod 700 "$LOG_DIR" "$ROOT_DIR/storage/jobs" "$ROOT_DIR/storage/metrics" "$ROOT_DIR/storage/backups" || true
chmod 755 "$ROOT_DIR/storage/generated" || true

if [ ! -f "$ROOT_DIR/.env" ]; then
  echo "Missing .env. Start with: cp .env.production.example .env" >&2
  exit 1
fi

chmod 600 "$ROOT_DIR/.env"

if [ ! -x "$ROOT_DIR/.venv/bin/python" ]; then
  echo "Missing .venv. Create it and install services/api/requirements.txt first." >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required." >&2
  exit 1
fi

printf '%s\n' "Running production preflight..."
"$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/scripts/production_preflight.py"

printf '%s\n' "Building Next.js production bundle..."
(
  cd "$ROOT_DIR/apps/web"
  NEXT_PUBLIC_API_URL="" TRIVEN_INTERNAL_API_URL="http://127.0.0.1:8000" npm run build
)

python3 - "$ROOT_DIR" "$LAUNCH_DIR" "$LOG_DIR" "$PATH_VALUE" <<'PY'
import plistlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
launch_dir = Path(sys.argv[2])
log_dir = Path(sys.argv[3])
path_value = sys.argv[4]

def write(label: str, script: str, *, keep_alive: bool, interval: int | None = None):
    payload = {
        "Label": label,
        "ProgramArguments": ["/bin/bash", str(root / "scripts" / script)],
        "WorkingDirectory": str(root),
        "RunAtLoad": True,
        "KeepAlive": keep_alive,
        "EnvironmentVariables": {
            "PATH": path_value,
            "HOME": str(Path.home()),
        },
        "StandardOutPath": str(log_dir / f"{label}.out.log"),
        "StandardErrorPath": str(log_dir / f"{label}.err.log"),
        "ProcessType": "Background",
        "ThrottleInterval": 10,
    }
    if interval is not None:
        payload["StartInterval"] = interval
        payload["RunAtLoad"] = False
        payload["KeepAlive"] = False
    target = launch_dir / f"{label}.plist"
    with target.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=False)
    target.chmod(0o644)
    print(target)

write("com.triven.cinema.api", "run_api_prod.sh", keep_alive=True)
write("com.triven.cinema.web", "run_web_prod.sh", keep_alive=True)
write("com.triven.cinema.cleanup", "cleanup_storage_prod.sh", keep_alive=False, interval=21600)
PY

for label in com.triven.cinema.api com.triven.cinema.web com.triven.cinema.cleanup; do
  launchctl bootout "gui/$UID_VALUE" "$LAUNCH_DIR/$label.plist" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$UID_VALUE" "$LAUNCH_DIR/$label.plist"
  launchctl enable "gui/$UID_VALUE/$label" || true
done

launchctl kickstart -k "gui/$UID_VALUE/com.triven.cinema.api"
launchctl kickstart -k "gui/$UID_VALUE/com.triven.cinema.web"

cat <<EOF

Installed Triven Cinema launchd services.

API:  http://127.0.0.1:8000
Web:  http://127.0.0.1:3000
Logs: $LOG_DIR

Check status:
  ./scripts/status_mac_server.sh

For public HTTPS, put Caddy/Cloudflare in front of port 3000. Do not expose port 8000.
EOF
