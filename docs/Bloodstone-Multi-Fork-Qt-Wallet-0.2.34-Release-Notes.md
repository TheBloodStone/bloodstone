# Multi-Fork Qt Wallet 0.2.34

**Date:** 2026-08-01  
**Theme:** WP2 runtime catalog (T+0 coin discoverability)

## Changes

- **Remote runtime catalog** — MFQ fetches `fork-lab-runtime-catalog.json` (and portal API fallback) so new Fork Lab / burn-launched coins appear without a local `fork_lab.db`.
- Merges remote entries with built-ins (STONE / LRGK / AZURE) and any local Fork Lab DB.
- Coins with **metadata-only** daemon packs are labeled in the description (no fake child binaries).

## Downloads

- Source: https://bloodstone.rocks/downloads/bloodstone-multi-fork-qt-0.2.34.tar.gz  
- Latest alias: https://bloodstone.rocks/downloads/bloodstone-multi-fork-qt-latest.tar.gz  
- Runtime catalog: https://bloodstone.rocks/downloads/fork-lab-runtime-catalog.json  
- Daemon packs: https://bloodstone.rocks/downloads/mfq-daemons/manifest.json  

## Note on Windows installers

If win64 setup/portable artifacts for 0.2.34 are not yet rebuilt, use the source tarball on Linux or wait for the next installer train tag. Daemon pack downloads for STONE/LRGK/AZURE remain on the existing published zips.
