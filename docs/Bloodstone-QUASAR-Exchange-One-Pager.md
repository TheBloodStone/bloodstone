# Bloodstone QUASAR — Exchange Integrator One-Pager

**51% defense summary for CEX ops, wallet teams, and listing reviewers**  
**Version 1.0 · July 2026**  
**Coordinator:** https://bloodstonewallet.mytunnel.org  
**Listing JSON:** https://bloodstonewallet.mytunnel.org/api/exchange  
**QUASAR hub:** https://bloodstonewallet.mytunnel.org/quasar/

---

## TL;DR for listing committees

| Question | Bloodstone answer |
|----------|-------------------|
| Single PoW algorithm? | **No** — SHA256d + Neoscrypt + Yespower (three lanes) |
| 51% SHA256 rent = chain takeover? | **No** — weighted work favors CPU lanes; see QUASAR layers |
| Can we use pool VPS RPC for deposits? | **Never** — run exchange node package or your own full node |
| Default deposit confirmations? | **6** (base); increase when QUASAR braid/witness signals skew |
| SPV available? | **Yes** — ElectrumX `ssl://bloodstonewallet.mytunnel.org:50002` |

**Tagline:** *You don't need 51% of one hash. You need 51% of reality.*

---

## What is QUASAR?

**QU**orum **A**daptive **S**ecurity **A**gainst **R**eorgs — a seven-layer **software** defense that wraps live multi-algo PoW:

| Layer | Name | Status | Exchange relevance |
|-------|------|--------|-------------------|
| L1 | Triple-purpose PoW | ✅ Live | Three independent attack markets |
| L2 | Tri-algo work tensor | ✅ Live | SHA256d dominance ≠ tip control |
| L3 | Epoch braid finality | 📋 Phase 1 | Bump confirms when braid skewed |
| L4 | Mesh witness capsules | 🛠️ Phase 2 | Quorum depth before large credits |
| L5 | LAN echo quorum | 🛠️ Phase 2 | Split-brain detection signal |
| L6 | Exchange witness policy | 📋 Phase 1 | Dynamic `confirmations_deposit` |
| L7 | Anomaly tripwires | 🛠️ Phase 2 | Halt/auto-bump on rental spikes |

---

## Integrator actions (do this)

1. **Run your own node** — `bloodstone-exchange-node-*-linux-x86_64.tar.gz` from `/downloads/`  
2. **Poll** `/api/exchange` for genesis, seeds, ElectrumX, confirmation defaults  
3. **Monitor** algo mix — if SHA256d share spikes vs Neoscrypt/Yespower, **increase confirmations** (12–20)  
4. **Require** `getblockchaininfo` / `getchaintips` agreement before large hot-wallet credits  
5. **Read** full white paper: `Bloodstone-QUASAR-51-Percent-Defense-White-Paper.md`  

---

## Confirmation policy (recommended)

| Signal | Action |
|--------|--------|
| Normal epoch braid + node tip stable | 6 confirmations (listing default) |
| SHA256d-heavy epoch (>85% blocks one algo) | 12–20 confirmations |
| Witness/capsule disagreement (when live) | Halt deposits, manual review |
| Pool tripwire: possible private fork | Halt + alert ops |

*Proposed `/api/quasar/status` endpoint — poll alongside `/api/exchange` when live.*

---

## Why rented hashrate is insufficient

Worked example (order-of-magnitude):

- Attacker: **80%** SHA256d, **10%** Neoscrypt, **10%** Yespower  
- Consensus uses `powAlgoLog2Weight` (SHA256d lowest, Yespower highest)  
- Honest CPU majority retains disproportionate **chain decision mass**

An attacker must win **tensor work**, not a single rental billboard.

---

## Contacts & artifacts

| Resource | URL |
|----------|-----|
| Exchange listing page | https://bloodstonewallet.mytunnel.org/exchange/ |
| QUASAR landing | https://bloodstonewallet.mytunnel.org/quasar/ |
| RPC reference | `/downloads/Bloodstone-RPC-Reference.md` |
| Full QUASAR paper | `/downloads/Bloodstone-QUASAR-51-Percent-Defense-White-Paper.md` |

---

*Bloodstone · STONE mainnet · Built with Grok Build · QUASAR Exchange One-Pager v1.0*