#!/bin/bash
set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"

echo "Health:"
curl -fsS "$API_URL/api/v1/health"
echo

echo "Capabilities:"
curl -fsS "$API_URL/api/v1/generations/capabilities"
echo
