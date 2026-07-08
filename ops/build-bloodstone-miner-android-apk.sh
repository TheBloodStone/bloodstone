#!/usr/bin/env bash
# Build and publish a sideload Bloodstone Android miner APK.
set -euo pipefail

VERSION="${BLOODSTONE_MINER_ANDROID_VERSION:-1.3.76}"
OUT_DL="${BLOODSTONE_DOWNLOADS_DIR:-/var/www/bloodstone/downloads}"
APK_NAME="bloodstone-miner-android-${VERSION}.apk"
SRC="/root/bloodstone-miner-android"
PUBLIC_ROOT="${BLOODSTONE_PUBLIC_ROOT:-https://bloodstonewallet.mytunnel.org}"
ANDROID_SDK="${ANDROID_SDK_ROOT:-/opt/android-sdk}"
KEYSTORE="${BLOODSTONE_ANDROID_KEYSTORE:-/root/.bloodstone/android-release.keystore}"
KEYSTORE_PASS="${BLOODSTONE_ANDROID_KEYSTORE_PASS:-bloodstone-miner}"
KEY_ALIAS="${BLOODSTONE_ANDROID_KEY_ALIAS:-bloodstone-miner}"

export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
export ANDROID_SDK_ROOT="$ANDROID_SDK"
export PATH="$JAVA_HOME/bin:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$ANDROID_SDK_ROOT/platform-tools:$PATH"

MINER_WEB="/root/bloodstone-miner-web"
MINING_STATIC="${BLOODSTONE_MINING_STATIC:-/var/www/bloodstone/mining-static}"

log() { echo "[bloodstone-apk] $*" >&2; }

sync_web_assets() {
  log "Syncing miner web static assets into Capacitor www (preserving Android-only files) ..."
  mkdir -p "${SRC}/www/static"
  local preserve_dir
  preserve_dir=$(mktemp -d)
  # Portal static must not overwrite Android-only UI (on-device wallet panel, offline shell).
  for rel in \
    offline-mine.html \
    static/js/local-wallet.js \
    static/js/local-node.js \
    static/js/network-nodes.js \
    static/js/power-guard.js \
    static/js/web-miner.js \
    static/js/stratum-transport.js \
    static/js/bridge-warmup-boot.js \
    static/js/chain-sync-boot.js \
    static/js/android-ota-boot.js \
    static/js/app-update.js \
    static/js/node-diagnostics.js \
    static/js/node-diagnostics-track.js \
    static/js/node-diagnostics-boot.js \
    static/js/pull-refresh-boot.js \
    static/js/mesh-chain-restore.js \
    static/js/mesh-share-internet.js \
    static/js/mesh-gateway-lan.js \
    static/js/mesh-lan-internet-client.js \
    static/js/mesh-internet-gateway.js \
    static/js/miner-start-boot.js \
    static/js/miner-log-boot.js \
    static/js/web-miner-loader.js \
    static/js/safeguard-bypass.js \
    static/js/miner-paths.js \
    static/js/thermal-guard.js \
    static/js/device-network-info.js \
    static/js/mining-setup-instructions.js \
    static/js/mining-math.js \
    static/js/web-miner-worker.js \
    static/css/miner.css; do
    if [[ -f "${SRC}/www/${rel}" ]]; then
      mkdir -p "$(dirname "${preserve_dir}/${rel}")"
      cp -f "${SRC}/www/${rel}" "${preserve_dir}/${rel}"
    fi
  done
  rsync -a \
    "${MINER_WEB}/static/" \
    "${SRC}/www/static/"
  for rel in \
    offline-mine.html \
    static/js/local-wallet.js \
    static/js/local-node.js \
    static/js/network-nodes.js \
    static/js/power-guard.js \
    static/js/web-miner.js \
    static/js/stratum-transport.js \
    static/js/bridge-warmup-boot.js \
    static/js/chain-sync-boot.js \
    static/js/android-ota-boot.js \
    static/js/app-update.js \
    static/js/node-diagnostics.js \
    static/js/node-diagnostics-track.js \
    static/js/node-diagnostics-boot.js \
    static/js/pull-refresh-boot.js \
    static/js/mesh-chain-restore.js \
    static/js/mesh-share-internet.js \
    static/js/mesh-gateway-lan.js \
    static/js/mesh-lan-internet-client.js \
    static/js/mesh-internet-gateway.js \
    static/js/miner-start-boot.js \
    static/js/miner-log-boot.js \
    static/js/web-miner-loader.js \
    static/js/safeguard-bypass.js \
    static/js/miner-paths.js \
    static/js/thermal-guard.js \
    static/js/device-network-info.js \
    static/js/mining-setup-instructions.js \
    static/js/mining-math.js \
    static/js/web-miner-worker.js \
    static/css/miner.css; do
    if [[ -f "${preserve_dir}/${rel}" ]]; then
      cp -f "${preserve_dir}/${rel}" "${SRC}/www/${rel}"
    fi
  done
  rm -rf "$preserve_dir"
  # Stamp bundled version so update UI never shows "0" before native bridge is ready.
  if [[ -f "${SRC}/www/offline-mine.html" ]]; then
    sed -i "s/data-app-version=\"[^\"]*\"/data-app-version=\"${VERSION}\"/" \
      "${SRC}/www/offline-mine.html" || true
    if ! grep -q 'data-app-version=' "${SRC}/www/offline-mine.html"; then
      sed -i "s/data-android-app=\"1\"/data-android-app=\"1\" data-app-version=\"${VERSION}\"/" \
        "${SRC}/www/offline-mine.html"
    fi
  fi
  if [[ -d "$MINING_STATIC" ]]; then
    log "Publishing static assets to ${MINING_STATIC} ..."
    rsync -a --delete \
      "${MINER_WEB}/static/" \
      "${MINING_STATIC}/"
  fi
}

