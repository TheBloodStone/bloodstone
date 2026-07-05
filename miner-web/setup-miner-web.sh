#!/bin/bash
set -euo pipefail

DIR=/root/bloodstone-miner-web
SECRETS="$DIR/secrets.conf"

if [[ -f "$SECRETS" ]]; then
  echo "Secrets exist: $SECRETS"
  exit 0
fi

if [[ ! -d "$DIR/venv" ]]; then
  python3 -m venv "$DIR/venv"
  "$DIR/venv/bin/pip" install -q -r "$DIR/requirements.txt"
fi

"$DIR/venv/bin/python3" - <<'PY'
import secrets
from pathlib import Path
from werkzeug.security import generate_password_hash

root = Path("/root/bloodstone-miner-web")
admin_pass = secrets.token_urlsafe(10)
secret_key = secrets.token_hex(32)

(root / "secrets.conf").write_text(
    f"secret_key={secret_key}\n"
    f"admin_password_hash={generate_password_hash(admin_pass)}\n",
    encoding="utf-8",
)
(root / "secrets.conf").chmod(0o600)
(root / "ADMIN.txt").write_text(
    f"Bloodstone Mining Dashboard admin\n"
    f"URL: http://64.188.22.190:8893/admin\n"
    f"Password: {admin_pass}\n",
    encoding="utf-8",
)
(root / "ADMIN.txt").chmod(0o600)
print(admin_pass)
PY

echo "Admin login saved to $DIR/ADMIN.txt"