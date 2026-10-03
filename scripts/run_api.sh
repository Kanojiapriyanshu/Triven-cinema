#!/bin/bash

set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR:$ROOT_DIR/services/api"

exec uvicorn app.main:app \
  --reload \
  --port 8000
