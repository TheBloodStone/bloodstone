#!/usr/bin/env bash
# Provision self-signed TLS cert + systemd unit for Pi DTN HTTPS proxy (port 8443).
# Audit 2026-07-12: C= must be ISO 3166 2-letter (not C=LAN); peers use CA file not VERIFY=0.
set -euo pipefail

CERT_DIR="${DTN_TLS_CERT_DIR:-/etc/bloodstone/dtn}"
PORT="${DTN_LAN_TLS_PORT:-8443}"
BACKEND="${DTN_TLS_BACKEND:-http://127.0.0.1:8887}"
NODE_ID="${DTN_NODE_ID:-$(hostname -s)}"
DAYS="${DTN_TLS_CERT_DAYS:-825}"
# F-05 / OpenSSL: countryName must be exactly 2 characters (ISO 3166-1 alpha-2).
COUNTRY="${DTN_TLS_COUNTRY:-US}"
COUNTRY="$(echo "$COUNTRY" | tr '[:lower:]' '[:upper:]' | tr -cd 'A-Z' | cut -c1-2)"
if [[ ${#COUNTRY} -ne 2 ]]; then
  COUNTRY="US"
fi
ORG="${DTN_TLS_ORG:-Bloodstone DTN}"

log() { echo "[setup-dtn-pi-tls] $*"; }

mkdir -p "$CERT_DIR"
chmod 700 "$CERT_DIR"

if [[ ! -f "$CERT_DIR/tls.crt" || ! -f "$CERT_DIR/tls.key" ]]; then
  log "generating self-signed cert for $NODE_ID (C=${COUNTRY})"
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$CERT_DIR/tls.key" \
    -out "$CERT_DIR/tls.crt" \
    -days "$DAYS" \
    -subj "/CN=${NODE_ID}/O=${ORG}/C=${COUNTRY}"
  chmod 600 "$CERT_DIR/tls.key"
  chmod 644 "$CERT_DIR/tls.crt"
else
  log "keeping existing certs in $CERT_DIR"
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
log "Pi peers should set:"
log "  DTN_TLS_PEER=1"
log "  DTN_TLS_VERIFY=1"
log "  DTN_TLS_CA_FILE=${CERT_DIR}/tls.crt"
log "Distribute ${CERT_DIR}/tls.crt to peers (preferred). Do NOT set DTN_TLS_VERIFY=0 in production."
log "Lab-only fallback if CA cannot be distributed: DTN_TLS_VERIFY=0 (insecure — not for internet-facing hosts)."
