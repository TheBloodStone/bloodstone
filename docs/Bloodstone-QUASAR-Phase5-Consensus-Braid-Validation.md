# Bloodstone QUASAR — Phase 5 Consensus Braid Validation

**Status:** Live (gated on fork activation)  
**Version:** 5.0  
**Updated:** July 2026

---

## 1. Summary

Phase 5 adds **consensus-level epoch braid validation** in `validation.cpp`. Rules apply only when the `quasar_braid_finality` BIP9 deployment is **active** for the connecting chain.

| Layer | Phase 5 |
|-------|---------|
| Consensus | Reject deferred epochs without cross-algo restitch at epoch boundaries |
| Policy | Unchanged — enforcement API, wallet gates, braid index |
| Regtest / Signet | `ALWAYS_ACTIVE` — use for local braid rejection drills |

---

## 2. Rule (epoch boundary)

Every **E** blocks (default **10**, `-quasarepochblocks`):

1. Compute braid vector `(sha256d, neoscrypt, yespower)` for the epoch.
2. If status is **deferred** (SHA256d ≥ 85% with CPU < 10%):
3. Require **≥2 algorithm streams** with ancestry to the previous epoch tip.
4. Otherwise return `bad-quasar-braid` and reject the block.

Disable even when active: `-quasarbraidconsensus=0`.

---

## 3. API / RPC

- `getquasaractivation` — `phase: 5`, `consensus_braid_rejection: true`
- `/api/quasar/activation` — same descriptor via Python layer
- Mainnet: deployment remains `defined` until miners lock in bit 3

---

## 4. Roadmap after Phase 5

| Track | Focus |
|-------|-------|
| Mainnet | Vote start height, exchange sign-off, miner signaling campaign |
| Convergence | Full Pi-hosted Condenser (Layer 5 UI beyond embed preview) |
| QUASAR L6–7 | Exchange witness policy, anomaly tripwire hardening |

---

*Bloodstone · QUASAR Phase 5 · July 2026*