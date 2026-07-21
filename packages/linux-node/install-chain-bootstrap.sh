#!/bin/bash
# Shared chain bootstrap for headless Bloodstone nodes (Pi ARM64, Linux x86_64).
# Sourced or exec'd from start-node.sh. Keeps wallets; only refreshes chain data.
#
# Env:
#   BLOODSTONE_DATADIR                 default ~/.bloodstone
#   BLOODSTONE_CHAIN_BOOTSTRAP_URL     snapshot URL
#   BLOODSTONE_SKIP_BOOTSTRAP=1        skip (full P2P IBD)
#   BLOODSTONE_FORCE_BOOTSTRAP=1       reinstall even if data exists
#   BLOODSTONE_MIN_BOOTSTRAP_HEIGHT    reinstall if marker below this (default 10200)
#   BLOODSTONE_PUBLIC_ROOT             default https://bloodstone.rocks
#   BLOODSTONE_BOOTSTRAP_ALLOW_UNVERIFIED=1  emergency only
#
# Hardened (quick-pass audit 0.7.6): fixed shebang, IFS, HTTPS curl flags,
# clear SHA256 failures, tar extract without ownership/perms from archive,
# reject absolute/traversal/symlink members.

set -euo pipefail
IFS=$'\n\t'
umask 077

PUBLIC_ROOT="${BLOODSTONE_PUBLIC_ROOT:-https://bloodstone.rocks}"
BOOTSTRAP_URL="${BLOODSTONE_CHAIN_BOOTSTRAP_URL:-${PUBLIC_ROOT}/downloads/bloodstone-chain-bootstrap-latest.tar.gz}"
BOOTSTRAP_SHA_URL="${BLOODSTONE_CHAIN_BOOTSTRAP_SHA_URL:-${BOOTSTRAP_URL}.sha256}"
SKIP_BOOTSTRAP="${BLOODSTONE_SKIP_BOOTSTRAP:-0}"
FORCE_BOOTSTRAP="${BLOODSTONE_FORCE_BOOTSTRAP:-0}"
MIN_BOOTSTRAP_HEIGHT="${BLOODSTONE_MIN_BOOTSTRAP_HEIGHT:-10200}"
DATADIR="${BLOODSTONE_DATADIR:-${HOME}/.bloodstone}"

log() {
  echo "[node-bootstrap] $*"
  if command -v logger >/dev/null 2>&1; then
    logger -t node-bootstrap -- "$*" 2>/dev/null || true
  fi
}

die() {
  echo "[node-bootstrap] ERROR: $*" >&2
  if command -v logger >/dev/null 2>&1; then
    logger -t node-bootstrap -p user.err -- "ERROR: $*" 2>/dev/null || true
  fi
  # Best-effort kernel log when stderr may be discarded
  if [[ -w /dev/kmsg ]]; then
    echo "node-bootstrap: ERROR: $*" >/dev/kmsg 2>/dev/null || true
  fi
  exit 1
}

needs_bootstrap() {
  if [[ "$FORCE_BOOTSTRAP" == "1" ]]; then
    return 0
  fi
  if [[ ! -d "${DATADIR}/blocks" ]] || [[ ! -d "${DATADIR}/chainstate" ]]; then
    return 0
  fi
  if [[ -f "${DATADIR}/.bootstrap-height" ]]; then
    local h
    h="$(tr -cd '0-9' < "${DATADIR}/.bootstrap-height" || true)"
    if [[ -n "$h" && "$h" -lt "$MIN_BOOTSTRAP_HEIGHT" ]]; then
      log "Existing bootstrap height $h < $MIN_BOOTSTRAP_HEIGHT — reinstalling"
      return 0
    fi
  fi
  return 1
}

_curl_get() {
  # $1=url $2=output
  local url="$1" out="$2"
  # Prefer strict HTTPS; fall back without --cert-status (not on all curl builds).
  if curl --help 2>&1 | grep -q -- '--proto'; then
    if curl --help 2>&1 | grep -q -- '--cert-status'; then
      curl -fsSL --proto '=https' --tlsv1.2 --cert-status --retry 3 --retry-delay 2 -o "$out" "$url" \
        || curl -fsSL --proto '=https' --tlsv1.2 --retry 3 --retry-delay 2 -o "$out" "$url"
    else
      curl -fsSL --proto '=https' --tlsv1.2 --retry 3 --retry-delay 2 -o "$out" "$url"
    fi
  else
    curl -fsSL --retry 3 --retry-delay 2 -o "$out" "$url"
  fi
}

