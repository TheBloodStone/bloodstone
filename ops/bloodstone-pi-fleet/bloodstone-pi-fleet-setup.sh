#!/usr/bin/env bash
# One-shot Pi fleet node setup — portal, DTN mDNS, TLS proxy, memo rail enforcement.
# Audit 2026-07-12 fixes: pip retries, sudo -H, verify retry loop, portal path, TLS country.
set -euo pipefail

export HOME="${HOME:-/root}"
ROOT="${BLOODSTONE_ROOT:-/root}"
ENV_FILE="${BLOODSTONE_CONVERGENCE_ENV:-/etc/bloodstone/convergence.env}"
NODE_ID="${DTN_NODE_ID:-$(hostname -s)}"
REGION="${DTN_DEFAULT_REGION:-lan}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIP_TIMEOUT="${PIP_TIMEOUT:-60}"
PIP_RETRIES="${PIP_RETRIES:-5}"

log() { echo "[pi-fleet-setup] $*"; }

require_root() {
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    log "re-run with: sudo -H -E $0"
    exit 1
  fi
  # E-02: ensure root home for pip cache (avoid /home/pi/.cache permission noise)
  export HOME=/root
  export PIP_CACHE_DIR="${PIP_CACHE_DIR:-/root/.cache/pip}"
  mkdir -p "$PIP_CACHE_DIR"
}

install_packages() {
  log "installing system packages"
  apt-get update -qq || true
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3 python3-venv python3-pip avahi-daemon avahi-utils openssl rsync curl jq \
    || true
  systemctl enable --now avahi-daemon 2>/dev/null || true
}

pip_install() {
  # Critical #2: retries + timeout for flaky Pi networks
  local venv_pip="$1"
  shift
  local attempt=1
  local max_attempts=3
  while [[ $attempt -le $max_attempts ]]; do
    log "pip install (attempt ${attempt}/${max_attempts}): $*"
    if "$venv_pip" install \
      --disable-pip-version-check \
      --timeout "$PIP_TIMEOUT" \
      --retries "$PIP_RETRIES" \
      "$@"; then
      return 0
    fi
    log "pip install failed — retrying in 5s…"
    sleep 5
    attempt=$((attempt + 1))
  done
  log "ERROR: pip install failed after ${max_attempts} attempts"
  return 1
}

ensure_portal_modules() {
  # Critical #3: copy required bloodstone_* / pool_* modules next to portal if missing
  local dest="$ROOT/bloodstone-portal"
  mkdir -p "$dest"
  local f
  for f in \
    bloodstone_branding.py \
    bloodstone_http_auth.py \
    bloodstone_downloads.py \
    bloodstone_quasar.py \
    bloodstone_rich_list.py \
    bloodstone_beta_codes.py \
    bloodstone_time.py \
    bloodstone_client_ip.py \
    bloodstone_device_guard.py \
    bloodstone_broadcast.py \
    pool_db.py \
    pool_device_fleet.py \
    pool_payout_settings.py \
    pool_algos.py \
    pool_payout.py
  do
    if [[ -f "$ROOT/$f" && ! -f "$dest/$f" ]]; then
      log "copying $f into portal package dir"
      cp -a "$ROOT/$f" "$dest/$f"
    fi
  done
  # Critical #4: ensure app.py has portal dir on sys.path
  if [[ -f "$dest/app.py" ]] && ! grep -q 'bloodstone-portal' "$dest/app.py"; then
    log "patching portal app.py sys.path for local modules"
    # Insert after first sys.path.insert if present, else after import sys
    if grep -q 'sys.path.insert(0, "/root")' "$dest/app.py"; then
      sed -i '/sys.path.insert(0, "\/root")/a sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\nsys.path.insert(0, "/root/bloodstone-portal")' "$dest/app.py" \
        || true
    fi
  fi
  # Prefer dynamic patch that always works even if paths differ
  if [[ -f "$dest/app.py" ]] && ! grep -q 'dirname(os.path.abspath(__file__))' "$dest/app.py"; then
    python3 - <<'PY' "$dest/app.py" || true
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
needle = 'sys.path.insert(0, "/root")'
inject = (
    'sys.path.insert(0, "/root")\n'
    'sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n'
    'sys.path.insert(0, "/root/bloodstone-portal")'
)
if needle in text and "dirname(os.path.abspath(__file__))" not in text:
    text = text.replace(needle, inject, 1)
    open(path, "w", encoding="utf-8").write(text)
    print("patched", path)
else:
    print("skip patch", path)
PY
  fi
}

