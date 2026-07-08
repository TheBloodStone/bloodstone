# Bloodstone QUASAR Defense

## A Software Stack Against 51% Attacks — Not a Whitepaper About Hope, a Blueprint About Hydra Logic

**Document version:** 1.0 · July 2026  
**Codename:** QUASAR — **QU**orum **A**daptive **S**ecurity **A**gainst **R**eorgs  
**Audience:** Security researchers, exchange integrators, skeptics, and anyone who thinks “rented SHA256” ends the conversation  
**Coordinator:** https://bloodstonewallet.mytunnel.org

---

## Executive summary

A 51% attack is not a magic spell. It is a **budget problem**: can an adversary produce a **private fork** with more **valid work** than the public chain, then **outrun** honest propagation long enough to **double-spend**?

Most coins answer this with one algorithm and prayer. Bloodstone answers with **QUASAR** — a **seven-layer software defense** where each layer multiplies the attacker’s cost. You do not need to trust a single hero miner. You need to understand that an attacker must simultaneously win:

1. **Three independent PoW games** (not one)  
2. **Weighted chain-work math** that punishes SHA256d dominance  
3. **Time-braided finality windows** across algorithms  
4. **Mesh witness capsules** anchored on-chain (BSM1)  
5. **LAN echo quorum** from household full/pruned nodes  
6. **Exchange-grade confirmation policy** tied to witness depth  
7. **Anomaly tripwires** on rented-hash spikes  

**The wow moment:** Bloodstone treats 51% resistance as a **distributed immune system**, not a hashrate poster. The chain does not ask “do you have 51% of one number?” It asks “can you forge an alternate universe where **three clocks**, **thousands of phones**, **mesh anchors**, and **exchange policy** all agree you won?”

That is a different sport.

---

## 1. The fairy tale everyone was taught

Traditional security slides show:

```
Attacker hash% > 50%  →  Attacker wins
```

Reality on multi-algo chains:

```
Attacker wins  IF  Work_private > Work_public
              AND  Propagation > Honest network
              AND  Exchanges accept shallow confirms
              AND  No one runs witness checks
```

**51% of SHA256 on a rental market ≠ 51% of Bloodstone security.**

Bloodstone mainnet runs **three consensus PoW algorithms**:

| Algorithm | Role | Attacker profile |
|-----------|------|------------------|
| **SHA256d** | Merge-mined auxpow (chain ID 1899) | Rented ASIC / Bitaxe farms |
| **Neoscrypt** | Standalone CPU/GPU lane | GPU renters, LAN miners |
| **Yespower** | Standalone CPU lane | Phones, laptops, Pi nodes |

Each algorithm has **independent Dark Gravity retargeting** on its own ancestor stream. Chain tip selection uses **weighted cumulative work** (`powAlgoLog2Weight`: SHA256d = 6, Neoscrypt = 10, Yespower = 22). SHA256d work is **deliberately down-weighted** relative to CPU lanes.

An attacker who buys a mountain of SHA256d rent **does not buy a mountain of chain decision power** the way they would on Bitcoin.

---

## 2. QUASAR layer map (the hydra)

```
                    ┌─────────────────────────────────────┐
                    │  L7  Anomaly Tripwire (pool + API)   │
                    └──────────────────┬──────────────────┘
                    ┌──────────────────▼──────────────────┐
                    │  L6  Exchange Witness Policy        │
                    └──────────────────┬──────────────────┘
                    ┌──────────────────▼──────────────────┐
                    │  L5  LAN Echo Quorum (mDNS fleet)   │
                    └──────────────────┬──────────────────┘
                    ┌──────────────────▼──────────────────┐
                    │  L4  Mesh Witness Capsules (BSM1)   │
                    └──────────────────┬──────────────────┘
                    ┌──────────────────▼──────────────────┐
                    │  L3  Epoch Braid Finality (E-BF)    │
                    └──────────────────┬──────────────────┘
                    ┌──────────────────▼──────────────────┐
                    │  L2  Tri-Algo Work Tensor (consensus)│
                    └──────────────────┬──────────────────┘
                    ┌──────────────────▼──────────────────┐
                    │  L1  Triple-Purpose PoW (live)     │
                    └─────────────────────────────────────┘
```

**L1–L2 are live in Bloodstone Core today.**  
**L3–L7 are the QUASAR software envelope** — deployable without replacing PoW, using nodes, mesh, pool telemetry, and exchange integration you already ship.

