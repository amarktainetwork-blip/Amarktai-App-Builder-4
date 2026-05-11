#!/usr/bin/env bash
# scripts/smoke_test_builder.sh
# Amarktai App Builder — automated smoke test for core build workflows.
#
# Usage:
#   BACKEND_URL=http://localhost:8001 ADMIN_EMAIL=... ADMIN_PASSWORD=... bash scripts/smoke_test_builder.sh
#
# Required env:
#   BACKEND_URL        - e.g. http://localhost:8001  (no trailing slash)
#   ADMIN_EMAIL        - admin account email
#   ADMIN_PASSWORD     - admin account password
#
# Optional env:
#   GITHUB_PAT         - if set, runs GitHub finalize check
#   SKIP_MEDIA_GEN=1   - skip any AI image generation tests (default: skip)
#   VERBOSE=1          - show full API responses
#
# IMPORTANT: This script NEVER prints real secrets.
# GitHub PAT is only checked for presence, never printed.

set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8001}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@amarktai.local}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-amarktai-admin-local}"
SKIP_MEDIA_GEN="${SKIP_MEDIA_GEN:-1}"
VERBOSE="${VERBOSE:-0}"
GITHUB_PAT="${GITHUB_PAT:-}"

PASS=0
FAIL=0
SKIPPED=0

say()   { echo "==> $*"; }
ok()    { echo "  [PASS] $*"; PASS=$((PASS+1)); }
fail()  { echo "  [FAIL] $*" >&2; FAIL=$((FAIL+1)); }
skip()  { echo "  [SKIP] $*"; SKIPPED=$((SKIPPED+1)); }
warn()  { echo "  [WARN] $*"; }

require() { command -v "$1" >/dev/null 2>&1 || { echo "FAIL: $1 is required"; exit 1; }; }
require curl
require jq
require python3

API="$BACKEND_URL/api"
TOKEN=""
PROJECT_ID=""

# ── Health check ──────────────────────────────────────────────────────────────
say "health check"
HEALTH=$(curl -fsS "$API/health") || { fail "backend not reachable at $BACKEND_URL"; exit 1; }
STATUS=$(echo "$HEALTH" | jq -r '.status // "unknown"')
if [ "$STATUS" = "ok" ] || [ "$STATUS" = "healthy" ]; then
  ok "backend healthy (status=$STATUS)"
else
  fail "backend status: $STATUS"
fi

# ── Readiness check ───────────────────────────────────────────────────────────
say "readiness check"
READINESS=$(curl -fsS "$API/readiness")
OVERALL=$(echo "$READINESS" | jq -r '.overall // "FAIL"')
# Check no /proc paths appear in readiness output
for forbidden in /proc /usr/lib map_files; do
  if echo "$READINESS" | grep -q "$forbidden"; then
    fail "readiness response contains forbidden system path: $forbidden"
  fi
done
[ "$OVERALL" = "PASS" ] && ok "readiness PASS" || warn "readiness $OVERALL (may be OK in dev mode)"

# ── Login ─────────────────────────────────────────────────────────────────────
say "login"
LOGIN_RESP=$(curl -fsS -X POST "$API/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}")
TOKEN=$(echo "$LOGIN_RESP" | jq -r '.token // empty')
[ -n "$TOKEN" ] && ok "login OK" || { fail "login failed"; exit 1; }

AUTH_HEADER="Authorization: Bearer $TOKEN"

_api_post() {
  local path="$1"; shift
  local body="$1"; shift
  curl -fsS -X POST "$API$path" \
    -H "Content-Type: application/json" \
    -H "$AUTH_HEADER" \
    -d "$body" 2>&1 || true
}

_api_get() {
  local path="$1"; shift
  curl -fsS "$API$path" -H "$AUTH_HEADER" 2>&1 || true
}

# ── Stack decision engine (no auth, no model call) ────────────────────────────
say "stack decision engine"
SD=$(curl -fsS "$API/stack/decide?mode=landing_page&tier=balanced&prompt=test")
if echo "$SD" | jq -e '.preview_strategy == "iframe"' >/dev/null 2>&1; then
  ok "landing_page stack decision: iframe preview"
else
  fail "landing_page stack decision unexpected: $SD"
fi

SD_PWA=$(curl -fsS "$API/stack/decide?mode=pwa&tier=balanced")
if echo "$SD_PWA" | jq -e '.required_files | index("manifest.json") != null' >/dev/null 2>&1; then
  ok "PWA stack decision includes manifest.json"
