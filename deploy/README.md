# Deployment

The production target for Triven Cinema is a **Hostinger Linux VPS** for the application layer and **Modal** for LTX GPU inference.

Use the Hostinger deployment guide:

```text
deploy/hostinger/README.md
```

The production Docker Compose stack keeps FastAPI and Next.js loopback-only. The existing host Nginx owns ports 80/443 and routes same-origin `/api/*` and `/media/*` traffic to FastAPI on 127.0.0.1:3337, with all other traffic sent to Next.js on 127.0.0.1:3336.

```bash
./scripts/deploy_hostinger.sh
```

Before any multi-instance deployment, replace local SQLite job state and generated-media storage with shared services such as Postgres and object storage. The current design intentionally assumes one application VPS.
