#!/usr/bin/env bash
# check_runtime_health.sh — Phase 2J: Report runtime health summary.
#
# Reports:
#   - Active preview sandbox dirs
#   - Stale preview dirs (>2h old)
#   - Disk usage of /tmp
#   - Preview-related process count
#   - Backend process status
#
# Usage:
#   bash scripts/check_runtime_health.sh
#
set -euo pipefail

log() { echo "[runtime_health] $*"; }

echo "==========================================="
echo " Amarktai Runtime Health Check"
echo " $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "==========================================="

# 1. Active preview directories
active_dirs=$(find /tmp -maxdepth 1 -type d \( -name "sandbox_*" -o -name "preview_*" -o -name "amarktai_sandbox_*" \) 2>/dev/null | wc -l)
log "Active preview directories: $active_dirs"

# 2. Stale preview directories (>2h old)
stale_dirs=$(find /tmp -maxdepth 1 -type d \( -name "sandbox_*" -o -name "preview_*" -o -name "amarktai_sandbox_*" \) -mmin +120 2>/dev/null | wc -l)
log "Stale preview directories (>2h): $stale_dirs"

# 3. Disk usage of /tmp
tmp_usage=$(du -sh /tmp 2>/dev/null | cut -f1 || echo "unknown")
log "Disk usage (/tmp): $tmp_usage"

# 4. Preview processes (vite/next dev servers)
preview_procs=$(pgrep -c -f "vite|next dev|uvicorn" 2>/dev/null || echo "0")
log "Preview process count (vite/next/uvicorn): $preview_procs"

# 5. Backend process
backend_pid=$(pgrep -f "uvicorn.*server:app" 2>/dev/null | head -1 || echo "")
if [[ -n "$backend_pid" ]]; then
    log "Backend process: running (PID $backend_pid)"
else
    log "Backend process: NOT RUNNING"
fi

# 6. MongoDB check (basic connectivity)
if command -v mongosh &>/dev/null; then
    mongo_ok=$(mongosh --quiet --eval "db.runCommand({ping:1}).ok" 2>/dev/null || echo "0")
    if [[ "$mongo_ok" == "1" ]]; then
        log "MongoDB: connected"
    else
        log "MongoDB: NOT REACHABLE"
    fi
else
    log "MongoDB: mongosh not found (skipping check)"
fi

echo "==========================================="
echo " Summary:"
echo "   Active previews:  $active_dirs"
echo "   Stale previews:   $stale_dirs"
echo "   /tmp disk usage:  $tmp_usage"
echo "   Preview procs:    $preview_procs"
echo "==========================================="
