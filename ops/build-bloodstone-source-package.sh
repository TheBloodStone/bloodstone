#!/usr/bin/env bash
# Package Bloodstone source trees for public download (no secrets, no .git).
# Produces:
#   bloodstone-core-${VERSION}-source.tar.gz   — full-node / consensus source
#   bloodstone-source-${VERSION}.tar.gz        — OSS monorepo snapshot (apps + ops + docs)
set -euo pipefail

VERSION="${BLOODSTONE_VERSION:-0.7.2}"
STAMP="$(date -u +%Y%m%dT%H%MZ)"
OUT_ROOT="${BLOODSTONE_DOWNLOADS_DIR:-/var/www/bloodstone/downloads}"
STAGE_ROOT="${BLOODSTONE_SOURCE_STAGE:-/tmp/bloodstone-source-pack}"
# Prefer full source tree (bloodstone-core on VPS is often binary-only).
CORE_SRC="${BLOODSTONE_CORE_SRC:-}"
if [[ -z "$CORE_SRC" ]]; then
  if [[ -f /root/bloodstone-core-src/src/init.cpp ]]; then
    CORE_SRC="/root/bloodstone-core-src"
  elif [[ -f /root/bloodstone-repo/core/src/init.cpp ]]; then
    CORE_SRC="/root/bloodstone-repo/core"
  elif [[ -f /root/bloodstone-core/src/init.cpp ]]; then
    CORE_SRC="/root/bloodstone-core"
  else
    CORE_SRC="/root/bloodstone-core-src"
  fi
fi
OSS_SRC="${BLOODSTONE_OSS_SRC:-/root/bloodstone-repo}"
PUBLIC_ROOT="${BLOODSTONE_PUBLIC_ROOT:-https://bloodstonewallet.mytunnel.org}"

CORE_NAME="bloodstone-core-${VERSION}-source"
FULL_NAME="bloodstone-source-${VERSION}"
CORE_TAR="${CORE_NAME}.tar.gz"
FULL_TAR="${FULL_NAME}.tar.gz"

log() { echo "[source-pack] $*" >&2; }

RSYNC_EXCLUDES=(
  --exclude '.git'
  --exclude '.git/**'
  --exclude 'node_modules'
  --exclude 'venv'
  --exclude '.venv'
  --exclude '__pycache__'
  --exclude '*.pyc'
  --exclude '.gradle'
  --exclude 'android/app/build'
  --exclude 'android/build'
  --exclude 'dist'
  --exclude 'out'
  --exclude '*.log'
  --exclude '.DS_Store'
  --exclude 'autom4te.cache'
  --exclude 'secrets.conf'
  --exclude 'service-overrides.conf'
  --exclude '*.keystore'
  --exclude 'keystore.properties'
  --exclude '.env'
  --exclude '.env.*'
  --exclude '*.o'
  --exclude '*.a'
  --exclude '*.la'
  --exclude '*.lo'
  --exclude '*.dylib'
  --exclude '*.so'
  --exclude '*.so.*'
  --exclude '*.dll'
  --exclude '*.exe'
  --exclude 'src/bloodstoned'
  --exclude 'src/bloodstone-cli'
  --exclude 'src/bloodstone-tx'
  --exclude 'src/bloodstone-wallet'
  --exclude 'src/bloodstone-qt'
  --exclude 'src/qt/bloodstone-qt'
  --exclude 'src/test/test_bloodstone'
  --exclude 'src/bench/bench_bloodstone'
  --exclude 'src/.libs'
  --exclude '**/Makefile'
  --exclude '**/Makefile.in'
  # keep Makefile.am / configure.ac; drop generated build trees
  --exclude 'config.log'
  --exclude 'config.status'
  --exclude 'libtool'
  --exclude 'src/config/bitcoin-config.h'
  --exclude 'DEPLOY_KEY'
  --exclude 'DEPLOY_KEY.pub'
  --exclude 'id_rsa'
  --exclude 'id_ed25519'
  --exclude '*.pem'
  --exclude 'glpat-*'
)

rm -rf "$STAGE_ROOT"
mkdir -p "$STAGE_ROOT" "$OUT_ROOT"

# --- Core node source ---
if [[ ! -d "$CORE_SRC/src" ]]; then
  echo "Missing core source tree at $CORE_SRC" >&2
  exit 1
fi
log "Packaging core from $CORE_SRC"
mkdir -p "$STAGE_ROOT/$CORE_NAME"
rsync -a "${RSYNC_EXCLUDES[@]}" "$CORE_SRC/" "$STAGE_ROOT/$CORE_NAME/"

