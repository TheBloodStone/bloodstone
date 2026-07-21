#!/bin/bash
# Start Bloodstone full node (Linux x86_64 / ARM64 / Raspberry Pi).
# Installs full chain bootstrap on first run (skips slow IBD / stuck heights).
#
# Security notes (quick-pass audit 0.7.6):
#   - Fixed shebang (/bin/bash), IFS, umask, conf mode 600
#   - Seeds overridable via BLOODSTONE_SEED_NODES (space-separated host:port)
set -euo pipefail
IFS=$'\n\t'
umask 077

ROOT="$(cd "$(dirname "$0")" && pwd)"
export BLOODSTONE_DATADIR="${BLOODSTONE_DATADIR:-$HOME/.bloodstone}"
CONF_DIR="$BLOODSTONE_DATADIR"
CONF_FILE="$CONF_DIR/bloodstone.conf"

# Default seed peers (addnode only — never exclusive connect=).
# Override (either name works):
#   BLOODSTONE_SEEDS="host1:17333 host2:17333"
#   BLOODSTONE_SEED_NODES="host1:17333 host2:17333"
DEFAULT_SEEDS=(
  "64.188.22.190:17333"
  "192.119.82.145:17333"
)

mkdir -p "$CONF_DIR"
chmod 700 "$CONF_DIR" 2>/dev/null || true

if [[ ! -f "$CONF_FILE" ]]; then
  if [[ -f "$ROOT/bloodstone.conf.example" ]]; then
    cp "$ROOT/bloodstone.conf.example" "$CONF_FILE"
  else
    cat > "$CONF_FILE" <<'CONF'
server=1
daemon=1
listen=1
port=17333
rpcport=18332
rpcbind=127.0.0.1
rpcallowip=127.0.0.1
rpcuser=bloodstone
rpcpassword=CHANGE_ME
allowminingwhennotconnected=1
CONF
  fi
  chmod 600 "$CONF_FILE"

  # Prefer random rpc password on fresh installs
  if grep -q 'CHANGE_ME\|rpcpassword=$' "$CONF_FILE" 2>/dev/null || ! grep -q '^rpcpassword=' "$CONF_FILE"; then
    if command -v openssl >/dev/null 2>&1; then
      pass="$(openssl rand -hex 16)"
      if grep -q '^rpcpassword=' "$CONF_FILE"; then
        sed -i "s|^rpcpassword=.*|rpcpassword=${pass}|" "$CONF_FILE"
      else
        echo "rpcpassword=${pass}" >> "$CONF_FILE"
      fi
    fi
  fi

  # Seed peers (addnode only). Space-separated host:port list.
  seeds=()
  _seed_env="${BLOODSTONE_SEEDS:-${BLOODSTONE_SEED_NODES:-}}"
  if [[ -n "$_seed_env" ]]; then
    _oldifs="$IFS"
    IFS=' '
    # shellcheck disable=SC2206
    seeds=(${_seed_env})
    IFS="$_oldifs"
    unset _oldifs _seed_env
  else
    seeds=("${DEFAULT_SEEDS[@]}")
    unset _seed_env
  fi
  for seed in "${seeds[@]}"; do
    [[ -n "$seed" ]] || continue
    grep -Fq "addnode=${seed}" "$CONF_FILE" 2>/dev/null || echo "addnode=${seed}" >> "$CONF_FILE"
  done

  # Strip exclusive connect= so seeds can discover peers
  if grep -q '^connect=' "$CONF_FILE"; then
    grep -v '^connect=' "$CONF_FILE" > "${CONF_FILE}.tmp" && mv "${CONF_FILE}.tmp" "$CONF_FILE"
  fi
  chmod 600 "$CONF_FILE"
  echo "Created $CONF_FILE (mode 600) — do not expose RPC without a firewall."
else
  # Tighten perms on existing conf if world/group readable
  if [[ -f "$CONF_FILE" ]]; then
    chmod 600 "$CONF_FILE" 2>/dev/null || true
  fi
fi

# Full tip snapshot (blocks + chainstate + index [+ txindex when published])
if [[ -f "$ROOT/install-chain-bootstrap.sh" ]]; then
  # shellcheck source=/dev/null
  # Prefer sourcing when functions are available; fall back to bash exec.
  if grep -q 'install_chain_bootstrap' "$ROOT/install-chain-bootstrap.sh" 2>/dev/null; then
    # shellcheck source=/dev/null
    source "$ROOT/install-chain-bootstrap.sh"
    install_chain_bootstrap
  else
    bash "$ROOT/install-chain-bootstrap.sh"
  fi
fi

exec "$ROOT/bin/bloodstoned" -conf="$CONF_FILE" -daemon "$@"
