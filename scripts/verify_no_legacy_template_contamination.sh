#!/usr/bin/env sh
set -eu

ROOT="${WORKSPACE_PATH:-${1:-.}}"

if [ ! -d "$ROOT" ]; then
  echo "Workspace path does not exist: $ROOT" >&2
  exit 2
fi

echo "== Legacy template contamination check =="
echo "Workspace: $ROOT"

FOUND=""
for name in finance.html inventory.html vehicle-detail.html; do
  if find "$ROOT" -path "*/node_modules" -prune -o -path "*/.git" -prune -o -name "$name" -print | grep -q .; then
    FOUND="${FOUND} ${name}"
  fi
done

if [ -n "$FOUND" ]; then
  if [ "${ALLOW_AUTOMOTIVE_TEMPLATES:-0}" = "1" ]; then
    echo "Automotive template files found and explicitly allowed:$FOUND"
  else
    echo "Forbidden automotive template files found in non-automotive build:$FOUND" >&2
    find "$ROOT" -path "*/node_modules" -prune -o -path "*/.git" -prune -o \( -name finance.html -o -name inventory.html -o -name vehicle-detail.html \) -print >&2
    exit 1
  fi
fi

echo "No forbidden legacy automotive template files found."
