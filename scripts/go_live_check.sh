#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${CHECK_MODE:-development}"
DC="${DOCKER_COMPOSE:-docker compose}"
if command -v yarn >/dev/null 2>&1; then
  YARN=(yarn)
elif command -v npx >/dev/null 2>&1; then
  YARN=(npx yarn@1.22.22)
else
  YARN=()
fi

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

say() {
  echo "==> $*"
}

scan_for() {
  local label="$1"
  local pattern="$2"
  if grep -RniE "$pattern" . --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=build --exclude-dir=dist; then
    fail "$label references remain"
  fi
}

legacy_a="${LEGACY_A:-AI}"
legacy_b="${LEGACY_B:-VA}"
legacy_e1="eme"
legacy_e2="rgent"

say "checking legacy assistant names"
scan_for "legacy assistant" "${legacy_a}${legacy_b}|Ai${legacy_b}|ai${legacy_b}"

say "checking legacy platform names"
scan_for "legacy platform" "${legacy_e1}${legacy_e2}|Eme${legacy_e2}|${legacy_e1}${legacy_e2}base|assets\\.${legacy_e1}${legacy_e2}\\.sh|${legacy_e1}${legacy_e2}integrations"

say "checking .env.example"
test -f .env.example || fail ".env.example is missing"

say "backend compile"
python -m compileall backend

if find backend/tests -name "test*.py" -print -quit | grep -q .; then
  say "backend pytest"
  (cd backend && pytest)
fi

say "frontend install"
if [ "${#YARN[@]}" -eq 0 ]; then
  fail "yarn is not installed and npx is unavailable"
fi
(cd frontend && "${YARN[@]}" install --frozen-lockfile)

say "frontend build"
(cd frontend && "${YARN[@]}" build)

say "docker compose config"
$DC config >/tmp/amarktai-compose-config.yml

say "docker compose build"
$DC build

say "starting stack"
$DC up -d

say "waiting for backend health"
for _ in $(seq 1 60); do
  if curl -fsS "http://localhost:${BACKEND_PORT:-8001}/api/health" >/tmp/amarktai-health.json; then
    break
  fi
  sleep 2
done
curl -fsS "http://localhost:${BACKEND_PORT:-8001}/api/health" | tee /tmp/amarktai-health.json
echo

say "checking readiness"
READINESS="$(curl -fsS "http://localhost:${BACKEND_PORT:-8001}/api/readiness")"
echo "$READINESS" | tee /tmp/amarktai-readiness.json
echo

OVERALL="$(python - <<'PY'
import json
from pathlib import Path
data=json.loads(Path('/tmp/amarktai-readiness.json').read_text())
print(data.get('overall','FAIL'))
PY
)"

if [ "$MODE" = "production" ] && [ "$OVERALL" != "PASS" ]; then
  fail "production readiness is $OVERALL"
fi

if [ "$MODE" != "production" ] && [ "$OVERALL" != "PASS" ]; then
  echo "WARN: development check completed, readiness is $OVERALL because production secrets or live provider validation may be absent."
fi

echo "PASS: go-live verification command completed in $MODE mode"
