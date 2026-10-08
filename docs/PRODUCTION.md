# Production runbook

One application server (Docker Compose) plus Modal for the GPU. Continuous integration builds and smoke-tests the
same images that you deploy (`.github/workflows/ci.yml`).

## 1. What runs where

| Piece | Where | Notes |
|---|---|---|
| Web (Next.js) | `web` container :3000 → `127.0.0.1:3336` | Same-origin `/api/*` and `/media/*` are proxied to the API |
| API (FastAPI) | `api` container :8000 → `127.0.0.1:3337` | Runs as an unprivileged user, one worker, SQLite state in `./storage` |
| Maintenance | `maintenance` container | Backup + storage cleanup every 6 hours |
| GPU | Modal app `triven-cinema-ltx` | `generate_video`, `retake_audio`, `upscale_video` |
| Edge | Host Nginx or Caddy (`deploy/hostinger`) | TLS and the public domain |

## 2. First deployment

The public URL is **https://cinema.devansh.info**. Follow the ordered
[Hostinger setup](../deploy/hostinger/README.md) for DNS, environment, first container startup, and TLS.
Ports `3336` (web) and `3337` (API) are host-loopback upstreams; users connect on HTTPS port 443.

```bash
cp .env.production.example .env
chmod 600 .env
# Edit .env with the required values below.
python3 scripts/production_preflight.py
# First boot only, before the proxy certificate exists:
./scripts/deploy_hostinger.sh --skip-public-check
# Install the Nginx site and issue TLS as described in the Hostinger guide.
./scripts/status_hostinger.sh
```

### Required settings

Production startup blocks unsafe authentication and rendering configuration:

- `TRIVEN_SECRET_KEY`: at least 32 random characters. Generate with
  `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` and keep it stable in your secret manager.
  It signs sessions and encrypts stored YouTube tokens. Changing it signs users out and prevents decrypting old tokens.
- `TRIVEN_DOMAIN=cinema.devansh.info`, `FRONTEND_URL=https://cinema.devansh.info`, `APP_ENV=production`, `DEBUG=false`.
- `AUTH_ENABLED=true`, `AUTO_LOGIN_EMAIL=""`, `DEMO_AUTH_SHOW_OTP=false`, `ALLOW_PRODUCTION_DEMO_AUTH=false`.
  Each user signs in with an emailed code. Shared auto-login is available only for local development.
- For email sign-in: `SMTP_HOST`, `SMTP_FROM` (a verified sender), and your provider's `SMTP_USERNAME` / `SMTP_PASSWORD`.
  Use `SMTP_SECURITY=starttls` (usually port 587) or `ssl` (usually port 465).
- `VIDEO_PROVIDER=modal`, dedicated `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET`, and the deployed Modal app/function names.
- `ENABLE_SYNC_RENDER_ENDPOINTS=false`, `JOB_WORKERS=1`, and a small positive `JOB_MAX_PENDING`.
- `CORS_ORIGINS=""` for this same-origin deployment; wildcard origins are rejected.
- `BILLING_ENABLED=true` additionally needs Stripe keys and at least one configured credit-pack price.

Email verification allows people who can receive codes to create accounts. With `BILLING_ENFORCE_CREDITS=false`,
those users can still submit operator-funded renders. For a public paid service, finish the Stripe checkout/webhook
verification and enable credit enforcement before admitting users; otherwise restrict access at the proxy.

### Restricted demo without SMTP

To show the sign-in code in the browser on the production host, set both flags in the VPS `.env`:

```env
AUTH_ENABLED=true
AUTO_LOGIN_EMAIL=""
DEMO_AUTH_SHOW_OTP=true
ALLOW_PRODUCTION_DEMO_AUTH=true
```

SMTP is optional only while both demo flags are true. If SMTP is configured, it must still use TLS.
Preflight and startup report a warning: anyone reaching the login can sign in as any email, including existing accounts.
Restrict access at the proxy for this demo. Run `python3 scripts/production_preflight.py`, then deploy with
`bash scripts/deploy_hostinger.sh` (add `--skip-public-check` only before TLS setup). To restore email verification,
configure SMTP and set both demo flags to `false` before redeploying.

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
- **Update:** after running jobs finish, `git pull --ff-only && ./scripts/deploy_hostinger.sh`. The script aborts on failed backups, local readiness, or public HTTPS checks.
- **Roll back:** check out the previous tag/commit and run the same command.
- **Backups:** the maintenance service writes dated snapshots to `./storage/backups` (kept `BACKUP_RETENTION_DAYS`).
  Copy that folder off the server; it holds database snapshots and metrics. Also back up the full `./storage` tree for generated videos and Element image files, and store `.env` separately in a secret manager. Database snapshots alone cannot restore media.
- **Disk:** renders are refused below `MINIMUM_FREE_DISK_GB`; old previews and finals are cleaned by retention settings.

## 4. Costs and quality settings creators should know

| Setting | Typical wall time (15 s clip, B200) |
|---|---|
| Draft (Preview, Standard) | about 1.5 minutes |
| Full HD upscale of an approved Draft | about 5 minutes (256 GPU seconds measured) |
| 1080p with Real Skin | about 9 minutes |

Draft and Full HD are different generation engines. "Upscale to Full HD" refines the approved Draft, so the picture,
motion and voice stay the same; re-rendering at 1080p produces a different video.

### Finishing pass (exposure stability + highlight bloom)

Every new clip is run through a short ffmpeg pass on the **app host** (CPU, no GPU, no Modal redeploy) before it is
stored, correcting two artefacts of raw LTX output:

- **brightness that drifts up and down** across the clip - `deflicker` holds the exposure steady;
- **highlight bloom on bright skin/faces** - a gentle roll-off compresses only the top of the tonal range (mid-tones
  and skin are untouched); the audio is stream-copied, so voice and timing are identical.

It is fail-open: if ffmpeg is missing or errors, the raw clip is kept rather than losing a paid render. Tune it with
`TRIVEN_VIDEO_FINISHING` (on/off), `TRIVEN_VIDEO_DEFLICKER_SIZE` (window in frames, up to 129 ≈ 5s for a shot that must
hold one exposure; `0` disables) and `TRIVEN_VIDEO_HIGHLIGHT_ROLLOFF` (`0.0`–`0.4`; `0` disables). Changes take effect on
the next clip after an API restart (check running jobs first). The Retake path is skipped because it only touches audio.

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
- [ ] Public launch: email sign-in tested with real SMTP, both demo flags `false`, and `AUTO_LOGIN_EMAIL=""`; restricted demo: both demo flags `true` and proxy access restricted
- [ ] `modal deploy modal/app.py` done and one Draft rendered end to end
- [ ] Gemini billing enabled (or creators told to upload their own start frame)
- [ ] TLS, certificate renewal, and both public web/API health checks verified
- [ ] Paid access policy chosen: tested Stripe credit enforcement or proxy access restriction
- [ ] Backups copied off the server once and a restore tried
- [ ] CI is green on the commit being deployed
