#!/usr/bin/env bash
# Promote beta artifacts to the GLOBAL stable baseline (downloads page + LANs with no local validation).
# Per-LAN stable OTA is unlocked when beta testers tap "Approve for this LAN" in the app.
set -euo pipefail

OUT_DL="${BLOODSTONE_DOWNLOADS_DIR:-/var/www/bloodstone/downloads}"

log() { echo "[promote-beta] $*"; }

promote_link() {
  local beta_name="$1"
  local stable_name="$2"
  local beta_path="${OUT_DL}/${beta_name}"
  local stable_path="${OUT_DL}/${stable_name}"

  if [[ ! -L "$beta_path" ]]; then
    log "skip ${stable_name} — beta link missing (${beta_name})"
    return 0
  fi

  local target
  target="$(readlink "$beta_path")"
  [[ -n "$target" ]] || { log "skip ${stable_name} — empty beta target"; return 0; }

  ln -sfn "$target" "$stable_path"
  log "stable ${stable_name} -> ${target}"
}

log "Promoting beta channel to stable in ${OUT_DL}"
promote_link "bloodstone-miner-android-beta.apk" "bloodstone-miner-android-latest.apk"
promote_link "bloodstone-miner-android-web-beta.zip" "bloodstone-miner-android-web-latest.zip"
promote_link "bloodstone-miner-desktop-beta-win64.exe" "bloodstone-miner-desktop-latest-win64.exe"
promote_link "bloodstone-miner-desktop-beta-linux-x86_64.tar.gz" "bloodstone-miner-desktop-latest-linux-x86_64.tar.gz"

if [[ -x /root/sync-bloodstone-downloads-to-worker.sh ]]; then
  /root/sync-bloodstone-downloads-to-worker.sh \
    "${OUT_DL}/bloodstone-miner-android-latest.apk" \
    "${OUT_DL}/bloodstone-miner-android-web-latest.zip" \
    "${OUT_DL}/bloodstone-miner-desktop-latest-win64.exe" \
    "${OUT_DL}/bloodstone-miner-desktop-latest-linux-x86_64.tar.gz" \
    || true
fi

PYTHONPATH="${PYTHONPATH:-}:/root" python3 - <<'PY' 2>/dev/null || true
import bloodstone_downloads as bd
bd.invalidate_download_meta_cache()
PY

if [[ "${BLOODSTONE_GITLAB_AUTO_SUBMIT:-0}" == "1" && -n "${BLOODSTONE_VERSION:-}" && -x /root/submit-bloodstone-gitlab-release.sh ]]; then
  log "GitLab auto-submit enabled for version ${BLOODSTONE_VERSION}"
  /root/submit-bloodstone-gitlab-release.sh "${BLOODSTONE_VERSION}" \
    --notes "Promoted beta to global stable baseline" || \
    log "GitLab submit skipped or failed (non-fatal)"
fi

log "Done — global baseline updated. Each LAN still needs local beta approval for stable OTA."