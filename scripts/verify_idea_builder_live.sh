#!/usr/bin/env sh
set -eu

BASE_URL="${BASE_URL:-https://builder.amarktai.com}"
TOKEN="${AMARKTAI_TOKEN:-}"

if [ -z "$TOKEN" ]; then
  echo "AMARKTAI_TOKEN is required for Idea Builder verification." >&2
  exit 2
fi

json_get() {
  curl -fsS -H "Authorization: Bearer $TOKEN" "$@"
}

json_post() {
  curl -fsS -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" "$@"
}

echo "== Idea Builder health =="
curl -fsS "$BASE_URL/api/health" | python3 -m json.tool >/dev/null

echo "== Create Idea Builder session =="
SESSION_JSON=$(json_post "$BASE_URL/api/idea-builder/sessions" \
  -d '{"title":"Live verification","initial_message":"I want an elite AI app builder website with cinematic motion and real media."}')
echo "$SESSION_JSON" | python3 -m json.tool
SESSION_ID=$(printf '%s' "$SESSION_JSON" | python3 -c 'import json,sys; data=json.load(sys.stdin); print((data.get("session") or data).get("id",""))')
test -n "$SESSION_ID"

echo "== Refine idea =="
json_post "$BASE_URL/api/idea-builder/sessions/$SESSION_ID/messages" \
  -d '{"message":"Make it premium, production-ready, with media, motion, runtime QA, and GitHub workflow proof."}' \
  | python3 -m json.tool

echo "== Finalize prompt =="
FINAL_JSON=$(json_post "$BASE_URL/api/idea-builder/sessions/$SESSION_ID/finalize" -d '{}')
echo "$FINAL_JSON" | python3 -m json.tool
printf '%s' "$FINAL_JSON" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert data.get("final_prompt") or (data.get("brief") or {}).get("final_prompt")'

echo "Idea Builder live verification passed."
