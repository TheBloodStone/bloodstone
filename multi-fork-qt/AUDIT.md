# Multi-Fork Qt (MFQ) — audit entry point

**MFQ** = **Multi-Fork Qt** wallet (STONE + all live Fork Lab coins: AZURE, LRGK, future).

| Item | Value |
|------|--------|
| Version | See `VERSION` |
| Language | Python 3 + PyQt5 |
| Entry | `main.py` |
| Package | `bloodstone_mfq/` |

## Review first

1. `bloodstone_mfq/daemon_manager.py` — process spawn, seed peers, RPC port handling  
2. `bloodstone_mfq/rpc.py` — JSON-RPC to local daemons  
3. `bloodstone_mfq/catalog.py` — live fork discovery  
4. `bloodstone_mfq/ui/mainwindow.py` — send/receive UI  
5. `scripts/` — package / Windows build  

## Security model

- Talks only to **local JSON-RPC** using credentials from each coin’s conf file.  
- Do not expose RPC ports publicly.  
- Daemons/binaries for forks are separate; this tree is the wallet GUI + orchestrator.

## Canonical downloads

- Source tarball: https://bloodstone.rocks/downloads/bloodstone-multi-fork-qt-latest.tar.gz  
- Windows EXE: https://bloodstone.rocks/downloads/bloodstone-multi-fork-qt-win64-latest.exe  
- README: https://bloodstone.rocks/downloads/Bloodstone-Multi-Fork-Qt-Wallet.md  

## GitHub location

This directory is published for third-party audit (Megadrive / Claude / reviewers).
