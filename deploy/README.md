# Deployment

For this project, the preferred production target is the user's Mac mini running the application layer natively, with LTX inference on Modal. See [`deploy/mac/README.md`](mac/README.md).

Docker remains available as an optional application-layer deployment baseline.

## Docker notes

The web container uses same-origin `/api` and `/media` URLs and proxies them internally to `http://api:8000`. The API is not published to the host by the production compose file.

```bash
docker compose -f docker-compose.production.yml up --build
```

Open `http://localhost:3000`.

Before any multi-instance deployment, replace local SQLite job state and generated-media storage with shared services such as Postgres and object storage. The current single-instance design intentionally assumes one application server.
