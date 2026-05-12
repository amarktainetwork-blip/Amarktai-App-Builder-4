#!/usr/bin/env bash
# cleanup_previews.sh — Phase 2J: Remove stale preview artefacts.
#
# Cleans up:
#   - Stale preview sandbox directories under /tmp (prefix: sandbox_ or preview_)
#   - Orphan preview processes (node vite/next dev servers older than 1 hour)
#   - Preview workspace directories older than 2 hours
#
# Usage:
#   bash scripts/cleanup_previews.sh [--dry-run]
#
set -euo pipefail

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=1

log() { echo "[cleanup_previews] $*"; }

removed_dirs=0
removed_procs=0

# 1. Remove stale sandbox/preview temp directories (older than 2 hours)
while IFS= read -r -d '' dir; do
    if [[ $DRY_RUN -eq 1 ]]; then
        log "DRY-RUN: would remove $dir"
    else
        rm -rf "$dir" && log "Removed stale dir: $dir" || true
        removed_dirs=$((removed_dirs + 1))
    fi
done < <(find /tmp -maxdepth 1 -type d \
    \( -name "sandbox_*" -o -name "preview_*" -o -name "amarktai_sandbox_*" \) \
    -mmin +120 -print0 2>/dev/null)

# 2. Kill orphan preview processes (vite/next dev servers running > 1h)
while IFS= read -r pid; do
    elapsed=$(ps -p "$pid" -o etimes= 2>/dev/null | tr -d ' ' || echo "0")
    if [[ "${elapsed:-0}" -ge 3600 ]]; then
        if [[ $DRY_RUN -eq 1 ]]; then
            log "DRY-RUN: would kill PID $pid"
        else
            kill "$pid" 2>/dev/null && log "Killed stale process: PID $pid" || true
            removed_procs=$((removed_procs + 1))
        fi
    fi
done < <(pgrep -f "vite|next dev" 2>/dev/null || true)

log "Done. Removed $removed_dirs director(ies), $removed_procs process(es)."
