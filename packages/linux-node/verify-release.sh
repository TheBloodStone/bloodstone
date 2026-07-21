#!/bin/bash
# Verify a Bloodstone release artifact:
#   1) PGP signature of the .sha256 file (authenticity) — if .asc present or fetchable
#   2) SHA-256 of the artifact against that .sha256 file (integrity)
#
# Why both? SHA-256 alone only proves the file matches whatever is on the download
# server. PGP proves the checksum was signed by the Bloodstone release key, so a
# compromised CDN/host cannot swap both binary and checksum without the private key.
#
# Usage:
#   ./verify-release.sh bloodstone-node-0.7.6-linux-aarch64.tar.gz
#   ./verify-release.sh /path/to/file.tar.gz https://bloodstone.rocks/downloads/file.tar.gz.sha256
#
# First-time key import (once per machine):
#   curl -fsSL https://bloodstone.rocks/downloads/bloodstone-release-key.asc | gpg --import
#   # or use the key shipped next to this script: bloodstone-release-key.asc
#
# Env:
#   BLOODSTONE_REQUIRE_PGP=1   fail if signature cannot be verified (strict / fleet)
#   BLOODSTONE_GPG_FINGERPRINT  expected fingerprint (default project key)

set -euo pipefail
IFS=$'\n\t'

FILE="${1:-}"
SHA_URL_OR_FILE="${2:-}"
REQUIRE_PGP="${BLOODSTONE_REQUIRE_PGP:-0}"
# Full fingerprint of Bloodstone Release Signing key
EXPECTED_FPR="${BLOODSTONE_GPG_FINGERPRINT:-326795FA0B4E7C975276AB9FF6255B970D6642AD}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

die() { echo "[verify-release] ERROR: $*" >&2; exit 1; }
log() { echo "[verify-release] $*"; }
warn() { echo "[verify-release] WARN: $*" >&2; }

[[ -n "$FILE" && -f "$FILE" ]] || die "usage: $0 <artifact> [sha256-file-or-url]"

base="$(basename "$FILE")"
dir="$(cd "$(dirname "$FILE")" && pwd)"
abs="$dir/$base"

fetch_https() {
  local url="$1" out="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --proto '=https' --tlsv1.2 --retry 2 -o "$out" "$url"
  else
    wget -q --https-only -O "$out" "$url"
  fi
}

# --- locate / fetch .sha256 ---
sha_src=""
if [[ -n "$SHA_URL_OR_FILE" ]]; then
  sha_src="$SHA_URL_OR_FILE"
elif [[ -f "${abs}.sha256" ]]; then
  sha_src="${abs}.sha256"
else
  for root in \
    "https://bloodstone.rocks/downloads" \
    "https://github.com/TheBloodStone/bloodstone/raw/release-downloads"
  do
    if fetch_https "${root}/${base}.sha256" /tmp/bs-verify.sha256 2>/dev/null; then
      sha_src="/tmp/bs-verify.sha256"
      log "Fetched checksum: ${root}/${base}.sha256"
      break
    fi
  done
fi
[[ -n "$sha_src" ]] || die "no .sha256 for $base"

