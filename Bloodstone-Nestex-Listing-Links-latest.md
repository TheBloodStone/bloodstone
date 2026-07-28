# Bloodstone (STONE) — Nestex listing pack

**Prepared for:** nestex.one  
**Date:** 2026-07-28  
**Primary origin:** https://bloodstone.rocks  
**Downloads index:** https://bloodstone.rocks/downloads/  

Use the **`*-latest*`** URLs where available so links stay current after releases. Each binary usually has a matching `.sha256` sidecar (append `.sha256` to the URL).

---

## 1. Exchange integration (start here)

| Resource | URL |
|----------|-----|
| **Exchange API (coin params, deposit policy, chain tip helpers)** | https://bloodstone.rocks/api/exchange |
| **QUASAR status (confirmation / security policy)** | https://bloodstone.rocks/api/quasar/status |
| **QUASAR exchange one-pager (MD)** | https://bloodstone.rocks/downloads/Bloodstone-QUASAR-Exchange-One-Pager.md |
| **QUASAR one-pager (latest alias)** | https://bloodstone.rocks/downloads/Bloodstone-QUASAR-Exchange-One-Pager-latest.md |
| **QUASAR one-pager (HTML)** | https://bloodstone.rocks/downloads/Bloodstone-QUASAR-Exchange-One-Pager.html |
| **QUASAR site** | https://bloodstone.rocks/quasar/ |
| **Explorer (web)** | https://bloodstone.rocks/explorer/ |
| **Web wallet** | https://bloodstone.rocks/wallet/ |
| **Mining portal** | https://bloodstone.rocks/mining/ |
| **Support** | https://bloodstone.rocks/support/ |
| **Faucet** | https://bloodstone.rocks/faucet/ |

### Coin identity (from live `/api/exchange` + node)

