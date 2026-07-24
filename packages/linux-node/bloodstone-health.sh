#!/bin/bash
# Lightweight operational health check for a Bloodstone full node.
# Usage: ./bloodstone-health.sh   (or install as bloodstone-health)
set -euo pipefail
IFS=$'\n\t'
umask 077

ROOT="$(cd "$(dirname "$0")" && pwd)"
DATADIR="${BLOODSTONE_DATADIR:-$HOME/.bloodstone}"
CONF="${BLOODSTONE_CONF:-$DATADIR/bloodstone.conf}"
CLI="${BLOODSTONE_CLI:-}"
DAEMON_BIN="${BLOODSTONE_DAEMON:-$ROOT/bin/bloodstoned}"

if [[ -z "$CLI" ]]; then
  if [[ -x "$ROOT/bin/bloodstone-cli" ]]; then
    CLI="$ROOT/bin/bloodstone-cli"
  elif command -v bloodstone-cli >/dev/null 2>&1; then
    CLI="$(command -v bloodstone-cli)"
  else
    CLI=""
  fi
fi

PASS=0
FAIL=0
WARN=0

ok()   { echo "  [OK]   $*"; PASS=$((PASS + 1)); }
bad()  { echo "  [FAIL] $*"; FAIL=$((FAIL + 1)); }
warn() { echo "  [WARN] $*"; WARN=$((WARN + 1)); }

echo "Bloodstone node health"
echo "======================"
echo "datadir: $DATADIR"
echo "conf:    $CONF"
echo ""

# --- config ---
echo "Configuration"
if [[ -f "$CONF" ]]; then
  mode="$(stat -c '%a' "$CONF" 2>/dev/null || stat -f '%Lp' "$CONF" 2>/dev/null || echo '?')"
  if [[ "$mode" == "600" || "$mode" == "400" ]]; then
    ok "conf permissions $mode"
  else
    warn "conf permissions $mode (prefer 600)"
  fi
  if grep -qE '^rpcpassword=(CHANGE_ME)?$' "$CONF" 2>/dev/null; then
    bad "rpcpassword still default/empty — rotate before exposing RPC"
  else
    ok "rpcpassword set"
  fi
  if grep -qE '^connect=' "$CONF" 2>/dev/null; then
    warn "exclusive connect= present (can limit peer discovery)"
  else
    ok "no exclusive connect="
  fi
else
  bad "missing conf $CONF"
fi
echo ""

# --- disk ---
echo "Disk"
if [[ -d "$DATADIR" ]]; then
  avail_kb="$(df -Pk "$DATADIR" 2>/dev/null | awk 'NR==2 {print $4}')"
  if [[ -n "${avail_kb:-}" && "$avail_kb" -lt 1048576 ]]; then
    warn "less than ~1 GiB free on datadir filesystem (${avail_kb} KiB)"
  elif [[ -n "${avail_kb:-}" ]]; then
    ok "free space $((avail_kb / 1024)) MiB on datadir filesystem"
  else
    warn "could not measure free disk"
  fi
else
  warn "datadir does not exist yet"
fi
echo ""

# --- bootstrap marker ---
echo "Bootstrap"
if [[ -f "$DATADIR/.bootstrap-height" ]]; then
  h="$(tr -cd '0-9' < "$DATADIR/.bootstrap-height" || true)"
  ok "bootstrap height marker: ${h:-unknown}"
else
  warn "no .bootstrap-height (full IBD or bootstrap not used)"
fi
if [[ -d "$DATADIR/blocks" && -d "$DATADIR/chainstate" ]]; then
  ok "blocks/ and chainstate/ present"
else
  warn "blocks/ or chainstate/ missing"
fi
echo ""

# --- process ---
echo "Daemon process"
pid=""
if [[ -f "$DATADIR/bloodstoned.pid" ]]; then
  pid="$(tr -cd '0-9' < "$DATADIR/bloodstoned.pid" || true)"
fi
if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
  ok "bloodstoned running (pid $pid)"
elif pgrep -x bloodstoned >/dev/null 2>&1; then
  ok "bloodstoned process found (pgrep)"
else
  bad "bloodstoned does not appear to be running"
fi
if [[ -x "$DAEMON_BIN" ]]; then
  ok "daemon binary: $DAEMON_BIN"
else
  warn "daemon binary not found at $DAEMON_BIN"
fi
echo ""

# --- RPC ---
echo "RPC / chain"
if [[ -z "$CLI" || ! -x "$CLI" ]]; then
  warn "bloodstone-cli not found — skip RPC checks"
else
  if [[ ! -f "$CONF" ]]; then
    bad "cannot query RPC without conf"
  else
    if info="$("$CLI" -conf="$CONF" getblockchaininfo 2>/dev/null)"; then
      ok "RPC responsive (getblockchaininfo)"
      height="$(printf '%s\n' "$info" | sed -n 's/.*"blocks"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -1)"
      headers="$(printf '%s\n' "$info" | sed -n 's/.*"headers"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' | head -1)"
      chain="$(printf '%s\n' "$info" | sed -n 's/.*"chain"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
      [[ -n "$height" ]] && ok "height: $height" || warn "could not parse blocks height"
      [[ -n "$headers" ]] && ok "headers: $headers" || true
      [[ -n "$chain" ]] && ok "chain: $chain" || true
      if [[ -n "$height" && -n "$headers" && "$height" -lt "$headers" ]]; then
        warn "still syncing (blocks $height < headers $headers)"
      fi
    else
      bad "RPC not responsive (check daemon + conf)"
    fi
    if peers="$("$CLI" -conf="$CONF" getconnectioncount 2>/dev/null)"; then
      peers="$(printf '%s' "$peers" | tr -cd '0-9')"
      if [[ -n "$peers" && "$peers" -gt 0 ]]; then
        ok "peers: $peers"
      else
        warn "peers: ${peers:-0} (check firewall TCP 17333 / seeds)"
      fi
    fi
  fi
fi
echo ""

echo "Summary: $PASS ok, $WARN warn, $FAIL fail"
if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