ensure_portal_venv() {
  local req="$ROOT/bloodstone-portal/requirements.txt"
  local venv="$ROOT/bloodstone-portal/venv"
  local pip="$venv/bin/pip"
  if [[ ! -x "$pip" ]]; then
    log "creating portal venv at $ROOT/bloodstone-portal"
    python3 -m venv "$venv"
  fi
  pip_install "$pip" --upgrade pip setuptools wheel || true
  if [[ -f "$req" ]]; then
    pip_install "$pip" -r "$req" || \
      pip_install "$pip" flask gunicorn requests zeroconf
  else
    pip_install "$pip" flask gunicorn requests zeroconf
  fi
  # Ensure critical imports exist even if requirements was partial
  pip_install "$pip" flask gunicorn requests zeroconf || true
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
  # Document LAN-open danger in env file once
  if ! grep -q 'CHAIN_MESH_LAN_OPEN_REGISTER' "$ENV_FILE" 2>/dev/null; then
    cat >>"$ENV_FILE" <<'EOF'

# --- Security (F-07) ---
# Do NOT set CHAIN_MESH_LAN_OPEN_REGISTER=1 on internet-facing hosts.
# It only applies when no CHAIN_MESH_API_TOKEN is configured (lab/air-gap).
# CHAIN_MESH_LAN_OPEN_REGISTER=0
# CHAIN_MESH_REQUIRE_OWNERSHIP_PROOF=0
# CHAIN_MESH_OWNERSHIP_MODE=token
EOF
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
    # Pass 2-letter country for OpenSSL (audit: C=LAN is invalid)
    DTN_NODE_ID="$NODE_ID" DTN_TLS_COUNTRY="${DTN_TLS_COUNTRY:-US}" \
      "$ROOT/setup-dtn-pi-tls.sh"
    systemctl enable --now bloodstone-dtn-tls.service 2>/dev/null || true
  else
    log "skip TLS — $ROOT/setup-dtn-pi-tls.sh not found"
  fi
}

verify_node() {
  # E-01: retry — gunicorn needs a moment after systemctl start
  log "verifying convergence status (with retries)"
  local ok=0
  local i
  for i in $(seq 1 15); do
    if curl -fsS --connect-timeout 2 --max-time 5 \
      "http://127.0.0.1:8887/api/convergence/status" >/tmp/pi-fleet-status.json 2>/dev/null; then
      ok=1
      break
    fi
    log "portal not ready yet (try $i/15) — sleeping 2s"
    sleep 2
  done
  if [[ "$ok" -ne 1 ]]; then
    log "WARN: portal did not answer on :8887 after retries — check: journalctl -u bloodstone-portal -n 50"
    return 0
  fi
  if command -v jq >/dev/null 2>&1; then
    jq -e '.ok == true' /tmp/pi-fleet-status.json >/dev/null 2>&1 \
      || log "WARN: convergence status .ok != true"
    jq -e '.storage_rail.enforce_quota == true' /tmp/pi-fleet-status.json >/dev/null 2>&1 \
      || log "WARN: storage enforce_quota not true — check $ENV_FILE"
  fi
  if curl -fsSk --connect-timeout 2 --max-time 5 \
    "https://127.0.0.1:8443/api/convergence/status" >/dev/null 2>&1; then
    log "TLS proxy :8443 OK"
  else
    log "WARN: TLS :8443 not answering yet (cert/proxy). Check bloodstone-dtn-tls.service"
  fi
  log "node_id=$NODE_ID region=$REGION portal=:8887 tls=:8443"
}

main() {
  require_root
  install_packages
  ensure_portal_modules
  ensure_portal_venv
  install_convergence_env
  install_systemd_units
  install_tls_proxy
  verify_node
  log "done — see $SCRIPT_DIR/README.md for fleet operations"
  log "security: keep CHAIN_MESH_LAN_OPEN_REGISTER unset/0 on internet-facing nodes"
}

main "$@"
