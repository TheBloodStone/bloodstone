#!/usr/bin/env bash
# Generate a one-time Bloodstone beta tester invite code.
set -euo pipefail

LABEL="${1:-}"
COUNT="${BLOODSTONE_BETA_CODE_COUNT:-1}"
CREATED_BY="${BLOODSTONE_BETA_CREATED_BY:-cli}"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage: generate-beta-tester-code.sh [label]

Creates one-time beta tester codes for unlocking the beta OTA/download channel.
Codes are shown once — save them immediately.

Environment:
  BLOODSTONE_BETA_CODE_COUNT   Number of codes to generate (default: 1)
  BLOODSTONE_BETA_CREATED_BY   Audit label for who generated the codes

Beta testers redeem on a LAN-connected device (Options → Beta testing).
EOF
  exit 0
fi

export PYTHONPATH="${PYTHONPATH:-}:/root"
python3 - <<'PY' "$LABEL" "$COUNT" "$CREATED_BY"
import json
import sys

import bloodstone_beta_codes as beta

label, count_raw, created_by = sys.argv[1:4]
try:
    count = max(1, min(int(count_raw), 50))
except ValueError:
    count = 1

codes = []
for _ in range(count):
    row = beta.generate_code(label=label, created_by=created_by)
    codes.append(row["code"])

print(json.dumps({"ok": True, "count": len(codes), "codes": codes}, indent=2))
for code in codes:
    print(f"[beta-code] {code}", file=sys.stderr)
PY