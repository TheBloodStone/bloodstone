#!/bin/bash
# Install Bloodstone LAN mesh internet gateway (share internet with household miners).
#
#   curl -fsSL https://bloodstonewallet.mytunnel.org/downloads/install-lan-mesh-gateway.sh | bash
#
# Requires: python3, internet on this machine, device_id from Bloodstone APK/portal.

set -euo pipefail

POOL_URL="${POOL_URL:-https://bloodstonewallet.mytunnel.org}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/bloodstone-mesh-gateway}"
INTERVAL="${MESH_GATEWAY_INTERVAL:-4}"

read -rp "Bloodstone device_id (from APK fleet panel): " DEVICE_ID
if [ -z "${DEVICE_ID}" ]; then
  echo "device_id required" >&2
  exit 1
fi

mkdir -p "$INSTALL_DIR"
curl -fsSL "${POOL_URL}/downloads/lan-mesh-internet-gateway.py" \
  -o "${INSTALL_DIR}/lan-mesh-internet-gateway.py"
chmod +x "${INSTALL_DIR}/lan-mesh-internet-gateway.py"

UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNIT_DIR"
cat > "${UNIT_DIR}/bloodstone-mesh-gateway.service" <<EOF
[Unit]
Description=Bloodstone mesh internet gateway (free internet for LAN miners)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
Environment=POOL_URL=${POOL_URL}
Environment=MESH_GATEWAY_DEVICE_ID=${DEVICE_ID}
Environment=MESH_GATEWAY_PEER_KIND=pc
Environment=MESH_GATEWAY_INTERVAL=${INTERVAL}
ExecStart=/usr/bin/env python3 ${INSTALL_DIR}/lan-mesh-internet-gateway.py
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now bloodstone-mesh-gateway.service
loginctl enable-linger "${USER}" 2>/dev/null || true

echo ""
echo "Mesh internet gateway running for device_id=${DEVICE_ID}"
systemctl --user --no-pager status bloodstone-mesh-gateway.service || true
echo ""
echo "LAN miners: open BSM4 tunnel — they will auto-elect this gateway when on the same public IP."