# Triven Cinema

Triven Cinema is an AI video-generation MVP built around the project recording requirements: prompt input, optional AI storyboard generation, LTX-2.5 rendering, multiple aspect ratios, scene previews, final clip combination, a production-oriented Modal path, and 1080p delivery output.

## What is implemented

- Prompt -> Gemini storyboard -> editable scene prompts.
- Direct prompt mode that skips storyboard generation.
- LTX-2.5 generation through the current Hugging Face ZeroGPU development provider.
- Self-hosted Modal LTX-2.5 provider code using persistent model/output volumes.
- Provider selector: ZeroGPU development or Modal production.
- Model architecture with LTX-2.5 enabled and WAN/MiniMax placeholders for the next phase.
- 16:9, 9:16 and 1:1 output paths.
- Per-scene render previews and regeneration.
- "Render missing & combine" behavior that reuses already-rendered clips instead of spending GPU again.
- FFmpeg final composition.
- 1080p delivery files via FFmpeg upscale/pad. This is explicitly labeled as delivery upscaling, not native 1080p generation.
- Download endpoint for final and scene MP4s.
- Basic render timing metrics in `storage/metrics/generations.jsonl`.
- Development UI progress states for planning, scene rendering and combining.

## Still outside this patch

These belong to the later pipeline from the recording rather than the immediate video MVP: WAN/MiniMax inference implementations, ElevenLabs voice, music generation, automatic research/script production, voice/video synchronization, persistent user/project database, cloud object storage, and YouTube publishing.

## Local setup

```bash
cp .env.example .env
```

Add `GEMINI_API_KEY` and `HF_TOKEN` to `.env`. Do not commit `.env`.

Create/activate Python 3.12 venv and install API dependencies:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r services/api/requirements.txt
```

Install the frontend:

```bash
cd apps/web
npm ci
cd ../..
```

Start API:

```bash
./scripts/run_api.sh
```

Start frontend in another terminal:

```bash
cd apps/web
npm run dev
```

Open `http://localhost:3000`.

## Development inference: free/shared ZeroGPU

Keep:

```env
VIDEO_PROVIDER="huggingface"
HF_LTX_SPACE="ChopperBlu/ltx-2-5-demo"
```

This is for development only. It depends on another user's public Hugging Face Space and has shared quota/runtime availability.

## Modal production path

The production path is prepared in `modal/app.py`. It follows the official LTX-2.5 self-hosted flow and uses persistent Modal volumes so model weights are not downloaded for every GPU job.

Prerequisites:

1. Accept the LTX-2.5 gated model terms on Hugging Face.
2. `modal setup`
3. Add a payment method / GPU access to the Modal account.
4. Keep a valid `HF_TOKEN` in local `.env`.

Then:

```bash
./scripts/setup_modal.sh
```

This script:

1. creates/updates the Modal `huggingface-secret`,
2. downloads LTX-2.5 weights to `triven-cinema-models`,
3. deploys the `triven-cinema-ltx` Modal app.

Switch the API to Modal:

```env
VIDEO_PROVIDER="modal"
```

The UI can also select Modal per request.

### GPU selection

The deployment defaults to B200 because the project recording specifically requested B200 evaluation. Override before deploying if needed:

```bash
export TRIVEN_MODAL_GPU=H100
modal deploy modal/app.py
```

Benchmark H100/H200/B200 for render time, output quality and actual cost before choosing production hardware.

## Render quality

`Source preview` uses the current fast source profile:

- 16:9 -> 1024x576
- 9:16 -> 576x1024
- 1:1 -> 512x512

`1080p delivery` currently performs FFmpeg delivery upscaling after LTX generation:

- 16:9 -> 1920x1080
- 9:16 -> 1080x1920
- 1:1 -> 1080x1080

This is intentionally transparent: the file dimensions are 1080-class, but the MVP does **not** claim the LTX source frames were generated natively at that resolution. Native/high-fidelity LTX DFR settings should be benchmarked on Modal before production claims are made.

## Main API endpoints

```text
GET  /api/v1/health
GET  /api/v1/generations/capabilities
POST /api/v1/generations/plan
POST /api/v1/generations/video
POST /api/v1/generations/combine
POST /api/v1/generations/full-video
GET  /api/v1/generations/download/{filename}
```

`/combine` performs FFmpeg-only combination of already-rendered scene clips and therefore does not call LTX/GPU again.

## Recommended test flow

Use the free provider first:

1. Storyboard mode.
2. 2 scenes.
3. 16:9.
4. 1 second per scene.
5. Source preview.
6. Render Scene 1 and Scene 2.
7. Click `Combine scenes`.

The final combine should not consume additional ZeroGPU quota.

Then test direct mode with one 1-second clip.

Only after that, deploy Modal and repeat the same test with provider = Modal.
