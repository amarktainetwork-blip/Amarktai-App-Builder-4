#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://builder.amarktai.com}"

echo "== Amarktai production runtime verification =="
echo "Base URL: ${BASE_URL}"

curl -fsS "${BASE_URL}/api/health" | python3 -m json.tool
curl -fsS "${BASE_URL}/api/readiness" | python3 -m json.tool
curl -fsS "${BASE_URL}/api/capabilities/status" | python3 -m json.tool

echo
echo "Expected readiness checks:"
echo "- Playwright runtime: PASS"
echo "- Lighthouse runtime: PASS"
echo "- GenX live models: PASS"
echo "- Mongo ping/admin user: PASS"

echo
echo "Authenticated runtime QA/media/repo workflow checks require AMARKTAI_TOKEN."
if [ -z "${AMARKTAI_TOKEN:-}" ]; then
  echo "AMARKTAI_TOKEN not set; public runtime checks complete."
  exit 0
fi

if [ -z "${WORKSPACE_PATH:-}" ] || [ -z "${PROJECT_ID:-}" ]; then
  echo "Set PROJECT_ID and WORKSPACE_PATH to run authenticated runtime QA."
  exit 0
fi

AUTH=(-H "Authorization: Bearer ${AMARKTAI_TOKEN}" -H "Content-Type: application/json")
BODY="{\"workspace_path\":\"${WORKSPACE_PATH}\",\"strict\":true,\"require_runtime\":true,\"require_media\":true,\"require_motion\":true}"
curl -fsS "${AUTH[@]}" -d "${BODY}" "${BASE_URL}/api/builds/${PROJECT_ID}/quality-gate" | python3 -m json.tool
