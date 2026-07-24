#!/bin/bash
# Install Bloodstone node as a hardened systemd service.
# Run as root from the extracted package directory.
set -euo pipefail
IFS=$'\n\t'
umask 022

ROOT="$(cd "$(dirname "$0")" && pwd)"
UNIT_SRC="$ROOT/bloodstone-node.service"
UNIT_DST="/etc/systemd/system/bloodstone-node.service"
INSTALL_ROOT="${BLOODSTONE_SYSTEMD_ROOT:-/opt/bloodstone-node}"
DATADIR="${BLOODSTONE_SYSTEMD_DATADIR:-/var/lib/bloodstone}"
RUN_USER="${BLOODSTONE_SYSTEMD_USER:-bloodstone}"
RUN_GROUP="${BLOODSTONE_SYSTEMD_GROUP:-$RUN_USER}"

log() { echo "[install-systemd] $*"; }
die() { echo "[install-systemd] ERROR: $*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || die "run as root (sudo $0)"
[[ -f "$UNIT_SRC" ]] || die "missing $UNIT_SRC"
[[ -x "$ROOT/start-node.sh" ]] || die "missing start-node.sh in $ROOT"
[[ -x "$ROOT/bin/bloodstoned" ]] || die "missing bin/bloodstoned — extract a full node package first"
command -v systemctl >/dev/null 2>&1 || die "systemctl not found"

if ! id -u "$RUN_USER" >/dev/null 2>&1; then
  log "Creating system user $RUN_USER"
  useradd --system --home-dir "$DATADIR" --shell /usr/sbin/nologin --create-home "$RUN_USER" \
    || useradd --system --home-dir "$DATADIR" --shell /bin/false "$RUN_USER"
fi

log "Installing package tree → $INSTALL_ROOT"
mkdir -p "$INSTALL_ROOT" "$DATADIR"
# Copy package contents (preserve layout)
rsync -a --delete \
  --exclude '.git' \
  --exclude 'logs' \
  "$ROOT/" "$INSTALL_ROOT/" \
  2>/dev/null || {
  # rsync optional; fallback
  mkdir -p "$INSTALL_ROOT/bin"
  cp -a "$ROOT/bin/." "$INSTALL_ROOT/bin/"
  for f in start-node.sh install-chain-bootstrap.sh install-from-source.sh verify-release.sh \
           bloodstone-health.sh bloodstone.conf.example bloodstone-node.service install-systemd.sh \
           BUILD-INFO.txt README.txt README.md; do
    [[ -e "$ROOT/$f" ]] && cp -a "$ROOT/$f" "$INSTALL_ROOT/$f"
  done
  chmod 755 "$INSTALL_ROOT/start-node.sh" "$INSTALL_ROOT/bin/bloodstoned" 2>/dev/null || true
  [[ -x "$INSTALL_ROOT/bloodstone-health.sh" ]] && chmod 755 "$INSTALL_ROOT/bloodstone-health.sh"
}

chown -R "$RUN_USER:$RUN_GROUP" "$DATADIR"
# Binaries owned by root; data by service user
chown -R root:root "$INSTALL_ROOT"
chmod 755 "$INSTALL_ROOT" "$INSTALL_ROOT/bin" 2>/dev/null || true
chmod 755 "$INSTALL_ROOT/start-node.sh" "$INSTALL_ROOT/bin/"* 2>/dev/null || true

# Symlink convenience CLI
if [[ -x "$INSTALL_ROOT/bloodstone-health.sh" ]]; then
  ln -sfn "$INSTALL_ROOT/bloodstone-health.sh" /usr/local/bin/bloodstone-health
fi
if [[ -x "$INSTALL_ROOT/bin/bloodstone-cli" ]]; then
  ln -sfn "$INSTALL_ROOT/bin/bloodstone-cli" /usr/local/bin/bloodstone-cli
fi

log "Writing unit $UNIT_DST"
# Rewrite paths in unit for this install
sed \
  -e "s|/opt/bloodstone-node|${INSTALL_ROOT}|g" \
  -e "s|/var/lib/bloodstone|${DATADIR}|g" \
  -e "s|^User=.*|User=${RUN_USER}|" \
  -e "s|^Group=.*|Group=${RUN_GROUP}|" \
  "$UNIT_SRC" > "$UNIT_DST"
chmod 644 "$UNIT_DST"

# Ensure conf exists under service datadir (first-run generation as service user)
if [[ ! -f "$DATADIR/bloodstone.conf" ]]; then
  log "First-run conf will be created on service start under $DATADIR"
fi
chown -R "$RUN_USER:$RUN_GROUP" "$DATADIR"
chmod 700 "$DATADIR"

systemctl daemon-reload
systemctl enable bloodstone-node.service
log "Starting bloodstone-node…"
systemctl restart bloodstone-node.service || systemctl start bloodstone-node.service

log "Done."
log "  systemctl status bloodstone-node"
log "  journalctl -u bloodstone-node -f"
log "  bloodstone-health"
log "  Datadir: $DATADIR"
