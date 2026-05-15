#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://builder.amarktai.com}"
: "${AMARKTAI_TOKEN:?Set AMARKTAI_TOKEN to a dashboard bearer token}"

PROMPT='Create a premium cinematic one-page website for "Amarktai Builder".

Requirements:
- dark cinematic design
- minimum 8 sections
- real CSS styling
- animated hero
- AI-generated images OR Pixabay fallback images
- at least 3 real persisted media assets
- motion/3D effects
- GitHub workflow section
- AI agent orchestration section
- runtime QA section
- no placeholder copy
- no broken links
- no broken image references
- no unrelated pages
- output must include media_manifest and motion_manifest'
export PROMPT

AUTH=(-H "Authorization: Bearer ${AMARKTAI_TOKEN}" -H "Content-Type: application/json")
BODY=$(python3 - <<'PY'
import json, os
print(json.dumps({
  "name": "Amarktai Static Premium Verification",
  "prompt": os.environ["PROMPT"],
  "mode": "landing_page",
  "quality_tier": "premium",
  "media_requirements": "required",
  "motion_requirements": "required",
}))
PY
)

echo "== Creating exact static premium verification build =="
PROJECT=$(curl -fsS "${AUTH[@]}" -d "${BODY}" "${BASE_URL}/api/projects")
printf '%s\n' "${PROJECT}" | python3 -m json.tool
PROJECT_ID=$(printf '%s' "${PROJECT}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

echo "Project: ${PROJECT_ID}"
echo "Wait for completion, then re-run with WORKSPACE_PATH=/var/www/amarktai/builds/generated/${PROJECT_ID}."

if [ -z "${WORKSPACE_PATH:-}" ]; then
  exit 0
fi

test -f "${WORKSPACE_PATH}/index.html"
test -f "${WORKSPACE_PATH}/styles.css"
test -f "${WORKSPACE_PATH}/script.js"
test -f "${WORKSPACE_PATH}/media_manifest.json"
test -f "${WORKSPACE_PATH}/motion_manifest.json"
test -f "${WORKSPACE_PATH}/runtime-qa/runtime-qa-report.json"
test -f "${WORKSPACE_PATH}/runtime-qa/accessibility-report.json"
test -f "${WORKSPACE_PATH}/runtime-qa/performance-report.json"
test -f "${WORKSPACE_PATH}/runtime-qa/screenshots/desktop.png"
test -f "${WORKSPACE_PATH}/runtime-qa/screenshots/tablet.png"
test -f "${WORKSPACE_PATH}/runtime-qa/screenshots/mobile.png"

if [ -e "${WORKSPACE_PATH}/package.json" ] || [ -e "${WORKSPACE_PATH}/src/App.jsx" ] || [ -e "${WORKSPACE_PATH}/src/main.jsx" ]; then
  echo "Static landing page contains forbidden React scaffold files." >&2
  exit 1
fi

ASSET_COUNT=$(find "${WORKSPACE_PATH}/media" -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.webp' -o -name '*.mp4' -o -name '*.svg' \) | wc -l | tr -d ' ')
[ "${ASSET_COUNT}" -ge 3 ] || { echo "Expected at least 3 persisted media assets, found ${ASSET_COUNT}" >&2; exit 1; }

grep -qi '</html>' "${WORKSPACE_PATH}/index.html"
grep -q 'data-amarktai-motion-scene' "${WORKSPACE_PATH}/index.html"
grep -q 'data-motion-runtime' "${WORKSPACE_PATH}/index.html"
grep -q 'data-amarktai-media-asset' "${WORKSPACE_PATH}/index.html"
grep -q ':root' "${WORKSPACE_PATH}/styles.css"
grep -q '@media' "${WORKSPACE_PATH}/styles.css"
grep -q 'motionRuntime' "${WORKSPACE_PATH}/script.js"
if grep -Eiq 'Your Product|Lorem ipsum|Coming Soon|Under Construction|placeholder\\.|broken\\.jpg|Feature One' "${WORKSPACE_PATH}/index.html" "${WORKSPACE_PATH}/styles.css"; then
  echo "Placeholder or broken placeholder content detected in static premium build." >&2
  exit 1
fi
if grep -Eiq 'src=["'\''](broken|placeholder|/placeholder)' "${WORKSPACE_PATH}/index.html"; then
  echo "Broken/placeholder media reference detected in static premium build." >&2
  exit 1
fi

WORKSPACE_PATH="${WORKSPACE_PATH}" scripts/verify_no_legacy_template_contamination.sh
echo "Static premium build artifacts verified."
