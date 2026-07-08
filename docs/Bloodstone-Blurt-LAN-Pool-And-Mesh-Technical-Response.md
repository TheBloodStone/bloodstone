# Bloodstone Technical Response to Blurt — LAN Pool, Mesh Manifests & Multi-Algo Security

**Document version:** 1.0 · July 2026  
**Audience:** Blurt Core (Megadrive)  
**Coordinator:** https://bloodstonewallet.mytunnel.org  
**Related:** [LAN Pool Coordinator Guide](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-LAN-Pool-Coordinator-Guide.md) · [Mesh v2.0-Lite System](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Blurt-Mesh-v2-Lite-System.docx)

---

## Executive summary

Blurt asked whether Bloodstone’s **LAN pool coordinator** (mining) has an equivalent for **storage manifests** versus the central `mytunnel.org` coordinator, and raised three follow-up questions from their AI on **51% / SHA256d dominance**, **Neoscrypt/Yespower validation on Android**, and **on-chain payouts from LAN coordinators**.

**Short answers:**

| Question | Answer |
|----------|--------|
| Storage manifests vs central coordinator? | **Mining LAN coordinator is live now.** Storage follows the same decentralization philosophy via **chain mesh v2.0-Lite** (Blurt L1 manifests + trustless chunks). A household **LAN mesh cache** profile is the planned analogue. |
| 51% / peer verification? | LAN peer verification is **pool accounting only**, not consensus-level 51% protection. Multi-algo PoW exists at consensus; ASIC dominance rebalance is **pool-level**. DigiByte-style geometric-mean consensus is a **future option**, not deployed. |
| Neoscrypt/Yespower on Android? | **SHA256d** has full hash validation on-device; **Neoscrypt/Yespower** use submit + **peer cross-check** today. Native CPU hash modules are on the roadmap; multi-peer quorum remains defense-in-depth. |
| LAN coordinator payouts? | Block rewards credit **`pending_stone`** in SQLite automatically; **on-chain `sendtoaddress`** is a separate operator step requiring a **funded host wallet**. |

---

## 1. LAN pool coordinator vs storage manifests

### 1.1 What shipped (mining)

The **LAN pool coordinator** (Android APK **1.3.84+**, web UI OTA **1.3.129-web+**) replaces the **VPS stratum relay** (`64.188.22.190`) for **jobs, shares, and pool accounting** on household Wi‑Fi — after **≥1 synced peer** agrees on chain/pool state over HTTP **:18342**.

It does **not** replace the mesh manifest catalog or chunk plane.

### 1.2 Storage manifests (separate layer)

**Chain mesh** handles file storage:

| Layer | Today | Direction |
|-------|-------|-----------|
| **Manifest registry** | BSM1 anchors on Bloodstone chain + coordinator catalog at `bloodstonewallet.mytunnel.org` | **v2.0-Lite** (Blurt RFC): manifests on **Blurt L1** via `custom_json` (`chain_mesh_anchor`); coordinator becomes **fallback**, not primary discovery |
| **Chunk plane** | 256 KiB content-addressed chunks; clients verify SHA-256 + Merkle root | Peer replication on mesh nodes; libp2p/DHT planned |
| **LAN equivalent** | Not shipped yet | Same pattern as mining: **household nodes cache manifests + replicate chunks locally**, resolve from on-chain anchors (or Blurt registry), fetch bytes peer-to-peer without hitting mytunnel for every read |

### 1.3 Summary

- **Mining LAN coordinator** = **live** (pool jobs/shares/payout ledger on LAN).
- **Storage LAN** = same philosophy (decentralize the coordinator role), implemented first for Blurt via **v2.0-Lite**, then extensible to any tenant manifest format.

---

## 2. 51% attack protection and peer verification

### 2.1 What LAN peer verification does

Peer verification is **pool accounting trust**, not **consensus-level 51% protection**.

Every ~20 seconds, synced nodes exchange a **pool snapshot** (`GET /api/lan-pool/snapshot`) and compare:

- Chain tip (**block height** + **best block hash**)
- Open round **job heights** per algorithm (Neoscrypt, Yespower, SHA256d)
- **Share weights** (must agree within ±5%)
- **Recent block finds**

