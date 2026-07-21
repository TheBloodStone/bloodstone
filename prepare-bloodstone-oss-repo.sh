#!/usr/bin/env bash
# Assemble a publishable open-source snapshot of the Bloodstone project.
set -euo pipefail

SRC_ROOT="${BLOODSTONE_SRC_ROOT:-/root}"
OUT="${BLOODSTONE_OSS_OUT:-/root/bloodstone-repo}"
STAMP="$(date -u +%Y%m%d)"

log() { echo "[bloodstone-oss] $*" >&2; }

cd /root

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
  --exclude 'chain_mesh.db'
  --exclude 'dtn_forward_queue'
  --exclude '__pycache__'
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
GIT_BACKUP=""
META_BACKUP=""
if [[ -d "$OUT/.git" ]]; then
  GIT_BACKUP="$(mktemp -d)"
  cp -a "$OUT/.git" "$GIT_BACKUP/"
  log "preserved existing git metadata"
fi
if [[ -f "$OUT/README.md" || -f "$OUT/LICENSE" || -f "$OUT/CONTRIBUTING.md" ]]; then
  META_BACKUP="$(mktemp -d)"
  for f in README.md LICENSE CONTRIBUTING.md .gitignore DEPLOY_KEY.pub prepare-bloodstone-oss-repo.sh push-bloodstone-oss.sh; do
    [[ -f "$OUT/$f" ]] && cp -a "$OUT/$f" "$META_BACKUP/"
  done
fi
rm -rf "$OUT"
mkdir -p "$OUT/ops" "$OUT/downloads"
if [[ -n "$GIT_BACKUP" && -d "$GIT_BACKUP/.git" ]]; then
  cp -a "$GIT_BACKUP/.git" "$OUT/.git"
  rm -rf "$GIT_BACKUP"
fi
if [[ -n "$META_BACKUP" ]]; then
  cp -a "$META_BACKUP/"* "$OUT/" 2>/dev/null || true
  rm -rf "$META_BACKUP"
fi
if [[ ! -f "$OUT/prepare-bloodstone-oss-repo.sh" && -f "$SRC_ROOT/prepare-bloodstone-oss-repo.sh" ]]; then
  cp -f "$SRC_ROOT/prepare-bloodstone-oss-repo.sh" "$OUT/"
fi

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

# Installer packages (auditable surfaces — not the flat ops dump)
mkdir -p "$OUT/packages/linux-node"
if [[ -d "$SRC_ROOT/packages/linux-node" ]]; then
  rsync -a "$SRC_ROOT/packages/linux-node/" "$OUT/packages/linux-node/"
  [[ -f "$SRC_ROOT/packages/README.md" ]] && cp -f "$SRC_ROOT/packages/README.md" "$OUT/packages/"
  [[ -f "$SRC_ROOT/AUDITOR-MAP.md" ]] && cp -f "$SRC_ROOT/AUDITOR-MAP.md" "$OUT/"
  log "packages/linux-node + AUDITOR-MAP.md"
fi
copy_tree chain_mesh "$SRC_ROOT/chain_mesh"
copy_tree ops/bloodstone-pi-fleet "$SRC_ROOT/ops/bloodstone-pi-fleet"

# Shared ops scripts (VPS pool, stratum, builds, watchdogs)
for f in \
  bloodstone_downloads.py \
  bloodstone_beta_codes.py \
  bloodstone_branding.py \
  bloodstone_broadcast.py \
  bloodstone_rich_list.py \
  bloodstone_time.py \
  bloodstone-gitlab-lib.sh \
  build-bloodstone-miner-android-apk.sh \
  publish-android-miner-web-bundle.sh \
  publish-bloodstone-chain-bootstrap.sh \
  promote-beta-to-stable.sh \
  submit-bloodstone-gitlab-release.sh \
  generate-beta-tester-code.sh \
  publish-quasar-docs.sh \
  sync-quasar-braid-index.py \
  rehearse-quasar-fork.py \
  sync-blurt-convergence.py \
  emit-quasar-witness-capsule.py \
  bloodstone_quasar.py \
  bloodstone_quasar_api.py \
  bloodstone_quasar_enforcement.py \
  bloodstone_quasar_signaling.py \
  bloodstone_quasar_fork.py \
  bloodstone_quasar_tripwire.py \
  bloodstone_braid_index.py \
  bloodstone_witness.py \
  bloodstone_lan_echo.py \
  bloodstone-dtn-mdns.py \
  bloodstone-dtn-tls-proxy.py \
  setup-dtn-pi-tls.sh \
  build-bloodstone-pi-fleet-convergence-package.sh \
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