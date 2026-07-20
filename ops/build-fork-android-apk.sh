#!/usr/bin/env bash
# Build a rebranded fork full-node APK (separate package from Bloodstone).
# Usage:
#   FORK_TICKER=LRGK FORK_ID=e9d304f3379e96859acd131f \
#   FORK_ICON=/root/fork-brands/lrgk/LRGK.png \
#   ./build-fork-android-apk.sh
set -euo pipefail

FORK_TICKER="${FORK_TICKER:-LRGK}"
FORK_NAME="${FORK_NAME:-$FORK_TICKER}"
FORK_ID="${FORK_ID:-e9d304f3379e96859acd131f}"
FORK_WEBSITE="${FORK_WEBSITE:-https://buylrgk.com}"
FORK_ICON="${FORK_ICON:-/root/fork-brands/lrgk/LRGK.png}"
FORK_VERSION="${FORK_VERSION:-1.0.0}"
# Separate applicationId so it installs beside Bloodstone Miner
FORK_APP_ID="${FORK_APP_ID:-org.lrgk.fullnode}"
FORK_APP_LABEL="${FORK_APP_LABEL:-LRGK Full Node}"
PUBLIC_ROOT="${BLOODSTONE_PUBLIC_ROOT:-https://bloodstonewallet.mytunnel.org}"
PUBLIC_HOST="${BLOODSTONE_PUBLIC_HOST:-bloodstonewallet.mytunnel.org}"
SRC_BASE="/root/bloodstone-miner-android"
STAGE_ROOT="${FORK_APK_STAGE:-/root/fork-apk-builds}"
STAGE="${STAGE_ROOT}/${FORK_TICKER,,}-android"
OUT_DL="${BLOODSTONE_DOWNLOADS_DIR:-/var/www/bloodstone/downloads}"
APK_NAME="${FORK_TICKER,,}-full-node-android-${FORK_VERSION}.apk"
APK_LATEST="${FORK_TICKER,,}-full-node-android-latest.apk"
ANDROID_SDK="${ANDROID_SDK_ROOT:-/opt/android-sdk}"
KEYSTORE="${BLOODSTONE_ANDROID_KEYSTORE:-/root/.bloodstone/android-release.keystore}"
KEYSTORE_PASS="${BLOODSTONE_ANDROID_KEYSTORE_PASS:-bloodstone-miner}"
KEY_ALIAS="${BLOODSTONE_ANDROID_KEY_ALIAS:-bloodstone-miner}"

export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
export ANDROID_SDK_ROOT="$ANDROID_SDK"
export PATH="$JAVA_HOME/bin:$ANDROID_SDK_ROOT/cmdline-tools/latest/bin:$ANDROID_SDK_ROOT/platform-tools:$PATH"

log() { echo "[fork-apk:${FORK_TICKER}] $*" >&2; }

ticker_lower="${FORK_TICKER,,}"
ticker_upper="${FORK_TICKER^^}"

require_icon() {
  if [[ ! -f "$FORK_ICON" ]]; then
    log "FATAL: FORK_ICON not found: $FORK_ICON"
    exit 1
  fi
}

stage_tree() {
  log "Staging project at $STAGE ..."
  mkdir -p "$STAGE_ROOT"
  rm -rf "$STAGE"
  mkdir -p "$STAGE"
  # Copy sources; reuse node_modules + heavy plugin/native binaries via hardlink/rsync
  rsync -a \
    --exclude 'node_modules' \
    --exclude 'android/app/build' \
    --exclude 'android/.gradle' \
    --exclude 'android/build' \
    --exclude 'android/capacitor-cordova-android-plugins/build' \
    --exclude 'plugins/*/android/build' \
    --exclude 'plugins/*/android/.gradle' \
    --exclude 'plugins/*/node_modules' \
    "$SRC_BASE/" "$STAGE/"
  # Shared node_modules (read-only enough for gradle/cap)
  if [[ -d "$SRC_BASE/node_modules" ]]; then
    ln -sfn "$SRC_BASE/node_modules" "$STAGE/node_modules"
  fi
  # Link plugin android build caches not needed; ensure bloodstoned binaries present
  for abi in arm64-v8a armeabi-v7a; do
    src_bin="$SRC_BASE/plugins/bloodstone-local-node/android/src/main/assets/bloodstoned/${abi}/bloodstoned"
    dst_bin="$STAGE/plugins/bloodstone-local-node/android/src/main/assets/bloodstoned/${abi}/bloodstoned"
    if [[ -f "$src_bin" && ! -f "$dst_bin" ]]; then
      mkdir -p "$(dirname "$dst_bin")"
      cp -a "$src_bin" "$dst_bin"
    fi
    # jniLibs
    src_jni="$SRC_BASE/plugins/bloodstone-local-node/android/src/main/jniLibs/${abi}"
    dst_jni="$STAGE/plugins/bloodstone-local-node/android/src/main/jniLibs/${abi}"
    if [[ -d "$src_jni" ]]; then
      mkdir -p "$dst_jni"
      rsync -a "$src_jni/" "$dst_jni/"
    fi
  done
}