When **at least one peer agrees**, a node becomes a **verified LAN pool coordinator** and stops relaying pool stratum to the VPS.

This prevents a rogue phone from inventing pool credits on the LAN. It does **not** stop a SHA256d majority from rewriting chain history — that would require a **consensus change** (e.g. DigiByte’s multi-algo geometric mean).

### 2.2 What exists at consensus today

- **Multi-algo PoW** from block 1: Neoscrypt-Xaya, Yespower R16, SHA256d (aux/Bitaxe lane)
- Blocks carry algo metadata; miners compete on different lanes

### 2.3 What exists at pool level (VPS + LAN)

- **ASIC dominance rebalance** on Neoscrypt/Yespower when ASIC weight exceeds **75%** — redistributes **25%** of ASIC weight to CPU miners (pool accounting, not consensus)

### 2.4 Roadmap option (not committed)

A consensus fork toward **work-weight blending across algos** (DigiByte-style) if SHA256d share of chain work becomes a concern. Peer verification would remain the LAN trust layer either way — complementary, not a substitute.

---

## 3. Neoscrypt / Yespower validation on Android

| Algorithm | LAN coordinator today |
|-----------|-------------------------|
| **SHA256d** | Full share hash validation (native stratum server) |
| **Neoscrypt / Yespower** | Share accepted on submit; **peer cross-check** is the trust layer |

There is **no bundled Neoscrypt/Yespower hash binary on Android yet**, so on-device PoW re-check (as the VPS performs) is not available for CPU algos.

### Roadmap

1. **Near term:** peer verification remains the model for CPU algos on LAN (already live)
2. **Medium term:** JNI/native hash modules for Neoscrypt/Yespower on-device validation (reduces trust in peer snapshots)
3. **Permanent fallback:** multi-peer quorum even after native validation — defense in depth for household setups with 2+ nodes

Peer verification is not a stopgap because hash libraries were forgotten — it is the practical trust layer on phones until ARM-native PoW libraries are sized, tested, and shipped.

---

## 4. Payouts from LAN coordinators

Two distinct layers:

### 4.1 Pool accounting (automatic on block find)

When a LAN coordinator finds a block:

- Block reward (~**100 STONE** at current subsidy) is split per pool rules: **1% fee**, **5 STONE finder bonus**, remainder **pro-rata by share weight**
- Credits land as **`pending_stone`** in on-device SQLite (`bloodstone_lan_pool.db`)
- Peers replicate share/block-find events over `:18342`

Miners can query:

```http
GET http://<lan-ip>:18342/api/lan-pool/balance?address=YOUR_STONE_ADDRESS
```

### 4.2 On-chain sends (operator step)

Moving `pending_stone` → miner wallets via `sendtoaddress` is **separate** from share accounting. The coordinator’s **`bloodstoned` wallet** must hold spendable STONE.

| Event | What happens |
|-------|----------------|
| Block coinbase | Pays to whoever’s node mined the block (host phone wallet) |
| Pool credits | IOUs in SQLite until operator batches on-chain payouts |
| VPS comparison | Same pattern as the public pool — LAN moves the ledger local |

**Practical household model:** one plugged-in full node with a funded wallet pays out LAN miners on a schedule; miners poll the balance API for pending amounts.

**Future:** optional **auto-payout** (threshold + `sendtoaddress` from host wallet) in a future APK release.

---

## 5. One-line summary for partners

> Mining LAN coordinator is live. Storage is following the same pattern via mesh v2.0-Lite (Blurt L1 manifests + trustless chunks). Peer verification secures pool books, not consensus; native CPU hash validation is on the roadmap; on-chain payouts need a funded host wallet — accounting is automatic, sends are operator-triggered.

---

## Related documents

- [Bloodstone LAN Pool Coordinator Guide](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-LAN-Pool-Coordinator-Guide.md)
- [Bloodstone Blurt Mesh v2.0-Lite System](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Blurt-Mesh-v2-Lite-System.docx)
- [Chain Mesh Capacity & Usage FAQ](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Chain-Mesh-Capacity-And-Usage-FAQ.md)
- [Infrastructure Independence White Paper](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Infrastructure-Independence-White-Paper.docx)

---

*Bloodstone · Blurt technical response · July 2026*