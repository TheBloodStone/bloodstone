#!/usr/bin/env bash
# Wave Q — llama.cpp inference shim launcher + portal self-registration.
set -euo pipefail

ROOT="${BLOODSTONE_ROOT:-/root}"
ENV_FILE="${BLOODSTONE_CONVERGENCE_ENV:-/etc/bloodstone/convergence.env}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHIM_PY="${SCRIPT_DIR}/ai-inference-shim.py"

log() { echo "[ai-inference-shim] $*" >&2; }

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "$ENV_FILE"
  set +a
fi

NODE_ID="${DTN_NODE_ID:-$(hostname -s)}"
REGION="${DTN_DEFAULT_REGION:-lan}"
PORT="${AI_INFERENCE_PORT:-8081}"
LAN_PORT="${DTN_LAN_WEB_PORT:-8887}"
PUBLIC_ROOT="${BLOODSTONE_PUBLIC_ROOT:-http://127.0.0.1:${LAN_PORT}}"
PROVIDER_ID="${AI_PROVIDER_ID:-${NODE_ID}-ai}"
FLOPS="${AI_FLOPS_PER_SEC:-500000000}"

detect_llama() {
  if [[ -n "${LLAMA_SERVER_URL:-}" ]]; then
    return 0
  fi
  if command -v llama-server >/dev/null 2>&1; then
    export LLAMA_SERVER_URL="http://127.0.0.1:8080"
    if ! curl -fsS --max-time 2 "${LLAMA_SERVER_URL}/health" >/dev/null 2>&1; then
      log "llama-server found — start it on :8080 or set LLAMA_SERVER_URL"
      unset LLAMA_SERVER_URL
    fi
    return 0
  fi
  log "no llama-server — using beta stub responses"
}

register_provider() {
  local host
  host="$(hostname -I 2>/dev/null | awk '{print $1}')"
  [[ -n "$host" ]] || host="127.0.0.1"
  local register_url="${PUBLIC_ROOT%/}/api/convergence/ai/providers/register"
  local body
  body="$(jq -n \
    --arg pid "$PROVIDER_ID" \
    --arg nid "$NODE_ID" \
    --arg region "$REGION" \
    --arg health "http://${host}:${LAN_PORT}/api/convergence/ai/provider/health" \
    --arg infer "http://${host}:${PORT}/v1/completions" \
    --argjson flops "$FLOPS" \
    '{
      provider_id: $pid,
      node_id: $nid,
      display_name: ($nid + " AI"),
      runtimes: ["llama.cpp", "cpu-inference"],
      region: $region,
      offline_capable: true,
      endpoints: {health_url: $health, inference_url: $infer},
      flops_per_sec: $flops,
      max_concurrent: 2
    }')"
  for attempt in 1 2 3 4 5; do
    if curl -fsS -X POST "$register_url" \
      -H "Content-Type: application/json" \
      -d "$body" >/dev/null 2>&1; then
      log "registered provider $PROVIDER_ID at $register_url"
      return 0
    fi
    sleep 2
  done
  log "WARN: provider registration failed — portal may not be up yet"
  return 0
}

main() {
  chmod +x "$SHIM_PY" 2>/dev/null || true
  detect_llama
  register_provider &
  exec python3 "$SHIM_PY"
}

main "$@"