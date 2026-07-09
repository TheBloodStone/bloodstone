#!/usr/bin/env bash
# Build Pi fleet convergence bundle (portal + chain_mesh + DTN helpers) for Raspberry Pi.
set -euo pipefail

VERSION="${1:-0.36.0-beta}"
OUT_DL="${BLOODSTONE_DOWNLOADS_DIR:-/var/www/bloodstone/downloads}"
STAGING="/tmp/bloodstone-pi-fleet-convergence-${VERSION}"
PKG="bloodstone-pi-fleet-convergence-${VERSION}"
TARBALL="${OUT_DL}/${PKG}.tar.gz"
PUBLIC="${BLOODSTONE_PUBLIC_ROOT:-https://bloodstonewallet.mytunnel.org}"

log() { echo "[pi-fleet-pkg] $*"; }

rm -rf "$STAGING"
mkdir -p "$STAGING/root/ops/bloodstone-pi-fleet"

log "staging portal (no venv)..."
rsync -a --exclude venv --exclude __pycache__ --exclude '*.pyc' \
  /root/bloodstone-portal/ "$STAGING/root/bloodstone-portal/"

log "staging chain_mesh..."
rsync -a --exclude __pycache__ --exclude '*.pyc' \
  /root/chain_mesh/ "$STAGING/root/chain_mesh/"

for f in sync-blurt-convergence.py bloodstone-dtn-mdns.py bloodstone-dtn-tls-proxy.py setup-dtn-pi-tls.sh; do
  cp -a "/root/$f" "$STAGING/root/$f"
done

rsync -a /root/ops/bloodstone-pi-fleet/ "$STAGING/root/ops/bloodstone-pi-fleet/"
chmod +x "$STAGING/root/ops/bloodstone-pi-fleet/bloodstone-pi-fleet-setup.sh"
chmod +x "$STAGING/root/ops/bloodstone-pi-fleet/scripts/"*.sh 2>/dev/null || true
chmod +x "$STAGING/root/setup-dtn-pi-tls.sh"

cat >"$STAGING/INSTALL.md" <<'EOF'
# Bloodstone Pi Fleet — Quick Install

1. Extract to `/` (creates `/root/bloodstone-portal`, `/root/chain_mesh`, etc.)
2. Set your node id: `export DTN_NODE_ID=your-pi-name`
3. Run: `sudo /root/ops/bloodstone-pi-fleet/bloodstone-pi-fleet-setup.sh`
4. Verify: `curl -fsS http://127.0.0.1:8887/api/convergence/status | jq .ok`

See `/root/ops/bloodstone-pi-fleet/README.md` for full playbook.
EOF

mkdir -p "$OUT_DL"
tar -C "$STAGING" -czf "$TARBALL" .
sha256sum "$TARBALL" | awk '{print $1}' > "${TARBALL}.sha256"
ln -sfn "$(basename "$TARBALL")" "${OUT_DL}/bloodstone-pi-fleet-convergence-latest.tar.gz"
cp -f /root/ops/bloodstone-pi-fleet/README.md "${OUT_DL}/Bloodstone-Pi-Fleet-Playbook-v${VERSION}.md"
ln -sfn "Bloodstone-Pi-Fleet-Playbook-v${VERSION}.md" "${OUT_DL}/Bloodstone-Pi-Fleet-Playbook-latest.md"
sha256sum "${OUT_DL}/Bloodstone-Pi-Fleet-Playbook-v${VERSION}.md" | awk '{print $1}' > "${OUT_DL}/Bloodstone-Pi-Fleet-Playbook-v${VERSION}.md.sha256"
ln -sfn "Bloodstone-Pi-Fleet-Playbook-v${VERSION}.md.sha256" "${OUT_DL}/Bloodstone-Pi-Fleet-Playbook-latest.md.sha256"
if [[ -f /root/bloodstone-docs/Blurt-Pi-Fleet-Install-Instructions.md ]]; then
  cp -f /root/bloodstone-docs/Blurt-Pi-Fleet-Install-Instructions.md "${OUT_DL}/Blurt-Pi-Fleet-Install-Instructions.md"
  sha256sum "${OUT_DL}/Blurt-Pi-Fleet-Install-Instructions.md" | awk '{print $1}' > "${OUT_DL}/Blurt-Pi-Fleet-Install-Instructions.md.sha256"
fi

if [[ -x /root/sync-bloodstone-downloads-to-worker.sh ]]; then
  /root/sync-bloodstone-downloads-to-worker.sh \
    "$TARBALL" "${TARBALL}.sha256" \
    "${OUT_DL}/bloodstone-pi-fleet-convergence-latest.tar.gz" \
    "${OUT_DL}/Bloodstone-Pi-Fleet-Playbook-latest.md" \
    "${OUT_DL}/Bloodstone-Pi-Fleet-Playbook-latest.md.sha256" || true
fi

log "published ${PUBLIC}/downloads/$(basename "$TARBALL")"
log "published ${PUBLIC}/downloads/bloodstone-pi-fleet-convergence-latest.tar.gz"
log "size $(wc -c < "$TARBALL") bytes"