# Triven Cinema application-layer deployment

The GPU/model layer stays on Modal. The application layer can run anywhere that supports Docker.

## API container

Build from repository root:

```bash
docker build -f Dockerfile.api -t triven-cinema-api .
```

The API needs the same environment values used locally, especially `GEMINI_API_KEY`, `VIDEO_PROVIDER=modal`, `MODAL_APP_NAME`, and Modal credentials available to the container. Persist `/app/storage` or replace it with object storage/database services before multi-instance production.

## Web container

```bash
docker build \
  --build-arg NEXT_PUBLIC_API_URL=https://api.example.com \
  -t triven-cinema-web \
  apps/web
```

## Single-host smoke deployment

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000 docker compose -f docker-compose.production.yml up --build
```

This is a deployable application-layer baseline, not a claim of production HA. Before horizontal scaling, move job state/output files from local disk to Postgres/object storage.
