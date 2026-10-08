# Triven Cinema on Hostinger VPS

Production URL: **https://cinema.devansh.info**. Run one Linux VPS for the web/API and Modal for GPU inference.

| Public route | Host upstream | Container |
| --- | --- | --- |
| `/` and frontend assets | `127.0.0.1:3336` | Next.js :3000 |
| `/api/*` and `/media/*` | `127.0.0.1:3337` | FastAPI :8000 |

Host Nginx owns ports 80/443 and terminates TLS. Application ports bind only to loopback. Other domains can keep their
existing Nginx sites. Compose runs API, web, and maintenance; it does not start a second public reverse proxy.

## 1. Install host requirements and configure DNS

Use Ubuntu LTS, Docker Engine 28 or newer, Docker Compose v2 with `up --wait`, Nginx, and Certbot.
Install Docker from its [official Ubuntu instructions](https://docs.docker.com/engine/install/ubuntu/).

```bash
sudo apt update
sudo apt install -y ca-certificates curl git ufw nginx certbot python3-certbot-nginx
# Confirm Docker is installed and its daemon is running.
docker --version
docker compose version
docker info
nginx -v
```

Create an A record for **cinema.devansh.info** pointing to the VPS IPv4. Add an AAAA record only if this VPS serves IPv6.
Leave records for the apex `devansh.info` and other applications unchanged.

Allow your actual SSH port before enabling the firewall. If using the standard SSH profile:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

Apply matching rules in the Hostinger firewall. Keep ports 3336, 3337, 3000, and 8000 closed to the internet.

## 2. Configure the application

Run these from your checkout on the VPS:

```bash
cp .env.production.example .env
chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
nano .env
```

Paste the generated value into `TRIVEN_SECRET_KEY`. Fill in:

- `SMTP_HOST`, `SMTP_FROM`, and the username/password required by your SMTP provider. Use `starttls`/587 or `ssl`/465.
- `GEMINI_API_KEY` for planning and image generation.
- Dedicated `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`, plus the deployed app/function names.

Keep the configured production values:

```env
TRIVEN_DOMAIN="cinema.devansh.info"
FRONTEND_URL="https://cinema.devansh.info"
APP_ENV="production"
DEBUG=false
CORS_ORIGINS=""
AUTH_ENABLED=true
AUTO_LOGIN_EMAIL=""
DEMO_AUTH_SHOW_OTP=false
ENABLE_SYNC_RENDER_ENDPOINTS=false
JOB_WORKERS=1
JOB_MAX_PENDING=3
```

The API rejects shared auto-login, demo codes, weak signing keys, missing SMTP, and other unsafe production settings.
Never place server credentials in `NEXT_PUBLIC_*` variables. Keep the signing secret stable across releases.
Email login verifies identity; it does not by itself limit who may register or spend render credits. Before public use,
configure and test Stripe credit enforcement or restrict admission at the reverse proxy. See
[the production runbook](../../docs/PRODUCTION.md) and [billing/YouTube setup](../../docs/AI_VIDEO_FACTORY.md).

## 3. Deploy the Modal worker

Using the dedicated production Modal credentials on your trusted administration machine:

```bash
pip install modal
modal token set --token-id YOUR_TOKEN_ID --token-secret YOUR_TOKEN_SECRET
modal run modal/app.py::download_models
modal deploy modal/app.py
```

The model download is a first-time setup. Redeploy after changes under `modal/` or GPU/runtime settings.
Keep `TRIVEN_LTX_REPO_REF` pinned to your validated revision. Rendering smoke tests incur GPU charges.

## 4. Start the containers

```bash
python3 scripts/production_preflight.py
./scripts/deploy_hostinger.sh --skip-public-check
```

Fix every `[FAIL]`. DNS/TLS warnings are expected until the next step. `--skip-public-check` is for first boot only;
it still requires API and web readiness on both loopback ports. The normal deploy command also requires working public
HTTPS and returns failure when either public endpoint fails.

The deploy script backs up existing SQLite/metrics state before replacing containers and stops if backup fails.
An empty first installation is handled normally. Check the local endpoints:

```bash
curl -fsS http://127.0.0.1:3337/api/v1/health/ready
curl -fsS -o /dev/null http://127.0.0.1:3336/
docker compose -f docker-compose.production.yml ps
```

## 5. Install Nginx and enable HTTPS

The supplied site is an HTTP bootstrap configuration so Nginx can load before a certificate exists. Install it only for
this hostname; preserve existing sites for other domains.

```bash
sudo cp deploy/hostinger/nginx.triven-cinema.conf /etc/nginx/sites-available/triven-cinema
sudo ln -s /etc/nginx/sites-available/triven-cinema /etc/nginx/sites-enabled/triven-cinema
sudo nginx -t
sudo systemctl reload nginx
curl -I http://cinema.devansh.info
sudo certbot --nginx --redirect -d cinema.devansh.info
sudo nginx -t
sudo systemctl reload nginx
sudo certbot renew --dry-run
```

If the symlink already exists, inspect it and reuse it. Certbot adds the certificate paths, HTTPS listener, and HTTP
redirect. Do not overwrite that generated TLS configuration with the bootstrap file on later app updates. Compare and
merge future proxy changes into the installed site, then run `nginx -t` before reloading.

For a host that uses **Caddy instead of Nginx**, the provided `Caddyfile` uses the same loopback upstreams and automatic
HTTPS. Merge it into the host Caddy configuration, validate, and reload Caddy. Only one proxy should own 80/443.

## 6. Verify the release

```bash
./scripts/status_hostinger.sh
curl -fsS https://cinema.devansh.info/api/v1/health/ready
curl -fsS -o /dev/null https://cinema.devansh.info/
# Anonymous Studio access must return 401.
curl -s -o /dev/null -w '%{http_code}\n' https://cinema.devansh.info/api/v1/elements
```

Sign in using a real emailed code, upload an Element, and run one short Draft to verify the external providers. Check
that a second account cannot read the first account's media. Register these URLs if enabling integrations:

- Stripe webhook: `https://cinema.devansh.info/api/v1/billing/webhook`
- YouTube OAuth callback: `https://cinema.devansh.info/api/v1/youtube/callback`

## 7. Updates, logs, and rollback

Wait for queued/running renders to finish before restarting the API. Jobs are process-local; interrupted renders can
lose their output and need manual reconciliation.

```bash
git pull --ff-only
./scripts/deploy_hostinger.sh
./scripts/status_hostinger.sh
docker compose -f docker-compose.production.yml logs --tail=100 api web maintenance
```

Redeploy Modal too if its code changed. For rollback, check out the previous known-good commit/tag and run the deployment
script. Preserve `.env` and `storage`; verify data/schema compatibility before restoring an older application version.

## 8. Persistent storage and recovery

`./storage` is mounted into API and maintenance. Maintenance backs up SQLite/metrics and performs retention cleanup every
six hours. These local snapshots **do not contain generated videos or Element image files** and do not protect against
VPS loss. Copy the full storage tree and database snapshots to a separate backup destination; keep a separate encrypted
copy of `.env`. Test restoration on an isolated host before relying on it.

```bash
# Manual state snapshot:
docker compose -f docker-compose.production.yml exec -T api python /app/scripts/backup_state.py
# Preview retention cleanup:
docker compose -f docker-compose.production.yml exec -T api python /app/scripts/cleanup_storage.py
```

Monitor disk space, both HTTPS endpoints, failed jobs, maintenance logs, and certificate expiry. Keep Hostinger snapshots
as an additional recovery path. Restore database snapshots to their original storage subdirectories with the matching
media and signing secret while the application is stopped.

## Scaling boundary

This is a single-VPS deployment with SQLite, local media, and one render worker. Before adding API instances, migrate
state to Postgres, work execution to a durable queue, and media to object storage. Do not scale the API container or add
Uvicorn workers to this deployment.
