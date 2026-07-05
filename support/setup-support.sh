#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [ ! -d venv ]; then
  python3 -m venv venv
fi

./venv/bin/pip install -q -U pip
./venv/bin/pip install -q flask gunicorn werkzeug

if [ ! -f secrets.conf ]; then
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  ADMIN_PW="${SUPPORT_ADMIN_PASSWORD:-BloodstoneSupport!}"
  HASH=$(./venv/bin/python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('$ADMIN_PW'))")
  cat > secrets.conf <<EOF
# Bloodstone support — keep private
secret_key=$SECRET
admin_password_hash=$HASH
EOF
  chmod 600 secrets.conf
  echo "[*] Created secrets.conf (admin password: $ADMIN_PW)"
  echo "[*] Change via SUPPORT_ADMIN_PASSWORD=... when re-running setup."
else
  echo "[*] secrets.conf already exists — not overwriting"
fi

echo "[*] Support venv ready"