#!/bin/sh
set -eu

if [ "${RUN_PAID_BENCHMARKS:-0}" != "1" ]; then
  echo "Refusing to spend GPU credits."
  echo "Run with: RUN_PAID_BENCHMARKS=1 ./scripts/benchmark_gpus.sh"
  exit 2
fi

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

API_URL=${TRIVEN_API_URL:-http://127.0.0.1:8000}
GPUS=${GPUS:-"B200 H200 H100"}
ORIGINAL_GPU=${TRIVEN_MODAL_GPU:-B200}
mkdir -p storage/benchmarks

for gpu in $GPUS; do
  echo "==> Deploying Modal app on $gpu"
  TRIVEN_MODAL_GPU="$gpu" modal deploy modal/app.py

  echo "==> Running 1-second 1:1 benchmark on $gpu"
  curl -fsS -X POST "$API_URL/api/v1/generations/video" \
    -H "Content-Type: application/json" \
    -d "{\"prompt\":\"A silver sports car slowly driving through a neon city at night, cinematic tracking camera, wet reflections.\",\"aspect_ratio\":\"1:1\",\"duration_seconds\":1,\"seed\":42,\"decoder\":\"conv\",\"enhance_prompt\":false,\"quality\":\"preview\",\"provider\":\"modal\",\"model\":\"ltx-2.5\"}" \
    > "storage/benchmarks/${gpu}.json"
  echo
  python - "$gpu" <<'PY'
import json
import sys
from pathlib import Path
p=Path("storage/benchmarks")/f"{sys.argv[1]}.json"
d=json.loads(p.read_text())
print({
    "gpu": d.get("gpu"),
    "render_seconds": d.get("render_seconds"),
    "wall_seconds": d.get("wall_seconds"),
    "estimated_cost_usd": d.get("estimated_cost_usd"),
    "estimated_cost_per_output_minute_usd": d.get("estimated_cost_per_output_minute_usd"),
    "has_audio": d.get("media_info", {}).get("has_audio"),
})
PY
done

echo "==> Restoring deployment target: $ORIGINAL_GPU"
TRIVEN_MODAL_GPU="$ORIGINAL_GPU" modal deploy modal/app.py

echo "Benchmark files saved under storage/benchmarks/."
