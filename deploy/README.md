# Deployment

The production target for Triven Cinema is a **Hostinger Linux VPS** for the application layer and **Modal** for LTX GPU inference.

Use the Hostinger deployment guide:

```text
deploy/hostinger/README.md
```

The production Docker Compose stack keeps FastAPI and Next.js private and exposes only Caddy on ports 80/443. Browser traffic stays same-origin, while `/api/*` and `/media/*` are routed to FastAPI internally.

```bash
./scripts/deploy_hostinger.sh
```

Before any multi-instance deployment, replace local SQLite job state and generated-media storage with shared services such as Postgres and object storage. The current design intentionally assumes one application VPS.
