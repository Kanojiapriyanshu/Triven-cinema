# Triven Cinema production audit — Hostinger VPS

## Current production architecture

```text
Internet
  -> host Nginx :80/:443
     -> 127.0.0.1:3336 Next.js
     -> 127.0.0.1:3337 FastAPI
        -> persistent local job/billing/integration state
        -> generated media
        -> Gemini/fallback planner
        -> Modal API -> B200 -> LTX-2.5
```

Docker does not publish the application on public interfaces. Nginx/Certbot already serve other Triven domains on this VPS, so Caddy is intentionally not part of the Compose stack.

## Production issues addressed

1. **Public app ports:** API/web bind only to `127.0.0.1:3337` / `127.0.0.1:3336`.
2. **Same-origin browser routing:** Nginx routes `/api/*` and `/media/*` to FastAPI; everything else goes to Next.js.
3. **Internal-state exposure:** SQLite/metrics/backups are private, and `/media/generated/{filename}` is served through a signed-workspace ownership check instead of a raw static storage mount.
4. **Paid GPU concurrency:** bounded production job queue; synchronous paid render routes must be disabled.
5. **Planner resilience:** Gemini has bounded timeouts and local storyboard fallback.
6. **Process recovery:** Docker restart policies, health checks and graceful shutdown are configured.
7. **Storage growth:** disk floor, retention cleanup, backup pruning and Docker log rotation.
8. **State backup:** jobs, billing and integration SQLite databases are backed up before deploys and by maintenance.
9. **Modal credentials:** server uses dedicated `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET`.
10. **TLS:** host Nginx + Certbot is configured for ports 80/443; issue the `cinema.devansh.info` certificate during deployment.
11. **Long scenes:** 1080p supports 30s/scene and 4K delivery supports 15s/scene. Modal LTX uses upstream temporal-window carry/blend for long scenes.
12. **Audio:** LTX audio is probed, preserved/mastered/muted explicitly; missing audio is surfaced rather than hidden.
13. **Customer payment:** Stripe Checkout credit packs + signed webhook + idempotent credit ledger + failure refunds.
14. **Publishing:** encrypted per-workspace YouTube OAuth refresh tokens + resumable/chunked uploads.
15. **Workspace isolation:** background job polling is restricted to the signed workspace that created the job.
16. **Authentication:** production rejects shared auto-login, unacknowledged visible OTPs, weak keys, and unencrypted SMTP. A restricted demo may show OTPs without SMTP only with both `DEMO_AUTH_SHOW_OTP=true` and `ALLOW_PRODUCTION_DEMO_AUTH=true`; this warns because anyone reaching login can sign in as any email. Account identity takes precedence over stale workspace cookies; production media requires an active login.
17. **Deploy verification:** a failed backup stops deployment. Both containers, both loopback ports, and both public HTTPS routes are checked before success.

## Required launch checks

- `.env` mode 600 and not tracked by Git.
- rotate any token previously pasted into chat/terminal history before public launch.
- `TRIVEN_SECRET_KEY` set to at least 32 random characters; real SMTP sign-in tested for public launch, or both demo flags enabled with proxy access restricted for a demo.
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
- individual email login -> organizations/RBAC and managed admission;
- metrics/logging -> centralized observability and alerting.
