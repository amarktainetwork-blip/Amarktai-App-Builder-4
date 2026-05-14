#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://builder.amarktai.com}"
: "${AMARKTAI_TOKEN:?Set AMARKTAI_TOKEN to a dashboard bearer token}"

AUTH=(-H "Authorization: Bearer ${AMARKTAI_TOKEN}" -H "Content-Type: application/json")

echo "== GitHub Repo Workbench live verification =="
curl -fsS "${AUTH[@]}" "${BASE_URL}/api/integrations/github/status" | python3 -m json.tool
curl -fsS "${AUTH[@]}" "${BASE_URL}/api/integrations/github/repos?per_page=20" | python3 -m json.tool

if [ -n "${GITHUB_OWNER:-}" ] && [ -n "${GITHUB_REPO:-}" ]; then
  curl -fsS "${AUTH[@]}" "${BASE_URL}/api/integrations/github/repos/${GITHUB_OWNER}/${GITHUB_REPO}/branches" | python3 -m json.tool
fi

if [ -n "${PROJECT_ID:-}" ] && [ -n "${WORKSPACE_PATH:-}" ]; then
  BODY="{\"workspace_path\":\"${WORKSPACE_PATH}\",\"prompt\":\"Verify repo workflow from dashboard script\",\"auto_apply\":false,\"run_build\":false,\"run_tests\":false}"
  curl -fsS "${AUTH[@]}" -d "${BODY}" "${BASE_URL}/api/builds/${PROJECT_ID}/repo-workflow/run" | python3 -m json.tool
fi
