#!/usr/bin/env bash
# Assemble a publishable open-source snapshot of the Bloodstone project.
set -euo pipefail

SRC_ROOT="${BLOODSTONE_SRC_ROOT:-/root}"
OUT="${BLOODSTONE_OSS_OUT:-/root/bloodstone-repo}"
STAMP="$(date -u +%Y%m%d)"

log() { echo "[bloodstone-oss] $*" >&2; }

RSYNC_EXCLUDES=(
  --exclude '.git'
  --exclude 'node_modules'
  --exclude 'venv'
  --exclude '__pycache__'
  --exclude '*.pyc'
  --exclude '.gradle'
  --exclude 'android/app/build'
  --exclude 'android/build'
  --exclude 'android/.gradle'
  --exclude 'plugins/*/android/build'
  --exclude 'capacitor-cordova-android-plugins/build'
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
)

copy_tree() {
  local name="$1"
  local src="$2"
  local dest="$OUT/$name"
  if [[ ! -d "$src" ]]; then
    log "skip missing $src"
    return 0
  fi
  log "copy $name <- $src"
  mkdir -p "$dest"
  rsync -a --delete "${RSYNC_EXCLUDES[@]}" "$src/" "$dest/"
}

log "preparing $OUT"
rm -rf "$OUT"
mkdir -p "$OUT/ops" "$OUT/downloads"

# Core chain + apps
copy_tree core "$SRC_ROOT/bloodstone-core-src"
copy_tree chain "$SRC_ROOT/bloodstone-chain"
copy_tree miner-android "$SRC_ROOT/bloodstone-miner-android"
copy_tree miner-web "$SRC_ROOT/bloodstone-miner-web"
copy_tree portal "$SRC_ROOT/bloodstone-portal"
copy_tree node-gui "$SRC_ROOT/bloodstone-node-gui"
copy_tree wallet-node-gui "$SRC_ROOT/bloodstone-wallet-node-gui"
copy_tree explorer "$SRC_ROOT/bloodstone-explorer"
copy_tree faucet "$SRC_ROOT/bloodstone-faucet"
copy_tree dex "$SRC_ROOT/bloodstone-dex"
copy_tree support "$SRC_ROOT/bloodstone-support"
copy_tree electrumx "$SRC_ROOT/bloodstone-electrumx"
copy_tree docs "$SRC_ROOT/bloodstone-docs"

# Shared ops scripts (VPS pool, stratum, builds, watchdogs)
for f in \
  bloodstone_downloads.py \
  bloodstone_branding.py \
  bloodstone_broadcast.py \
  bloodstone_rich_list.py \
  bloodstone-time.py \
  bloodstone_downloads.py \
  build-bloodstone-miner-android-apk.sh \
  publish-android-miner-web-bundle.sh \
  publish-bloodstone-chain-bootstrap.sh \
  sync-bloodstone-downloads-to-worker.sh \
  bloodstone-stratum.py \
  bloodstone-stratum-yespower.py \
  bloodstone-stratum-sha256.py \
  bloodstone-stratum-rod-neoscrypt.py \
  bloodstone-stratum-rod-sha256.py \
  bloodstone-node-watchdog.sh \
  bloodstone-pool-algo-watchdog.py \
  bloodstone-settings-guard.sh \
  bloodstone-link-check.sh; do
  if [[ -f "$SRC_ROOT/$f" ]]; then
    cp -f "$SRC_ROOT/$f" "$OUT/ops/"
  fi
done

if [[ -f "$SRC_ROOT/bloodstone-downloads-index.html" ]]; then
  cp -f "$SRC_ROOT/bloodstone-downloads-index.html" "$OUT/downloads/index.html.template"
fi

# Example configs only — never copy live secrets
cat > "$OUT/miner-web/secrets.conf.example" <<'EOF'
# Copy to secrets.conf and fill in locally. Never commit secrets.conf.
secret_key=GENERATE_A_RANDOM_HEX_SECRET
admin_password_hash=scrypt:...from werkzeug generate_password_hash...
EOF

cat > "$OUT/miner-web/service-overrides.conf.example" <<'EOF'
# Optional systemd EnvironmentFile overrides for miner-web deployments.
# BLOODSTONE_PUBLIC_ROOT=https://your-domain.example
EOF

log "done — $(du -sh "$OUT" | awk '{print $1}')"