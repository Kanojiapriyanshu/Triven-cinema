# Triven Cinema on Hostinger VPS

This is the production deployment for the current single-server application architecture.

```text
Internet
  |
  v
Caddy :80/:443
  |--------------------|
  v                    v
Next.js :3000       FastAPI :8000
                        |
                        +-- SQLite jobs / generated media on VPS storage
                        +-- Gemini storyboard planner or local fallback
                        +-- Modal API -> LTX 2.5 GPU rendering
```

FastAPI and Next.js are private Docker services. Only Caddy publishes ports to the public internet. Heavy LTX inference stays on Modal; the VPS does not need a GPU and should not store the LTX model weights.

## 1. Prepare the VPS

Use a supported Ubuntu LTS image on Hostinger VPS.

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl git ufw
curl -fsSL https://get.docker.com | sudo sh
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Log out and back in after adding the Docker group, then verify:

```bash
docker --version
docker compose version
```

## 2. Firewall

Keep SSH available before enabling UFW:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw enable
sudo ufw status
```

If Hostinger's control panel firewall is enabled, allow the same public ports there. Do not expose 3000 or 8000.

## 3. DNS

Create an A record for the hostname you want to use:

```text
cinema.example.com -> YOUR_VPS_PUBLIC_IPV4
```

If you publish an AAAA record, it must point to the same VPS over working IPv6. Remove stale AAAA records instead of leaving them pointed elsewhere.

Caddy requests and renews HTTPS certificates automatically after DNS points to the VPS and ports 80/443 are reachable.

## 4. Place the project on the VPS

Use a stable path instead of a home-directory Downloads/Desktop folder:

```bash
sudo mkdir -p /opt/triven-cinema
sudo chown -R "$USER":"$USER" /opt/triven-cinema
cd /opt/triven-cinema
```

Clone or upload the repository there.

## 5. Configure production secrets

```bash
cp .env.production.example .env
chmod 600 .env
nano .env
```

Set at minimum:

```text
TRIVEN_DOMAIN
FRONTEND_URL
GEMINI_API_KEY
MODAL_TOKEN_ID
MODAL_TOKEN_SECRET
MODAL_APP_NAME
MODAL_FUNCTION_NAME
```

`TRIVEN_DOMAIN` must be the hostname only, for example `cinema.example.com`, without `https://`.

Use a dedicated Modal production token. The Modal Python client reads `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`, so the VPS does not need your personal `~/.modal.toml`.

For a reproducible Modal runtime, replace `TRIVEN_LTX_REPO_REF=main` with the exact LTX commit/tag you have validated.

## 6. Preflight

```bash
python3 scripts/production_preflight.py
```

Fix every `[FAIL]` before deploying. Warnings explain non-blocking issues such as DNS not being propagated yet or the LTX repository still being unpinned.

## 7. Deploy

```bash
./scripts/deploy_hostinger.sh
```

The script:

- validates the production environment;
- creates a state backup before replacing containers;
- pulls current base images while rebuilding;
- starts/recreates the API, web, Caddy and maintenance services;
- waits for FastAPI readiness;
- attempts an external HTTPS health check.

Status:

```bash
./scripts/status_hostinger.sh
```

Live logs:

```bash
docker compose -f docker-compose.production.yml logs -f --tail=200
```

## 8. Modal deployment

Normal web/API deployments do not redownload LTX model weights. The LTX model volume stays in Modal.

Only redeploy the Modal application when `modal/app.py`, LTX runtime code, GPU type, or model runtime configuration changes:

```bash
docker compose -f docker-compose.production.yml run --rm api \
  modal deploy /app/modal/app.py
```

If model files already exist in the Modal volume, do not run the model-download setup again.

## 9. Persistent storage and cleanup

Application state is bind-mounted from:

```text
/opt/triven-cinema/storage/
```

The maintenance container runs every six hours and:

1. creates a consistent SQLite/metrics state backup;
2. removes expired preview/final media according to `.env` retention values;
3. prunes old completed/failed job records;
4. removes state backups older than `BACKUP_RETENTION_DAYS`.

Manual dry-run cleanup:

```bash
docker compose -f docker-compose.production.yml exec -T api \
  python /app/scripts/cleanup_storage.py
```

Manual state backup:

```bash
docker compose -f docker-compose.production.yml exec -T api \
  python /app/scripts/backup_state.py
```

These local backups protect against application mistakes, not total VPS/disk loss. Enable Hostinger snapshots/backups and copy important final media to offsite/object storage if it must survive loss of the VPS.

## 10. Updating the application

After pulling/uploading new code:

```bash
cd /opt/triven-cinema
./scripts/deploy_hostinger.sh
```

The host `storage/` directory and Caddy certificate volumes survive container rebuilds.

Before major upgrades, keep a Git tag/commit you can return to. A simple rollback is:

```bash
git checkout <previous-known-good-commit>
./scripts/deploy_hostinger.sh
```

Do not roll back the `storage/` directory unless you intentionally want to restore older application state.

## 11. Production checks

From the VPS:

```bash
./scripts/status_hostinger.sh
```

From another machine/network:

```bash
curl -fsS https://cinema.example.com/api/v1/health/ready
```

Then test the actual product flow with one short preview render before submitting longer paid generations.

## 12. Security checklist

- Keep `.env` mode `600` and never commit it.
- Use SSH keys; disable password SSH only after key access is proven.
- Public ports should normally be only SSH, HTTP and HTTPS.
- Do not publish 3000 or 8000.
- Keep Ubuntu and Docker security updates current.
- Keep synchronous paid render endpoints disabled in production.
- Use a dedicated Modal token for this server and rotate it if exposed.
- Add real application authentication (or an access gateway) before allowing untrusted users to generate paid videos.
- Do not put Gemini, Modal or Hugging Face secrets into `NEXT_PUBLIC_*` variables.

## Current architecture limit

The current render queue is process-local and job state uses SQLite. Keep one API application instance and one application VPS. Before horizontal scaling, migrate queue/state to a durable shared system (for example Postgres/Redis) and generated media to object storage.
