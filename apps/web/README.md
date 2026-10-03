# Triven Cinema web

Next.js frontend for Triven Cinema.

## Development

From the repository root, run the API first and then:

```bash
./scripts/run_web.sh
```

The browser uses same-origin `/api` and `/media` URLs. `next.config.ts` rewrites them to `http://127.0.0.1:8000`, so you normally do **not** need `NEXT_PUBLIC_API_URL`.

## Native Mac production

The repository-level production scripts build and start this app on loopback:

```bash
NEXT_PUBLIC_API_URL="" TRIVEN_INTERNAL_API_URL="http://127.0.0.1:8000" npm run build
../../scripts/run_web_prod.sh
```

For the full launchd/Caddy setup, see `../../deploy/mac/README.md`.
