#!/usr/bin/env bash
# Unified MFQ daemon pack builder entrypoint (monorepo).
#
# Target: ops/build-mfq-fork-daemons.sh --coin LRGK|AZURE|STONE
#
# Phase 1 (2026-07-30): stub that documents the contract and fails closed until
# forks/lrgk and forks/azure contain buildable trees (and STONE pin is defined).
# Operator host may still use the legacy VPS script until source lands.
#
# See: docs/mfq-daemons-manifest-v2.md, AUDITOR-MAP.md, forks/*/README.md
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COIN=""

usage() {
  cat <<'EOF'
Usage: ops/build-mfq-fork-daemons.sh --coin <STONE|LRGK|AZURE>

Builds Windows (or configured) daemon packs for Multi-Fork Qt from monorepo paths:

  STONE  -> core/ or chain/   (parent; auxpow chain id 1899)
  LRGK   -> forks/lrgk/       (auxpow chain id 1900)
  AZURE  -> forks/azure/      (auxpow chain id 1901)

Outputs (planned):
  downloads/mfq-daemons/<COIN>-win64.zip
  + .sha256
  + manifest.json provenance update (schema v2)

Status: STUB — full monorepo build not enabled until fork source trees land.
Legacy operator path (temporary): /root/build-mfq-fork-daemons-windows.sh
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --coin)
      COIN="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      usage
      exit 2
      ;;
  esac
done

COIN="$(echo "$COIN" | tr '[:lower:]' '[:upper:]')"
if [[ -z "$COIN" ]]; then
  usage
  exit 2
fi

case "$COIN" in
  STONE)
    SRC_PATH="core"
    CHAIN_ID=1899
    ;;
  LRGK)
    SRC_PATH="forks/lrgk"
    CHAIN_ID=1900
    ;;
  AZURE)
    SRC_PATH="forks/azure"
    CHAIN_ID=1901
    ;;
  *)
    echo "Unsupported --coin $COIN (add forks/<ticker> + chain id registry first)" >&2
    exit 2
    ;;
esac

echo "[build-mfq-fork-daemons] repo=$ROOT coin=$COIN path=$SRC_PATH auxpow_chain_id=$CHAIN_ID"

if [[ ! -d "$ROOT/$SRC_PATH" ]]; then
  echo "ERROR: missing monorepo path $SRC_PATH" >&2
  exit 1
fi

# Full tree gate: stub README-only dirs are not buildable
if [[ "$COIN" != "STONE" ]]; then
  if [[ ! -f "$ROOT/$SRC_PATH/src/bitcoind.cpp" && ! -f "$ROOT/$SRC_PATH/src/init.cpp" && ! -d "$ROOT/$SRC_PATH/src" ]]; then
    echo "ERROR: $SRC_PATH is a structure stub only (no consensus src/ yet)." >&2
    echo "Land full source before monorepo pack builds. Use operator legacy script until then." >&2
    exit 1
  fi
fi

echo "ERROR: monorepo MinGW pack build not wired yet (Phase 1 stub)." >&2
echo "When ready: cross-compile from $SRC_PATH, write zip+sha256, set provenance.source_commit=\$(git rev-parse HEAD)." >&2
exit 1
