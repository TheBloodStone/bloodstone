#!/usr/bin/env bash
# Publish chain bootstrap for Android: blocks + chainstate (skips phone reindex).
set -euo pipefail

DATADIR="${BLOODSTONE_DATADIR:-/root/.bloodstone}"
OUT_DL="${BLOODSTONE_DOWNLOADS_DIR:-/var/www/bloodstone/downloads}"
RPC_USER="${BLOODSTONE_RPC_USER:-bloodstone}"
RPC_PASS="${BLOODSTONE_RPC_PASS:-$(grep -m1 '^rpcpassword=' "$DATADIR/bloodstone.conf" | cut -d= -f2)}"
RPC_URL="${BLOODSTONE_RPC_URL:-http://127.0.0.1:18332/}"

log() { echo "[chain-bootstrap] $*"; }

HEIGHT=$(curl -sS --user "$RPC_USER:$RPC_PASS" "$RPC_URL" \
  -d '{"jsonrpc":"1.0","id":"x","method":"getblockcount","params":[]}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',0))" 2>/dev/null || echo 0)
[[ "$HEIGHT" =~ ^[0-9]+$ ]] && [[ "$HEIGHT" -gt 0 ]] || HEIGHT=9080
log "chain tip height $HEIGHT — stopping bloodstoned for consistent snapshot"
curl -sS --user "$RPC_USER:$RPC_PASS" "$RPC_URL" \
  -d '{"jsonrpc":"1.0","id":"x","method":"stop","params":[]}' >/dev/null || true
for _ in $(seq 1 45); do
  pgrep -x bloodstoned >/dev/null || break
  sleep 1
done

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/blocks"
# Ship blk/rev plus blocks/index with chainstate (consistent stopped-daemon snapshot).
shopt -s nullglob
for blk in "$DATADIR/blocks"/blk*.dat; do
  cp -a "$blk" "$TMP/blocks/"
done
for rev in "$DATADIR/blocks"/rev*.dat; do
  cp -a "$rev" "$TMP/blocks/"
done
shopt -u nullglob
if [[ -d "$DATADIR/blocks/index" ]] && [[ -n "$(ls -A "$DATADIR/blocks/index" 2>/dev/null)" ]]; then
  cp -a "$DATADIR/blocks/index" "$TMP/blocks/"
  log "bundled blocks/index ($(du -sh "$TMP/blocks/index" | awk '{print $1}'))"
  printf '1\n' > "$TMP/.bootstrap-includes-index"
fi
[[ -n "$(ls -A "$TMP/blocks" 2>/dev/null)" ]] || {
  log "ERROR: no blk*.dat in $DATADIR/blocks"
  exit 1
}
if [[ -d "$DATADIR/chainstate" ]] && [[ -n "$(ls -A "$DATADIR/chainstate" 2>/dev/null)" ]]; then
  cp -a "$DATADIR/chainstate" "$TMP/"
  log "bundled chainstate ($(du -sh "$TMP/chainstate" | awk '{print $1}'))"
else
  log "WARN: no chainstate — phones will reindex from blocks"
  printf '1\n' > "$TMP/.bootstrap-reindex"
fi
echo "$HEIGHT" > "$TMP/.bootstrap-height"

BUNDLE="bloodstone-chain-bootstrap-${HEIGHT}.tar.gz"
mkdir -p "$OUT_DL"
TAR_ITEMS=(blocks .bootstrap-height)
[[ -d "$TMP/chainstate" ]] && TAR_ITEMS+=(chainstate)
[[ -f "$TMP/.bootstrap-includes-index" ]] && TAR_ITEMS+=(.bootstrap-includes-index)
[[ -f "$TMP/.bootstrap-reindex" ]] && TAR_ITEMS+=(.bootstrap-reindex)
tar -czf "$OUT_DL/$BUNDLE" -C "$TMP" "${TAR_ITEMS[@]}"
sha256sum "$OUT_DL/$BUNDLE" | awk '{print $1}' > "$OUT_DL/$BUNDLE.sha256"
ln -sfn "$BUNDLE" "$OUT_DL/bloodstone-chain-bootstrap-latest.tar.gz"
ln -sfn "$BUNDLE.sha256" "$OUT_DL/bloodstone-chain-bootstrap-latest.tar.gz.sha256"

log "published $OUT_DL/$BUNDLE ($(wc -c < "$OUT_DL/$BUNDLE") bytes)"
log "sha256: $(cat "$OUT_DL/$BUNDLE.sha256")"

systemctl start bloodstoned 2>/dev/null || true

if [[ -x /root/sync-bloodstone-downloads-to-worker.sh ]]; then
  /root/sync-bloodstone-downloads-to-worker.sh \
    "$OUT_DL/$BUNDLE" \
    "$OUT_DL/$BUNDLE.sha256" \
    "$OUT_DL/bloodstone-chain-bootstrap-latest.tar.gz" \
    "$OUT_DL/bloodstone-chain-bootstrap-latest.tar.gz.sha256" || true
fi