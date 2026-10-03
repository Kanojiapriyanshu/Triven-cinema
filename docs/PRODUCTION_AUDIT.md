# Triven Cinema production audit — Mac mini server

Scope: current single-Mac application server + Modal GPU inference architecture.

## Production shape

The Mac mini is the **application/orchestration server**, not the LTX GPU server:

```text
HTTPS / access control
  -> Next.js (127.0.0.1:3000)
  -> FastAPI (127.0.0.1:8000, one worker)
  -> SQLite jobs + local generated media
  -> Gemini with local storyboard fallback
  -> Modal on-demand LTX GPU
```

This is intentionally a **single-instance** design. Do not add multiple Uvicorn workers without first moving the in-process render queue and job state to shared infrastructure.

## Critical issues found and fixed

### 1. Entire storage directory was public

Previous `StaticFiles` mounted all of `storage/` at `/media`, which included `storage/jobs/jobs.sqlite3` and `storage/metrics/generations.jsonl`.

**Fix:** only `storage/generated/` is mounted publicly at `/media/generated`.

### 2. Production scripts were development servers

Previous scripts used Uvicorn `--reload` and `next dev`.

**Fix:** dedicated production scripts use one Uvicorn worker and `next start`, both loopback-only. launchd keeps them alive.

### 3. Remote-browser localhost bug

The frontend defaulted to `http://localhost:8000`. On a remote user's browser, that means the remote user's computer, not the server Mac.

**Fix:** browser requests are same-origin (`/api`, `/media`). Next.js rewrites them to the Mac's loopback FastAPI service. Caddy can proxy API/media directly for efficiency.

### 4. Paid GPU queue could be spammed

The in-process executor allowed multiple paid jobs and had an unbounded pending queue; synchronous render endpoints bypassed it entirely.

**Fix:** configurable bounded queue, one paid render worker by default, HTTP 429 when full, and production option to disable synchronous paid render endpoints.

### 5. Gemini planning could block or exhaust quota

The prior SDK path retried errors and could leave the UI waiting. A one-scene storyboard also spent a Gemini request unnecessarily.

**Fix:** one scene uses a local fast path; multi-scene planning uses a direct REST request with a hard timeout and deterministic editable fallback on quota/HTTP/timeout errors.

### 6. SQLite connections were not explicitly closed

Python's SQLite connection context manager commits/rolls back but does not close the connection by itself, producing resource warnings under tests.

**Fix:** all job-store connections now use explicit closing; WAL + busy timeout + indexes were added.

### 7. Mac disk could grow without bound

Generated MP4s, job history, metrics and service logs had no server lifecycle policy.

**Fix:** preview/final retention, job pruning, metrics rotation, log rotation, periodic launchd maintenance, free-disk readiness check, and pre-render disk guard.

### 8. Modal output volume would keep generated clips

The function committed each temporary generated clip to a persistent Modal output volume even though the clip was immediately returned to the Mac.

**Fix:** generated Modal clips now use ephemeral `/tmp`; only model weights remain persistent.

### 9. Production errors/debug/docs leaked too much information

Debug/docs and raw exception details were appropriate for development but not for a public server.

**Fix:** production disables docs/OpenAPI, sanitizes main render errors, and adds basic security headers/request IDs.

### 10. No server process supervision

There was no native macOS service definition, reboot recovery, or log location.

**Fix:** launchd installers are included for both per-user LaunchAgents and optional boot-before-login LaunchDaemons.

## High-priority operational requirements still outside application code

1. Put Caddy or Cloudflare Tunnel/Access in front of the web server before public exposure.
2. Do not expose ports 8000 or 3000 directly to the internet; Caddy/Cloudflare should be the public entry point.
3. Use authentication/access control before allowing public users to trigger paid GPU jobs.
4. Move the project from Desktop to `~/Services/triven-cinema` before treating the Mac as a long-lived unattended server.
5. Configure macOS sleep/power-restart behavior for a server.
6. Keep an off-device backup/Time Machine backup for important final videos and `.env` secrets.
7. Pin `TRIVEN_LTX_REPO_REF` to a validated LTX-2 commit/tag instead of `main` for reproducible Modal builds.
8. Run actual H100/H200/B200 benchmarks before deciding the final GPU/cost profile.

## Architecture limits that remain by design

These are not bugs for the current single-Mac MVP, but they block horizontal/high-availability scaling:

- Job queue executor is process-local.
- Job state is SQLite on the Mac.
- Generated media is local disk on the Mac.
- No user/account database or app-level authorization is implemented; access control should currently be at Caddy/Cloudflare.
- A running Modal render cannot be transparently resumed if the Mac/API process is killed mid-job.

If Triven Cinema later needs multiple application servers, migrate job orchestration to a durable queue, job state to Postgres, media to object storage, and introduce real application authentication before scaling out.
