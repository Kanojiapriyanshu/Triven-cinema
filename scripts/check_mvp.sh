#!/bin/sh
set -eu

API_URL=${API_URL:-http://127.0.0.1:8000}

echo "Health:"
curl -fsS "$API_URL/api/v1/health"
echo

echo "Readiness:"
curl -fsS "$API_URL/api/v1/health/ready"
echo

echo "Capabilities:"
curl -fsS "$API_URL/api/v1/generations/capabilities"
echo

echo "Metrics summary (optional in production):"
if ! curl -fsS "$API_URL/api/v1/generations/metrics/summary"; then
  echo "metrics endpoint disabled/unavailable (expected when ENABLE_METRICS_ENDPOINT=false)"
fi
echo
