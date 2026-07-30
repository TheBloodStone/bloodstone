#!/usr/bin/env bash
# Build Windows x64 setup EXE + portable zip for Multi-Fork Qt Wallet.
# Cross-builds on Linux: embeddable CPython + win_amd64 wheels + NSIS.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "${ROOT}/VERSION")"
NAME="bloodstone-multi-fork-qt"
OUT_DL="${BLOODSTONE_DOWNLOADS_DIR:-/var/www/bloodstone/downloads}"
CACHE="${BLOODSTONE_CACHE:-/var/cache/bloodstone}"
WORK="${BLOODSTONE_MFQ_WIN_WORK:-/tmp/mfq-win-build}"
STAGE="${WORK}/stage"
PAYLOAD="${STAGE}/${NAME}-${VERSION}-win64"
PYTHON_VER="${MFQ_PYTHON_VER:-3.11.9}"
PYTHON_EMBED_ZIP="${CACHE}/python-${PYTHON_VER}-embed-amd64.zip"
PYTHON_EMBED_URL="${MFQ_PYTHON_EMBED_URL:-https://www.python.org/ftp/python/${PYTHON_VER}/python-${PYTHON_VER}-embed-amd64.zip}"
WHEELS_DIR="${WORK}/wheels"
SETUP_EXE="${OUT_DL}/${NAME}-${VERSION}-win64-setup.exe"
PORTABLE_ZIP="${OUT_DL}/${NAME}-${VERSION}-win64-portable.zip"
LATEST_SETUP="${OUT_DL}/${NAME}-win64-setup-latest.exe"
LATEST_PORTABLE="${OUT_DL}/${NAME}-win64-portable-latest.zip"
NSI="${WORK}/mfq-setup.nsi"

log() { echo "[mfq-win] $*"; }

need() { command -v "$1" >/dev/null 2>&1 || { log "missing tool: $1"; exit 1; }; }
need curl
need unzip
need zip
need makensis
need python3

mkdir -p "$CACHE" "$WORK" "$WHEELS_DIR" "$OUT_DL"
rm -rf "$STAGE"
mkdir -p "$PAYLOAD/python" "$PAYLOAD/app"

# ── 1) Embeddable CPython ──────────────────────────────────
if [[ ! -f "$PYTHON_EMBED_ZIP" ]]; then
  log "Downloading Python ${PYTHON_VER} embeddable…"
  curl -fL --retry 3 -o "$PYTHON_EMBED_ZIP" "$PYTHON_EMBED_URL"
fi
log "Extracting embeddable Python…"
unzip -qo "$PYTHON_EMBED_ZIP" -d "$PAYLOAD/python"

# Enable site-packages
PTH="$(echo "$PAYLOAD/python"/python*._pth)"
if [[ -f "$PTH" ]]; then
  # Rewrite ._pth for site-packages
  {
    echo "python311.zip"
    echo "."
    echo "Lib\\site-packages"
    echo "import site"
  } > "$PTH"
  # Fix zip name if version differs
  ZNAME="$(basename "$(ls "$PAYLOAD/python"/python*.zip | head -1)")"
  if [[ -n "$ZNAME" ]]; then
    sed -i "1s/.*/${ZNAME}/" "$PTH" 2>/dev/null || true
    # safer rewrite
    {
      echo "$ZNAME"
      echo "."
      echo "Lib\\site-packages"
      echo "import site"
    } > "$PTH"
  fi
fi
mkdir -p "$PAYLOAD/python/Lib/site-packages"

# ── 2) Download Windows wheels on Linux ────────────────────
log "Downloading win_amd64 wheels (PyQt5, requests)…"
rm -rf "$WHEELS_DIR"
mkdir -p "$WHEELS_DIR"

download_wheels() {
  python3 -m pip download \
    --only-binary=:all: \
    --python-version 311 \
    --platform win_amd64 \
    --implementation cp \
    --abi cp311 \
    -d "$WHEELS_DIR" \
    "$@"
}

set +e
download_wheels "PyQt5==5.15.10" "PyQt5-Qt5==5.15.2" 2>&1 | tail -30
download_wheels "requests" "urllib3" "certifi" "charset-normalizer" "idna" 2>&1 | tail -20
set -e

# PyQt5-sip: older pip often fails tag selection for win_amd64; fetch from PyPI JSON.
if ! ls "$WHEELS_DIR"/PyQt5_sip-*.whl "$WHEELS_DIR"/pyqt5_sip-*.whl >/dev/null 2>&1; then
  log "Fetching PyQt5-sip cp311 win_amd64 from PyPI…"
  python3 - <<'PY'
import json, urllib.request, sys
from pathlib import Path
out = Path("/tmp/mfq-win-build/wheels")
out.mkdir(parents=True, exist_ok=True)
data = json.load(urllib.request.urlopen("https://pypi.org/pypi/PyQt5-sip/json", timeout=60))
# Prefer a version that has cp311 win_amd64
picked = None
for ver in sorted(data["releases"].keys(), reverse=True):
    for f in data["releases"][ver]:
        name = f.get("filename") or ""
        if "cp311" in name and "win_amd64" in name and name.endswith(".whl"):
            picked = f
            break
    if picked:
        break
