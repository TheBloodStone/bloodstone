#!/usr/bin/env bash
# Verify Bloodstone public page links return 200/302 (not timeout or 5xx).
set -euo pipefail

BASE="${BLOODSTONE_PUBLIC_ROOT:-https://bloodstonewallet.mytunnel.org}"
TIMEOUT="${BLOODSTONE_LINK_CHECK_TIMEOUT:-30}"
LOG="${BLOODSTONE_LINK_CHECK_LOG:-/root/.bloodstone/link-check.log}"

ROUTES=(
  /
  /exchange/
  /atomicdex/
  /explorer/
  /explorer/miners
  /explorer/names
  /explorer/search
  /wallet/
  /wallet/login
  /wallet/register
  /wallet/usdt
  /wallet/swap
  /wallet/staking
  /wallet/fund
  /wallet/gift
  /wallet/referrals
  /mining/
  /mining/mine
  /mining/pool/neoscrypt
  /mining/pool/yespower
  /mining/pool/sha256d
  /mining/pool/rod_neoscrypt
  /mining/admin/login
  /faucet/
  /faucet/fund
  /dex/
  /dex/sell
  /dex/bid
  /dex/my
  /support/
  /support/lookup
  /downloads/
  /downloads/bloodstone-miner-android-1.3.2.apk
  /login
  /register
)

mkdir -p "$(dirname "$LOG")"
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
failed=0
slow=0

echo "[$ts] link check $BASE" | tee -a "$LOG"
for path in "${ROUTES[@]}"; do
  url="$BASE$path"
  raw=$(curl -sk -o /dev/null -w "%{http_code} %{time_total}" --max-time "$TIMEOUT" -L "$url" 2>/dev/null || echo "000 0")
  code=$(echo "$raw" | awk '{print $1}')
  latency=$(echo "$raw" | awk '{print $2}')
  ok=0
  [[ "$code" =~ ^(200|301|302|303|307|308|401|403)$ ]] && ok=1
  if (( ok )); then
    if awk -v l="$latency" -v t="8" 'BEGIN {exit !(l > t)}'; then
      printf "SLOW %s %ss %s\n" "$code" "$latency" "$path" | tee -a "$LOG"
      slow=$((slow + 1))
    else
      printf "OK   %s %ss %s\n" "$code" "$latency" "$path" | tee -a "$LOG"
    fi
  else
    printf "FAIL %s %ss %s\n" "$code" "$latency" "$path" | tee -a "$LOG"
    failed=$((failed + 1))
  fi
done

echo "[$ts] done failed=$failed slow=$slow total=${#ROUTES[@]}" | tee -a "$LOG"
exit $(( failed > 0 ? 1 : 0 ))