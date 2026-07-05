#!/usr/bin/env bash
# Publish /var/www/bloodstone/downloads/ (or a single file) to the secondary worker.
set -euo pipefail

WORKER="${BLOODSTONE_POOL_WORKER:-192.119.82.145}"
SSH_USER="${BLOODSTONE_SSH_USER:-root}"
SSH_KEY="${BLOODSTONE_SSH_KEY:-/root/.ssh/bloodstone_copy_key}"
SSH_TIMEOUT="${BLOODSTONE_SSH_TIMEOUT:-20}"
LOCAL_DL="${BLOODSTONE_DOWNLOADS_DIR:-/var/www/bloodstone/downloads}"
REMOTE_DL="/var/www/bloodstone/downloads"

log() { echo "[downloads-sync] $*"; }

ssh_worker() {
  ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout="$SSH_TIMEOUT" \
    -o StrictHostKeyChecking=accept-new "${SSH_USER}@${WORKER}" "$@"
}

if [[ $# -gt 0 ]]; then
  ssh_worker "mkdir -p '$REMOTE_DL'"
  for f in "$@"; do
    [[ -f "$f" ]] || { log "skip missing $f"; continue; }
    base=$(basename "$f")
    log "upload $base"
    rsync -avz \
      -e "ssh -i $SSH_KEY -o BatchMode=yes -o ConnectTimeout=$SSH_TIMEOUT -o StrictHostKeyChecking=accept-new" \
      "$f" "${SSH_USER}@${WORKER}:${REMOTE_DL}/${base}"
    if [[ -f "${f}.sha256" ]]; then
      rsync -avz \
        -e "ssh -i $SSH_KEY -o BatchMode=yes -o ConnectTimeout=$SSH_TIMEOUT -o StrictHostKeyChecking=accept-new" \
        "${f}.sha256" "${SSH_USER}@${WORKER}:${REMOTE_DL}/${base}.sha256"
    fi
  done
else
  log "full sync $LOCAL_DL -> ${WORKER}:${REMOTE_DL}"
  ssh_worker "mkdir -p '$REMOTE_DL'"
  rsync -avz --delete \
    -e "ssh -i $SSH_KEY -o BatchMode=yes -o ConnectTimeout=$SSH_TIMEOUT -o StrictHostKeyChecking=accept-new" \
    "${LOCAL_DL}/" "${SSH_USER}@${WORKER}:${REMOTE_DL}/"
fi

log "done"