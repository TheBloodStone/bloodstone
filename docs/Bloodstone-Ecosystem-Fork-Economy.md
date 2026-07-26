# Bloodstone Ecosystem Fork Economy

**Status:** Product lock · July 2026  
**Schema:** `bloodstone/ecosystem-fork-economy/v1`  
**Audience:** Fork Lab creators, mesh providers, LRGK / sister-chain founders, resellers  

---

## Problem (what founders agreed)

Sister coins and Fork Lab launches must **boost Bloodstone**, not cannibalise it.

- Ryan / LRGK-class: expand mesh rewards **without** competing with STONE for resource settlement.  
- Izal and future creators: want their own minable coin under the **same** rules.  
- Mesh providers: should earn from **each** new coin’s hash, while users still pay STONE for resources.

---

## Locked formula — when a coin is added

| # | Rule | Detail |
|---|------|--------|
| **1** | **Merge-mine surface grows** | Miners can merge-mine the new coin. **Forks MUST merge-mine Bloodstone (STONE)** on SHA256d/AuxPoW. Sister links are **optional** checkboxes. Bloodstone may **optionally** enable each child (default **off**). CPU lanes stay local per chain. |
| **2** | **Mesh providers earn from the new coin’s mining** | A locked **bps of that coin’s block subsidy / pool payout** is paid to mesh providers **in the new ticker** (default **1000 bps = 10%**). This is **additive** income. |
| **3** | **Protocol services settle in STONE** | **All native Bloodstone protocol services are settled exclusively in STONE.** That includes storage, compute, bandwidth, mesh networking, content cataloguing, identity services, and **future core protocol capabilities** — so the rule need not be re-amended for each new native capability. Fork coins do not reprice or replace protocol settlement. |
| **4** | **Reseller path** | Resellers may accept fork coins / USDT from customers, but **bulk purchase of native protocol services settles in STONE**. |

### Default block split (per 10 000 bps)

| Recipient | bps | Paid in |
|-----------|----:|---------|
| Miners / pool shares | **9000** (default) | Fork ticker |
| Mesh providers | **1000** (default) | Fork ticker |
| Lab reserve | **0** (default) | Fork ticker |

Example: **100** FOO per block → **90 FOO** miners + **10 FOO** mesh providers.

Env overrides:

- `ECOSYSTEM_MESH_PROVIDER_REWARD_BPS` (default `1000`)  
- `ECOSYSTEM_FORK_LAB_RESERVE_BPS` (default `0`)

---

## Constitutional settlement (durable wording)

> **All native Bloodstone protocol services are settled exclusively in STONE.**

**Protocol services** (illustrative, not a closed list):

- Storage  
- Compute  
- Bandwidth  
- Mesh networking  
- Content cataloguing  
- Identity services  
- Future core protocol capabilities  

This keeps the rule **simple, durable, and extensible** — the same architectural discipline as the Edge Presence Proof RFC: constitutional language stays stable while implementations evolve.

---

## Non-cannibalisation (LRGK & friends)

| Layer | Currency | Role |
|-------|----------|------|
| **Native protocol services** (what users buy on Bloodstone rails) | **STONE** | Always / exclusive |
| Mesh **hash bonus** from coin X | **X** | Extra stream when X is mined / merge-mined |
| Companion chain (e.g. LRGK) | Own ticker | Same formula; optional sister; must not divert protocol settlement off STONE |

**One-line test:** *Does this coin increase STONE demand for protocol services and give mesh more optional reward streams?* If yes → ship. If it tries to replace STONE protocol settlement → reject.

---

## Implementation map

| Piece | Status |
|-------|--------|
| Policy module `ecosystem_fork_economy.py` | **Live** |
| Fork Lab manifests (`ecosystem_economy` field) | **Live** |
| Public API `GET /api/ecosystem-fork-economy` | **Live** |
| Fork Lab UI “Ecosystem formula” panel | **Live** |
| Merge-mine registry (mandatory parent) | **Live** (see Merge-Mining.md) |
| Pool accounting: auto-split mesh bps to providers | **Next** (policy already binds every new coin) |
| Multi-aux stratum jobs for N children | **Next** |

---

## APIs

```http
GET /api/ecosystem-fork-economy
GET /api/ecosystem-merge-mine
GET /api/fork-lab
```

Each live fork public object includes:

- `merge_mine` — parent mandatory, sisters optional  
- `ecosystem_economy` — this formula + numeric split for that ticker  

---

## Related

- [Bloodstone-Ecosystem-Merge-Mining.md](./Bloodstone-Ecosystem-Merge-Mining.md)  
- Fork Lab: `/fork-lab/`  
- Mesh / catalog settlement remains STONE on portal monetize rails  

---

*Additive mesh · STONE demand floor · fork-coin hash bonuses for providers*