| Field | Value |
|-------|--------|
| Ticker | **STONE** |
| Name | Bloodstone |
| Decimals | **8** |
| Algorithms | **neoscrypt**, **yespower**, **sha256d** |
| Target block time | **~90 s** (network multi-algo) |
| Genesis hash | `df04225074039e630dad825b24818a695462bd19cd585131a0568f50e9bf71d0` |
| P2P port | **17333** |
| RPC port (local) | **18332** |
| Address formats | Legacy **S…** (P2PKH) · Bech32 **stone1…** |
| Coinbase maturity | **100** |
| Deposit confirmations (API default) | **6** (recommended **20**) |
| Withdrawal confirmations (API default) | **6** |
| Node version (ops) | **/Bloodstone:0.7.6/** · protocol **120018** |

---

## 2. Full node packages (wallet / deposit / withdrawal backend)

### Linux x86_64 (primary exchange host)

| Package | URL |
|---------|-----|
| **H1 node (recommended latest)** | https://bloodstone.rocks/downloads/bloodstone-node-h1-timewarp-linux-x86_64-latest.tar.gz |
| SHA256 | https://bloodstone.rocks/downloads/bloodstone-node-h1-timewarp-linux-x86_64-latest.tar.gz.sha256 |
| Versioned 0.7.6 H1 | https://bloodstone.rocks/downloads/bloodstone-node-0.7.6-h1-timewarp-linux-x86_64.tar.gz |
| SHA256 | https://bloodstone.rocks/downloads/bloodstone-node-0.7.6-h1-timewarp-linux-x86_64.tar.gz.sha256 |

### Linux ARM64 (Pi / ARM servers)

| Package | URL |
|---------|-----|
| Node 0.7.6 aarch64 | https://bloodstone.rocks/downloads/bloodstone-node-0.7.6-linux-aarch64.tar.gz |
| SHA256 | https://bloodstone.rocks/downloads/bloodstone-node-0.7.6-linux-aarch64.tar.gz.sha256 |
| Pi full-node pack (latest) | https://bloodstone.rocks/downloads/bloodstone-pi-full-node-latest.tar.gz |
| SHA256 | https://bloodstone.rocks/downloads/bloodstone-pi-full-node-latest.tar.gz.sha256 |
| Pi fleet convergence (latest) | https://bloodstone.rocks/downloads/bloodstone-pi-fleet-convergence-latest.tar.gz |
| SHA256 | https://bloodstone.rocks/downloads/bloodstone-pi-fleet-convergence-latest.tar.gz.sha256 |

### Exchange-oriented node packs

| Package | URL |
|---------|-----|
| Exchange node pack (latest) | https://bloodstone.rocks/downloads/bloodstone-exchange-node-latest.tar.gz |
| Versioned example | https://bloodstone.rocks/downloads/bloodstone-exchange-node-0.7.1-linux-x86_64.tar.gz |

### Chain bootstrap (optional sync accelerate)

| Package | URL |
|---------|-----|
| Chain bootstrap (latest) | https://bloodstone.rocks/downloads/bloodstone-chain-bootstrap-latest.tar.gz |
| Exchange chain bootstrap alias | https://bloodstone.rocks/downloads/bloodstone-exchange-chain-bootstrap-latest.tar.gz |

---

## 3. Desktop wallets (ops / cold / support)

| Package | URL |
|---------|-----|
| **Windows Qt wallet (0.7.7)** | https://bloodstone.rocks/downloads/bloodstone-qt-0.7.7-win64.exe |
| SHA256 | https://bloodstone.rocks/downloads/bloodstone-qt-0.7.7-win64.exe.sha256 |
| Windows Qt alias | https://bloodstone.rocks/downloads/bloodstone-qt-win64.exe |
| Windows wallet zip 0.7.7 | https://bloodstone.rocks/downloads/bloodstone-wallet-0.7.7-win64.zip |
| SHA256 | https://bloodstone.rocks/downloads/bloodstone-wallet-0.7.7-win64.zip.sha256 |
| Qt fix-and-launch helper (Win64) | https://bloodstone.rocks/downloads/bloodstone-qt-fix-and-launch-win64.exe |
| Linux aarch64 Qt (0.7.2) | https://bloodstone.rocks/downloads/bloodstone-qt-0.7.2-linux-aarch64.tar.gz |
| Linux aarch64 Qt latest | https://bloodstone.rocks/downloads/bloodstone-qt-linux-aarch64-latest.tar.gz |
| Linux wallet pack 0.7.2 x86_64 | https://bloodstone.rocks/downloads/bloodstone-wallet-0.7.2-linux-x86_64.tar.gz |

---

## 4. Source / build (audits, self-build)

| Package | URL |
|---------|-----|
| **Core source (latest)** | https://bloodstone.rocks/downloads/bloodstone-core-source-latest.tar.gz |
| Core source 0.7.2 | https://bloodstone.rocks/downloads/bloodstone-core-0.7.2-source.tar.gz |
| SHA256 | https://bloodstone.rocks/downloads/bloodstone-core-0.7.2-source.tar.gz.sha256 |
| Source tree pack (latest) | https://bloodstone.rocks/downloads/bloodstone-source-latest.tar.gz |
| Source 0.7.2 | https://bloodstone.rocks/downloads/bloodstone-source-0.7.2.tar.gz |
| Source manifest | https://bloodstone.rocks/downloads/bloodstone-source-manifest.json |
| GitHub (public) | https://github.com/TheBloodStone/bloodstone |

---

## 5. Mobile / miner clients (optional for listing; useful for ecosystem)

| Package | URL |
|---------|-----|
| **Android miner APK (latest) — v1.3.99** | https://bloodstone.rocks/downloads/bloodstone-miner-android-latest.apk |
| Versioned 1.3.99 | https://bloodstone.rocks/downloads/bloodstone-miner-android-1.3.99.apk |
| SHA256 | https://bloodstone.rocks/downloads/bloodstone-miner-android-1.3.99.apk.sha256 |
| Android legacy 32-bit (latest) | https://bloodstone.rocks/downloads/bloodstone-miner-android-legacy32-latest.apk |
| Cloud mining pack Linux x86_64 (latest) | https://bloodstone.rocks/downloads/bloodstone-cloud-mining-latest-linux-x86_64.tar.gz |
| Cloud mining pack Linux aarch64 (latest) | https://bloodstone.rocks/downloads/bloodstone-cloud-mining-latest-linux-aarch64.tar.gz |
| Cloud mining security notes | https://bloodstone.rocks/downloads/Bloodstone-Cloud-Mining-SECURITY.md |

---

## 6. Fork Lab / ecosystem (if Nestex also indexes sister coins)

| Resource | URL |
|----------|-----|
| Fork Lab | https://bloodstone.rocks/fork-lab/ |
| Fork Lab store | https://bloodstone.rocks/fork-lab/store/ |
| Fork explorer | https://bloodstone.rocks/fork-explorer/ |
| Ecosystem merge-mine API | https://bloodstone.rocks/api/ecosystem-merge-mine |
| Ecosystem QUASAR rules API | https://bloodstone.rocks/api/ecosystem-quasar |
| Merge-mine policy (MD) | https://bloodstone.rocks/downloads/Bloodstone-Ecosystem-Merge-Mining.md |
| Fork economy (MD) | https://bloodstone.rocks/downloads/Bloodstone-Ecosystem-Fork-Economy.md |
| QUASAR on forks (MD) | https://bloodstone.rocks/downloads/Bloodstone-Ecosystem-QUASAR-Forks.md |
| Premine policy (MD) | https://bloodstone.rocks/downloads/Bloodstone-Fork-Premine-Policy.md |
| Fork builder (Linux) | https://bloodstone.rocks/downloads/bloodstone-fork-builder-latest.tar.gz |
| Fork builder (Windows exe) | https://bloodstone.rocks/downloads/BloodstoneForkBuilder.exe |

---

## 7. Documentation pack (recommended reading for Nestex)

Prefer **Markdown** first (source of truth).

| Doc | URL |
|-----|-----|
| User handbook | https://bloodstone.rocks/downloads/Bloodstone-User-Handbook.md |
| QUASAR 51% defense white paper | https://bloodstone.rocks/downloads/Bloodstone-QUASAR-51-Percent-Defense-White-Paper.md |
| Halving / QSE schedule | https://bloodstone.rocks/downloads/Bloodstone-Halving-Schedule.md |
| Work ledger architecture | https://bloodstone.rocks/downloads/Bloodstone-Work-Ledger-Architecture-Synthesis.md |
| RFC-010 work view | https://bloodstone.rocks/downloads/Bloodstone-RFC-010-Deterministic-Work-View.md |
| RFC-011 work relay | https://bloodstone.rocks/downloads/Bloodstone-RFC-011-Work-Relay-Protocol-Prototype.md |
| Multi-algo redistribution response | https://bloodstone.rocks/downloads/Bloodstone-Multi-Algo-Redistribution-Options-Response.md |
| EPP pool-layer spec | https://bloodstone.rocks/downloads/Bloodstone-EPP-Phase1-Pool-Layer-Implementation-Spec.md |
| Linux node installer security audit | https://bloodstone.rocks/downloads/Bloodstone-Linux-Node-Installer-Security-Audit-Final.md |
| Android RFC-001 Hy3 remediation status | https://bloodstone.rocks/downloads/RFC-001-Hy3-Remediation-Status.md |
| DNS canonical (bloodstone.rocks) | https://bloodstone.rocks/downloads/Bloodstone-Rocks-DNS-Canonical.md |
| Full downloads catalog (HTML) | https://bloodstone.rocks/downloads/ |

---

## 8. Suggested Nestex wallet setup (minimal)

1. Deploy **Linux x86_64 H1 node**:  
   https://bloodstone.rocks/downloads/bloodstone-node-h1-timewarp-linux-x86_64-latest.tar.gz  
2. Configure `port=17333`, local RPC on `127.0.0.1:18332`, `txindex=1`.  
3. Open P2P **17333/tcp** to the public internet; keep RPC private.  
4. Optional faster sync:  
   https://bloodstone.rocks/downloads/bloodstone-chain-bootstrap-latest.tar.gz  
5. Integrate against live coin metadata:  
   https://bloodstone.rocks/api/exchange  
6. For dynamic confirmation policy, poll:  
   https://bloodstone.rocks/api/quasar/status  
7. Hot wallet: generate deposit addresses via node RPC (`getnewaddress` / wallet RPC) — prefer **stone1…** or **S…** as supported by your stack.  
8. Verify binary integrity with the `.sha256` sidecar before install.

---

## 9. One-line “give them everything” anchors

```
Downloads index:     https://bloodstone.rocks/downloads/
Exchange API:        https://bloodstone.rocks/api/exchange
Explorer:            https://bloodstone.rocks/explorer/
Node (Linux x86_64): https://bloodstone.rocks/downloads/bloodstone-node-h1-timewarp-linux-x86_64-latest.tar.gz
Source (latest):     https://bloodstone.rocks/downloads/bloodstone-core-source-latest.tar.gz
Android APK:         https://bloodstone.rocks/downloads/bloodstone-miner-android-latest.apk
QUASAR exchange note:https://bloodstone.rocks/downloads/Bloodstone-QUASAR-Exchange-One-Pager.md
This Nestex pack:    https://bloodstone.rocks/downloads/Bloodstone-Nestex-Listing-Links.md
```

---

*Bloodstone · Nestex listing links · 2026-07-28*