if not picked:
    sys.exit("No PyQt5-sip cp311 win_amd64 wheel on PyPI")
dest = out / picked["filename"]
if not dest.is_file():
    print("Downloading", picked["filename"])
    urllib.request.urlretrieve(picked["url"], dest)
print("OK", dest, dest.stat().st_size)
PY
fi

if ! ls "$WHEELS_DIR"/PyQt5-*.whl >/dev/null 2>&1; then
  log "ERROR: could not download PyQt5 win_amd64 wheel"
  ls -la "$WHEELS_DIR" || true
  exit 1
fi
ls -lh "$WHEELS_DIR"

log "Unpacking wheels into site-packages…"
SITE="$PAYLOAD/python/Lib/site-packages"
for whl in "$WHEELS_DIR"/*.whl; do
  log "  $(basename "$whl")"
  unzip -qo "$whl" -d "$SITE"
done

# ── 3) App sources ─────────────────────────────────────────
log "Copying application…"
rsync -a \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'win' \
  --exclude 'scripts' \
  --exclude '.git' \
  "${ROOT}/main.py" \
  "${ROOT}/VERSION" \
  "${ROOT}/README.md" \
  "${ROOT}/requirements.txt" \
  "${ROOT}/bloodstone_mfq" \
  "${ROOT}/resources" \
  "$PAYLOAD/app/"

cp -a "${ROOT}/win/launch.bat" "$PAYLOAD/launch.bat"
cp -a "${ROOT}/win/launch-console.bat" "$PAYLOAD/launch-console.bat"
cp -a "${ROOT}/win/README-WINDOWS.txt" "$PAYLOAD/README-WINDOWS.txt"

# Friendly root launcher name
cp -a "$PAYLOAD/launch.bat" "$PAYLOAD/BloodstoneMultiForkQt.bat"

# Bundle per-fork Windows daemons (STONE + any published packs)
log "Bundling local daemon packs…"
DAEMON_DL="${BLOODSTONE_DOWNLOADS_DIR:-/var/www/bloodstone/downloads}/mfq-daemons"
mkdir -p "$PAYLOAD/daemons"
for ticker in STONE AZURE LRGK; do
  zipf="${DAEMON_DL}/${ticker}-win64.zip"
  if [[ -f "$zipf" ]]; then
    mkdir -p "$PAYLOAD/daemons/${ticker}"
    unzip -qo "$zipf" -d "$PAYLOAD/daemons/${ticker}"
    # Flatten single top-level folder if present
    if [[ -d "$PAYLOAD/daemons/${ticker}/${ticker}-win64" ]]; then
      shopt -s dotglob
      mv "$PAYLOAD/daemons/${ticker}/${ticker}-win64"/* "$PAYLOAD/daemons/${ticker}/" 2>/dev/null || true
      rmdir "$PAYLOAD/daemons/${ticker}/${ticker}-win64" 2>/dev/null || true
      shopt -u dotglob
    fi
    log "  bundled ${ticker}"
  else
    log "  skip ${ticker} (no pack at $zipf)"
  fi
done
if [[ -f "${DAEMON_DL}/manifest.json" ]]; then
  cp -a "${DAEMON_DL}/manifest.json" "$PAYLOAD/daemons/manifest.json"
fi

# Version stamp
echo "$VERSION" > "$PAYLOAD/VERSION.txt"
cat > "$PAYLOAD/app/bloodstone_mfq/_build_info.py" <<EOF
VERSION = "${VERSION}"
PLATFORM = "win64"
BUILD_HOST = "$(hostname 2>/dev/null || echo unknown)"
EOF

# ── 4) Portable zip ────────────────────────────────────────
log "Writing portable zip…"
(
  cd "$STAGE"
  rm -f "$PORTABLE_ZIP"
  zip -rq "$PORTABLE_ZIP" "$(basename "$PAYLOAD")"
)
sha256sum "$PORTABLE_ZIP" | awk '{print $1}' > "${PORTABLE_ZIP}.sha256"
cp -f "$PORTABLE_ZIP" "$LATEST_PORTABLE"
cp -f "${PORTABLE_ZIP}.sha256" "${LATEST_PORTABLE}.sha256"
log "Portable: $PORTABLE_ZIP ($(du -h "$PORTABLE_ZIP" | awk '{print $1}'))"

# ── 5) NSIS setup EXE ──────────────────────────────────────
log "Writing NSIS installer…"
# Stage layout expected by NSIS: run from WORK with payload/ symlink
NSIS_ROOT="${WORK}/nsis-root"
rm -rf "$NSIS_ROOT"
mkdir -p "$NSIS_ROOT"
# Copy payload under nsis-root/payload so File /r "payload\*.*" works (fork-builder pattern)
cp -a "$PAYLOAD" "$NSIS_ROOT/payload"
NSI="${NSIS_ROOT}/setup.nsi"
cat > "$NSI" <<EOF
Unicode true
SetCompressor /SOLID lzma

!define PRODUCT_NAME "Bloodstone Multi-Fork Qt Wallet"
!define PRODUCT_VERSION "${VERSION}"
!define PRODUCT_PUBLISHER "Bloodstone"
!define PRODUCT_WEB "https://bloodstone.rocks/downloads/"

Name "\${PRODUCT_NAME} \${PRODUCT_VERSION}"
OutFile "${SETUP_EXE}"
InstallDir "\$LOCALAPPDATA\\Bloodstone\\MultiForkQt"
RequestExecutionLevel user
ShowInstDetails show

Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

Section "Install"
  SetOutPath "\$INSTDIR"
  File /r "payload\\*.*"

  CreateDirectory "\$SMPROGRAMS\\Bloodstone"
  ; Prefer launch.bat so cwd = install root (bundled daemons\\ discoverable).
  ; Direct pythonw shortcuts default cwd to python\\ and miss daemons\\.
  CreateShortCut "\$SMPROGRAMS\\Bloodstone\\Multi-Fork Qt Wallet.lnk" \\
    "\$INSTDIR\\launch.bat"
  CreateShortCut "\$SMPROGRAMS\\Bloodstone\\Multi-Fork Qt (console).lnk" \\
    "\$INSTDIR\\launch-console.bat"
  CreateShortCut "\$SMPROGRAMS\\Bloodstone\\Uninstall Multi-Fork Qt.lnk" \\
    "\$INSTDIR\\Uninstall.exe"
  CreateShortCut "\$DESKTOP\\Bloodstone Multi-Fork Qt.lnk" \\
    "\$INSTDIR\\launch.bat"

  WriteUninstaller "\$INSTDIR\\Uninstall.exe"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BloodstoneMultiForkQt" "DisplayName" "\${PRODUCT_NAME}"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BloodstoneMultiForkQt" "DisplayVersion" "\${PRODUCT_VERSION}"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BloodstoneMultiForkQt" "Publisher" "\${PRODUCT_PUBLISHER}"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BloodstoneMultiForkQt" "UninstallString" "\$INSTDIR\\Uninstall.exe"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BloodstoneMultiForkQt" "InstallLocation" "\$INSTDIR"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BloodstoneMultiForkQt" "URLInfoAbout" "\${PRODUCT_WEB}"

  MessageBox MB_YESNO|MB_ICONQUESTION "Install complete.\$\\r\$\\n\$\\r\$\\nLaunch Multi-Fork Qt Wallet now?" IDNO skip_run
    Exec '"\$INSTDIR\\python\\pythonw.exe" "\$INSTDIR\\app\\main.py"'
  skip_run:
SectionEnd

Section "Uninstall"
  Delete "\$SMPROGRAMS\\Bloodstone\\Multi-Fork Qt Wallet.lnk"
  Delete "\$SMPROGRAMS\\Bloodstone\\Multi-Fork Qt (console).lnk"
  Delete "\$SMPROGRAMS\\Bloodstone\\Uninstall Multi-Fork Qt.lnk"
  RMDir "\$SMPROGRAMS\\Bloodstone"
  Delete "\$DESKTOP\\Bloodstone Multi-Fork Qt.lnk"
  DeleteRegKey HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BloodstoneMultiForkQt"
  RMDir /r "\$INSTDIR"
SectionEnd
EOF

log "Running makensis (this can take several minutes)…"
(
  cd "$NSIS_ROOT"
  makensis -V2 setup.nsi
)

sha256sum "$SETUP_EXE" | awk '{print $1}' > "${SETUP_EXE}.sha256"
cp -f "$SETUP_EXE" "$LATEST_SETUP"
cp -f "${SETUP_EXE}.sha256" "${LATEST_SETUP}.sha256"

# Convenience aliases (versioned + latest, with and without -setup suffix)
cp -f "$SETUP_EXE" "${OUT_DL}/${NAME}-win64-setup.exe"
cp -f "${SETUP_EXE}.sha256" "${OUT_DL}/${NAME}-win64-setup.exe.sha256"
cp -f "$SETUP_EXE" "${OUT_DL}/${NAME}-${VERSION}-win64.exe"
cp -f "${SETUP_EXE}.sha256" "${OUT_DL}/${NAME}-${VERSION}-win64.exe.sha256"
cp -f "$SETUP_EXE" "${OUT_DL}/${NAME}-win64-latest.exe"
cp -f "${SETUP_EXE}.sha256" "${OUT_DL}/${NAME}-win64-latest.exe.sha256"

log "Setup EXE: $SETUP_EXE ($(du -h "$SETUP_EXE" | awk '{print $1}'))"
log "SHA256: $(cat "${SETUP_EXE}.sha256")"
log "Done."
echo "$SETUP_EXE"