---

## 3. Layer 1 — Triple-Purpose PoW (the bedrock)

Bloodstone inherits SpaceXpanse **triple-purpose mining**:

- Merge-mined **SHA256d** blocks (Bitcoin-style auxpow)  
- Standalone **Neoscrypt** blocks  
- Standalone **Yespower** blocks  

**Why this matters for 51% defense:**

| Single-algo chain | Bloodstone |
|-------------------|------------|
| Attacker picks one market (SHA256 rent) | Attacker must fight **three** markets |
| One difficulty knob | **Three** retargeting streams |
| Stall if one pool dies | Chain continues on other algos (~90s target block time) |

Even if one algorithm’s hashrate **collapses to zero**, blocks still arrive from the others. A censorship or stall attack cannot silence the chain without winning **all three lanes**.

**Status:** ✅ Live on mainnet.

---

## 4. Layer 2 — Tri-Algo Work Tensor (consensus physics)

Chain selection is not “longest chain.” It is **most weighted work**.

Bloodstone combines per-algorithm contributions through:

- `GetNextWorkRequired` — ancestors filtered by **same PoW algo**  
- `powAlgoLog2Weight` — SHA256d logs less weight per hash than Neoscrypt/Yespower  
- `GetBlockProofEquivalentTime` — cross-algo timing normalization (~270s per algo stream)  

**Intuition for skeptics:**

> Dominating SHA256d hashrate is like winning the **loud** section of an orchestra but not the **score**.

An attacker must outpace the public tip in **tensor work**, not rent a single billboard.

**Worked example (order-of-magnitude):**

Assume an attacker controls **80% of SHA256d** hashrate but **10%** of Neoscrypt and **10%** of Yespower.

| Resource | Attacker share | Weight in chain work |
|----------|----------------|----------------------|
| SHA256d | 80% | × 2^6 (low) |
| Neoscrypt | 10% | × 2^10 (high) |
| Yespower | 10% | × 2^22 (highest) |

The honest majority on CPU lanes contributes disproportionate **decision mass** even when SHA256d rent looks scary on a pool dashboard.

**Status:** ✅ Live in Core consensus.

---

## 5. Layer 3 — Epoch Braid Finality (E-BF)

**The creative punch:** treat finality as a **braid across algorithms**, not a single block height.

### Concept

Divide time into **epochs** of *E* blocks (~15 minutes at 90s/block). Within each epoch, count blocks per algorithm:

```
Braid vector B = ( #sha256d, #neoscrypt, #yespower ) in epoch k
```

A **settlement-grade** state requires:

1. Tip block on most-work chain (consensus)  
2. **Braid balance:** no single algorithm contributed > *φ* fraction of epoch blocks *unless* cumulative weighted work from other algos confirms the same tip ancestry  
3. **Braid continuity:** epoch *k* tip hash must appear as ancestor in epoch *k+1* across at least **two** algo streams  

### Why attackers hate braids

A private fork attacker can spam **one** algo cheaply (e.g. rented SHA256d). E-BF software flags **braid skew**:

```
if sha256d_blocks / epoch_blocks > 0.85 AND neoscrypt+yespower < threshold:
    mark epoch as DEFERRED_FINALITY
```

Wallets, explorers, and exchanges **display balances** but **delay high-value spends** until the braid restitches — without a hard fork, as a **node policy layer**.

### Implementation sketch (software-only)

| Component | Behavior |
|-----------|----------|
| `bloodstoned` index | Track per-epoch braid vector in memory + optional `indexes/braid/` |
| Qt / Electron GUIs | Show “Braid: healthy / skewed / deferred” |
| `/api/exchange` | Expose `braid_finality_epoch_blocks` confirmation multiplier |
| Pool dashboard | Highlight algo imbalance before it becomes a reorg risk |

**Status:** 📋 QUASAR Phase 1 (policy layer; no consensus change required).

---

## 6. Layer 4 — Mesh Witness Capsules (MWC)

Bloodstone already ships **Chain Mesh** with **BSM1 on-chain anchors** — content-addressed chunks, Merkle roots, tamper-evident publication.

**Mesh Witness Capsules** repurpose that machinery for security:

### Witness capsule contents (signed attestation bundle)

```json
{
  "type": "bloodstone/witness-capsule/v1",
  "height": 12450,
  "tip_hash": "abc123…",
  "algo_work": { "sha256d": "…", "neoscrypt": "…", "yespower": "…" },
  "peer_count": 14,
  "node_mode": "full|pruned",
  "capsule_id": "sha256(content)",
  "issued_at": "2026-07-08T12:00:00Z"
}
```

