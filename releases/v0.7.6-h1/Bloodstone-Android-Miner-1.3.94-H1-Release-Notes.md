# Bloodstone Android Miner APK 1.3.94 — H1 full node

**Version:** 1.3.94  
**Embedded node:** bloodstoned **v0.7.6** (Phase H1 timewarp)  
**Flag day:** mainnet activation height **H = 17000**  
**ABIs:** `arm64-v8a` + `armeabi-v7a` (one APK for modern 64-bit and legacy 32-bit phones)

## Why upgrade
The Android miner runs a local full node. After height 17000, H1 header-time rules apply. Nodes without 0.7.6 will not stay consensus-compatible.

## Download
- https://bloodstonewallet.mytunnel.org/downloads/bloodstone-miner-android-1.3.94.apk
- Latest alias: https://bloodstonewallet.mytunnel.org/downloads/bloodstone-miner-android-latest.apk
- Release notes (Markdown): https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Android-Miner-1.3.94-H1-Release-Notes.md

## Install
1. Sideload over the previous APK if the signing key matches (reinstall not always required).
2. Allow install from unknown sources if prompted.
3. Open the app, start/sync the local node; embedded daemon is **0.7.6**.

## Notes
- Dual-ABI package: Android installs the matching native `bloodstoned` for your CPU.
- Companion Linux node package remains `bloodstone-node-0.7.6-h1-timewarp` (H=17000).
