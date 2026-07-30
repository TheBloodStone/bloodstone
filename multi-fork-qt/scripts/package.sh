#!/usr/bin/env bash
# Build release tarball for Multi-Fork Qt Wallet
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "${ROOT}/VERSION")"
NAME="bloodstone-multi-fork-qt-${VERSION}"
OUT_DIR="${1:-/tmp}"
STAGE="${OUT_DIR}/${NAME}"
rm -rf "${STAGE}"
mkdir -p "${STAGE}"

# Copy sources (no __pycache__)
rsync -a \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.git' \
  --exclude '*.egg-info' \
  "${ROOT}/main.py" \
  "${ROOT}/VERSION" \
  "${ROOT}/README.md" \
  "${ROOT}/requirements.txt" \
  "${ROOT}/bloodstone-multi-fork-qt.desktop" \
  "${ROOT}/bloodstone_mfq" \
  "${ROOT}/scripts" \
  "${ROOT}/resources" \
  "${STAGE}/"

# Wrapper
cat > "${STAGE}/bloodstone-multi-fork-qt" <<'EOF'
#!/usr/bin/env bash
ROOT="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
exec python3 "${ROOT}/main.py" "$@"
EOF
chmod +x "${STAGE}/bloodstone-multi-fork-qt" "${STAGE}/scripts/"*.sh "${STAGE}/main.py"

TAR="${OUT_DIR}/${NAME}.tar.gz"
tar -C "${OUT_DIR}" -czf "${TAR}" "${NAME}"
SHA="$(sha256sum "${TAR}" | awk '{print $1}')"
echo "${SHA}  ${NAME}.tar.gz" > "${TAR}.sha256"
echo "Wrote ${TAR}"
echo "SHA256 ${SHA}"
echo "${TAR}"
