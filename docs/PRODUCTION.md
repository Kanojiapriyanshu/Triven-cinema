# Production runbook

One application server (Docker Compose) plus Modal for the GPU. Continuous integration builds and smoke-tests the
same images that you deploy (`.github/workflows/ci.yml`).

## 1. What runs where

| Piece | Where | Notes |
|---|---|---|
| Web (Next.js) | `web` container, port 3000 (loopback) | Same-origin `/api/*` and `/media/*` are proxied to the API |
| API (FastAPI) | `api` container, port 8000 (loopback) | Runs as an unprivileged user, one worker, SQLite state in `./storage` |
| Maintenance | `maintenance` container | Backup + storage cleanup every 6 hours |
| GPU | Modal app `triven-cinema-ltx` | `generate_video`, `retake_audio`, `upscale_video` |
| Edge | Host Nginx or Caddy (`deploy/hostinger`) | TLS and the public domain |

## 2. First deployment

```bash
git clone https://github.com/Kanojiapriyanshu/Triven-cinema.git && cd Triven-cinema
cp .env.production.example .env        # then edit every empty value you need
python3 scripts/production_preflight.py
docker compose -f docker-compose.production.yml up -d --build
docker compose -f docker-compose.production.yml ps          # api and web should become "healthy"
curl -fsS http://127.0.0.1:3334/api/v1/health/ready
```

### Open access (no sign-in)

`AUTO_LOGIN_EMAIL=studio@triven.local` (the default in the templates) removes the sign-in: every visitor is signed in
automatically as that account and lands in the studio. Consequences to accept knowingly:

- everyone shares **one** workspace (characters, projects, renders, credits);
- anyone who can open the URL can start paid GPU renders. Restrict access at the proxy (VPN, IP allow-list or HTTP basic
  auth in Nginx/Caddy) and keep `JOB_MAX_PENDING` low.

An account that already exists for that email keeps its data, so point it at your own account email to keep your existing
Elements. Clear the value (and set `SMTP_*`) to go back to email sign-in.

### Required settings

The API **refuses to start** when these are wrong (the error names the setting):

- `TRIVEN_SECRET_KEY` - at least 32 random characters. `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
  It signs sessions and encrypts stored YouTube tokens. Changing it signs everyone out.
- `DEBUG=false`.
- A way to sign in: `AUTO_LOGIN_EMAIL` (open access) or, for email sign-in, `SMTP_HOST` + `SMTP_FROM` (plus `SMTP_USERNAME`/`SMTP_PASSWORD`,
  `SMTP_SECURITY=starttls|ssl|none`). `DEMO_AUTH_SHOW_OTP=true` shows the code in the browser and only belongs on a
  private demo.
- `BILLING_ENABLED=true` also needs the Stripe keys.

### GPU worker (Modal)

```bash
pip install modal
modal token set --token-id ... --token-secret ...      # a dedicated production token
modal run modal/app.py::download_models                # once, downloads the LTX-2.5 weights to the volume
modal deploy modal/app.py                              # re-run after any change in modal/
```

Put the same token in `.env` as `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET`. A Modal error saying
`workspace ... is disabled` is a billing problem on the Modal account, not an application fault.

### Start frames (Gemini image generation)

Set `GEMINI_API_KEY`. Image generation needs a Google AI Studio project **with billing enabled**; on the free tier every
image model answers HTTP 429 (the app then explains this). Without it, creators can still upload their own start frame.

## 3. Operating it

- **Logs:** `docker compose -f docker-compose.production.yml logs -f api`.
- **Health:** `/api/v1/health` (alive) and `/api/v1/health/ready` (storage, ffmpeg, ffprobe, disk space).
- **Restarting the API ends running renders.** Check `storage/jobs/jobs.sqlite3` (`generation_jobs` with status
  `queued`/`running`) first. A job interrupted by a restart is marked failed with "Interrupted by API restart", its GPU
  output is lost, and it is not refunded automatically, so wait for running jobs to finish before restarting.
- **Update:** `git pull && docker compose -f docker-compose.production.yml up -d --build`.
- **Roll back:** check out the previous tag/commit and run the same command.
- **Backups:** the maintenance service writes dated snapshots to `./storage/backups` (kept `BACKUP_RETENTION_DAYS`).
  Copy that folder off the server; it holds accounts, chats, elements and job history.
- **Disk:** renders are refused below `MINIMUM_FREE_DISK_GB`; old previews and finals are cleaned by retention settings.

## 4. Costs and quality settings creators should know

| Setting | Typical wall time (15 s clip, B200) |
|---|---|
| Draft (Preview, Standard) | about 1.5 minutes |
| Full HD upscale of an approved Draft | about 5 minutes (256 GPU seconds measured) |
| 1080p with Real Skin | about 9 minutes |

Draft and Full HD are different generation engines. "Upscale to Full HD" refines the approved Draft, so the picture,
motion and voice stay the same; re-rendering at 1080p produces a different video.

## 5. Security notes

- Containers run as an unprivileged user with `no-new-privileges`; the API and web ports are published to loopback only.
- Runtime data (`storage/auth`, `storage/chats`, `storage/elements`, databases, media) is git-ignored and excluded from
  Docker images. **Never commit it.**
- Sign-in codes are throttled per address when email is sent, and Studio endpoints sit behind the login gate.
- Elements and generated media are served only to the workspace that owns them in production.
- This design assumes **one application server** (SQLite and local media). Before scaling horizontally, move job state
  and media to Postgres and object storage.

## 6. Pre-release checklist

- [ ] `python3 scripts/production_preflight.py` has no `[FAIL]`
- [ ] `TRIVEN_SECRET_KEY` set and backed up in a password manager
- [ ] Either email sign-in works (SMTP tested, `DEMO_AUTH_SHOW_OTP=false`) or open access is deliberately on and the site is protected at the proxy
- [ ] `modal deploy modal/app.py` done and one Draft rendered end to end
- [ ] Gemini billing enabled (or creators told to upload their own start frame)
- [ ] TLS and the public domain verified through Nginx/Caddy
- [ ] Backups copied off the server once and a restore tried
- [ ] CI is green on the commit being deployed
