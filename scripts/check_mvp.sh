#!/bin/sh
set -eu

API_URL=${API_URL:-http://localhost:8000}

echo "Health:"
curl -fsS "$API_URL/api/v1/health"
echo

echo "Capabilities:"
curl -fsS "$API_URL/api/v1/generations/capabilities"
echo

echo "Metrics summary:"
curl -fsS "$API_URL/api/v1/generations/metrics/summary"
echo