# Drop accidental credential-bearing remotes files if any
find "$STAGE_ROOT/$CORE_NAME" -type f \( -name '.git-credentials' -o -name 'credentials' -o -name '*token*' \) -delete 2>/dev/null || true

cat > "$STAGE_ROOT/$CORE_NAME/SOURCE-README.txt" <<EOF
Bloodstone Core — source distribution
=====================================

Package:  ${CORE_TAR}
Version:  ${VERSION}
Built:    ${STAMP} UTC
Upstream lineage: SpaceXpanse / Namecoin / Bitcoin Core heritage

Contents
--------
Full-node consensus daemon source (bloodstoned, bloodstone-cli, optional Qt).

Build (Linux, high level)
-------------------------
  ./autogen.sh
  ./configure --disable-tests --without-gui   # or with Qt deps for GUI
  make -j\$(nproc)
  # binaries: src/bloodstoned src/bloodstone-cli

Network
-------
  P2P: 17333
  RPC: 18332 (bind localhost in production)
  Genesis: df04225074039e630dad825b24818a695462bd19cd585131a0568f50e9bf71d0
  Ticker: STONE (Bloodstone mainnet, Jun 2026 relaunch)

Downloads & listing
-------------------
  ${PUBLIC_ROOT}/downloads/
  ${PUBLIC_ROOT}/api/exchange
  ${PUBLIC_ROOT}/exchange/

License: see COPYING / LICENSE in this tree.
EOF

# --- Full OSS snapshot ---
log "Packaging OSS monorepo from $OSS_SRC"
mkdir -p "$STAGE_ROOT/$FULL_NAME"
if [[ -d "$OSS_SRC" ]]; then
  rsync -a "${RSYNC_EXCLUDES[@]}" \
    --exclude 'downloads/*.tar.gz' \
    --exclude 'downloads/*.zip' \
    --exclude 'downloads/*.exe' \
    --exclude 'downloads/*.apk' \
    "$OSS_SRC/" "$STAGE_ROOT/$FULL_NAME/"
else
  log "WARN: OSS_SRC missing; full package will be core-only tree copy"
  rsync -a "$STAGE_ROOT/$CORE_NAME/" "$STAGE_ROOT/$FULL_NAME/core/"
fi

# Ensure chain_mesh is present (may live outside repo on VPS)
if [[ ! -d "$STAGE_ROOT/$FULL_NAME/chain_mesh" && -d /root/chain_mesh ]]; then
  log "Adding /root/chain_mesh"
  mkdir -p "$STAGE_ROOT/$FULL_NAME/chain_mesh"
  rsync -a "${RSYNC_EXCLUDES[@]}" /root/chain_mesh/ "$STAGE_ROOT/$FULL_NAME/chain_mesh/"
fi

# Ensure core is in monorepo snapshot
if [[ ! -d "$STAGE_ROOT/$FULL_NAME/core/src" ]]; then
  log "Embedding core into monorepo snapshot"
  mkdir -p "$STAGE_ROOT/$FULL_NAME/core"
  rsync -a "$STAGE_ROOT/$CORE_NAME/" "$STAGE_ROOT/$FULL_NAME/core/"
fi

# Scrub any embedded tokens/credentials from text files (defensive)
# Remove git config remotes that might embed tokens if .git slipped through
find "$STAGE_ROOT" -type d -name '.git' -prune -exec rm -rf {} + 2>/dev/null || true
# Scrub oauth tokens accidentally left in config samples
find "$STAGE_ROOT" -type f \( -name '*.md' -o -name '*.sh' -o -name '*.py' -o -name '*.json' -o -name '*.txt' -o -name 'config' -o -name '*.conf*' \) \
  -size -2M 2>/dev/null | while read -r f; do
  if grep -qE 'glpat-[A-Za-z0-9._-]+|ghp_[A-Za-z0-9]+|xox[baprs]-[A-Za-z0-9-]+' "$f" 2>/dev/null; then
    log "Scrubbing secrets in $f"
    sed -i -E \
      -e 's/glpat-[A-Za-z0-9._-]+/REDACTED/g' \
      -e 's/ghp_[A-Za-z0-9]+/REDACTED/g' \
      -e 's/xox[baprs]-[A-Za-z0-9-]+/REDACTED/g' \
      -e 's|https://oauth2:[^@]+@|https://oauth2:REDACTED@|g' \
      "$f" || true
  fi
done

cat > "$STAGE_ROOT/$FULL_NAME/SOURCE-README.txt" <<EOF
Bloodstone — full source snapshot
=================================

Package:  ${FULL_TAR}
Version:  ${VERSION}
Built:    ${STAMP} UTC

