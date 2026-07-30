#!/usr/bin/env bash
# Launch Bloodstone Multi-Fork Qt Wallet
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
exec python3 "${ROOT}/main.py" "$@"
