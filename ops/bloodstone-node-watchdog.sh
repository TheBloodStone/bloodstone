#!/bin/bash
# Auto-recover bloodstoned when RPC is down, settings are corrupt, or chainstate fails.
set -euo pipefail

CONF=/root/.bloodstone/bloodstone.conf
CLI=/root/bloodstone-cli
DAEMON=/root/bloodstoned
LOG=/root/.bloodstone/watchdog.log
LOCK=/run/bloodstone-watchdog.lock
RPC_PORT="${BLOODSTONE_RPC_PORT:-18332}"
SETTINGS_GUARD=/root/bloodstone-settings-guard.sh
STRATUM_UNITS=(
  bloodstone-stratum-neoscrypt
  bloodstone-stratum-sha256
  bloodstone-stratum-tls
  bloodstone-stratum-yespower
  bloodstone-stratum-ws
)
STRATUM_DISABLED=()
UPKEEP_CONF="${BLOODSTONE_UPKEEP_CONF:-/root/bloodstone-upkeep.conf}"
if [[ -f "$UPKEEP_CONF" ]]; then
  # shellcheck source=/root/bloodstone-upkeep.conf
  source "$UPKEEP_CONF"
  if [[ "${UPKEEP_ROLE:-main}" == "main" && -n "${LOCAL_STRATUM_DISABLED[*]:-}" ]]; then
    STRATUM_DISABLED=("${LOCAL_STRATUM_DISABLED[@]}")
    filtered=()
    for unit in "${STRATUM_UNITS[@]}"; do
      skip=0
      for off in "${STRATUM_DISABLED[@]}"; do
        [[ "$unit" == "$off" ]] && skip=1 && break
      done
      [[ "$skip" -eq 0 ]] && filtered+=("$unit")
    done
    STRATUM_UNITS=("${filtered[@]}")
    # Main VPS forwards :3437/:3438 to the worker; keep forwards up instead.
    STRATUM_UNITS+=(
      bloodstone-stratum-forward-neoscrypt
      bloodstone-stratum-forward-yespower
    )
  fi
fi

log() {
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" | tee -a "$LOG"
}

ensure_settings() {
  if [[ -x "$SETTINGS_GUARD" ]]; then
    "$SETTINGS_GUARD" || true
  fi
}

rpc_port_listening() {
  ss -tln 2>/dev/null | awk '{print $4}' | grep -qE ":${RPC_PORT}$"
}

settings_error_recent() {
  journalctl -u bloodstoned --since "15 min ago" --no-pager 2>/dev/null | \
    grep -qE 'Unable to parse settings file|Failed loading settings file'
}

systemd_node_active() {
  systemctl is-active --quiet bloodstoned 2>/dev/null
}

handoff_orphan_to_systemd() {
  if ! node_running; then
    return 1
  fi
  if systemd_node_active; then
    return 0
  fi
  log "Orphan bloodstoned process detected (not managed by systemd) — handing off"
  stop_stratum
  "$CLI" -conf="$CONF" stop 2>/dev/null || true
  pkill -x bloodstoned 2>/dev/null || true
  pkill -x spacexpansed 2>/dev/null || true
  sleep 3
  systemctl reset-failed bloodstoned 2>/dev/null || true
  systemctl start bloodstoned 2>/dev/null || true
  if wait_for_rpc 24 5; then
    log "Node online under systemd after orphan handoff"
    start_stratum
    return 0
  fi
  log "Orphan handoff failed; continuing recovery"
  return 1
}

stop_stratum() {
  for unit in "${STRATUM_UNITS[@]}" "${STRATUM_DISABLED[@]}"; do
    systemctl stop "$unit" 2>/dev/null || true
  done
}

start_stratum() {
  for unit in "${STRATUM_UNITS[@]}"; do
    systemctl start "$unit" 2>/dev/null || true
    sleep 2
  done
}

rpc_ok() {
  "$CLI" -conf="$CONF" getblockcount &>/dev/null
}

node_running() {
  pgrep -x bloodstoned >/dev/null || pgrep -x spacexpansed >/dev/null
}

wait_for_rpc() {
  local attempts="$1"
  local delay="$2"
  for _ in $(seq 1 "$attempts"); do
    if rpc_ok; then
      return 0
    fi
    sleep "$delay"
  done
  return 1
}

chainstate_error() {
  tail -100 /root/.bloodstone/debug.log 2>/dev/null | \
    grep -q "Error initializing block database"
}

