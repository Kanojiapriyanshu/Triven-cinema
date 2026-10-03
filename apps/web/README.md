# Triven Cinema web

Next.js frontend for Triven Cinema.

## Development

From the repository root, run the API first and then:

```bash
./scripts/run_web.sh
```

The browser uses same-origin `/api` and `/media` URLs. `next.config.ts` rewrites them to `http://127.0.0.1:8000`, so you normally do **not** need `NEXT_PUBLIC_API_URL`.

## Hostinger VPS production

The production Docker stack builds this app with the internal API URL set to `http://api:8000`. Caddy terminates HTTPS and routes browser requests on the public domain.

```bash
cd ../..
./scripts/deploy_hostinger.sh
```

For the full VPS deployment flow, see `../../deploy/hostinger/README.md`.