ensure_android_sdk() {
  if [[ -x "$ANDROID_SDK/platform-tools/adb" && -d "$ANDROID_SDK/platforms/android-34" ]]; then
    return 0
  fi
  log "Installing Android SDK to $ANDROID_SDK ..."
  mkdir -p "$ANDROID_SDK/cmdline-tools"
  if [[ ! -f /tmp/commandlinetools-linux.zip ]]; then
    wget -q -O /tmp/commandlinetools-linux.zip \
      "https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip"
  fi
  rm -rf /tmp/android-cmdline-tools
  unzip -qo /tmp/commandlinetools-linux.zip -d /tmp/android-cmdline-tools
  rm -rf "$ANDROID_SDK/cmdline-tools/latest"
  mv /tmp/android-cmdline-tools/cmdline-tools "$ANDROID_SDK/cmdline-tools/latest"
  yes | sdkmanager --licenses >/dev/null 2>&1 || true
  sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0"
}

ensure_keystore() {
  mkdir -p "$(dirname "$KEYSTORE")"
  if [[ ! -f "$KEYSTORE" ]]; then
    log "Creating release keystore at $KEYSTORE"
    keytool -genkeypair -v \
      -keystore "$KEYSTORE" \
      -alias "$KEY_ALIAS" \
      -keyalg RSA -keysize 2048 -validity 10000 \
      -storepass "$KEYSTORE_PASS" -keypass "$KEYSTORE_PASS" \
      -dname "CN=Bloodstone Miner, OU=Mobile, O=Bloodstone, L=Network, ST=NA, C=US"
  fi
}

patch_android_project() {
  local manifest="$SRC/android/app/src/main/AndroidManifest.xml"
  local gradle="$SRC/android/app/build.gradle"
  local netdir="$SRC/android/app/src/main/res/xml"
  mkdir -p "$netdir"
  cp -f "$SRC/android-res/network_security_config.xml" "$netdir/network_security_config.xml"
  if ! grep -q 'usesCleartextTraffic' "$manifest"; then
    sed -i 's/<application/<application android:usesCleartextTraffic="true" android:networkSecurityConfig="@xml\/network_security_config"/' "$manifest"
  fi
  cat > "$SRC/android/keystore.properties" <<EOF
storeFile=${KEYSTORE}
storePassword=${KEYSTORE_PASS}
keyAlias=${KEY_ALIAS}
keyPassword=${KEYSTORE_PASS}
EOF
  local version_code
  version_code=$(echo "$VERSION" | awk -F. '{print $3}')
  sed -i "s/versionCode [0-9]\\+/versionCode ${version_code}/" "$gradle"
  sed -i "s/versionName \"[^\"]*\"/versionName \"${VERSION}\"/" "$gradle"
}

