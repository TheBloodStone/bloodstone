#!/usr/bin/env bash
# One-shot Pi fleet node setup — portal, DTN mDNS, TLS proxy, memo rail enforcement.
set -euo pipefail

ROOT="${BLOODSTONE_ROOT:-/root}"
ENV_FILE="${BLOODSTONE_CONVERGENCE_ENV:-/etc/bloodstone/convergence.env}"
NODE_ID="${DTN_NODE_ID:-$(hostname -s)}"
REGION="${DTN_DEFAULT_REGION:-lan}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { echo "[pi-fleet-setup] $*"; }

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    log "re-run with sudo"
    exit 1
  fi
}

install_packages() {
  log "installing system packages"
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3 python3-venv python3-pip avahi-daemon avahi-utils openssl rsync curl jq
  systemctl enable --now avahi-daemon 2>/dev/null || true
}

ensure_portal_venv() {
  if [[ ! -d "$ROOT/bloodstone-portal/venv" ]]; then
    log "creating portal venv at $ROOT/bloodstone-portal"
    python3 -m venv "$ROOT/bloodstone-portal/venv"
    "$ROOT/bloodstone-portal/venv/bin/pip" install -q -r "$ROOT/bloodstone-portal/requirements.txt" 2>/dev/null \
      || "$ROOT/bloodstone-portal/venv/bin/pip" install -q flask gunicorn requests zeroconf
  fi
}

install_convergence_env() {
  mkdir -p /etc/bloodstone
  if [[ ! -f "$ENV_FILE" ]]; then
    log "writing $ENV_FILE"
    sed -e "s/pi-edge-01/${NODE_ID}/" -e "s/lan/${REGION}/" \
      "$SCRIPT_DIR/convergence.env.example" >"$ENV_FILE"
    chmod 600 "$ENV_FILE"
  else
    log "keeping existing $ENV_FILE"
  fi
}

install_systemd_units() {
  log "installing systemd units"
  sed "s|/root|${ROOT}|g" "$SCRIPT_DIR/bloodstone-portal-pi.service" \
    >/etc/systemd/system/bloodstone-portal.service
  sed "s|/root|${ROOT}|g" "$SCRIPT_DIR/bloodstone-dtn-mdns.service" \
    >/etc/systemd/system/bloodstone-dtn-mdns.service
  sed "s|/root|${ROOT}|g" "$SCRIPT_DIR/bloodstone-convergence-upkeep.service" \
    >/etc/systemd/system/bloodstone-convergence-upkeep.service
  cp -f "$SCRIPT_DIR/bloodstone-convergence-upkeep.timer" \
    /etc/systemd/system/bloodstone-convergence-upkeep.timer
  if [[ -f "$SCRIPT_DIR/bloodstone-ai-inference.service" ]]; then
    chmod +x "$SCRIPT_DIR/scripts/ai-inference-shim.sh" 2>/dev/null || true
    chmod +x "$SCRIPT_DIR/scripts/ai-inference-shim.py" 2>/dev/null || true
    sed "s|/root|${ROOT}|g" "$SCRIPT_DIR/bloodstone-ai-inference.service" \
      | sed "s|/root/ops|${ROOT}/ops|g" \
      >/etc/systemd/system/bloodstone-ai-inference.service
    systemctl enable --now bloodstone-ai-inference.service 2>/dev/null || true
  fi
  systemctl daemon-reload
  systemctl enable --now bloodstone-portal.service bloodstone-dtn-mdns.service
  systemctl enable --now bloodstone-convergence-upkeep.timer
}

install_tls_proxy() {
  if [[ -x "$ROOT/setup-dtn-pi-tls.sh" ]]; then
    log "provisioning DTN TLS proxy"
    DTN_NODE_ID="$NODE_ID" "$ROOT/setup-dtn-pi-tls.sh"
    systemctl enable --now bloodstone-dtn-tls.service 2>/dev/null || true
  else
    log "skip TLS — $ROOT/setup-dtn-pi-tls.sh not found"
  fi
}

verify_node() {
  log "verifying convergence status"
  sleep 2
  curl -fsS "http://127.0.0.1:8887/api/convergence/status" | jq -e '.storage_rail.enforce_quota == true' >/dev/null \
    || log "WARN: storage enforce_quota not true — check $ENV_FILE"
  curl -fsS "http://127.0.0.1:8887/api/convergence/dtn/status" | jq -e '.ok == true' >/dev/null \
    || log "WARN: DTN status check failed"
  log "node_id=$NODE_ID region=$REGION portal=:8887 tls=:8443"
}

main() {
  require_root
  install_packages
  ensure_portal_venv
  install_convergence_env
  install_systemd_units
  install_tls_proxy
  verify_node
  log "done — see $SCRIPT_DIR/README.md for fleet operations"
}

main "$@"