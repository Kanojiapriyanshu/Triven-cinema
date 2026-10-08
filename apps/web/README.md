# Triven Cinema web

Next.js frontend for Triven Cinema.

## Development

From the repository root, run the API first and then:

```bash
./scripts/run_web.sh
```

The browser uses same-origin `/api` and `/media` URLs. `next.config.ts` rewrites them to `http://127.0.0.1:8000`, so you normally do **not** need `NEXT_PUBLIC_API_URL`.

## Hostinger VPS production

The production Docker stack builds this app with the internal API URL set to `http://api:8000`. Host Nginx terminates HTTPS for `cinema.devansh.info` and forwards the studio to `127.0.0.1:3336` and `/api` plus `/media` to `127.0.0.1:3337`. The containers continue listening internally on web port `3000` and API port `8000`.

The web image uses Next.js standalone output, includes the generated static assets and public files, and runs as the unprivileged `node` user. API rewrites are fixed at build time, so rebuild the image when changing `TRIVEN_INTERNAL_API_URL`. The build downloads Geist fonts from Google Fonts; browser requests for these fonts are served locally from the web image.

```bash
cd ../..
./scripts/deploy_hostinger.sh
```

For the full VPS deployment flow, see `../../deploy/hostinger/README.md`.
