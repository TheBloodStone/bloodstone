#!/usr/bin/env bash
# Provision self-signed TLS cert + systemd unit for Pi DTN HTTPS proxy (port 8443).
set -euo pipefail

CERT_DIR="${DTN_TLS_CERT_DIR:-/etc/bloodstone/dtn}"
PORT="${DTN_LAN_TLS_PORT:-8443}"
BACKEND="${DTN_TLS_BACKEND:-http://127.0.0.1:8887}"
NODE_ID="${DTN_NODE_ID:-$(hostname -s)}"
DAYS="${DTN_TLS_CERT_DAYS:-825}"

log() { echo "[setup-dtn-pi-tls] $*"; }

mkdir -p "$CERT_DIR"
chmod 700 "$CERT_DIR"

if [[ ! -f "$CERT_DIR/tls.crt" || ! -f "$CERT_DIR/tls.key" ]]; then
  log "generating self-signed cert for $NODE_ID"
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$CERT_DIR/tls.key" \
    -out "$CERT_DIR/tls.crt" \
    -days "$DAYS" \
    -subj "/CN=${NODE_ID}/O=Bloodstone DTN/C=LAN"
  chmod 600 "$CERT_DIR/tls.key"
  chmod 644 "$CERT_DIR/tls.crt"
fi

UNIT=/etc/systemd/system/bloodstone-dtn-tls.service
cat >"$UNIT" <<EOF
[Unit]
Description=Bloodstone DTN TLS proxy (HTTPS ${PORT} -> portal)
After=network-online.target bloodstone-portal.service
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
Environment=DTN_LAN_TLS_PORT=${PORT}
Environment=DTN_TLS_BACKEND=${BACKEND}
Environment=DTN_TLS_CERT=${CERT_DIR}/tls.crt
Environment=DTN_TLS_KEY=${CERT_DIR}/tls.key
ExecStart=/root/bloodstone-portal/venv/bin/python3 /root/bloodstone-dtn-tls-proxy.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
log "enable: systemctl enable --now bloodstone-dtn-tls.service"
log "Pi peers should set DTN_TLS_PEER=1 DTN_TLS_VERIFY=0 (or install CA from ${CERT_DIR}/tls.crt)"