#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
python scripts/cleanup_bad_settings.py "$@"
