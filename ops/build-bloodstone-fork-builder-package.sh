#!/usr/bin/env bash
# Package offline Fork Builder for downloads (space-light; core source optional).
set -euo pipefail

SRC="/root/bloodstone-fork-builder"
# Prefer explicit env, else APP_VERSION from fork_builder.py, else fallback.
if [[ -z "${BLOODSTONE_FORK_BUILDER_VERSION:-}" ]]; then
  VERSION="$(python3 - <<'PY'
from pathlib import Path
import re
p = Path("/root/bloodstone-fork-builder/fork_builder.py")
m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', p.read_text(encoding="utf-8", errors="replace"))
print(m.group(1) if m else "1.5.1")
PY
)"
else
  VERSION="${BLOODSTONE_FORK_BUILDER_VERSION}"
fi
OUT_ROOT="${BLOODSTONE_DOWNLOADS_DIR:-/var/www/bloodstone/downloads}"
STAGE="/tmp/bloodstone-fork-builder-pack"
NAME="bloodstone-fork-builder-${VERSION}"
PUBLIC_ROOT="${BLOODSTONE_PUBLIC_ROOT:-https://bloodstonewallet.mytunnel.org}"
INCLUDE_CORE="${FORK_BUILDER_INCLUDE_CORE:-1}"

log() { echo "[fork-builder-pack] $*" >&2; }

FREE_GB=$(python3 - <<'PY'
import shutil
print(f"{shutil.disk_usage('/').free / (1024**3):.2f}")
PY
)
log "free disk ${FREE_GB} GB"
# Require at least 1.5 GB free to package safely
python3 - <<PY
import sys
free=float("${FREE_GB}")
if free < 1.5:
    print(f"Refusing: only {free} GB free (< 1.5 GB)", file=sys.stderr)
    sys.exit(2)
PY

rm -rf "$STAGE"
mkdir -p "$STAGE/$NAME/vendor" "$OUT_ROOT"

rsync -a --delete \
  --exclude 'work' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'vendor/*.tar.gz' \
  "$SRC/" "$STAGE/$NAME/"

chmod +x "$STAGE/$NAME/fork_builder.py" \
  "$STAGE/$NAME/start-gui.sh" \
  "$STAGE/$NAME/scripts/"*.sh 2>/dev/null || true

# Optional: ship core source inside package for true offline use (~7MB)
if [[ "$INCLUDE_CORE" == "1" ]]; then
  CORE_SRC="${BLOODSTONE_CORE_SOURCE_TAR:-/var/www/bloodstone/downloads/bloodstone-core-source-latest.tar.gz}"
  if [[ -f "$CORE_SRC" ]]; then
    log "bundling core source from $CORE_SRC"
    cp -L "$CORE_SRC" "$STAGE/$NAME/vendor/bloodstone-core-source-latest.tar.gz"
  else
    log "WARN: core tarball missing — package without vendor source"
  fi
fi

# Offline fetch helper (used when online)
cat > "$STAGE/$NAME/scripts/fetch-core-source.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT="\$(cd "\$(dirname "\$0")/.." && pwd)"
mkdir -p "\$ROOT/vendor"
URL="${PUBLIC_ROOT}/downloads/bloodstone-core-source-latest.tar.gz"
OUT="\$ROOT/vendor/bloodstone-core-source-latest.tar.gz"
echo "Downloading \$URL"
curl -fsSL "\$URL" -o "\$OUT"
echo "Saved \$OUT"
EOF
chmod +x "$STAGE/$NAME/scripts/fetch-core-source.sh"

# Windows zip + Linux tar.gz
(
  cd "$STAGE"
  tar -czf "${OUT_ROOT}/${NAME}-offline.tar.gz" "$NAME"
  # zip for Windows users
  if command -v zip >/dev/null 2>&1; then
    zip -qr "${OUT_ROOT}/${NAME}-offline.zip" "$NAME"
  else
    python3 - <<PY
import shutil
shutil.make_archive("${OUT_ROOT}/${NAME}-offline", "zip", "$STAGE", "$NAME")
PY
  fi
)

