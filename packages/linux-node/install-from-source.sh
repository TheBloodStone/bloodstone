#!/bin/bash
# Build Bloodstone node binaries from the public GitHub monorepo, then set up
# the same layout as the prebuilt tarball (start-node.sh + bootstrap helper).
#
# Transparency path (DeepSeek / auditor recommendation):
#   Users see source pulled from https://github.com/TheBloodStone/bloodstone
#   and compile bloodstoned locally instead of trusting a prebuilt binary.
#
# Usage:
#   ./install-from-source.sh              # clone + build + install into ./ (or PREFIX)
#   BLOODSTONE_SRC_DIR=/path ./install-from-source.sh   # use existing checkout
#   PREFIX=$HOME/bloodstone-node ./install-from-source.sh
#
# After success:
#   cd "$PREFIX" && ./start-node.sh
#
# Notes:
#   - On Raspberry Pi 4/5 this can take a long time (often 1–4+ hours).
#   - Requires build tools (see ensure_deps). Network for git clone + bootstrap later.
#   - Prebuilt tarballs remain available for convenience; this path maximises transparency.

set -euo pipefail
IFS=$'\n\t'
umask 077

REPO_URL="${BLOODSTONE_GIT_URL:-https://github.com/TheBloodStone/bloodstone.git}"
REPO_REF="${BLOODSTONE_GIT_REF:-main}"
PREFIX="${PREFIX:-}"
MAKE_JOBS="${MAKE_JOBS:-$(nproc 2>/dev/null || echo 2)}"
SKIP_DEPS="${BLOODSTONE_SKIP_DEPS:-0}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

log() { echo "[install-from-source] $*"; }
die() { echo "[install-from-source] ERROR: $*" >&2; exit 1; }

arch_triple() {
  local m
  m="$(uname -m)"
  case "$m" in
    x86_64|amd64) echo "linux-x86_64" ;;
    aarch64|arm64) echo "linux-aarch64" ;;
    *) echo "linux-${m}" ;;
  esac
}

ensure_deps() {
  if [[ "$SKIP_DEPS" == "1" ]]; then
    log "Skipping dependency install (BLOODSTONE_SKIP_DEPS=1)"
    return 0
  fi
  if ! command -v sudo >/dev/null 2>&1 && [[ "$(id -u)" -ne 0 ]]; then
    log "WARN: no sudo — install build deps yourself if configure fails"
    return 0
  fi
  local run=()
  if [[ "$(id -u)" -eq 0 ]]; then
    run=()
  else
    run=(sudo)
  fi
  if command -v apt-get >/dev/null 2>&1; then
    log "Installing build dependencies (Debian/Ubuntu/Raspberry Pi OS)…"
    "${run[@]}" apt-get update -qq
    "${run[@]}" DEBIAN_FRONTEND=noninteractive apt-get install -y \
      build-essential libtool autotools-dev automake pkg-config bsdmainutils \
      python3 git curl ca-certificates \
      libssl-dev libevent-dev libboost-system-dev libboost-filesystem-dev \
      libboost-chrono-dev libboost-test-dev libboost-thread-dev \
      libdb-dev libdb++-dev libminiupnpc-dev libnatpmp-dev libzmq3-dev \
      libsqlite3-dev 2>/dev/null \
      || "${run[@]}" DEBIAN_FRONTEND=noninteractive apt-get install -y \
        build-essential libtool autotools-dev automake pkg-config bsdmainutils \
        python3 git curl ca-certificates \
        libssl-dev libevent-dev libboost-all-dev libdb++-dev
  else
    log "WARN: not apt — ensure C++ toolchain, Boost, OpenSSL, libevent, Berkeley DB are installed"
  fi
}

resolve_core_dir() {
  local root="$1"
  if [[ -f "$root/core/configure.ac" ]]; then
    echo "$root/core"
  elif [[ -f "$root/configure.ac" && -f "$root/src/chainparams.cpp" ]]; then
    echo "$root"
  else
    die "No core/ or Bitcoin-style tree under $root"
  fi
}

clone_or_update() {
  local dest="$1"
  if [[ -n "${BLOODSTONE_SRC_DIR:-}" ]]; then
    [[ -d "$BLOODSTONE_SRC_DIR" ]] || die "BLOODSTONE_SRC_DIR not a directory: $BLOODSTONE_SRC_DIR"
    log "Using existing source: $BLOODSTONE_SRC_DIR"
    echo "$BLOODSTONE_SRC_DIR"
    return 0
  fi
  if [[ -d "$dest/.git" ]]; then
    log "Updating existing clone $dest (ref $REPO_REF)…"
    git -C "$dest" fetch --depth 1 origin "$REPO_REF" || git -C "$dest" fetch origin
    git -C "$dest" checkout "$REPO_REF" 2>/dev/null || git -C "$dest" checkout -B "$REPO_REF" "origin/$REPO_REF"
    git -C "$dest" pull --ff-only 2>/dev/null || true
  else
    log "Cloning public monorepo (this is intentional — you can watch git fetch the OSS tree):"
    log "  $REPO_URL  @ $REPO_REF"
    mkdir -p "$(dirname "$dest")"
    git clone --depth 1 --branch "$REPO_REF" "$REPO_URL" "$dest" \
      || git clone --depth 1 "$REPO_URL" "$dest"
  fi
  echo "$dest"
}