prepare_capacitor_project() {
  cd "$SRC"
  # Bundled UI is default (server.startPath in capacitor.config.json).
  # Set BLOODSTONE_CAPACITOR_REMOTE_UI=1 to inject a live portal URL for dev builds.
  if [[ "${BLOODSTONE_CAPACITOR_REMOTE_UI:-0}" == "1" && -f "$SRC/capacitor.config.json" ]]; then
    python3 - <<'PY' "$SRC/capacitor.config.json" "${PUBLIC_ROOT%/}/mining/mine?app=android"
import json, sys
path, url = sys.argv[1], sys.argv[2]
with open(path) as f:
    cfg = json.load(f)
cfg.setdefault("server", {})["url"] = url
cfg["server"].pop("startPath", None)
with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
    f.write("\n")
PY
  fi
  if [[ ! -d node_modules ]]; then
    log "npm install ..."
    npm install --no-audit --no-fund
  fi
  if [[ ! -d android ]]; then
    log "npx cap add android ..."
    npx cap add android
  fi
  npx cap sync android
  patch_android_project
}

build_apk() {
  cd "$SRC/android"
  chmod +x gradlew
  export GRADLE_OPTS="${GRADLE_OPTS:--Xmx768m}"
  local built=""
  if ./gradlew clean assembleRelease --no-daemon \
    -x lint -x lintVitalAnalyzeRelease -x lintVitalReportRelease -x lintVitalRelease; then
    built=$(find app/build/outputs/apk/release -name '*.apk' | head -1)
  fi
  if [[ -z "$built" || ! -f "$built" ]]; then
    log "Release build unavailable; building debug APK for sideload"
    ./gradlew assembleDebug --no-daemon \
      -x lint -x lintVitalAnalyzeRelease -x lintVitalReportRelease -x lintVitalRelease
    built=$(find app/build/outputs/apk/debug -name '*.apk' | head -1)
  fi
  [[ -n "$built" && -f "$built" ]] || { log "No APK produced"; exit 1; }
  mkdir -p "$OUT_DL"
  cp -f "$built" "${OUT_DL}/${APK_NAME}"
  sha256sum "${OUT_DL}/${APK_NAME}" | tee "${OUT_DL}/${APK_NAME}.sha256" >/dev/null
  CHANNEL="${BLOODSTONE_RELEASE_CHANNEL:-beta}"
  if [[ "$CHANNEL" == "stable" ]]; then
    ln -sfn "${APK_NAME}" "${OUT_DL}/bloodstone-miner-android-latest.apk"
    log "stable channel: bloodstone-miner-android-latest.apk -> ${APK_NAME}"
  else
    ln -sfn "${APK_NAME}" "${OUT_DL}/bloodstone-miner-android-beta.apk"
    log "beta channel: bloodstone-miner-android-beta.apk -> ${APK_NAME}"
  fi
  ls -lh "${OUT_DL}/${APK_NAME}" "${OUT_DL}/bloodstone-miner-android-beta.apk" 2>/dev/null \
    || ls -lh "${OUT_DL}/${APK_NAME}" "${OUT_DL}/bloodstone-miner-android-latest.apk"
  log "Published ${OUT_DL}/${APK_NAME}"
  publish_mesh_apk
  update_downloads_page
  if [[ -x /root/sync-bloodstone-downloads-to-worker.sh ]]; then
    /root/sync-bloodstone-downloads-to-worker.sh \
      "${OUT_DL}/${APK_NAME}" \
      "${OUT_DL}/${APK_NAME}.sha256" \
      "${OUT_DL}/bloodstone-miner-android-beta.apk" \
      "${OUT_DL}/bloodstone-miner-android-latest.apk" \
      "${OUT_DL}/index.html" || true
  fi
  if [[ -x /root/offload-bloodstone-downloads.sh ]]; then
    KEEP_ANDROID_APKS="${KEEP_ANDROID_APKS:-3}" /root/offload-bloodstone-downloads.sh || true
  fi
}

publish_mesh_apk() {
  local apk_path="${OUT_DL}/${APK_NAME}"
  [[ -f "$apk_path" ]] || return 0
  if [[ "${BLOODSTONE_SKIP_MESH_APK_PUBLISH:-0}" == "1" ]]; then
    log "Skipping chain mesh APK publish (BLOODSTONE_SKIP_MESH_APK_PUBLISH=1)"
    return 0
  fi
  log "Publishing ${APK_NAME} to chain mesh (BSM1 anchor) ..."
  if python3 /root/chain-mesh-publish-asset.py "$apk_path" \
    --key "downloads/${APK_NAME}" \
    --name "Bloodstone miner Android ${VERSION}" \
    --version "${VERSION}" \
    --mime "application/vnd.android.package-archive" \
    --pretty; then
    log "Mesh asset published: downloads/${APK_NAME}"
  else
    log "chain mesh APK publish failed (non-fatal)"
  fi
}

