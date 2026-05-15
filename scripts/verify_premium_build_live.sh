#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://builder.amarktai.com}"
: "${AMARKTAI_TOKEN:?Set AMARKTAI_TOKEN to a dashboard bearer token}"

PROMPT="${PROMPT:-Create an elite cinematic production-grade desktop-first website for Amarktai Builder with real media, motion, runtime QA, accessibility, performance validation, live preview, and quality gates.}"
NAME="${NAME:-Amarktai Runtime Verification}"
export PROMPT NAME
AUTH=(-H "Authorization: Bearer ${AMARKTAI_TOKEN}" -H "Content-Type: application/json")

echo "== Premium build live verification =="
if command -v docker >/dev/null 2>&1; then
  echo "== Docker frontend container check =="
  docker compose ps frontend
fi

CREATE_BODY=$(python3 - <<PY
import json, os
print(json.dumps({
  "name": os.environ.get("NAME", "Amarktai Runtime Verification"),
  "prompt": os.environ.get("PROMPT"),
  "mode": "website",
  "quality_tier": "premium",
  "media_requirements": "auto"
}))
PY
)

PROJECT=$(curl -fsS "${AUTH[@]}" -d "${CREATE_BODY}" "${BASE_URL}/api/projects")
echo "${PROJECT}" | python3 -m json.tool
PROJECT_ID=$(printf '%s' "${PROJECT}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

echo "Project: ${PROJECT_ID}"
echo "Watch dashboard/websocket until build completes, then run:"
echo "  PROJECT_ID=${PROJECT_ID} WORKSPACE_PATH=<workspace_path> AMARKTAI_TOKEN=... scripts/verify_production_runtime.sh"

if [ -n "${WORKSPACE_PATH:-}" ]; then
  echo "== Verifying generated workspace artifacts =="
  test -f "${WORKSPACE_PATH}/media_manifest.json"
  test -d "${WORKSPACE_PATH}/media"
  find "${WORKSPACE_PATH}/media" -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.webp' -o -name '*.mp4' -o -name '*.svg' \) | grep -q .
  test -f "${WORKSPACE_PATH}/runtime-qa/runtime-qa-report.json"
  test -f "${WORKSPACE_PATH}/runtime-qa/accessibility-report.json"
  test -f "${WORKSPACE_PATH}/runtime-qa/screenshots/desktop.png"
  test -f "${WORKSPACE_PATH}/runtime-qa/screenshots/tablet.png"
  test -f "${WORKSPACE_PATH}/runtime-qa/screenshots/mobile.png"
  test -f "${WORKSPACE_PATH}/motion_manifest.json"
  WORKSPACE_PATH="${WORKSPACE_PATH}" scripts/verify_no_legacy_template_contamination.sh
fi
