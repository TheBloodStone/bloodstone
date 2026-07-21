#!/bin/bash
# Verify a downloaded release artifact against published SHA-256 (and PGP if present).
#
# DeepSeek recommendation: verify signatures before running binaries.
# Today: SHA-256 sidecars are the standard attestation for Bloodstone downloads.
# PGP: if FILE.asc or FILE.sig exists next to the file, gpg --verify is attempted.
#
# Usage:
#   ./verify-release.sh bloodstone-node-0.7.6-linux-aarch64.tar.gz
#   ./verify-release.sh /path/to/file.tar.gz https://bloodstone.rocks/downloads/file.tar.gz.sha256

set -euo pipefail
IFS=$'\n\t'

FILE="${1:-}"
SHA_URL_OR_FILE="${2:-}"

die() { echo "[verify-release] ERROR: $*" >&2; exit 1; }
log() { echo "[verify-release] $*"; }

[[ -n "$FILE" && -f "$FILE" ]] || die "usage: $0 <artifact> [sha256-file-or-url]"

base="$(basename "$FILE")"
dir="$(cd "$(dirname "$FILE")" && pwd)"
abs="$dir/$base"

# Resolve .sha256
sha_src=""
if [[ -n "$SHA_URL_OR_FILE" ]]; then
  sha_src="$SHA_URL_OR_FILE"
elif [[ -f "${abs}.sha256" ]]; then
  sha_src="${abs}.sha256"
elif [[ -f "${dir}/${base}.sha256" ]]; then
  sha_src="${dir}/${base}.sha256"
else
  # try public mirrors
  for root in \
    "https://bloodstone.rocks/downloads" \
    "https://github.com/TheBloodStone/bloodstone/raw/release-downloads"
  do
    if curl -fsSL --proto '=https' --tlsv1.2 -o /tmp/bs-verify.sha256 "${root}/${base}.sha256" 2>/dev/null; then
      sha_src="/tmp/bs-verify.sha256"
      log "Fetched checksum: ${root}/${base}.sha256"
      break
    fi
  done
fi

[[ -n "$sha_src" ]] || die "no .sha256 found for $base (publish sidecar or pass path/URL as arg 2)"

if [[ "$sha_src" == https://* || "$sha_src" == http://* ]]; then
  curl -fsSL --proto '=https' --tlsv1.2 -o /tmp/bs-verify.sha256 "$sha_src"
  sha_src=/tmp/bs-verify.sha256
fi

expected="$(awk '{print $1; exit}' "$sha_src" | tr 'A-F' 'a-f' | tr -cd '0-9a-f')"
actual="$(sha256sum "$abs" | awk '{print $1}')"
[[ ${#expected} -eq 64 ]] || die "invalid checksum file"
if [[ "$expected" != "$actual" ]]; then
  die "SHA256 mismatch for $base (expected $expected got $actual)"
fi
log "SHA256 OK ($actual)"

# Optional PGP / clearsign
sig=""
for cand in "${abs}.asc" "${abs}.sig" "${abs}.gpg"; do
  [[ -f "$cand" ]] && sig="$cand" && break
done
if [[ -n "$sig" ]]; then
  if command -v gpg >/dev/null 2>&1; then
    log "Verifying PGP signature: $sig"
    gpg --verify "$sig" "$abs"
    log "PGP OK"
  else
    log "WARN: signature file present ($sig) but gpg not installed"
  fi
else
  log "No PGP signature (.asc/.sig) next to artifact — SHA-256 only (normal for current releases)."
  log "For maximum trust: build with ./install-from-source.sh from github.com/TheBloodStone/bloodstone"
fi

log "Verified: $abs"