try_mesh_restore() {
  if ! command -v python3 >/dev/null; then
    return 1
  fi
  if [[ ! -f /root/chain-mesh-restore.py ]]; then
    return 1
  fi
  log "Attempting chain mesh block restore before reindex"
  local out
  out="$(python3 /root/chain-mesh-restore.py --auto 2>/dev/null || true)"
  if echo "$out" | grep -q '"ok": true'; then
    if echo "$out" | grep -q '"skipped": true'; then
      log "Chain mesh coverage already complete on coordinator"
      return 1
    fi
    log "Chain mesh restore: $out"
    systemctl start bloodstoned 2>/dev/null || systemctl start spacexpansed
    if wait_for_rpc 60 5; then
      log "Node online after chain mesh restore, block count: $("$CLI" -conf="$CONF" getblockcount)"
      start_stratum
      return 0
    fi
    log "Chain mesh restore wrote blocks but RPC not ready yet"
  else
    log "Chain mesh restore unavailable or incomplete: $out"
  fi
  return 1
}

recover_reindex() {
  if try_mesh_restore; then
    return 0
  fi
  log "Starting chainstate reindex recovery"
  stop_stratum
  pkill -x bloodstoned 2>/dev/null || true
  pkill -x spacexpansed 2>/dev/null || true
  sleep 3
  systemctl stop bloodstoned 2>/dev/null || true
  systemctl stop spacexpansed 2>/dev/null || true
  sleep 2
  "$DAEMON" -conf="$CONF" -reindex-chainstate -daemon
  if wait_for_rpc 120 5; then
    log "Reindex complete, block count: $("$CLI" -conf="$CONF" getblockcount)"
    "$CLI" -conf="$CONF" stop 2>/dev/null || true
    sleep 3
    systemctl start bloodstoned 2>/dev/null || systemctl start spacexpansed
    if wait_for_rpc 24 5; then
      log "Node handed off to systemd"
      start_stratum
      return 0
    fi
  fi
  log "ERROR: reindex recovery timed out"
  return 1
}

recover_restart() {
  log "Restarting node via systemd"
  stop_stratum
  systemctl restart bloodstoned 2>/dev/null || systemctl restart spacexpansed
  if wait_for_rpc 18 5; then
    log "Node restart successful"
    start_stratum
    return 0
  fi
  if chainstate_error; then
    log "Restart failed with chainstate error, attempting reindex"
    recover_reindex
  else
    log "Restart slow or failed; waiting for RPC before restarting stratum"
    if wait_for_rpc 36 10; then
      log "Node RPC ready after slow restart"
      start_stratum
    else
      log "RPC still unavailable; stratum left stopped until next watchdog run"
    fi
  fi
}

exec 9>"$LOCK"
if ! flock -n 9; then
  exit 0
fi

ensure_settings

if settings_error_recent; then
  log "Recent settings.json parse failure in journal — repairing and restarting node"
  ensure_settings
  recover_restart
  exit 0
fi

if rpc_ok; then
  if ! systemd_node_active && node_running; then
    handoff_orphan_to_systemd || true
  fi
  python3 - <<'PY' 2>/dev/null | while read -r line; do log "$line"; done
import sys
sys.path.insert(0, "/root")
import bloodstone_broadcast as bb
s = bb.sync_status()
print(f"sync local={s['local_height']} peers={s['peer_count']} max_peer={s['max_peer_height']} lag={s['peer_lag']}")
if s["peer_lag"] > 3:
    print(f"WARN peer lag {s['peer_lag']} — blocks may not propagate until peers catch up")
PY
  # Node healthy — ensure stratum pools are up (watchdog may have stopped them earlier).
  for unit in "${STRATUM_UNITS[@]}"; do
    if ! systemctl is-active --quiet "$unit" 2>/dev/null; then
      log "RPC ok but $unit inactive; starting stratum stack"
      start_stratum
      break
    fi
  done
  python3 /root/bloodstone-pool-algo-watchdog.py --once 2>/dev/null | while read -r line; do
    [ -n "$line" ] && log "$line"
  done
  exit 0
fi

if node_running; then
  log "Node process running, waiting for RPC to become ready"
  if wait_for_rpc 30 10; then
    exit 0
  fi
  log "Node process alive but RPC still unavailable"
fi

if ! rpc_port_listening; then
  log "RPC port ${RPC_PORT} not listening"
else
  log "RPC port ${RPC_PORT} listening but CLI probe failed"
fi

ensure_settings

if handoff_orphan_to_systemd; then
  exit 0
fi

if chainstate_error; then
  recover_reindex
else
  recover_restart
fi