generate_icons() {
  log "Generating mipmap / splash from $FORK_ICON ..."
  python3 - <<'PY' "$FORK_ICON" "$STAGE/android/app/src/main/res" "$STAGE/www/static/img"
import sys
from pathlib import Path
from PIL import Image

src = Path(sys.argv[1])
res = Path(sys.argv[2])
web = Path(sys.argv[3])
web.mkdir(parents=True, exist_ok=True)

img = Image.open(src).convert("RGBA")
# Square cover-center for icon safe zone
def fit_square(im, size, pad_ratio=0.12):
    canvas = Image.new("RGBA", (size, size), (13, 15, 20, 255))  # dark bg
    # letterbox logo inside safe area
    inner = int(size * (1 - 2 * pad_ratio))
    logo = im.copy()
    logo.thumbnail((inner, inner), Image.LANCZOS)
    x = (size - logo.width) // 2
    y = (size - logo.height) // 2
    canvas.paste(logo, (x, y), logo)
    return canvas

def fit_fill(im, size):
    # Full-bleed icon (also used as foreground)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    logo = im.copy()
    logo.thumbnail((size, size), Image.LANCZOS)
    # scale up slightly if smaller
    if logo.width < size or logo.height < size:
        logo = logo.resize((size, size), Image.LANCZOS)
    # center-crop if not square after
    if logo.size != (size, size):
        logo = logo.resize((size, size), Image.LANCZOS)
    canvas.paste(logo, (0, 0), logo)
    return canvas

densities = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}
for folder, size in densities.items():
    d = res / folder
    d.mkdir(parents=True, exist_ok=True)
    base = fit_square(img, size)
    base.save(d / "ic_launcher.png", "PNG")
    base.save(d / "ic_launcher_round.png", "PNG")
    # Adaptive foreground: logo only on transparent
    fg = fit_fill(img, size)
    # Make slightly smaller for adaptive safe zone
    fg2 = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    logo = img.copy()
    logo.thumbnail((int(size * 0.72), int(size * 0.72)), Image.LANCZOS)
    x = (size - logo.width) // 2
    y = (size - logo.height) // 2
    fg2.paste(logo, (x, y), logo)
    fg2.save(d / "ic_launcher_foreground.png", "PNG")

