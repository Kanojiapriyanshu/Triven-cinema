# Triven Cinema

Triven Cinema is the low-cost AI video-generation MVP described in the project recording: prompt input, optional AI storyboard generation, self-hosted LTX-2.5 on on-demand Modal GPU, required aspect ratios, reusable scene previews, FFmpeg composition, 1080-class delivery output, native-audio inspection, persistent render jobs, progress, and cost/benchmark tooling.

## Implemented now

- Prompt -> Gemini storyboard -> editable scene prompts.
- Direct prompt mode that skips storyboard generation.
- Textual storyboard prompt-coverage diagnostic.
- LTX-2.5 through:
  - Hugging Face ZeroGPU development fallback.
  - Self-hosted Modal deployment with persistent model/output volumes.
- B200 deployment path already supported through `TRIVEN_MODAL_GPU`.
- 16:9, 9:16 and 1:1 source profiles.
- Persistent asynchronous video jobs in `storage/jobs/jobs.sqlite3`.
- UI polling with coarse real job stages: queued -> initializing -> rendering -> delivery -> probing -> complete.
- Per-scene source previews and regeneration.
- Existing previews are reused when combining; missing scenes only are rendered.
- Storyboard scene previews stay at source resolution even when final quality is 1080p, so the final sequence is upscaled only once.
- FFmpeg scene composition with audio-preservation handling.
- Native/embedded audio stream probing through `ffprobe`.
- Final MP4 preview and download.
- Render timing metrics and optional GPU cost estimates.
- Seed, decoder and prompt-enhancement controls in the UI.
- Modal GPU benchmark script and required-aspect-ratio smoke test.
- Docker deployment baseline for the Next.js/FastAPI application layer.

## Important quality wording

The current `1080p delivery` option creates a 1080-class output file after the LTX source render:

- 16:9 -> 1920x1080
- 9:16 -> 1080x1920
- 1:1 -> 1080x1080

Triven now applies that delivery upscale at most once. It still does **not** claim the LTX source frames were natively generated at 1080p. The recording explicitly called for validating model-specific resolution/pass behavior, so native/high-fidelity LTX quality remains a benchmark task rather than a marketing claim.

## Local setup

```bash
cp .env.example .env
```

Add `GEMINI_API_KEY` and `HF_TOKEN` locally. Never commit `.env`.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r services/api/requirements.txt
cd apps/web && npm ci && cd ../..
```

Run API:

```bash
./scripts/run_api.sh
```

Run web in another terminal:

```bash
./scripts/run_web.sh
```

Open `http://localhost:3000`.

## Modal production path

Prerequisites:

1. Accept LTX-2.5 gated access on Hugging Face.
2. Authenticate Modal.
3. Enable the required paid GPU access.
4. Keep a valid `HF_TOKEN` in local `.env`.

Prepare and deploy:

```bash
./scripts/setup_modal.sh
```

Use:

```env
VIDEO_PROVIDER="modal"
TRIVEN_MODAL_GPU="B200"
```

The web UI now defaults to Modal production but still allows ZeroGPU development fallback.

## Native audio verification

Every API generation response includes `media_info.has_audio` and `media_info.audio_codec` based on `ffprobe`.

For any existing MP4:

```bash
python scripts/inspect_media.py storage/generated/<video>.mp4
```

This verifies whether the actual output contains an audio stream; merely loading the LTX audio VAE is not treated as proof of audible output.

## Persistent asynchronous jobs

The UI uses:

```text
POST /api/v1/generations/jobs/video
GET  /api/v1/generations/jobs/{job_id}
```

Jobs are persisted in SQLite under `storage/jobs/`. If the API process restarts while a job is running, that interrupted job is marked failed instead of being left permanently "running".

The original synchronous endpoint remains available for CLI smoke tests:

```text
POST /api/v1/generations/video
```

## Cost tracking

Render timing is measured automatically. To enable cost estimates, copy the **current** hourly rates from your Modal dashboard into `.env`:

```env
MODAL_GPU_HOURLY_USD_B200=0
MODAL_GPU_HOURLY_USD_H200=0
MODAL_GPU_HOURLY_USD_H100=0
```

Do not enter guessed rates. When configured, responses include:

- `estimated_cost_usd`
- `estimated_cost_per_output_minute_usd`
- an explicit note that these are estimates, not billed cost

Metrics summary:

```bash
curl http://127.0.0.1:8000/api/v1/generations/metrics/summary
```

## Paid GPU benchmark tooling

The scripts refuse to run unless you explicitly opt in.

B200/H200/H100 comparison:

```bash
RUN_PAID_BENCHMARKS=1 ./scripts/benchmark_gpus.sh
```

Required aspect-ratio smoke test:

```bash
RUN_PAID_BENCHMARKS=1 python scripts/test_modal_aspects.py
```

Results are written under `storage/benchmarks/`.

## Verification

```bash
./scripts/verify_mvp.sh
```

It checks Python syntax, unit tests, shell syntax and the frontend build when dependencies are installed.

## Application-layer deployment baseline

The GPU/model layer remains on Modal. Docker files are included for the application layer:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000 \
  docker compose -f docker-compose.production.yml up --build
```

See `deploy/README.md`.

For multi-instance production, move generated media/job state from local disk to object storage/Postgres before scaling horizontally.

## Main API endpoints

```text
GET  /api/v1/health
GET  /api/v1/generations/capabilities
POST /api/v1/generations/plan
POST /api/v1/generations/video
POST /api/v1/generations/jobs/video
GET  /api/v1/generations/jobs/{job_id}
POST /api/v1/generations/combine
POST /api/v1/generations/full-video
GET  /api/v1/generations/metrics/summary
GET  /api/v1/generations/download/{filename}
```

## Still not honestly "done"

These are not silently claimed as complete because the recording/source does not provide enough implementation detail or they require separate external services/credentials:

- WAN inference implementation/version selection.
- MiniMax inference implementation/version selection.
- Native/high-fidelity 1080p LTX benchmark and optimal inference/pass settings.
- Actual H100/H200/B200 cost comparison until the paid benchmark scripts are run.
- Automated visual prompt-adherence scoring of rendered video (current score is text-only storyboard coverage).
- ElevenLabs voice generation and voice/video synchronization.
- Background music generation/mixing.
- Latest-topic research -> script automation.
- YouTube auto-publishing.
- Production Postgres/object storage/HA deployment.
