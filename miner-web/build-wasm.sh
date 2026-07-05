#!/usr/bin/env bash
# Build browser miner WASM modules (neoscrypt + yespower) into static/lib/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
# Same yespower implementation as cpuminer-opt / bloodstoned (YESPOWER_1_0 = 10).
NEO="/root/bloodstone-chain/src/crypto"
YESPOWER="/root/cpuminer-opt-src/algo/yespower"
OUT="$ROOT/static/lib"

if [[ -f /root/emsdk/emsdk_env.sh ]]; then
  # shellcheck source=/dev/null
  source /root/emsdk/emsdk_env.sh
  if [[ -x /root/android-ndk-r26d/toolchains/llvm/prebuilt/linux-x86_64/python3/bin/python3 ]]; then
    export EMSDK_PYTHON=/root/android-ndk-r26d/toolchains/llvm/prebuilt/linux-x86_64/python3/bin/python3
  fi
else
  echo "emsdk not found at /root/emsdk — run: git clone https://github.com/emscripten-core/emsdk.git /root/emsdk && /root/emsdk/emsdk install latest && /root/emsdk/emsdk activate latest" >&2
  exit 1
fi

COMMON_FLAGS=(
  -O2
  -s EXPORTED_FUNCTIONS='["_malloc","_free"]'
  -s EXPORTED_RUNTIME_METHODS='["cwrap","HEAPU8"]'
  -s ALLOW_MEMORY_GROWTH=1
  -s MODULARIZE=1
  -s EXPORT_ES6=1
)

echo "[*] Building neoscrypt WASM..."
emcc "$ROOT/wasm/neoscrypt_stratum.c" "$NEO/neoscrypt.c" \
  -I"$NEO" -I/root/bloodstone-chain/src \
  "${COMMON_FLAGS[@]}" \
  -s EXPORTED_FUNCTIONS='["_neoscrypt_stratum_hash","_malloc","_free"]' \
  -s EXPORT_NAME=createNeoscryptModule \
  -o "$OUT/neoscrypt.js"

SHA="/root/cpuminer-opt-src/algo/sha"
echo "[*] Building yespower WASM (reference impl + portable SHA256 for emscripten)..."
emcc "$ROOT/wasm/yespower_stratum.c" \
  "$YESPOWER/yespower-ref.c" \
  "$SHA/hmac-sha256-hash.c" \
  "$SHA/sph_sha2.c" \
  -I"$ROOT/wasm/include" \
  -I"$YESPOWER" \
  -I"/root/cpuminer-opt-src" \
  -I"$SHA" \
  "${COMMON_FLAGS[@]}" \
  -s EXPORTED_FUNCTIONS='["_yespower_stratum_hash","_malloc","_free"]' \
  -s EXPORT_NAME=createYespowerModule \
  -o "$OUT/yespower.js"

echo "[*] Done: $OUT/neoscrypt.{js,wasm} $OUT/yespower.{js,wasm}"