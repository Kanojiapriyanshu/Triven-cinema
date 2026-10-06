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

## Cinema Studio workspace and reusable Elements

Triven Cinema now uses a studio-first workflow instead of treating the prompt as the only source of identity.

### Workspace flow

```text
Create / My Elements / Takes
          -> Scene canvas
          -> compact Elements tray
          -> @Element scene prompt
          -> Director panel (Scene / Camera / Look / Elements)
          -> LTX-2.5 render
```

The browser exposes reusable `character`, `prop`, `location`, and `style` Elements. Each Element owns immutable versions and one or more protected reference images. The user can insert an Element into the prompt by typing `@`, selecting it from the reference picker, or choosing it from My Elements.

The UI deliberately follows the modern professional film-studio interaction pattern: a center hero frame, one compact Elements tray, an @mention composer, and a right-side director panel. Duplicate controls are intentionally avoided: aspect ratio, delivery quality and shot duration live beside Generate, while the Director panel keeps only production essentials and collapses advanced settings. Triven branding and controls remain original; external product branding/assets are not copied.

### Director controls

Camera, lens, framing, genre, colour, and tempo controls are `auto` by default. When a creator chooses a value, Triven compiles that explicit direction into the scene prompt. With all Director controls on `auto`, prompt-only Factory mode stays user-authored and does not add those directives.


### Reference conditioning timing

Identity conditioning no longer feeds LTX a fixed five-second guide. The Ingredients reference sheet is looped to the full generated clip length at the target frame rate, never below the 121-frame reference bucket, and encoded at the same target canvas as the generation request. This prevents the old short-guide mismatch that could bias the opening toward a frozen/held reference before action began.

Each Element may keep several uploaded views. Triven now uses the canonical image as the dominant panel view and can place up to two supporting views beside it in the same clean, text-free panel. This makes front/profile/full-body references materially useful instead of storing them without passing them to the model.

Conditioned prompts also explicitly separate appearance from timing: reference sheets define identity, while visible motion should begin immediately on the first generated frames unless the user explicitly asks for a still hold. Start-frame mode similarly treats the uploaded image as frame zero and animates forward rather than replaying it as a multi-second freeze.

### Reference limits

The Element library and the per-scene active-reference limit are separate concepts. A workspace may keep many saved Elements, but the deployed LTX Ingredients profile currently defaults to a smaller active scene set for quality and VRAM safety. Limits are returned by `/api/v1/generations/capabilities` and shown in the UI instead of being hidden client constants.

### Identity vs exact start frame

- `identity`: Triven builds a reference sheet and uses the LTX-2.5 Ingredients IC-LoRA path. The Element defines who/what must remain stable while the prompt controls action and composition.
- `start_frame`: the canonical image becomes frame-zero conditioning. Use this when the uploaded image is the exact composition that should be animated.

Only one start-frame Element is accepted in a scene. Other active Elements must use identity mode.
