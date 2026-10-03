#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env ]; then
  echo "Missing .env. Copy .env.example to .env first."
  exit 1
fi

set -a
. ./.env
set +a

if [ -z "${HF_TOKEN:-}" ]; then
  echo "HF_TOKEN is missing from .env"
  exit 1
fi

echo "Creating/updating Modal Hugging Face secret..."
modal secret create huggingface-secret HF_TOKEN="$HF_TOKEN" --force

echo "Downloading LTX-2.5 weights to the persistent Modal volume..."
modal run modal/app.py::download_models

echo "Deploying Triven Cinema LTX app..."
modal deploy modal/app.py

echo
printf '%s\n' "Modal deployment complete." "Set VIDEO_PROVIDER=modal in .env when you are ready to use paid GPU inference."
