#!/usr/bin/env bash
# Publish Bloodstone Android miner web UI bundle (HTML/JS/CSS) for live OTA updates.
# Phones with APK 1.3.17+ download this zip — no APK rebuild required for UI changes.
set -euo pipefail

VERSION="${BLOODSTONE_MINER_ANDROID_WEB_VERSION:-}"
SRC_WWW="${BLOODSTONE_ANDROID_WWW:-/root/bloodstone-miner-android/www}"
OUT_DL="${BLOODSTONE_DOWNLOADS_DIR:-/var/www/bloodstone/downloads}"
PUBLIC_ROOT="${BLOODSTONE_PUBLIC_ROOT:-https://bloodstonewallet.mytunnel.org}"
WORKER="${BLOODSTONE_POOL_WORKER:-192.119.82.145}"

log() { echo "[web-bundle] $*"; }

if [[ -z "$VERSION" ]]; then
  VERSION="$(date -u +%Y%m%d.%H%M%S)"
fi

BUNDLE_NAME="bloodstone-miner-android-web-${VERSION}.zip"
TARGET_ZIP="${OUT_DL}/${BUNDLE_NAME}"
if [[ -f "$TARGET_ZIP" && "${BLOODSTONE_WEB_BUNDLE_FORCE:-0}" != "1" ]]; then
  log "refusing to overwrite existing ${BUNDLE_NAME} (set BLOODSTONE_WEB_BUNDLE_FORCE=1 to replace)"
  exit 1
fi
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

[[ -f "${SRC_WWW}/offline-mine.html" ]] || {
  log "missing ${SRC_WWW}/offline-mine.html"
  exit 1
}

log "packaging ${SRC_WWW} -> ${BUNDLE_NAME} (version ${VERSION})"
(
  cd "$SRC_WWW"
  zip -qr "${STAGING}/${BUNDLE_NAME}" . -x '*.DS_Store' -x '__MACOSX/*'
)

mkdir -p "$OUT_DL"
cp -f "${STAGING}/${BUNDLE_NAME}" "${OUT_DL}/${BUNDLE_NAME}"
sha256sum "${OUT_DL}/${BUNDLE_NAME}" | awk '{print $1}' > "${OUT_DL}/${BUNDLE_NAME}.sha256"
CHANNEL="${BLOODSTONE_RELEASE_CHANNEL:-beta}"
if [[ "$CHANNEL" == "stable" ]]; then
  ln -sfn "${BUNDLE_NAME}" "${OUT_DL}/bloodstone-miner-android-web-latest.zip"
  log "stable channel: bloodstone-miner-android-web-latest.zip -> ${BUNDLE_NAME}"
else
  ln -sfn "${BUNDLE_NAME}" "${OUT_DL}/bloodstone-miner-android-web-beta.zip"
  log "beta channel: bloodstone-miner-android-web-beta.zip -> ${BUNDLE_NAME}"
fi

log "published ${OUT_DL}/${BUNDLE_NAME} ($(wc -c < "${OUT_DL}/${BUNDLE_NAME}") bytes)"
log "sha256: $(cat "${OUT_DL}/${BUNDLE_NAME}.sha256")"

export BLOODSTONE_MINER_ANDROID_WEB_VERSION="$VERSION"
export BLOODSTONE_MINER_ANDROID_WEB_BUNDLE="$BUNDLE_NAME"

LOCAL_SHA="$(tr -d '[:space:]' < "${OUT_DL}/${BUNDLE_NAME}.sha256")"

if [[ -x /root/sync-bloodstone-downloads-to-worker.sh ]]; then
  /root/sync-bloodstone-downloads-to-worker.sh \
    "${OUT_DL}/${BUNDLE_NAME}" \
    "${OUT_DL}/${BUNDLE_NAME}.sha256" \
    "${OUT_DL}/bloodstone-miner-android-web-beta.zip" \
    "${OUT_DL}/bloodstone-miner-android-web-latest.zip"
fi

WORKER_SHA=""
if command -v curl >/dev/null 2>&1; then
  WORKER_SHA="$(curl -fsS --max-time 12 "http://${WORKER}:8088/downloads/${BUNDLE_NAME}.sha256" 2>/dev/null | awk '{print $1}' || true)"
fi
if [[ -n "$WORKER_SHA" && "$WORKER_SHA" != "$LOCAL_SHA" ]]; then
  log "ERROR worker sha256 (${WORKER_SHA}) != local (${LOCAL_SHA})"
  exit 1
fi

PYTHONPATH="${PYTHONPATH:-}:/root" python3 - <<'PY' 2>/dev/null || true
try:
    import bloodstone_downloads as bd
    bd.invalidate_download_meta_cache()
except Exception:
    pass
PY

log "manifest will advertise web_bundle_version=${VERSION}"
log "URL: ${PUBLIC_ROOT}/downloads/${BUNDLE_NAME}"