This archive is a publishable open-source snapshot of the Bloodstone stack:
  core/          consensus full node (bloodstoned)
  portal/        public portal
  miner-web/     mining dashboard / admin
  miner-android/ Android miner
  chain_mesh/    Blurt convergence / mesh
  explorer/, faucet/, electrumx/, support/, dex/
  ops/           stratum, packaging, QUASAR helpers
  docs/          white papers and operator guides

Secrets, private keys, live configs, and .git history are excluded.
Build individual components from their directories; see core/SOURCE-README.txt
and each app's README.

Public downloads: ${PUBLIC_ROOT}/downloads/
Listing JSON:     ${PUBLIC_ROOT}/api/exchange
EOF

# Tar + checksums
log "Creating archives in $OUT_ROOT"
(
  cd "$STAGE_ROOT"
  tar -czf "${OUT_ROOT}/${CORE_TAR}" "$CORE_NAME"
  tar -czf "${OUT_ROOT}/${FULL_TAR}" "$FULL_NAME"
)

(
  cd "$OUT_ROOT"
  sha256sum "$CORE_TAR" | tee "${CORE_TAR}.sha256"
  sha256sum "$FULL_TAR" | tee "${FULL_TAR}.sha256"
  ln -sfn "$CORE_TAR" bloodstone-core-source-latest.tar.gz
  ln -sfn "${CORE_TAR}.sha256" bloodstone-core-source-latest.tar.gz.sha256
  ln -sfn "$FULL_TAR" bloodstone-source-latest.tar.gz
  ln -sfn "${FULL_TAR}.sha256" bloodstone-source-latest.tar.gz.sha256
)

# Manifest for exchange API consumers
cat > "${OUT_ROOT}/bloodstone-source-manifest.json" <<EOF
{
  "ok": true,
  "version": "${VERSION}",
  "built_utc": "${STAMP}",
  "packages": {
    "core": {
      "filename": "${CORE_TAR}",
      "url": "${PUBLIC_ROOT}/downloads/${CORE_TAR}",
      "latest_url": "${PUBLIC_ROOT}/downloads/bloodstone-core-source-latest.tar.gz",
      "sha256_url": "${PUBLIC_ROOT}/downloads/${CORE_TAR}.sha256",
      "description": "Bloodstone Core full-node / consensus source"
    },
    "full": {
      "filename": "${FULL_TAR}",
      "url": "${PUBLIC_ROOT}/downloads/${FULL_TAR}",
      "latest_url": "${PUBLIC_ROOT}/downloads/bloodstone-source-latest.tar.gz",
      "sha256_url": "${PUBLIC_ROOT}/downloads/${FULL_TAR}.sha256",
      "description": "Full Bloodstone OSS monorepo snapshot (apps, ops, docs, mesh)"
    }
  }
}
EOF
ln -sfn bloodstone-source-manifest.json "${OUT_ROOT}/bloodstone-source-manifest-latest.json"

# Sizes
ls -lh "${OUT_ROOT}/${CORE_TAR}" "${OUT_ROOT}/${FULL_TAR}"
log "done"

# Optional worker mirror
WORKER="${BLOODSTONE_POOL_WORKER:-192.119.82.145}"
SSH_KEY="${BLOODSTONE_SSH_KEY:-/root/.ssh/bloodstone_copy_key}"
if [[ "${BLOODSTONE_SYNC_SOURCE_TO_WORKER:-1}" == "1" && -f "$SSH_KEY" ]]; then
  log "Syncing source packages to worker ${WORKER}"
  scp -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=20 \
    "${OUT_ROOT}/${CORE_TAR}" \
    "${OUT_ROOT}/${CORE_TAR}.sha256" \
    "${OUT_ROOT}/${FULL_TAR}" \
    "${OUT_ROOT}/${FULL_TAR}.sha256" \
    "${OUT_ROOT}/bloodstone-source-manifest.json" \
    "root@${WORKER}:/var/www/bloodstone/downloads/" \
    && ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=20 "root@${WORKER}" \
      "cd /var/www/bloodstone/downloads && \
       ln -sfn ${CORE_TAR} bloodstone-core-source-latest.tar.gz && \
       ln -sfn ${CORE_TAR}.sha256 bloodstone-core-source-latest.tar.gz.sha256 && \
       ln -sfn ${FULL_TAR} bloodstone-source-latest.tar.gz && \
       ln -sfn ${FULL_TAR}.sha256 bloodstone-source-latest.tar.gz.sha256 && \
       ln -sfn bloodstone-source-manifest.json bloodstone-source-manifest-latest.json" \
    && log "Worker sync OK" \
    || log "WARN: worker sync failed (packages still local)"
fi
