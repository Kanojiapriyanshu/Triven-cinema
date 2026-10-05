# Triven Cinema production audit — Hostinger VPS

## Current production architecture

```text
Internet
  -> host Nginx :80/:443
     -> 127.0.0.1:3333 Next.js
     -> 127.0.0.1:3334 FastAPI
        -> persistent local job/billing/integration state
        -> generated media
        -> Gemini/fallback planner
        -> Modal API -> B200 -> LTX-2.5
```

Docker does not publish the application on public interfaces. Nginx/Certbot already serve other Triven domains on this VPS, so Caddy is intentionally not part of the Compose stack.

## Production issues addressed

1. **Public app ports:** API/web bind only to `127.0.0.1:3334` / `127.0.0.1:3333`.
2. **Same-origin browser routing:** Nginx routes `/api/*` and `/media/*` to FastAPI; everything else goes to Next.js.
3. **Internal-state exposure:** SQLite/metrics/backups are private, and `/media/generated/{filename}` is served through a signed-workspace ownership check instead of a raw static storage mount.
4. **Paid GPU concurrency:** bounded production job queue; synchronous paid render routes can be disabled.
5. **Planner resilience:** Gemini has bounded timeouts and local storyboard fallback.
6. **Process recovery:** Docker restart policies, health checks and graceful shutdown are configured.
7. **Storage growth:** disk floor, retention cleanup, backup pruning and Docker log rotation.
8. **State backup:** jobs, billing and integration SQLite databases are backed up before deploys and by maintenance.
9. **Modal credentials:** server uses dedicated `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET`.
10. **TLS:** existing host Nginx + Certbot owns ports 80/443 and the `devansh.info` certificate.
11. **Long scenes:** 1080p supports 30s/scene and 4K delivery supports 15s/scene. Modal LTX uses upstream temporal-window carry/blend for long scenes.
12. **Audio:** LTX audio is probed, preserved/mastered/muted explicitly; missing audio is surfaced rather than hidden.
13. **Customer payment:** Stripe Checkout credit packs + signed webhook + idempotent credit ledger + failure refunds.
14. **Publishing:** encrypted per-workspace YouTube OAuth refresh tokens + resumable/chunked uploads.
15. **Workspace isolation:** background job polling is restricted to the signed workspace that created the job.

## Required launch checks

- `.env` mode 600 and not tracked by Git.
- rotate any token previously pasted into chat/terminal history before public launch.
- `TRIVEN_SECRET_KEY` set before billing/YouTube is enabled.
- Stripe Checkout and webhook verified before `BILLING_ENFORCE_CREDITS=true`.
- YouTube OAuth callback registered exactly and private uploads tested before allowing public/unlisted.
- LTX repository revision pinned after the current long-video profile is benchmarked.
- Modal worker redeployed after this patch.
- at least one 30s 1080p and one 15s 4K delivery smoke test completed before advertising those profiles.

## Scaling boundary

The current queue is process-local and control-plane state uses SQLite. It is appropriate for the current single-VPS deployment, but it is not horizontal enterprise infrastructure.

Before a broad multi-tenant launch, migrate:

- jobs/billing/integrations -> Postgres;
- executor -> Redis/SQS/another durable queue;
- generated media -> S3/R2/object storage;
- signed browser workspace -> real login + organizations/RBAC;
- metrics/logging -> centralized observability and alerting.
