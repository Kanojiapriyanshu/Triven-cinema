# Triven Cinema — AI Video Factory production path

This patch turns the current Triven Cinema MVP into a bounded single-VPS production factory:

```text
customer prompt
   -> continuity-locked storyboard
   -> LTX-2.5 multimodal scene generation on Modal B200
   -> native temporal windows for long scenes
   -> scene-to-scene first-frame continuity
   -> FFmpeg composition
   -> audio master / native audio / mute
   -> 1080p or 4K delivery master
   -> optional connected-channel YouTube upload
```

It also adds Stripe Checkout generation credits, signed workspace isolation, persistent jobs, encrypted YouTube refresh-token storage, resumable YouTube uploads, retention/backups, and Hostinger/Nginx deployment hardening.

## Customer-facing duration profiles

The UI no longer caps every scene at five seconds.

- Source preview: up to 10 seconds per scene by default.
- 1080p delivery: up to 30 seconds per scene.
- 4K delivery: up to 15 seconds per scene.
- Factory: up to 300 seconds total by default, composed from continuity-locked scenes.

For long Modal scenes, Triven uses the upstream LTX-2.5 DistilledPipeline temporal-window mode with carry/blend overlap. The default window is 241 pixel frames (about 10 seconds at 24 fps) with a 25-frame carry/blend. This keeps a 15s/30s scene inside one LTX pipeline invocation instead of launching unrelated 5s generations.

The current 1080p/4K labels describe the **delivery master**. The validated source profile remains 1024x576, 576x1024, or 512x512 and is transcoded once at final delivery. Do not market this build as native 4K source generation until a native DFR/4K profile has been benchmarked and enabled.

## Audio

LTX-2.5 is invoked with the audio VAE, and the planner/prompt path carries explicit synchronized audio direction for ambience/Foley/dialogue when requested.

Delivery audio modes:

- `native`: preserve the LTX-generated audio stream.
- `mastered`: preserve LTX audio and normalize it to a delivery target using FFmpeg loudness normalization.
- `mute`: intentionally remove audio.

Every generated response is probed with `ffprobe`; the product reports `has_audio`, codec, channel count and duration instead of assuming audio exists.

## Factory mode

`POST /api/v1/factory/jobs` is the main prompt-to-finished-video route.

The factory:

1. Plans the requested number of story scenes.
2. Creates one character bible and one style bible.
3. Uses the same seed through the story.
4. Uses strict previous-final-frame conditioning between scenes when enabled.
5. Renders long scenes with LTX native temporal windows on Modal.
6. Composes all generated scene clips while preserving audio.
7. Creates the requested delivery master once.
8. Optionally publishes the final file to the connected YouTube channel.
9. Records timing/cost metrics and returns the final media/download URL.

## How a real customer pays

The patch uses Stripe Checkout with generation-time credit packs.

Default pack capacities are configurable, not hard-coded prices:

- Starter: 300 generation seconds.
- Pro: 1,800 generation seconds.
- Studio: 7,200 generation seconds.

Create the actual prices in Stripe, then put their Price IDs in `.env`:

```env
BILLING_ENABLED=true
BILLING_ENFORCE_CREDITS=false
STRIPE_SECRET_KEY="sk_..."
STRIPE_WEBHOOK_SECRET="whsec_..."
STRIPE_PRICE_STARTER="price_..."
STRIPE_PRICE_PRO="price_..."
STRIPE_PRICE_STUDIO="price_..."
```

Add the webhook endpoint in Stripe:

```text
https://devansh.info/api/v1/billing/webhook
```

Subscribe it to at least:

```text
checkout.session.completed
checkout.session.async_payment_succeeded
```

Flow:

```text
customer -> Buy credits -> Stripe-hosted Checkout
         -> Stripe webhook verifies payment
         -> idempotent credit ledger entry
         -> customer balance increases
         -> render start reserves/consumes generation seconds
         -> failed job refunds the consumed generation seconds
```

First test Checkout + webhook with `BILLING_ENFORCE_CREDITS=false`. After the webhook is verified end-to-end, change:

```env
BILLING_ENFORCE_CREDITS=true
```

The Stripe Price objects decide the real rupee/dollar amount, so pricing can be changed without changing application code.

## YouTube channel connection and publishing

Configure a Google Cloud OAuth web client and enable the YouTube Data API v3.

Register this OAuth callback exactly:

```text
https://devansh.info/api/v1/youtube/callback
```

Then configure:

```env
YOUTUBE_ENABLED=true
YOUTUBE_CLIENT_ID="..."
YOUTUBE_CLIENT_SECRET="..."
YOUTUBE_REDIRECT_URI="https://devansh.info/api/v1/youtube/callback"
YOUTUBE_ALLOW_PUBLIC=false
TRIVEN_SECRET_KEY="a-long-random-production-secret"
```

The customer clicks **Connect YouTube**, grants upload access, and Triven stores the refresh token encrypted at rest using a key derived from `TRIVEN_SECRET_KEY`.

Factory mode can then upload the final MP4 automatically. Large files use YouTube's resumable-upload protocol in 8 MiB chunks with retries and resume-offset recovery. Keep `YOUTUBE_ALLOW_PUBLIC=false` during initial production validation; the application will force private uploads even if the UI/request asks for public/unlisted.

## Hostinger deployment

The production shape is:

```text
Internet
   -> host Nginx :80/:443
      -> /api/* and /media/* -> 127.0.0.1:3334 (FastAPI container)
      -> everything else     -> 127.0.0.1:3333 (Next.js container)

FastAPI -> Modal API -> B200 / LTX-2.5
```

Docker Compose intentionally contains no Caddy service. This VPS already has host Nginx serving other Triven domains.

Install the template:

```bash
sudo cp deploy/hostinger/nginx.triven-cinema.conf /etc/nginx/sites-available/triven-cinema
sudo ln -sf /etc/nginx/sites-available/triven-cinema /etc/nginx/sites-enabled/triven-cinema
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d devansh.info
```

Deploy application containers:

```bash
docker compose -f docker-compose.production.yml up -d --build api web maintenance
```

Because the Modal worker changes in this patch, redeploy it too:

```bash
set -a
source .env
set +a
modal deploy modal/app.py
```

No LTX model redownload is required for the temporal-window change.

## Production safety boundary

This patch is a strong single-VPS production core, but do not call it horizontally scalable enterprise infrastructure yet.

Before a broad multi-tenant launch, migrate SQLite job/billing/integration state to Postgres, move generated media to S3/R2, move the in-process queue to Redis/SQS/another durable worker queue, and add account authentication/RBAC so customers can recover their workspace across browsers/devices. The signed workspace cookie in this patch isolates the current browser and protects billing/YouTube state, but it is not a full enterprise identity system.
