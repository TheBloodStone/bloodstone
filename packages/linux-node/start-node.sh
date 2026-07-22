#!/bin/bash
# Start Bloodstone full node (Linux x86_64 / ARM64 / Raspberry Pi).
# Installs full chain bootstrap on first run (skips slow IBD / stuck heights).
#
# Security notes (quick-pass audit 0.7.6 + final 2026-07 production audit):
#   - Fixed shebang (/bin/bash), IFS, umask, conf mode 600
#   - Seeds overridable via BLOODSTONE_SEED_NODES (space-separated host:port)
#   - Install logging under $BLOODSTONE_DATADIR/logs/
#   - Refuse duplicate daemon launch when already running
set -euo pipefail
IFS=$'\n\t'
umask 077

ROOT="$(cd "$(dirname "$0")" && pwd)"
export BLOODSTONE_DATADIR="${BLOODSTONE_DATADIR:-$HOME/.bloodstone}"
CONF_DIR="$BLOODSTONE_DATADIR"
CONF_FILE="$CONF_DIR/bloodstone.conf"
LOG_DIR="${BLOODSTONE_LOG_DIR:-$CONF_DIR/logs}"
INSTALL_LOG="$LOG_DIR/install.log"

# Default seed peers (addnode only — never exclusive connect=).
# Override (either name works):
#   BLOODSTONE_SEEDS="host1:17333 host2:17333"
#   BLOODSTONE_SEED_NODES="host1:17333 host2:17333"
DEFAULT_SEEDS=(
  "64.188.22.190:17333"
  "192.119.82.145:17333"
)

mkdir -p "$CONF_DIR" "$LOG_DIR"
chmod 700 "$CONF_DIR" 2>/dev/null || true
chmod 700 "$LOG_DIR" 2>/dev/null || true

log_install() {
  local line
  line="[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
  echo "$line"
  # Best-effort append; never fail start because of log I/O
  echo "$line" >> "$INSTALL_LOG" 2>/dev/null || true
}

daemon_already_running() {
  local pid=""
  if [[ -f "$CONF_DIR/bloodstoned.pid" ]]; then
    pid="$(tr -cd '0-9' < "$CONF_DIR/bloodstoned.pid" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  # Same binary path (avoid matching unrelated installs loosely)
  if command -v pgrep >/dev/null 2>&1; then
    if pgrep -f "$ROOT/bin/bloodstoned" >/dev/null 2>&1; then
      return 0
    fi
  fi
  return 1
}

if daemon_already_running; then
  log_install "bloodstoned already running for datadir $CONF_DIR — not starting a second instance"
  echo "Already running. Use: $ROOT/bloodstone-health.sh  (or bloodstone-health)"
  exit 0
fi

log_install "start-node begin datadir=$CONF_DIR root=$ROOT"

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
      log_install "generated random rpcpassword (not logged)"
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
  log_install "Created $CONF_FILE (mode 600) — do not expose RPC without a firewall."
else
  # Tighten perms on existing conf if world/group readable
  if [[ -f "$CONF_FILE" ]]; then
    chmod 600 "$CONF_FILE" 2>/dev/null || true
  fi
fi

# Full tip snapshot (blocks + chainstate + index [+ txindex when published])
if [[ -f "$ROOT/install-chain-bootstrap.sh" ]]; then
  log_install "running install-chain-bootstrap"
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

if [[ ! -e "$ROOT/bin/bloodstoned" ]]; then
  log_install "ERROR: missing $ROOT/bin/bloodstoned"
  echo "ERROR: missing $ROOT/bin/bloodstoned" >&2
  echo "" >&2
  echo "start-node.sh only launches an already-built daemon. You still need binaries:" >&2
  echo "  A) From source (in this directory):" >&2
  echo "       ./install-from-source.sh" >&2
  echo "       # wait for compile to finish — creates bin/bloodstoned here" >&2
  echo "       ./start-node.sh" >&2
  echo "  B) Or unpack a prebuilt node tarball and run its start-node.sh" >&2
  echo "       https://bloodstone.rocks/downloads/  (bloodstone-node-*-linux-aarch64.tar.gz)" >&2
  exit 1
fi
if [[ ! -x "$ROOT/bin/bloodstoned" ]]; then
  log_install "ERROR: $ROOT/bin/bloodstoned is not executable"
  echo "ERROR: $ROOT/bin/bloodstoned exists but is not executable. Try: chmod 755 $ROOT/bin/bloodstoned" >&2
  exit 1
fi
# Wrong-arch / missing dynamic linker also surfaces as "No such file or directory"
if ! "$ROOT/bin/bloodstoned" -version >/dev/null 2>&1 && ! "$ROOT/bin/bloodstoned" --version >/dev/null 2>&1; then
  if command -v file >/dev/null 2>&1; then
    log_install "WARN: bloodstoned may be wrong arch or broken: $(file -b "$ROOT/bin/bloodstoned" 2>/dev/null || true)"
    echo "WARN: could not run bloodstoned -version. file(1): $(file -b "$ROOT/bin/bloodstoned" 2>/dev/null || true)" >&2
    echo "If this is a Pi/ARM machine, use the aarch64 build (or install-from-source on this device)." >&2
  fi
fi

log_install "exec bloodstoned -conf=$CONF_FILE -daemon"
exec "$ROOT/bin/bloodstoned" -conf="$CONF_FILE" -daemon "$@"
