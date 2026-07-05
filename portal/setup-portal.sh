#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [ ! -d venv ]; then
  python3 -m venv venv
fi

./venv/bin/pip install -q -U pip
./venv/bin/pip install -q flask gunicorn requests

echo "[*] Portal venv ready: $DIR/venv"