# Splash / drawable
for folder, size in {
    "drawable": 480,
    "drawable-port-mdpi": 320,
    "drawable-port-hdpi": 480,
    "drawable-port-xhdpi": 720,
    "drawable-port-xxhdpi": 1080,
    "drawable-port-xxxhdpi": 1440,
    "drawable-land-mdpi": 320,
    "drawable-land-hdpi": 480,
    "drawable-land-xhdpi": 720,
    "drawable-land-xxhdpi": 1080,
    "drawable-land-xxxhdpi": 1440,
}.items():
    d = res / folder
    d.mkdir(parents=True, exist_ok=True)
    # portrait-ish splash with dark bg + centered logo
    w = size if "land" not in folder else int(size * 1.6)
    h = int(size * 1.6) if "land" not in folder else size
    if folder == "drawable":
        w = h = size
    splash = Image.new("RGBA", (w, h), (13, 15, 20, 255))
    logo = img.copy()
    logo.thumbnail((min(w, h) // 2, min(w, h) // 2), Image.LANCZOS)
    splash.paste(logo, ((w - logo.width) // 2, (h - logo.height) // 2), logo)
    splash.save(d / "splash.png", "PNG")

# Web assets
fit_square(img, 192).save(web / "lrgk-icon-192.png", "PNG")
fit_square(img, 512).save(web / "lrgk-icon-512.png", "PNG")
img.resize((256, 256), Image.LANCZOS).save(web / "lrgk-logo.png", "PNG")
print("icons ok")
PY
  # Adaptive icon background color (dark)
  mkdir -p "$STAGE/android/app/src/main/res/values"
  if [[ -f "$STAGE/android/app/src/main/res/values/ic_launcher_background.xml" ]]; then
    sed -i 's/>#[0-9A-Fa-f]\{6,8\}</>#0d0f14</' \
      "$STAGE/android/app/src/main/res/values/ic_launcher_background.xml" 2>/dev/null || true
  else
    cat > "$STAGE/android/app/src/main/res/values/ic_launcher_background.xml" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <color name="ic_launcher_background">#0d0f14</color>
</resources>
XML
  fi
}

rebrand_files() {
  log "Rebranding package id, labels, UI copy ..."
  local gradle="$STAGE/android/app/build.gradle"
  local strings="$STAGE/android/app/src/main/res/values/strings.xml"
  local cap="$STAGE/capacitor.config.json"
  local html="$STAGE/www/offline-mine.html"
  local version_code
  version_code=$(echo "$FORK_VERSION" | awk -F. '{print ($1*10000)+($2*100)+$3}')

  # applicationId separate from Bloodstone; keep Java namespace for plugins
  sed -i "s/applicationId \"org.bloodstone.miner\"/applicationId \"${FORK_APP_ID}\"/" "$gradle"
  sed -i "s/versionCode [0-9]\\+/versionCode ${version_code}/" "$gradle"
  sed -i "s/versionName \"[^\"]*\"/versionName \"${FORK_VERSION}\"/" "$gradle"

  cat > "$strings" <<EOF
<?xml version='1.0' encoding='utf-8'?>
<resources>
    <string name="app_name">${FORK_APP_LABEL}</string>
    <string name="title_activity_main">${FORK_APP_LABEL}</string>
    <string name="package_name">${FORK_APP_ID}</string>
    <string name="custom_url_scheme">${FORK_APP_ID}</string>
</resources>
EOF

  python3 - <<PY
import json
from pathlib import Path
cap = Path("$cap")
cfg = json.loads(cap.read_text())
cfg["appId"] = "$FORK_APP_ID"
cfg["appName"] = "$FORK_APP_LABEL"
cfg.setdefault("server", {})
cfg["server"]["startPath"] = "offline-mine.html"
cfg["server"]["androidScheme"] = "https"
cfg["server"]["cleartext"] = True
allow = cfg["server"].setdefault("allowNavigation", [])
for host in [
    "$PUBLIC_HOST",
    "*.mytunnel.org",
    "buylrgk.com",
    "www.buylrgk.com",
    "localhost",
    "127.0.0.1",
]:
    if host not in allow:
        allow.append(host)
cap.write_text(json.dumps(cfg, indent=2) + "\n")
print("capacitor ok", cfg["appId"], cfg["appName"])
PY

  # Embed fork profile + rebrand visible strings in offline shell
  python3 - <<'PY' "$html" "$FORK_TICKER" "$FORK_NAME" "$FORK_ID" "$FORK_WEBSITE" "$PUBLIC_ROOT" "$FORK_VERSION" "$FORK_APP_LABEL"
import re, sys, json
from pathlib import Path
html_path, ticker, name, fork_id, website, public_root, version, app_label = sys.argv[1:9]
text = Path(html_path).read_text(encoding="utf-8", errors="replace")
# Title / headers
text = text.replace("Bloodstone Offline Miner", f"{ticker} Full Node")
text = text.replace("Bloodstone Fleet Miner", f"{app_label}")
text = text.replace(">Bloodstone Fleet Miner<", f">{app_label}<")
# Payout / coin labels (visible UI)
text = re.sub(r"\bSTONE payout address\b", f"{ticker} payout address", text)
text = re.sub(r"\bSend STONE\b", f"Send {ticker}", text)
text = re.sub(r"Amount \(STONE\)", f"Amount ({ticker})", text)
text = re.sub(r"your STONE address", f"your {ticker} address", text)
text = re.sub(r"mined STONE", f"mined {ticker}", text)
text = re.sub(r"Paste Bloodstone WIF", f"Paste {ticker} WIF", text)
# data attributes on body
def set_data(attr, value):
    global text
    if re.search(rf'data-{attr}="[^"]*"', text):
        text = re.sub(rf'data-{attr}="[^"]*"', f'data-{attr}="{value}"', text, count=1)
    else:
        text = text.replace('data-android-app="1"', f'data-android-app="1" data-{attr}="{value}"', 1)

set_data("app-version", version)
set_data("public-root", public_root)
set_data("update-base", public_root)
set_data("fork-ticker", ticker)
set_data("fork-name", name)
set_data("fork-id", fork_id)
set_data("fork-website", website)
set_data("fork-profile-url", f"{public_root}/api/fork-lab/coins/{fork_id}/mobile-profile")
set_data("coin-ticker", ticker)

# Favicon / logo in head if present
if "rel=\"icon\"" not in text:
    text = text.replace(
        "</title>",
        f'</title>\n  <link rel="icon" href="static/img/lrgk-logo.png">\n  <link rel="apple-touch-icon" href="static/img/lrgk-icon-192.png">',
        1,
    )
else:
    text = re.sub(
        r'<link rel="icon"[^>]*>',
        '<link rel="icon" href="static/img/lrgk-logo.png">',
        text,
        count=1,
    )

# Inject fork boot config once
boot = f"""
<script>
window.__FORK_EDGE_PROFILE_URL = {json.dumps(public_root + '/api/fork-lab/coins/' + fork_id + '/mobile-profile')};
window.__FORK_META = {json.dumps({
  "ticker": ticker,
  "name": name,
  "fork_id": fork_id,
  "website": website,
  "app_label": app_label,
  "apk": "dedicated",
  "parent_note": "This APK is branded for " + ticker + " (separate from Bloodstone Miner).",
})};
document.addEventListener("DOMContentLoaded", function () {{
  try {{
    var h = document.querySelector("h1");
    if (h) h.textContent = {json.dumps(app_label)};
    document.title = {json.dumps(ticker + " Full Node")};
  }} catch (e) {{}}
}});
</script>
"""
if "__FORK_EDGE_PROFILE_URL" not in text:
    text = text.replace("</head>", boot + "\n</head>", 1)

Path(html_path).write_text(text, encoding="utf-8")
print("html rebrand ok")
PY

  # Default edge profile JSON shipped in assets for offline import
  mkdir -p "$STAGE/www/static/fork"
  curl -sk --max-time 20 \
    "${PUBLIC_ROOT}/api/fork-lab/coins/${FORK_ID}/mobile-profile" \
    -o "$STAGE/www/static/fork/edge-profile.json" || true
  # Local branding manifest
  python3 - <<PY
import json
from pathlib import Path
Path("$STAGE/www/static/fork/branding.json").write_text(json.dumps({
  "ticker": "$ticker_upper",
  "name": "$FORK_NAME",
  "fork_id": "$FORK_ID",
  "website": "$FORK_WEBSITE",
  "app_id": "$FORK_APP_ID",
  "app_label": "$FORK_APP_LABEL",
  "version": "$FORK_VERSION",
  "icon": "static/img/lrgk-logo.png",
  "separate_from_bloodstone": True,
}, indent=2) + "\n")
PY

  # Keystore props for this stage
  cat > "$STAGE/android/keystore.properties" <<EOF
storeFile=${KEYSTORE}
storePassword=${KEYSTORE_PASS}
keyAlias=${KEY_ALIAS}
keyPassword=${KEYSTORE_PASS}
EOF

  # Network security (cleartext LAN for local node)
  mkdir -p "$STAGE/android/app/src/main/res/xml"
  if [[ -f "$STAGE/android-res/network_security_config.xml" ]]; then
    cp -f "$STAGE/android-res/network_security_config.xml" \
      "$STAGE/android/app/src/main/res/xml/network_security_config.xml"
  fi
}

sync_cap_and_build() {
  cd "$STAGE"
  if [[ ! -d node_modules ]]; then
    log "npm install ..."
    npm install --no-audit --no-fund
  fi
  log "npx cap sync android ..."
  npx cap sync android
  # Re-apply applicationId after cap sync (can rewrite gradle)
  sed -i "s/applicationId \"org.bloodstone.miner\"/applicationId \"${FORK_APP_ID}\"/" \
    "$STAGE/android/app/build.gradle" || true
  if ! grep -q "applicationId \"${FORK_APP_ID}\"" "$STAGE/android/app/build.gradle"; then
    sed -i "s/applicationId \"[^\"]*\"/applicationId \"${FORK_APP_ID}\"/" \
      "$STAGE/android/app/build.gradle"
  fi
  # Restore rebranded strings if cap overwrote
  cat > "$STAGE/android/app/src/main/res/values/strings.xml" <<EOF
<?xml version='1.0' encoding='utf-8'?>
<resources>
    <string name="app_name">${FORK_APP_LABEL}</string>
    <string name="title_activity_main">${FORK_APP_LABEL}</string>
    <string name="package_name">${FORK_APP_ID}</string>
    <string name="custom_url_scheme">${FORK_APP_ID}</string>
</resources>
EOF
  # Re-apply icons after cap sync
  generate_icons

  cd "$STAGE/android"
  chmod +x gradlew
  export GRADLE_OPTS="${GRADLE_OPTS:--Xmx768m}"
  log "assembleRelease ..."
  local built=""
  if ./gradlew clean assembleRelease --no-daemon \
    -x lint -x lintVitalAnalyzeRelease -x lintVitalReportRelease -x lintVitalRelease; then
    built=$(find app/build/outputs/apk/release -name '*.apk' | head -1)
  fi
  if [[ -z "${built:-}" || ! -f "$built" ]]; then
    log "Release failed; trying debug APK"
    ./gradlew assembleDebug --no-daemon \
      -x lint -x lintVitalAnalyzeRelease -x lintVitalReportRelease -x lintVitalRelease
    built=$(find app/build/outputs/apk/debug -name '*.apk' | head -1)
  fi
  [[ -n "$built" && -f "$built" ]] || { log "No APK produced"; exit 1; }

  mkdir -p "$OUT_DL" "$OUT_DL/fork-icons"
  cp -f "$built" "${OUT_DL}/${APK_NAME}"
  sha256sum "${OUT_DL}/${APK_NAME}" | tee "${OUT_DL}/${APK_NAME}.sha256" >/dev/null
  ln -sfn "${APK_NAME}" "${OUT_DL}/${APK_LATEST}"
  # Brand icon for downloads / fork lab
  cp -f "$FORK_ICON" "${OUT_DL}/fork-icons/${ticker_lower}.png"
  cp -f "$FORK_ICON" "${OUT_DL}/fork-icons/${ticker_lower}-icon.png"
  # Convenience copy without version
  ln -sfn "fork-icons/${ticker_lower}.png" "${OUT_DL}/${ticker_lower}-icon.png" 2>/dev/null || \
    cp -f "$FORK_ICON" "${OUT_DL}/${ticker_lower}-icon.png"

  # Write sideload meta for portal
  python3 - <<PY
import json, hashlib, os, time
from pathlib import Path
apk = Path("${OUT_DL}/${APK_NAME}")
h = hashlib.sha256(apk.read_bytes()).hexdigest()
meta = {
  "ok": True,
  "ticker": "$ticker_upper",
  "name": "$FORK_NAME",
  "fork_id": "$FORK_ID",
  "app_id": "$FORK_APP_ID",
  "app_label": "$FORK_APP_LABEL",
  "version": "$FORK_VERSION",
  "filename": "$APK_NAME",
  "latest": "$APK_LATEST",
  "url": "${PUBLIC_ROOT}/downloads/${APK_NAME}",
  "latest_url": "${PUBLIC_ROOT}/downloads/${APK_LATEST}",
  "icon_url": "${PUBLIC_ROOT}/downloads/fork-icons/${ticker_lower}.png",
  "website": "$FORK_WEBSITE",
  "sha256": h,
  "size_bytes": apk.stat().st_size,
  "separate_from_bloodstone": True,
  "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
  "install_note": "Installs as ${FORK_APP_LABEL} (package ${FORK_APP_ID}) — does NOT replace Bloodstone Miner.",
}
Path("${OUT_DL}/${ticker_lower}-full-node-android-manifest.json").write_text(
  json.dumps(meta, indent=2) + "\n"
)
print(json.dumps(meta, indent=2))
PY

  log "Published ${OUT_DL}/${APK_NAME}"
  ls -lh "${OUT_DL}/${APK_NAME}" "${OUT_DL}/${APK_LATEST}" "${OUT_DL}/fork-icons/${ticker_lower}.png"

  if [[ -x /root/sync-bloodstone-downloads-to-worker.sh ]]; then
    /root/sync-bloodstone-downloads-to-worker.sh \
      "${OUT_DL}/${APK_NAME}" \
      "${OUT_DL}/${APK_NAME}.sha256" \
      "${OUT_DL}/${APK_LATEST}" \
      "${OUT_DL}/fork-icons/${ticker_lower}.png" \
      "${OUT_DL}/${ticker_lower}-full-node-android-manifest.json" || true
  fi
}

# --- main ---
require_icon
[[ -f "$KEYSTORE" ]] || { log "missing keystore $KEYSTORE"; exit 1; }
[[ -d "$SRC_BASE" ]] || { log "missing $SRC_BASE"; exit 1; }
stage_tree
generate_icons
rebrand_files
sync_cap_and_build
log "DONE — ${FORK_APP_LABEL} APK ready (separate from Bloodstone)"
