#!/usr/bin/env bash
# Publish a clean blocks-only chain bootstrap for Android full-node installs.
set -euo pipefail

DATADIR="${BLOODSTONE_DATADIR:-/root/.bloodstone}"
OUT_DL="${BLOODSTONE_DOWNLOADS_DIR:-/var/www/bloodstone/downloads}"
RPC_USER="${BLOODSTONE_RPC_USER:-bloodstone}"
RPC_PASS="${BLOODSTONE_RPC_PASS:-$(grep -m1 '^rpcpassword=' "$DATADIR/bloodstone.conf" | cut -d= -f2)}"
RPC_URL="${BLOODSTONE_RPC_URL:-http://127.0.0.1:18332/}"

log() { echo "[chain-bootstrap] $*"; }

log "stopping bloodstoned for consistent snapshot"
curl -sS --user "$RPC_USER:$RPC_PASS" "$RPC_URL" \
  -d '{"jsonrpc":"1.0","id":"x","method":"stop","params":[]}' >/dev/null || true
for _ in $(seq 1 45); do
  pgrep -x bloodstoned >/dev/null || break
  sleep 1
done

HEIGHT=$(curl -sS --user "$RPC_USER:$RPC_PASS" "$RPC_URL" \
  -d '{"jsonrpc":"1.0","id":"x","method":"getblockcount","params":[]}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',0))" 2>/dev/null || echo 0)
[[ "$HEIGHT" =~ ^[0-9]+$ ]] && [[ "$HEIGHT" -gt 0 ]] || HEIGHT=9080

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cp -a "$DATADIR/blocks" "$TMP/"
echo "$HEIGHT" > "$TMP/.bootstrap-height"
echo "1" > "$TMP/.bootstrap-reindex"

BUNDLE="bloodstone-chain-bootstrap-${HEIGHT}.tar.gz"
mkdir -p "$OUT_DL"
tar -czf "$OUT_DL/$BUNDLE" -C "$TMP" blocks .bootstrap-height .bootstrap-reindex
sha256sum "$OUT_DL/$BUNDLE" | awk '{print $1}' > "$OUT_DL/$BUNDLE.sha256"
ln -sfn "$BUNDLE" "$OUT_DL/bloodstone-chain-bootstrap-latest.tar.gz"

log "published $OUT_DL/$BUNDLE ($(wc -c < "$OUT_DL/$BUNDLE") bytes)"
log "sha256: $(cat "$OUT_DL/$BUNDLE.sha256")"

systemctl start bloodstoned 2>/dev/null || true

if [[ -x /root/sync-bloodstone-downloads-to-worker.sh ]]; then
  /root/sync-bloodstone-downloads-to-worker.sh \
    "$OUT_DL/$BUNDLE" \
    "$OUT_DL/$BUNDLE.sha256" \
    "$OUT_DL/bloodstone-chain-bootstrap-latest.tar.gz" || true
fi