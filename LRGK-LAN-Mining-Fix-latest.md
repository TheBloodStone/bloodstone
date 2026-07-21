# LRGK LAN / ASIC mining fix (1.0.31)

## Why nobody was hitting blocks

`creatework` / `createauxblock` refused to issue jobs when the node had **zero P2P peers**:

```text
error: Bloodstone is not connected!
```

Phones and the public seed often mine **solo / LAN** with no peers. Local stratum showed hashrate (UI) but **no real jobs** (or jobs never refreshed), so LAN miners and ASICs could not find blocks.

Separately, phones still on the **pre-reset** chain tip (`8fa7b7cc…` height 1) were rejected by the host with `bad-diffbits` after the 500-LRGK economics reset.

## Fix

- Removed the zero-peer gate in `auxMiningCheck` (host + Android `lrgkd`).
- Jobs work with 0 peers: verified `creatework` + `createauxblock` return height 4, **coinbasevalue = 50000000000** (500 LRGK).
- APK **1.0.31** ships the fixed daemon.

## What you must do

1. Install https://bloodstonewallet.mytunnel.org/downloads/lrgk-full-node-android-1.0.31.apk  
2. **Reset / wipe LRGK chain data** on the phone (or clear app data for LRGK only) so you leave the old tip.  
3. Connect to public seed `64.188.22.190:33685` and sync.  
4. ASIC → phone LAN: `stratum+tcp://<phone-ip>:3429`, user `L….rig1`, password `solo`.  
5. Confirm jobs appear (stratum notify) and height advances past the public tip.

## Links

- APK: https://bloodstonewallet.mytunnel.org/downloads/lrgk-full-node-android-1.0.31.apk  
- Latest: https://bloodstonewallet.mytunnel.org/downloads/lrgk-full-node-android-latest.apk  
- Economics: https://bloodstonewallet.mytunnel.org/downloads/LRGK-Halving-Schedule.md  
