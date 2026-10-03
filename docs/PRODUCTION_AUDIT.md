# Triven Cinema production audit — Hostinger VPS

## Production architecture

Triven Cinema now targets a **single Hostinger Linux VPS** for the web/API/orchestration layer and **Modal** for LTX 2.5 GPU inference.

```text
Internet
  |
  v
Caddy :80/:443
  |--------------------|
  v                    v
Next.js :3000       FastAPI :8000
                        |
                        +-- SQLite job state
                        +-- generated media on VPS storage
                        +-- Gemini storyboard planner / local fallback
                        +-- Modal API -> LTX 2.5 GPU rendering
```

The VPS does not need a GPU and does not store LTX model weights.

## Production issues addressed

### 1. Application ports were directly exposable

FastAPI and Next.js should not be public production listeners.

**Fix:** Docker Compose uses `expose` for ports 8000/3000. Only Caddy publishes 80/443.

### 2. Remote browsers could resolve localhost incorrectly

A browser on another computer must never receive an API URL such as `http://localhost:8000`.

**Fix:** the web app uses same-origin `/api` and `/media` paths. Caddy routes those paths to FastAPI.

### 3. Generated media and internal state needed separation

SQLite job state, metrics, backups and logs must not be publicly downloadable.

**Fix:** FastAPI only exposes generated media under `/media/generated`; internal storage remains private.

### 4. Paid GPU work needed bounded concurrency

Unbounded concurrent jobs can consume Modal credits quickly.

**Fix:** production defaults to one render worker with a small pending queue. Synchronous paid-render endpoints are disabled in the production profile.

### 5. Storyboard planning could block the product

Gemini quota errors, slow responses or request failures previously left the UI waiting.

**Fix:** single-scene requests use the prompt directly; multi-scene planning uses a bounded remote request and falls back to an editable local storyboard.

### 6. Container/process recovery was not production-safe

Development reloaders and manually started terminals are not suitable for a VPS.

**Fix:** Docker Compose uses restart policies, health checks, init handling and graceful shutdown windows.

### 7. VPS storage could grow without bound

Generated previews/finals, jobs, metrics and logs can eventually fill a VPS disk.

**Fix:** retention limits, free-disk checks, scheduled maintenance, backup pruning and Docker log rotation are included.

### 8. Deployments needed state protection

Rebuilding containers must not silently destroy job state or media.

**Fix:** `storage/` is bind-mounted from the VPS host and a state backup is attempted before each deploy. Caddy certificate data is stored in named volumes.

### 9. Modal authentication needed server-safe credentials

A production VPS should not depend on a developer's personal Modal config file.

**Fix:** production uses `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` from the private `.env` file.

### 10. HTTPS and reverse proxy configuration were missing

**Fix:** Caddy is included in the production Compose stack and automatically manages TLS after DNS points to the VPS.

## Required production checks

Before deployment:

1. Use an Ubuntu LTS Hostinger VPS with Docker Engine and Docker Compose.
2. Point `TRIVEN_DOMAIN` DNS to the VPS.
3. Allow only SSH, TCP 80, TCP/UDP 443 publicly; do not expose 3000/8000.
4. Copy `.env.production.example` to `.env`, fill secrets, and run `chmod 600 .env`.
5. Use a dedicated Modal production token.
6. Run `python3 scripts/production_preflight.py` and fix every `[FAIL]`.
7. Deploy with `./scripts/deploy_hostinger.sh`.
8. Verify with `./scripts/status_hostinger.sh` and a short paid render.
9. Enable Hostinger snapshots/backups; local state backups do not protect against total VPS/disk loss.
10. Add application authentication or an access gateway before allowing untrusted users to trigger paid renders.

## Current scaling boundary

The current queue is process-local and job state uses SQLite. This is intentionally a **single-VPS / single-API-instance** architecture.

Before horizontal scaling, migrate job state/queue to shared infrastructure such as Postgres + Redis and move generated media to object storage such as S3/R2.
