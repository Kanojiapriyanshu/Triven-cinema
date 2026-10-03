# Triven Cinema on a Mac mini

This is the preferred production shape for the current project:

```text
Internet / LAN
    |
Caddy or Cloudflare Tunnel (HTTPS + access control)
    |
127.0.0.1:3000  Next.js production server
    |
Next.js same-origin rewrites
    |
127.0.0.1:8000  FastAPI (one worker)
    |
    +-- local SQLite jobs + generated media + metrics
    +-- Gemini storyboard API (with local fallback)
    +-- Modal B200/H200/H100 for LTX inference
```

The Mac does **not** run LTX locally. It is the stable application/orchestration server; Modal remains the GPU layer.

## 1. Recommended project location

For a long-running macOS service, prefer:

```bash
mkdir -p ~/Services
mv ~/Desktop/triven-cinema ~/Services/triven-cinema
cd ~/Services/triven-cinema
```

Desktop/Documents can be affected by macOS privacy (TCC), iCloud/Desktop sync and GUI-session behavior. The launchd installer will still work from Desktop in many setups, but `~/Services` is a cleaner server location.

## 2. Production environment

```bash
cp .env.production.example .env
chmod 600 .env
```

Fill in your Gemini key, HF token if needed, and verified Modal cost rates. Keep:

```env
APP_ENV=production
DEBUG=false
VIDEO_PROVIDER=modal
JOB_WORKERS=1
ENABLE_SYNC_RENDER_ENDPOINTS=false
ENABLE_METRICS_ENDPOINT=false
```

Do not put `NEXT_PUBLIC_API_URL=http://localhost:8000` in the web app. Production uses same-origin `/api` and `/media` rewrites, so remote browsers never try to call their own localhost.

## 3. Install dependencies

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r services/api/requirements.txt
cd apps/web && npm ci && cd ../..
```

Install FFmpeg if needed:

```bash
brew install ffmpeg
```

## 4. Preflight

```bash
source .venv/bin/activate
python scripts/production_preflight.py
```

Resolve all `[FAIL]` items before exposing the app.

## 5. Install launchd services

```bash
./scripts/install_mac_server.sh
```

This creates three per-user launchd services:

- API: keeps FastAPI running on `127.0.0.1:8000`.
- Web: keeps Next.js running on `127.0.0.1:3000`.
- Cleanup: removes old preview/final media and old job records every 6 hours according to `.env` retention values.

Check them:

```bash
./scripts/status_mac_server.sh
```

Logs are written under `storage/logs/`.

Because these are LaunchAgents, they start when this macOS user session is logged in. This is the safest default for Homebrew/Modal credentials.

For a truly unattended Mac mini that must recover after a reboot **before anyone logs in**, first move the project out of Desktop/Documents and then use:

```bash
./scripts/install_mac_server_daemon.sh
```

That installer creates `/Library/LaunchDaemons` entries, runs them as your normal macOS user, and requires `sudo`. Validate the LaunchAgent setup first before switching to boot-time daemons.

## 6. Prevent server sleep

Review current settings:

```bash
pmset -g custom
```

For a Mac mini dedicated as a server, commonly useful settings are:

```bash
sudo pmset -a sleep 0
sudo pmset -a autorestart 1
sudo pmset -a womp 1
```

`autorestart 1` asks macOS to restart automatically after a power failure. `womp 1` enables wake-on-network support where available. Only change power settings you are comfortable keeping system-wide.

## 7. HTTPS / public access

**Never expose FastAPI port 8000 directly to the internet.** It contains paid generation endpoints.

Use one of:

1. **Caddy** on the Mac, proxying only to `127.0.0.1:3000`.
2. **Cloudflare Tunnel + Cloudflare Access**, which avoids opening inbound router ports and can require login before anyone can trigger paid renders.

Caddy example:

```bash
brew install caddy
cp deploy/mac/Caddyfile.example deploy/mac/Caddyfile
# generate a password hash if you want Caddy basic auth:
caddy hash-password
# edit the domain and optional basic_auth section
caddy validate --config deploy/mac/Caddyfile
caddy run --config deploy/mac/Caddyfile
```

For an internal/private Triven deployment, add Caddy basic auth or Cloudflare Access. The application intentionally does not put a secret API key in `NEXT_PUBLIC_*` variables because anything `NEXT_PUBLIC_*` is visible to the browser.

## 8. Firewall / router

Keep ports 8000 and 3000 loopback-only. If using Caddy directly, only 80/443 should be reachable externally. If using Cloudflare Tunnel, you generally do not need public inbound ports.

## 9. Disk management

The Mac is local storage for finished clips, so retention is important. Defaults:

```env
PREVIEW_RETENTION_DAYS=3
FINAL_RETENTION_DAYS=30
JOB_RETENTION_DAYS=14
MINIMUM_FREE_DISK_GB=10
```

Preview cleanup dry run:

```bash
python scripts/cleanup_storage.py
```

Apply manually:

```bash
python scripts/cleanup_storage.py --apply
```

The launchd maintenance service creates a lightweight SQLite/metrics state backup and applies cleanup automatically every 6 hours. Backups live under `storage/backups/` and do not copy large MP4 files or `.env` secrets.

For important final videos, move/copy them to durable object storage or a backup before the retention window expires.

## 10. Backup

Use Time Machine or another backup for the Mac itself. `scripts/backup_state.py` gives you a small local state snapshot, but it is not a substitute for an off-device backup. At minimum back up:

- `.env` (securely; it contains secrets)
- `storage/jobs/jobs.sqlite3`
- `storage/metrics/`
- any final MP4s you want to retain

Do not rely on the Mac's internal disk as the only copy of business-critical final renders.

## 11. Updates

Before updating code:

```bash
git add -A
git commit -m "checkpoint before server update"
./scripts/verify_mvp.sh
```

After updating:

```bash
source .venv/bin/activate
./scripts/verify_mvp.sh
python scripts/production_preflight.py
./scripts/install_mac_server.sh
```

The installer rebuilds Next.js and reloads the launchd services.
