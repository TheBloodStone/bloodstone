#!/usr/bin/env bash
# Generate Bloodstone beta tester invite codes (single-use or lifetime unlock).
set -euo pipefail

LABEL="${1:-}"
COUNT="${BLOODSTONE_BETA_CODE_COUNT:-1}"
CREATED_BY="${BLOODSTONE_BETA_CREATED_BY:-cli}"
CODE_TYPE="${BLOODSTONE_BETA_CODE_TYPE:-single}"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage: generate-beta-tester-code.sh [label]

Creates beta tester codes for unlocking the beta OTA/download channel.
Codes are shown once — save them immediately.

Code types (BLOODSTONE_BETA_CODE_TYPE):
  single    One-time invite for one tester (default)
  lifetime  Reusable unlock — tester stays on beta across every future pre-release

Environment:
  BLOODSTONE_BETA_CODE_COUNT   Number of codes to generate (default: 1)
  BLOODSTONE_BETA_CODE_TYPE    single or lifetime (default: single)
  BLOODSTONE_BETA_CREATED_BY   Audit label for who generated the codes

Beta testers redeem on a LAN-connected device (Options → Beta testing).
Lifetime testers pull down to check for the newest beta build.
EOF
  exit 0
fi

export PYTHONPATH="${PYTHONPATH:-}:/root"
python3 - <<'PY' "$LABEL" "$COUNT" "$CREATED_BY" "$CODE_TYPE"
import json
import sys

import bloodstone_beta_codes as beta

label, count_raw, created_by, code_type = sys.argv[1:5]
try:
    count = max(1, min(int(count_raw), 50))
except ValueError:
    count = 1

codes = []
for _ in range(count):
    row = beta.generate_code(label=label, created_by=created_by, code_type=code_type)
    codes.append(row["code"])

print(json.dumps({"ok": True, "count": len(codes), "code_type": code_type, "codes": codes}, indent=2))
for code in codes:
    print(f"[beta-code] {code}", file=sys.stderr)
PY