### Publication path

1. Android full/pruned nodes, LAN coordinators, exchange nodes emit capsules every *N* blocks  
2. Capsules mesh-published under `assets/witness/YYYY-MM/`  
3. Optional BSM1 anchor tx commits Merkle root of capsule batch  
4. Explorers index anchors via `/api/mesh-anchors`  

### Defense logic

An attacker’s private chain must not only beat work — it must **explain away missing witness capsules** from thousands of independent phones and VPS nodes that observed a different tip.

Exchanges treat:

```
confirmations_effective = base_confirmations + witness_quorum_depth
```

where `witness_quorum_depth` counts distinct capsule signers (by mesh key / node fingerprint) agreeing on tip hash.

**This is Sybil-resistant at the economic layer:** capsules cost **real sync + real mesh publish + optional anchor fee**, not anonymous HTTP votes.

**Status:** 🛠️ QUASAR Phase 2 (uses live mesh; witness schema new).

---

## 7. Layer 5 — LAN Echo Quorum (LEQ)

Bloodstone’s killer fleet advantage: **Android pruned/full nodes on household Wi‑Fi** serving LAN RPC and stratum.

**LAN Echo Quorum** is cross-attestation between LAN-visible peers:

| Step | Action |
|------|--------|
| 1 | Node A on Wi‑Fi broadcasts mDNS `_bloodstone-lan._tcp` with tip hash + algo heights |
| 2 | Node B echoes signed **Echo Packet** if tips match within Δ blocks |
| 3 | Coordinator aggregates echoes; flags **split-brain** if LAN quorum disagrees with pool VPS tip |
| 4 | Miner UI shows “LAN quorum: 4/5 agree” |

**Why it’s not pool theater:**

LAN Echo is **consensus-adjacent observation**, not payout accounting. When a rented-hash attacker drives pool stratum but **LAN nodes never see the blocks**, the UI screams before an exchange credits a deposit.

**Physicality bonus:** you cannot fake “4 household LANs in 4 cities agree” from one VPS Sybil — mDNS scope is **local radio**, not global HTTP.

**Status:** 🛠️ QUASAR Phase 2 (extends existing LAN pool coordinator + `device-network-info.js`).

---

## 8. Layer 6 — Exchange Witness Policy (EWP)

Integrators already consume `/api/exchange`. QUASAR adds **dynamic confirmation policy**:

| Signal | Policy response |
|--------|-----------------|
| Braid healthy + witness quorum ≥ 3 | Standard 6 confirmations |
| Braid skewed (SHA256d-heavy epoch) | 12–20 confirmations |
| Witness split (capsules disagree) | Halt deposits; manual review |
| Pool tripwire fired (L7) | Auto-bump `confirmations_deposit` in listing pack JSON |

**No exchange code fork required** — poll `/api/exchange` + `/api/quasar/status` (proposed) and adjust hot-wallet crediting.

**Status:** 📋 QUASAR Phase 1 (API extension + documentation).

---

## 9. Layer 7 — Anomaly Tripwire (AT)

Pool operators see **share velocity**, **algo mix**, and **block find rate** in real time.

**Tripwire rules (examples):**

```
TRIPWIRE_SHA256D_SURGE:
  if sha256d_share_rate_1h > 4 * sha256d_share_rate_24h_median
  AND neoscrypt+yespower block_find_rate drops
  → emit QUASAR_ALERT_SHA256D_RENTAL

TRIPWIRE_ORPHAN_SHADOW:
  if pool block finds not reflected in local node tip within 2 * block_time
  → emit QUASAR_ALERT_POSSIBLE_PRIVATE_FORK
```

Alerts propagate to:

- Portal banner  
- `/api/exchange` listing notes  
- Mesh `assets/alerts/quasar/` for integrators  
- Optional webhook for exchange ops  

**Status:** 🛠️ QUASAR Phase 2 (pool telemetry exists; alert bus new).

---

## 10. Attack theater — five scenarios, five humiliations

### Scenario A: “Rent SHA256 and reorg 6 blocks”

