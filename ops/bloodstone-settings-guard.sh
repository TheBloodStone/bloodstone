#!/usr/bin/env bash
# Validate /root/.bloodstone/settings.json and restore from backup when corrupt.
set -euo pipefail

SETTINGS="${BLOODSTONE_SETTINGS:-/root/.bloodstone/settings.json}"
BACKUP="${BLOODSTONE_SETTINGS_BACKUP:-/root/.bloodstone/settings.json.bak}"
LOG="${BLOODSTONE_SETTINGS_GUARD_LOG:-/root/.bloodstone/watchdog.log}"

# Minimal wallet list required for pool, faucet, swap, and staking services.
FALLBACK_JSON='{
    "wallet": [
        "mine",
        "webuser2",
        "webuser1",
        "webuser3",
        "faucet",
        "gifts",
        "swap-pool",
        "staking-pool"
    ]
}'

log() {
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) [settings-guard] $*" | tee -a "$LOG"
}

settings_valid() {
  local path="$1"
  [[ -f "$path" ]] || return 1
  [[ -s "$path" ]] || return 1
  python3 - "$path" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)
wallets = data.get("wallet")
if not isinstance(wallets, list) or not wallets:
    raise SystemExit(1)
if not all(isinstance(w, str) and w.strip() for w in wallets):
    raise SystemExit(1)
PY
}

restore_from() {
  local src="$1"
  local stamp
  stamp=$(date -u +%Y%m%d-%H%M%S)
  if [[ -f "$SETTINGS" ]]; then
    cp -a "$SETTINGS" "${SETTINGS}.broken.${stamp}" 2>/dev/null || true
  fi
  cp -a "$src" "$SETTINGS"
  chmod 600 "$SETTINGS" 2>/dev/null || true
  log "Restored settings.json from $src"
}

main() {
  mkdir -p "$(dirname "$LOG")"
  if settings_valid "$SETTINGS"; then
    return 0
  fi

  log "WARN settings.json missing, empty, or invalid: $SETTINGS"
  if settings_valid "$BACKUP"; then
    restore_from "$BACKUP"
    return 0
  fi

  log "WARN backup invalid ($BACKUP) — writing embedded fallback wallet list"
  printf '%s\n' "$FALLBACK_JSON" >"$SETTINGS"
  chmod 600 "$SETTINGS" 2>/dev/null || true
  return 0
}

main "$@"