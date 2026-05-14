#!/usr/bin/env sh
set -eu

REPORT="${1:-test_reports/all_agents_execution_matrix.json}"

if [ ! -f "$REPORT" ]; then
  echo "Missing agent execution matrix: $REPORT" >&2
  exit 1
fi

python3 - "$REPORT" <<'PY'
import json
import sys

path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
agents = data.get("agents") or data.get("matrix") or data
if isinstance(agents, dict):
    items = [{"agent": k, **(v if isinstance(v, dict) else {"status": v})} for k, v in agents.items()]
else:
    items = list(agents)

missing = []
for item in items:
    name = item.get("agent") or item.get("name")
    status = str(item.get("status") or item.get("runtime_status") or "").lower()
    has_event = item.get("runtime_event") or item.get("dashboard_event") or item.get("event_visible")
    has_contract = item.get("output_contract") or item.get("contract")
    if status in {"active", "required", "wired"} and (not has_event or not has_contract):
        missing.append(name or "<unknown>")

if missing:
    raise SystemExit(f"Agents missing event/contract evidence: {', '.join(missing)}")

print(f"Agent matrix verified: {len(items)} agents inspected.")
PY