| Step | Attacker | QUASAR response |
|------|----------|-----------------|
| Buy rent | Wins SHA256d lane temporarily | L2: weighted work still needs CPU lanes |
| Private mine | Builds shadow fork | L3: braid skew → deferred finality |
| Broadcast | Race propagation | L4–L5: witness capsules + LAN echoes disagree |
| Double-spend | Exchange credit | L6: confirmations not met under witness policy |
| Profit | Maybe pool payout | L7: tripwire already fired |

**Outcome:** Expensive, loud, slow — bad business.

### Scenario B: “Sybil ten thousand fake nodes”

Fake HTTP nodes are cheap. **Mesh witness capsules with BSM1 anchors** are not — each ties to chunk storage, anchor fees, and reproducible tip hashes. LEQ requires **LAN radio locality**, not a CSV of IPs.

**Outcome:** Sybil budget shifts from $50 VPS to **fleet-scale sync theater**.

### Scenario C: “Stop blocks — denial of service”

Attacker kills one algo. L1 triple-purpose mining continues on the other two. Chain slows but **does not halt**.

**Outcome:** Stalemate, not takeover.

### Scenario D: “Deep reorg names / DEX state”

Bloodstone names and game moves anchor to block ancestry. Deep reorgs **orphan name updates** and game ZMQ histories — integrators and DEX atomic trades observe inconsistent state and halt.

**Outcome:** Reorg wins PoW but **loses application layer**.

### Scenario E: “51% the pool, not the chain”

Pool ≥51% affects **payout splits**, not canonical chain. QUASAR explicitly separates **pool economics** vs **consensus security** (see Blurt partnership response).

**Outcome:** Miners may complain; chain tip remains honest on full nodes.

---

## 11. What QUASAR is not

| Myth | Truth |
|------|-------|
| “QUASAR replaces PoW” | No — it **amplifies** multi-algo PoW |
| “Phones vote on consensus” | No — witnesses **observe**; they do not sign blocks into chain |
| “Zero risk” | Nothing is zero risk; QUASAR raises **cost, time, and detectability** |
| “Fully deployed day one” | L1–L2 live; L3–L7 phased (see §12) |

We do not promise magic. We promise **asymmetric warfare** favoring defenders with a real fleet.

---

## 12. Implementation roadmap

| Phase | Layers | Deliverable | Consensus change? |
|-------|--------|-------------|-------------------|
| **Now** | L1–L2 | Core 0.7.x multi-algo | Already live |
| **Phase 1** (weeks) | L3, L6 | Braid status in explorer + exchange API; witness-aware confirmation guide | No |
| **Phase 2** (months) | L4, L5, L7 | Witness capsule schema; LAN Echo in Android; pool tripwire alerts | No |
| **Phase 3** (research) | L3 hard | Consensus-enforced braid finality (optional soft-fork) | Maybe |
| **Parallel** | — | Security appendix with worked attack budgets per algo | Docs only |

---

## 13. Why this makes people say “wow”

Most projects respond to 51% fear with:

- A single merged-mining slide  
- “We have lots of hashrate trust me”  
- A Discord mod saying “unlikely”  

Bloodstone QUASAR says:

> **Come attack us — you will need three hashrate markets, a braid that stays balanced, mesh anchors you cannot forge from a VPS, LAN echoes from real living rooms, exchanges that read witness depth, and a pool that screams when you rent SHA256. And even then, you still fight weighted work math baked into consensus.**

That is not a mood board. That is **software architecture**.

---

## 14. Integrator checklist

1. Run your own **exchange node** or **full node** — never trust pool RPC alone  
2. Poll `/api/exchange` and (when live) `/api/quasar/status`  
3. Require **mesh witness quorum** before large deposits  
4. Monitor **braid skew** — bump confirmations when SHA256d-heavy  
5. Read [RPC Reference](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-RPC-Reference.md) for `getblockchaininfo`, `getchaintips`, `getmininginfo`  
6. Study [Blurt 51% response](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Blurt-Partnership-Response.md) for consensus vs pool distinction  

---

## Related documents

- [Economic Model White Paper](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Economic-Model-White-Paper.docx)  
- [Decentralized Network White Paper](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Decentralized-Network-White-Paper.docx)  
- [Infrastructure Independence White Paper](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Infrastructure-Independence-White-Paper.docx)  
- [Chain Mesh Storage White Paper](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx)  
- [Blurt LAN Pool Technical Response](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Blurt-LAN-Pool-And-Mesh-Technical-Response.md)  

---

*Bloodstone · QUASAR 51% Defense · July 2026 · “You don’t need 51% of one hash. You need 51% of reality.”*