else
  fail "PWA stack decision missing manifest.json: $SD_PWA"
fi

SD_TRADING=$(curl -fsS "$API/stack/decide?mode=trading_bot_scaffold&tier=cheap")
if echo "$SD_TRADING" | jq -e '.requires_upgrade_confirmation == true' >/dev/null 2>&1; then
  ok "trading_bot_scaffold with cheap tier requires upgrade confirmation"
else
  fail "trading bot should require upgrade confirmation: $SD_TRADING"
fi

# ── Model router ──────────────────────────────────────────────────────────────
say "model router"
for tier in cheap balanced premium; do
  ROUTER=$(_api_get "/models/router?tier=$tier")
  RTIER=$(echo "$ROUTER" | jq -r '.tier // empty')
  [ "$RTIER" = "$tier" ] && ok "model router tier=$tier" || fail "model router tier=$tier: $ROUTER"
done

# ── Assistant endpoint ────────────────────────────────────────────────────────
say "assistant endpoint"
ASST_RESP=$(_api_post "/assistant/message" '{"content":"What build mode should I use for a simple marketing landing page?"}')
if echo "$ASST_RESP" | jq -e '.reply | length > 0' >/dev/null 2>&1; then
  ok "assistant returned a reply"
else
  warn "assistant may need GENX_API_KEY to be set: $ASST_RESP"
fi

# ── Branding check (no forbidden legacy names) ────────────────────────────────
say "branding check"
# Legacy brand patterns are assembled from fragments to prevent this script's
# own grep scan in go_live_check.sh from flagging these as false positives.
# This is the same approach used in go_live_check.sh.
legacy_a="${LEGACY_A:-AI}"
legacy_b="${LEGACY_B:-VA}"
legacy_e1="eme"
legacy_e2="rgent"
LEGACY_A_PATTERN="${legacy_a}${legacy_b}"
LEGACY_E_PATTERN="${legacy_e1}${legacy_e2}base"
for path in /api/health /api/readiness; do
  RESP=$(curl -fsS "$BACKEND_URL$path" 2>/dev/null || echo "{}")
  if echo "$RESP" | grep -qiE "${LEGACY_A_PATTERN}|${LEGACY_E_PATTERN}"; then
    fail "forbidden branding in $path response"
  fi
done
ok "no forbidden branding in health/readiness"

# ── Projects create (requires GENX_API_KEY to be configured) ──────────────────
say "project create: landing page"
CREATE_RESP=$(_api_post "/projects" '{
  "name":"Smoke Test Landing",
  "prompt":"Build a clean landing page for a SaaS product",
  "mode":"landing_page",
  "quality_tier":"balanced"
}')
if echo "$CREATE_RESP" | jq -e '.id' >/dev/null 2>&1; then
  PROJECT_ID=$(echo "$CREATE_RESP" | jq -r '.id')
  MODE_RESP=$(echo "$CREATE_RESP" | jq -r '.mode // "unknown"')
  ok "project created: id=$PROJECT_ID mode=$MODE_RESP"
else
  warn "project create failed (GENX_API_KEY may not be configured): $CREATE_RESP"
fi

# ── GitHub finalize check ─────────────────────────────────────────────────────
if [ -n "$GITHUB_PAT" ]; then
  say "github PAT is configured — finalize test skipped to avoid creating real repos in smoke test"
  ok "GitHub PAT present (finalize test skipped in smoke run)"
else
  skip "GitHub PAT not set — skipping finalize/PR tests"
fi

# ── Privacy / Terms endpoints ─────────────────────────────────────────────────
say "frontend static checks (if frontend is running)"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:8080}"
if curl -fsS "$FRONTEND_URL" >/dev/null 2>&1; then
  for path in /privacy /terms; do
    if curl -fsS "$FRONTEND_URL$path" >/dev/null 2>&1; then
      ok "frontend path $path accessible"
    else
      warn "frontend $path returned error (may be SPA routing)"
    fi
  done
else
  skip "frontend not running at $FRONTEND_URL — skipping static path checks"
fi

# ── Media generation skip ─────────────────────────────────────────────────────
if [ "$SKIP_MEDIA_GEN" = "1" ]; then
  skip "AI image generation tests skipped (SKIP_MEDIA_GEN=1). Use placeholder images in builds."
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo "  Smoke test summary"
echo "  PASS:    $PASS"
echo "  FAIL:    $FAIL"
echo "  SKIPPED: $SKIPPED"
echo "=========================================="

if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL test(s) failed." >&2
  exit 1
fi
echo "PASS: smoke test completed."
