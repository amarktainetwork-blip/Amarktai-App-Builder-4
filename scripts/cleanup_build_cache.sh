#!/usr/bin/env bash
# cleanup_build_cache.sh — Phase 2J: Remove stale build cache artefacts.
#
# Cleans up:
#   - Python __pycache__ directories
#   - .pytest_cache directories
#   - Old frontend build output directories under /tmp
#   - pip and npm cache where safe
#   - Node .cache directories under /tmp
#
# Usage:
#   bash scripts/cleanup_build_cache.sh [--dry-run]
#
set -euo pipefail

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

log() { echo "[cleanup_build_cache] $*"; }

removed=0

remove() {
    local target="$1"
    if [[ $DRY_RUN -eq 1 ]]; then
        log "DRY-RUN: would remove $target"
    else
        rm -rf "$target" && log "Removed: $target" || true
        removed=$((removed + 1))
    fi
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 1. Python __pycache__ in the backend (safe to remove — Python recreates them)
while IFS= read -r -d '' dir; do
    remove "$dir"
done < <(find "${REPO_ROOT}/backend" -type d -name "__pycache__" -print0 2>/dev/null)

# 2. .pytest_cache
while IFS= read -r -d '' dir; do
    remove "$dir"
done < <(find "${REPO_ROOT}" -type d -name ".pytest_cache" -print0 2>/dev/null)

# 3. Old frontend dist/build artefacts under /tmp (older than 1 hour)
while IFS= read -r -d '' dir; do
    remove "$dir"
done < <(find /tmp -maxdepth 1 -type d \
    \( -name "dist_*" -o -name "build_*" -o -name "node_cache_*" \) \
    -mmin +60 -print0 2>/dev/null)

# 4. npm cache directories under /tmp (sandboxed builds)
while IFS= read -r -d '' dir; do
    remove "$dir"
done < <(find /tmp -maxdepth 1 -type d \
    \( -name ".npm_*" -o -name "npm_*" \) \
    -mmin +60 -print0 2>/dev/null)

log "Done. Removed $removed item(s)."
