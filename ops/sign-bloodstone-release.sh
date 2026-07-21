#!/bin/bash
# Sign Bloodstone release artifacts with the project PGP key.
#
# Signs the .sha256 checksum file (Bitcoin-style), producing .sha256.asc
# Also signs the artifact itself if BLOODSTONE_SIGN_BINARY=1.
#
# Usage:
#   sign-bloodstone-release.sh path/to/file.tar.gz
#   sign-bloodstone-release.sh path/to/file.tar.gz.sha256   # sign checksum only
#   sign-bloodstone-release.sh --all-downloads              # sign all .sha256 under downloads/
#
# Env:
#   BLOODSTONE_GNUPGHOME  default /root/.bloodstone/gnupg-bootstrap
#   BLOODSTONE_GPG_KEY_ID default F6255B970D6642AD
#   BLOODSTONE_SIGN_BINARY=1  also create file.asc for the binary

set -euo pipefail
IFS=$'\n\t'

export GNUPGHOME="${BLOODSTONE_GNUPGHOME:-/root/.bloodstone/gnupg-bootstrap}"
KEY_ID="${BLOODSTONE_GPG_KEY_ID:-F6255B970D6642AD}"
SIGN_BINARY="${BLOODSTONE_SIGN_BINARY:-0}"
OUT_DL="${BLOODSTONE_DOWNLOADS_DIR:-/var/www/bloodstone/downloads}"

log() { echo "[sign-release] $*"; }
die() { echo "[sign-release] ERROR: $*" >&2; exit 1; }

[[ -d "$GNUPGHOME" ]] || die "GNUPGHOME missing: $GNUPGHOME"
gpg --homedir "$GNUPGHOME" --list-secret-keys "$KEY_ID" >/dev/null 2>&1 \
  || die "secret key $KEY_ID not found in $GNUPGHOME"

sign_sha_file() {
  local sha="$1"
  [[ -f "$sha" ]] || die "missing $sha"
  local asc="${sha}.asc"
  gpg --homedir "$GNUPGHOME" --batch --yes --local-user "$KEY_ID" \
    --detach-sign --armor -o "$asc" "$sha"
  log "signed $asc"
  # quick self-verify
  gpg --homedir "$GNUPGHOME" --verify "$asc" "$sha" >/dev/null 2>&1 \
    || die "self-verify failed for $asc"
}

sign_artifact() {
  local f="$1"
  [[ -f "$f" ]] || die "missing $f"

  local sha="${f}.sha256"
  if [[ ! -f "$sha" ]]; then
    log "creating $sha"
    (cd "$(dirname "$f")" && sha256sum "$(basename "$f")" | awk '{print $1}') > "$sha"
    # prefer "hash  filename" format for sha256sum -c compatibility
    (cd "$(dirname "$f")" && sha256sum "$(basename "$f")") > "$sha"
  fi

  sign_sha_file "$sha"

  if [[ "$SIGN_BINARY" == "1" ]]; then
    gpg --homedir "$GNUPGHOME" --batch --yes --local-user "$KEY_ID" \
      --detach-sign --armor -o "${f}.asc" "$f"
    log "signed ${f}.asc"
  fi
}

if [[ "${1:-}" == "--all-downloads" ]]; then
  n=0
  while IFS= read -r -d '' sha; do
    # skip already-signed if fresh? always re-sign
    sign_sha_file "$sha"
    n=$((n + 1))
  done < <(find "$OUT_DL" -maxdepth 1 -type f -name '*.sha256' ! -name '*.asc' -print0 2>/dev/null)
  log "signed $n checksum files under $OUT_DL"
  exit 0
fi

[[ $# -ge 1 ]] || die "usage: $0 <artifact|artifact.sha256> | --all-downloads"

for arg in "$@"; do
  if [[ "$arg" == *.sha256 ]]; then
    sign_sha_file "$arg"
  else
    sign_artifact "$arg"
  fi
done

log "done — publish public key: bloodstone-release-key.asc (key $KEY_ID)"
