#!/usr/bin/env bash
# Build a tree already patched by fork_builder.py prepare
set -euo pipefail
ROOT="${1:-.}"
cd "$ROOT"
[[ -d src ]] || { echo "usage: $0 /path/to/patched-core" >&2; exit 1; }
./autogen.sh
./configure --disable-tests --disable-bench --without-gui --with-incompatible-bdb \
  || ./configure --disable-tests --disable-bench --without-gui
make -j"$(nproc 2>/dev/null || echo 2)"
ls -la src/bloodstoned src/bloodstone-cli 2>/dev/null || ls -la src/*d src/*-cli 2>/dev/null || true
