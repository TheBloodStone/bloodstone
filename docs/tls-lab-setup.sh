#!/bin/bash
# Provision self-signed cert and systemd unit for BSM4 TLS lab (port 18443).
set -euo pipefail

CERT_DIR="${BSM4_TLS_LAB_CERT_DIR:-/etc/bloodstone/tls-lab}"
PORT="${BSM4_TLS_LAB_PORT:-18443}"
SNI="${BSM4_TLS_LAB_SNI:-bloodstone-tls-lab}"

mkdir -p "$CERT_DIR"
if [[ ! -f "$CERT_DIR/bloodstone-tls-lab.crt" ]]; then
  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$CERT_DIR/bloodstone-tls-lab.key" \
    -out "$CERT_DIR/bloodstone-tls-lab.crt" \
    -days 90 -subj "/CN=$SNI"
  chmod 600 "$CERT_DIR/bloodstone-tls-lab.key"
fi

install -m 644 /root/bloodstone-docs/bloodstone-tls-lab.service /etc/systemd/system/bloodstone-tls-lab.service
systemctl daemon-reload
systemctl enable bloodstone-tls-lab.service
systemctl restart bloodstone-tls-lab.service
systemctl --no-pager status bloodstone-tls-lab.service