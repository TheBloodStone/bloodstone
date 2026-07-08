# Bloodstone LAN Pool Coordinator Guide

**Document version:** 1.0 · July 2026  
**Coordinator:** https://bloodstonewallet.mytunnel.org  
**APK:** 1.3.84+ · **Web UI OTA:** 1.3.129-web+

---

## Summary

Bloodstone Android full nodes can act as **LAN pool coordinators** that replace the central VPS pool for **jobs, shares, and payouts** on your household Wi‑Fi. A node only takes over after it **speaks with at least one other synced node** and **compares notes** (chain tip, open rounds, recent block finds). Until verification succeeds, pool mode continues to relay to the VPS as before.

---

## How it works

1. **Two or more synced nodes** on the same Wi‑Fi run **Full chain** or **Pruned** mode with the local node started.
2. Every ~20 seconds each node exchanges a **pool snapshot** over LAN HTTP **port 18342** (`GET /api/lan-pool/snapshot`).
3. Nodes compare:
   - Chain tip (**block height** + **best block hash**)
   - Open round **job heights** per algorithm (Neoscrypt, Yespower, SHA256d)
   - **Share weights** (must agree within 5%)
   - **Recent block finds**
4. When **at least one peer agrees**, the node becomes a **verified LAN pool coordinator** and:
   - Stops relaying pool stratum to the VPS
   - Serves **jobs** from local `bloodstoned` (`creatework` / `createauxblock`)
   - **Validates and records shares** in on-device SQLite
   - **Distributes block rewards** to miner `pending_stone` balances
   - **Replicates** shares and block-finds to verified peers

---

## Requirements

| Component | Version | Required for |
|-----------|---------|--------------|
| Android APK | **1.3.84+** | Native coordinator, stratum pool mode, SQLite ledger |
| Web UI OTA | **1.3.129-web+** | Routing, status panel, “no VPS” miner log messages |

Download APK: https://bloodstonewallet.mytunnel.org/downloads/bloodstone-miner-android-latest.apk  
Then open **Updates → Check for updates** for the web bundle.

---

## Household setup

### Host nodes (coordinator candidates)

1. Set **Local node mode** → **Full chain** or **Pruned (~550 MiB)**.
2. Tap **Start full node** (or Start pruned node).
3. Stay on **Wi‑Fi** and **power** until chain sync completes (~99.9%+).
4. Repeat on a **second phone** on the same LAN (verification needs ≥1 peer).

### Miners (LAN clients, Bitaxe, other phones)

1. Set **Local node mode** → **LAN client — no chain download**.
2. Enter your **STONE payout address**.
3. Set **Mining mode** → **Pool** (or **Solo** for local blocks only).
4. Tap **Start mining** — the app finds a verified coordinator on Wi‑Fi.

### Bitaxe (SHA256d)

- **Host:** phone LAN IP, port **3429**
- **Worker:** `YOUR_STONE_ADDRESS.rig1`
- **Password:** `x` (pool through LAN coordinator) or `solo` (local blocks via host node)

---

## Status in the app

| UI location | What you see |
|-------------|--------------|
| Local node detail | “LAN pool coordinator active — verified with N peer(s)” |
| Local node detail (waiting) | “Need another synced node on Wi‑Fi to compare notes” |
| Miner log | “LAN pool coordinator on this phone — jobs, shares, payouts local” |
| Miner log (remote) | “LAN pool coordinator &lt;ip&gt; — no VPS” |

### Pending balance API (LAN only)

```
GET http://<lan-ip>:18342/api/lan-pool/balance?address=YOUR_STONE_ADDRESS
```

---

## LAN pool HTTP API (port 18342)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/lan-pool/snapshot` | GET | Peer verification — chain + pool state |
| `/api/lan-pool/status` | GET | Coordinator running / verified / active |
| `/api/lan-pool/balance?address=` | GET | Pending STONE balance for payout address |
| `/api/lan-pool/share-import` | POST | Replicate a credited share from peer |
| `/api/lan-pool/block-find` | POST | Replicate block distribution from peer |

All endpoints accept **LAN clients only** (private RFC1918 addresses).

---

## Stratum ports (unchanged)

| Algorithm | Port |
|-----------|------|
| Neoscrypt-Xaya | 3437 |
| Yespower R16 | 3438 |
| SHA256d / Bitaxe | 3429 |

When the coordinator is **not** verified, pool password `x` still **relays** to the VPS (`64.188.22.190`). When **verified**, the same ports serve the **local pool**.

---

## Before vs after verification

| Phase | Pool jobs | Shares | Payouts | VPS |
|-------|-----------|--------|---------|-----|
| **Before verification** | Relayed from VPS | Accounted on VPS | VPS `pool.db` | Required |
| **After verification** | Local `bloodstoned` | On-device SQLite + peer sync | Local `pending_stone` | Not used for pool |

---

## Algorithm notes

- **SHA256d:** Full share hash validation on the coordinator (same as native stratum server).
- **Neoscrypt / Yespower:** Shares credited after submit; **peer cross-check** is the trust layer (no bundled neoscrypt/yespower hash binary on Android yet).
- **Solo mode** (`password: solo` on SHA256d, or mining mode Solo): Always mines through the local full node — independent of VPS and coordinator verification.

---

## Payouts and on-chain sends

Coordinators track **`pending_stone`** per address in the local pool database. **On-chain payout transactions** (`mark_paid` / wallet send) are a separate step from share accounting — operators can pay miners from the host wallet when balances accumulate.

Default distribution (per block find):

- Block reward: **100 STONE** (configurable via chain subsidy)
- Pool fee: **1%**
- Finder bonus: **5 STONE** (when finder address is valid)

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| “Waiting for peers” | Only one synced node on LAN | Start a second full/pruned node on same Wi‑Fi |
| Still using VPS pool | Coordinator not verified | Wait for sync; ensure two nodes see each other via mDNS |
| LAN client finds no host | No stratum host running | Start full node on one plugged-in device |
| Old APK | No native coordinator | Upgrade to APK **1.3.84+** |

---

## Related documents

- [Infrastructure Independence White Paper](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Infrastructure-Independence-White-Paper.docx)
- [Mesh Virtual LAN White Paper](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Mesh-Virtual-LAN-White-Paper.docx)
- [Chain Mesh Storage White Paper](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx)

---

*Bloodstone · LAN pool coordinator · APK 1.3.84 · Web 1.3.129-web*