install_chain_bootstrap() {
  if [[ "$SKIP_BOOTSTRAP" == "1" ]]; then
    log "Skipping chain bootstrap (BLOODSTONE_SKIP_BOOTSTRAP=1)"
    return 0
  fi
  if ! needs_bootstrap; then
    log "Chain data present under $DATADIR — skip bootstrap (BLOODSTONE_FORCE_BOOTSTRAP=1 to reinstall)"
    return 0
  fi

  mkdir -p "$DATADIR"
  chmod 700 "$DATADIR" 2>/dev/null || true
  # Wipe chain only (never wallets).
  for name in blocks chainstate indexes mempool.dat fee_estimates.dat .lock bloodstoned.pid \
    .bootstrap-height .bootstrap-includes-index .bootstrap-includes-txindex .bootstrap-reindex; do
    rm -rf "${DATADIR:?}/${name}"
  done

  local tmp archive shafile
  tmp="$(mktemp -d)"
  archive="${tmp}/bootstrap.tar.gz"
  shafile="${tmp}/bootstrap.sha256"
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp'" RETURN

  log "Downloading full chain bootstrap:"
  log "  $BOOTSTRAP_URL"
  if command -v curl >/dev/null 2>&1; then
    _curl_get "$BOOTSTRAP_URL" "$archive" || die "download failed: $BOOTSTRAP_URL"
  elif command -v wget >/dev/null 2>&1; then
    wget -q --https-only -O "$archive" "$BOOTSTRAP_URL" || die "download failed: $BOOTSTRAP_URL"
  else
    die "curl or wget required for chain bootstrap"
  fi
  local size
  size="$(wc -c < "$archive" | tr -d ' ')"
  log "Downloaded ${size} bytes"

  # Integrity: require published .sha256 unless emergency override
  local allow_unverified="${BLOODSTONE_BOOTSTRAP_ALLOW_UNVERIFIED:-0}"
  local sha_ok=0
  if command -v curl >/dev/null 2>&1; then
    if _curl_get "$BOOTSTRAP_SHA_URL" "$shafile" 2>/dev/null; then
      sha_ok=1
    fi
  elif command -v wget >/dev/null 2>&1; then
    if wget -q --https-only -O "$shafile" "$BOOTSTRAP_SHA_URL" 2>/dev/null; then
      sha_ok=1
    fi
  fi

  if [[ "$sha_ok" -eq 1 ]]; then
    local expected actual
    expected="$(awk '{print $1; exit}' "$shafile" | tr 'A-F' 'a-f' | tr -cd '0-9a-f')"
    actual="$(sha256sum "$archive" | awk '{print $1}')"
    if [[ -z "$expected" || ${#expected} -ne 64 ]]; then
      die "bootstrap checksum file invalid"
    fi
    if [[ "$expected" != "$actual" ]]; then
      die "bootstrap SHA256 mismatch (expected $expected got $actual)"
    fi
    log "SHA256 OK"
  else
    if [[ "$allow_unverified" == "1" ]]; then
      log "WARN: could not verify SHA256 — continuing (BLOODSTONE_BOOTSTRAP_ALLOW_UNVERIFIED=1)"
    else
      die "bootstrap checksum download failed — refusing extract. Set BLOODSTONE_BOOTSTRAP_ALLOW_UNVERIFIED=1 only in emergencies."
    fi
  fi

  # Reject path traversal, absolute paths, and symlinks (tar slip / link abuse)
  local member unsafe=0
  while IFS= read -r member; do
    if [[ "$member" == /* ]] || [[ "$member" == ../* ]] || [[ "$member" == */../* ]] \
      || [[ "$member" == */.. ]] || [[ "$member" == .. ]]; then
      echo "Unsafe archive member: $member" >&2
      unsafe=1
      break
    fi
  done < <(tar -tzf "$archive" 2>/dev/null || true)
  if [[ "$unsafe" -ne 0 ]]; then
    die "archive rejected (path traversal / absolute paths)"
  fi
  # Reject symlink and hardlink members (GNU tar -t: first field type l or h)
  if tar -tvzf "$archive" 2>/dev/null | awk '{print substr($0,1,1)}' | grep -q '[lh]'; then
    die "archive rejected (contains symlink or hardlink members)"
  fi

  log "Extracting into $DATADIR ..."
  # Do not apply archive owner/mode (avoids privilege surprises under multi-user systems).
  # --no-overwrite-dir when supported (GNU tar); ignore if unavailable.
  if tar --help 2>&1 | grep -q -- '--no-overwrite-dir'; then
    tar -xzf "$archive" -C "$DATADIR" --no-same-owner --no-same-permissions --no-overwrite-dir
  else
    tar -xzf "$archive" -C "$DATADIR" --no-same-owner --no-same-permissions
  fi
  [[ -d "${DATADIR}/blocks" ]] || die "bootstrap extract failed — blocks/ missing"
  [[ -d "${DATADIR}/chainstate" ]] || log "WARN: chainstate missing — first start may reindex"

  local height="?"
  if [[ -f "${DATADIR}/.bootstrap-height" ]]; then
    height="$(tr -cd '0-9' < "${DATADIR}/.bootstrap-height")"
  fi
  log "Full chain bootstrap installed (height marker: ${height})"
  if [[ -d "${DATADIR}/indexes/txindex" ]]; then
    log "txindex included (good for explorers / deposit lookups)"
  fi
}

# When executed directly (not only sourced):
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  install_chain_bootstrap
fi
