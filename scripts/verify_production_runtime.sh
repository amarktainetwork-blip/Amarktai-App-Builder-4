#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://builder.amarktai.com}"

echo "== Amarktai production runtime verification =="
echo "Base URL: ${BASE_URL}"

curl -fsS "${BASE_URL}/api/health" | python3 -m json.tool
READINESS_JSON=$(curl -fsS "${BASE_URL}/api/readiness")
printf '%s' "${READINESS_JSON}" | python3 -m json.tool
READINESS_JSON="${READINESS_JSON}" python3 - <<'PY'
import json, os
data = json.loads(os.environ["READINESS_JSON"])
text = json.dumps(data).lower()
if "app_env" in text and "development" in text:
    raise SystemExit("APP_ENV is still reported as development during production verification.")
if data.get("overall") == "FAIL" or data.get("status") == "FAIL":
    raise SystemExit("Readiness reports FAIL.")
blockers = data.get("blockers") or []
if blockers:
    raise SystemExit(f"Readiness blockers present: {blockers}")
PY
curl -fsS "${BASE_URL}/api/capabilities/status" | python3 -m json.tool

echo
echo "== Frontend Dockerfile lockfile guard =="
if grep -q 'COPY package.json yarn.lock' frontend/Dockerfile 2>/dev/null && [ ! -f frontend/yarn.lock ]; then
  echo "frontend/Dockerfile requires missing yarn.lock" >&2
  exit 1
fi

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

test -f "${WORKSPACE_PATH}/media_manifest.json"
test -d "${WORKSPACE_PATH}/media"
ASSET_COUNT=$(find "${WORKSPACE_PATH}/media" -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.webp' -o -name '*.mp4' -o -name '*.svg' \) | wc -l | tr -d ' ')
[ "${ASSET_COUNT}" -ge 3 ] || { echo "Expected at least 3 persisted media assets, found ${ASSET_COUNT}" >&2; exit 1; }
test -f "${WORKSPACE_PATH}/runtime-qa/runtime-qa-report.json"
test -f "${WORKSPACE_PATH}/runtime-qa/accessibility-report.json"
test -f "${WORKSPACE_PATH}/runtime-qa/screenshots/desktop.png"
test -f "${WORKSPACE_PATH}/runtime-qa/screenshots/tablet.png"
test -f "${WORKSPACE_PATH}/runtime-qa/screenshots/mobile.png"
test -f "${WORKSPACE_PATH}/motion_manifest.json"
if [ -e "${WORKSPACE_PATH}/package.json" ] || [ -e "${WORKSPACE_PATH}/src/App.jsx" ] || [ -e "${WORKSPACE_PATH}/src/main.jsx" ]; then
  echo "Static production verification found React scaffold files in generated static workspace." >&2
  exit 1
fi
WORKSPACE_PATH="${WORKSPACE_PATH}" scripts/verify_no_legacy_template_contamination.sh