build_core() {
  local core="$1"
  log "Building in $core (jobs=$MAKE_JOBS)…"
  cd "$core"
  if [[ ! -f configure && -f autogen.sh ]]; then
    ./autogen.sh
  elif [[ ! -f configure ]]; then
    die "No autogen.sh/configure in $core"
  fi
  # Prefer clean out-of-tree if build/ exists from a prior failed run
  ./configure --prefix=/usr/local --without-gui --disable-tests --disable-bench \
    ${BLOODSTONE_CONFIGURE_ARGS:-} \
    || ./configure --without-gui --disable-tests --disable-bench ${BLOODSTONE_CONFIGURE_ARGS:-}
  make -j"$MAKE_JOBS"
  [[ -x src/bloodstoned ]] || [[ -x src/spacexpansed ]] || die "bloodstoned binary not produced"
}

install_layout() {
  local core="$1"
  local dest="$2"
  local daemon cli
  if [[ -x "$core/src/bloodstoned" ]]; then
    daemon="$core/src/bloodstoned"
  else
    daemon="$core/src/spacexpansed"
  fi
  if [[ -x "$core/src/bloodstone-cli" ]]; then
    cli="$core/src/bloodstone-cli"
  elif [[ -x "$core/src/spacexpanse-cli" ]]; then
    cli="$core/src/spacexpanse-cli"
  else
    cli=""
  fi

  mkdir -p "$dest/bin"
  cp -a "$daemon" "$dest/bin/bloodstoned"
  chmod 755 "$dest/bin/bloodstoned"
  if [[ -n "$cli" ]]; then
    cp -a "$cli" "$dest/bin/bloodstone-cli"
    chmod 755 "$dest/bin/bloodstone-cli"
  fi

  # Installer scripts from this package tree (or next to this script)
  for f in start-node.sh install-chain-bootstrap.sh bloodstone.conf.example; do
    if [[ -f "$SCRIPT_DIR/$f" ]]; then
      cp -a "$SCRIPT_DIR/$f" "$dest/$f"
    fi
  done
  chmod 755 "$dest/start-node.sh" "$dest/install-chain-bootstrap.sh" 2>/dev/null || true

  # Record provenance for auditors
  {
    echo "built_from_source=1"
    echo "repo_url=${REPO_URL}"
    echo "repo_ref=${REPO_REF}"
    echo "built_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "host=$(uname -a)"
    if [[ -d "${SRC_ROOT:-}/.git" ]]; then
      echo "git_commit=$(git -C "$SRC_ROOT" rev-parse HEAD 2>/dev/null || true)"
    fi
    echo "daemon_sha256=$(sha256sum "$dest/bin/bloodstoned" | awk '{print $1}')"
  } > "$dest/BUILD-PROVENANCE.txt"
  chmod 644 "$dest/BUILD-PROVENANCE.txt"

  cat > "$dest/README-FROM-SOURCE.txt" <<EOF
Bloodstone node — built from public source
==========================================

This install was produced by install-from-source.sh (not a prebuilt binary drop).

Repository: ${REPO_URL}
Ref:        ${REPO_REF}
Provenance: BUILD-PROVENANCE.txt

Start:
  ./start-node.sh

RPC credentials:
  First run creates ~/.bloodstone/bloodstone.conf with a random rpcpassword
  and mode 600. Change credentials before exposing RPC on a network.

Binary vs source:
  Prebuilt tarballs are convenience builds. This path maximises transparency
  by compiling bloodstoned on your machine from the monorepo you can inspect.
EOF

  log "Installed layout → $dest"
  log "  bin/bloodstoned"
  [[ -x "$dest/bin/bloodstone-cli" ]] && log "  bin/bloodstone-cli"
  log "  start-node.sh / install-chain-bootstrap.sh"
  log "  BUILD-PROVENANCE.txt (git + binary hash)"
}

main() {
  log "=== Bloodstone from-source install ==="
  log "Goal: clone public monorepo, compile bloodstoned, install runner scripts"
  ensure_deps

  local work src_root core_dir
  work="${BLOODSTONE_BUILD_WORK:-$HOME/bloodstone-src-build}"
  src_root="$(clone_or_update "$work/bloodstone")"
  SRC_ROOT="$src_root"
  core_dir="$(resolve_core_dir "$src_root")"
  log "Core tree: $core_dir"

  build_core "$core_dir"

  if [[ -z "$PREFIX" ]]; then
    PREFIX="${SCRIPT_DIR}/bloodstone-node-from-source-$(arch_triple)"
  fi
  install_layout "$core_dir" "$PREFIX"

  log ""
  log "Done. Next:"
  log "  cd \"$PREFIX\""
  log "  ./start-node.sh"
  log ""
  log "Optional seed override: BLOODSTONE_SEEDS=\"ip:17333\" ./start-node.sh"
}

main "$@"
