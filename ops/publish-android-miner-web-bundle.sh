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
ln -sfn "${BUNDLE_NAME}" "${OUT_DL}/bloodstone-miner-android-web-latest.zip"

log "published ${OUT_DL}/${BUNDLE_NAME} ($(wc -c < "${OUT_DL}/${BUNDLE_NAME}") bytes)"
log "sha256: $(cat "${OUT_DL}/${BUNDLE_NAME}.sha256")"

export BLOODSTONE_MINER_ANDROID_WEB_VERSION="$VERSION"
export BLOODSTONE_MINER_ANDROID_WEB_BUNDLE="$BUNDLE_NAME"

if [[ -x /root/sync-bloodstone-downloads-to-worker.sh ]]; then
  /root/sync-bloodstone-downloads-to-worker.sh \
    "${OUT_DL}/${BUNDLE_NAME}" \
    "${OUT_DL}/${BUNDLE_NAME}.sha256" \
    "${OUT_DL}/bloodstone-miner-android-web-latest.zip" || true
fi

log "manifest will advertise web_bundle_version=${VERSION}"
log "URL: ${PUBLIC_ROOT}/downloads/${BUNDLE_NAME}"