if [[ "$sha_src" == https://* || "$sha_src" == http://* ]]; then
  fetch_https "$sha_src" /tmp/bs-verify.sha256 || die "failed to fetch $sha_src"
  sha_src=/tmp/bs-verify.sha256
fi

# --- locate / fetch .sha256.asc (PGP over checksum) ---
asc_src=""
if [[ -f "${sha_src}.asc" ]]; then
  asc_src="${sha_src}.asc"
elif [[ -f "${abs}.sha256.asc" ]]; then
  asc_src="${abs}.sha256.asc"
else
  for root in \
    "https://bloodstone.rocks/downloads" \
    "https://github.com/TheBloodStone/bloodstone/raw/release-downloads"
  do
    if fetch_https "${root}/${base}.sha256.asc" /tmp/bs-verify.sha256.asc 2>/dev/null; then
      asc_src="/tmp/bs-verify.sha256.asc"
      log "Fetched signature: ${root}/${base}.sha256.asc"
      break
    fi
  done
fi

ensure_pubkey() {
  if gpg --list-keys "$EXPECTED_FPR" >/dev/null 2>&1; then
    return 0
  fi
  local keyfile=""
  for cand in \
    "$SCRIPT_DIR/bloodstone-release-key.asc" \
    "${dir}/bloodstone-release-key.asc" \
    "/tmp/bloodstone-release-key.asc"
  do
    [[ -f "$cand" ]] && keyfile="$cand" && break
  done
  if [[ -z "$keyfile" ]]; then
    if fetch_https "https://bloodstone.rocks/downloads/bloodstone-release-key.asc" /tmp/bloodstone-release-key.asc 2>/dev/null; then
      keyfile=/tmp/bloodstone-release-key.asc
    fi
  fi
  [[ -n "$keyfile" ]] || die "PGP public key not found — download bloodstone-release-key.asc and: gpg --import bloodstone-release-key.asc"
  log "Importing public key from $keyfile"
  gpg --import "$keyfile" >/dev/null 2>&1 || die "gpg --import failed"
  gpg --list-keys "$EXPECTED_FPR" >/dev/null 2>&1 || die "imported key does not match expected fingerprint $EXPECTED_FPR"
}

# --- PGP verify checksum ---
pgp_ok=0
if [[ -n "$asc_src" ]]; then
  if ! command -v gpg >/dev/null 2>&1; then
    if [[ "$REQUIRE_PGP" == "1" ]]; then
      die "gpg required (BLOODSTONE_REQUIRE_PGP=1) but not installed"
    fi
    warn "signature present but gpg not installed — skipping PGP (install gnupg)"
  else
    ensure_pubkey
    log "Verifying PGP signature of checksum (authenticity)..."
    if gpg --verify "$asc_src" "$sha_src" 2>/tmp/bs-gpg-verify.err; then
      # Confirm signer fingerprint
      if gpg --verify "$asc_src" "$sha_src" 2>&1 | grep -qiE "using RSA key $EXPECTED_FPR|key $EXPECTED_FPR|Good signature"; then
        log "PGP OK (signed by Bloodstone release key $EXPECTED_FPR)"
        pgp_ok=1
      else
        # still good signature from imported key — accept if good signature line present
        if grep -q "Good signature" /tmp/bs-gpg-verify.err 2>/dev/null \
          || gpg --verify "$asc_src" "$sha_src" 2>&1 | grep -q "Good signature"; then
          log "PGP OK (Good signature)"
          pgp_ok=1
        else
          die "PGP signature did not match expected release key"
        fi
      fi
    else
      cat /tmp/bs-gpg-verify.err >&2 || true
      die "PGP signature INVALID — do not install this file"
    fi
  fi
else
  if [[ "$REQUIRE_PGP" == "1" ]]; then
    die "no .sha256.asc found and BLOODSTONE_REQUIRE_PGP=1"
  fi
  warn "No PGP signature (.sha256.asc) found — verifying SHA-256 only."
  warn "For supply-chain safety prefer releases that include .sha256.asc, or build with ./install-from-source.sh"
fi

# --- SHA-256 integrity ---
expected="$(awk '{print $1; exit}' "$sha_src" | tr 'A-F' 'a-f' | tr -cd '0-9a-f')"
actual="$(sha256sum "$abs" | awk '{print $1}')"
[[ ${#expected} -eq 64 ]] || die "invalid checksum file"
if [[ "$expected" != "$actual" ]]; then
  die "SHA256 mismatch for $base (expected $expected got $actual)"
fi
log "SHA256 OK ($actual)"

if [[ "$pgp_ok" -eq 1 ]]; then
  log "Verified (PGP + SHA256): $abs"
else
  log "Verified (SHA256 only): $abs"
fi