(
  cd "$OUT_ROOT"
  sha256sum "${NAME}-offline.tar.gz" | tee "${NAME}-offline.tar.gz.sha256"
  if [[ -f "${NAME}-offline.zip" ]]; then
    sha256sum "${NAME}-offline.zip" | tee "${NAME}-offline.zip.sha256"
  fi
  ln -sfn "${NAME}-offline.tar.gz" bloodstone-fork-builder-latest.tar.gz
  ln -sfn "${NAME}-offline.tar.gz.sha256" bloodstone-fork-builder-latest.tar.gz.sha256
  if [[ -f "${NAME}-offline.zip" ]]; then
    ln -sfn "${NAME}-offline.zip" bloodstone-fork-builder-latest.zip
    ln -sfn "${NAME}-offline.zip.sha256" bloodstone-fork-builder-latest.zip.sha256
  fi
)

# Manifest for API / downloads
python3 - <<PY
import json, os, time
from pathlib import Path
out = Path("${OUT_ROOT}")
name = "${NAME}"
pub = "${PUBLIC_ROOT}"
def meta(fn):
    p = out / fn
    if not p.is_file():
        return None
    import hashlib
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    return {
        "filename": fn,
        "url": f"{pub}/downloads/{fn}",
        "sha256": h,
        "size_bytes": p.stat().st_size,
    }
payload = {
    "ok": True,
    "app": "bloodstone-fork-builder",
    "version": "${VERSION}",
    "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "linux_tar": meta(f"{name}-offline.tar.gz"),
    "windows_zip": meta(f"{name}-offline.zip"),
    "latest_tar": f"{pub}/downloads/bloodstone-fork-builder-latest.tar.gz",
    "latest_zip": f"{pub}/downloads/bloodstone-fork-builder-latest.zip",
    "fork_lab": f"{pub}/fork-lab/",
    "note": "Offline app to patch + compile paid Fork Lab coins on a home PC.",
}
(out / "bloodstone-fork-builder-manifest.json").write_text(json.dumps(payload, indent=2) + "\n")
print(json.dumps(payload, indent=2))
PY

ls -lh "${OUT_ROOT}/${NAME}-offline.tar.gz" "${OUT_ROOT}/${NAME}-offline.zip" 2>/dev/null || true
log "done"

# mirror worker
WORKER="${BLOODSTONE_POOL_WORKER:-192.119.82.145}"
SSH_KEY="${BLOODSTONE_SSH_KEY:-/root/.ssh/bloodstone_copy_key}"
if [[ -f "$SSH_KEY" ]]; then
  scp -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=20 \
    "${OUT_ROOT}/${NAME}-offline.tar.gz" \
    "${OUT_ROOT}/${NAME}-offline.tar.gz.sha256" \
    "${OUT_ROOT}/${NAME}-offline.zip" \
    "${OUT_ROOT}/${NAME}-offline.zip.sha256" \
    "${OUT_ROOT}/bloodstone-fork-builder-manifest.json" \
    "root@${WORKER}:/var/www/bloodstone/downloads/" 2>/dev/null && \
  ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=15 "root@${WORKER}" \
    "cd /var/www/bloodstone/downloads && \
     ln -sfn ${NAME}-offline.tar.gz bloodstone-fork-builder-latest.tar.gz && \
     ln -sfn ${NAME}-offline.tar.gz.sha256 bloodstone-fork-builder-latest.tar.gz.sha256 && \
     ln -sfn ${NAME}-offline.zip bloodstone-fork-builder-latest.zip && \
     ln -sfn ${NAME}-offline.zip.sha256 bloodstone-fork-builder-latest.zip.sha256" \
    && log "worker synced" || log "worker sync skipped/failed"
fi