update_downloads_page() {
  local notes="${BLOODSTONE_ANDROID_RELEASE_NOTES:-APK ${VERSION}: chain bootstrap on first full sync; bridge warmup; node diagnostics; pull-to-refresh}"
  local prev=""
  if [[ -f "${OUT_DL}/index.html" ]]; then
    prev=$(grep -oP 'bloodstone-miner-android-\K[0-9]+\.[0-9]+\.[0-9]+(?=\.apk</a> · <a href="bloodstone-miner-android-latest)' \
      "${OUT_DL}/index.html" 2>/dev/null | head -1 || true)
  fi
  if [[ -x /root/update-bloodstone-downloads-android.py ]]; then
    log "Updating downloads index for Android ${VERSION} ..."
    python3 /root/update-bloodstone-downloads-android.py \
      --version "${VERSION}" \
      --notes "${notes}" \
      ${prev:+--prev-version "${prev}"} \
      --deploy || log "downloads index update failed (non-fatal)"
  else
    cp -f /root/bloodstone-downloads-index.html "${OUT_DL}/index.html" 2>/dev/null || true
  fi
}

sync_bloodstoned_jni_libs() {
  local abi asset jni
  for abi in arm64-v8a armeabi-v7a; do
    asset="${SRC}/plugins/bloodstone-local-node/android/src/main/assets/bloodstoned/${abi}"
    jni="${SRC}/plugins/bloodstone-local-node/android/src/main/jniLibs/${abi}"
    mkdir -p "$jni"
    if [[ -f "${asset}/bloodstoned" ]]; then
      cp -f "${asset}/bloodstoned" "${jni}/libbloodstoned_node.so"
      chmod 755 "${jni}/libbloodstoned_node.so"
    fi
    if [[ -f "${asset}/libc++_shared.so" ]]; then
      cp -f "${asset}/libc++_shared.so" "${jni}/libc++_shared.so"
    fi
  done
}

verify_bloodstoned_assets() {
  local abi bin jni size
  sync_bloodstoned_jni_libs
  for abi in arm64-v8a armeabi-v7a; do
    bin="${SRC}/plugins/bloodstone-local-node/android/src/main/assets/bloodstoned/${abi}/bloodstoned"
    jni="${SRC}/plugins/bloodstone-local-node/android/src/main/jniLibs/${abi}/libbloodstoned_node.so"
    if [[ ! -f "$bin" ]]; then
      log "FATAL: missing ${bin} — run /root/build-bloodstoned-arm64.sh android ${abi}"
      exit 1
    fi
    if [[ ! -f "$jni" ]]; then
      log "FATAL: missing ${jni} — run sync_bloodstoned_jni_libs"
      exit 1
    fi
    size=$(stat -c%s "$bin" 2>/dev/null || stat -f%z "$bin")
    if [[ "$size" -lt 8000000 ]]; then
      log "FATAL: bloodstoned ${abi} binary too small (${size} bytes)"
      exit 1
    fi
    log "bloodstoned ${abi} OK ($(du -h "$bin" | awk '{print $1}'))"
    log "bloodstoned jniLibs ${abi} OK ($(du -h "$jni" | awk '{print $1}'))"
  done
}

ensure_android_sdk
ensure_keystore
verify_bloodstoned_assets
sync_web_assets
if [[ "${BLOODSTONE_PUBLISH_WEB_BUNDLE:-0}" == "1" && -x /root/publish-android-miner-web-bundle.sh ]]; then
  if [[ -z "${BLOODSTONE_MINER_ANDROID_WEB_VERSION:-}" ]]; then
    log "BLOODSTONE_PUBLISH_WEB_BUNDLE=1 requires BLOODSTONE_MINER_ANDROID_WEB_VERSION — skipping web bundle publish"
  else
    /root/publish-android-miner-web-bundle.sh || log "web bundle publish failed (non-fatal)"
  fi
fi
prepare_capacitor_project
build_apk