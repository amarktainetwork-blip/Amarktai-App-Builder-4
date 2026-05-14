#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://builder.amarktai.com}"
: "${AMARKTAI_TOKEN:?Set AMARKTAI_TOKEN to a dashboard bearer token}"

PROMPT="${PROMPT:-Create an elite cinematic production-grade desktop-first website for Amarktai Builder with real media, motion, runtime QA, accessibility, performance validation, live preview, and quality gates.}"
NAME="${NAME:-Amarktai Runtime Verification}"
export PROMPT NAME
AUTH=(-H "Authorization: Bearer ${AMARKTAI_TOKEN}" -H "Content-Type: application/json")

echo "== Premium build live verification =="
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
