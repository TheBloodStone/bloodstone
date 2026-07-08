# Bloodstone QUASAR — Phase 4 Fork Rehearsal Proposal

**Status:** Live (software layer) · testnet rehearsal started  
**Version:** 4.0  
**Updated:** July 2026

---

## 1. Summary

Phase 4 implements **miner signaling infrastructure** and **testnet fork rehearsal** for the `quasar_braid_finality` soft-fork proposed in Phase 3. Policy enforcement remains unchanged.

| Deliverable | Phase 4 |
|-------------|---------|
| Version-bit signaling tracker | `/api/quasar/signaling` |
| Rehearsal coordinator | `/api/quasar/fork-rehearsal` |
| Persistent rehearsal status | `{datadir}/indexes/braid/fork-rehearsal/status.json` |
| Core deployment | `DEPLOYMENT_QUASAR_BRAID` bit 3 |
| Miner operator guide | Published to `/downloads` |

---

## 2. Architecture

```
Miners set nVersion bit 3
        ↓
bloodstoned (future) OR Python window scanner
        ↓
/api/quasar/signaling  →  state: defined → started → locked_in → active
        ↓
/api/quasar/fork-rehearsal  →  readiness checks (index, signaling, braid health)
```

Readiness checks (all must pass for `ready: true`):

1. Braid index synced (`enforcement_ready`)
2. At least one signaling block OR BIP9 `started`
3. Braid status not `deferred` (rehearsal prefers healthy/skewed epochs)
4. Fork start height reached (if configured)

---

## 3. Chain deployment parameters

| Network | Bit | Start | Timeout |
|---------|-----|-------|---------|
| Mainnet | 3 | `NEVER_ACTIVE` | — |
| Testnet | 3 | 2026-07-01 UTC | 2028-01-01 UTC |
| Regtest / Signet | 3 | `ALWAYS_ACTIVE` | — |

---

## 4. API reference

### `GET /api/quasar/signaling`

Returns window scan of block versions, threshold math, and derived BIP9 state.

### `GET /api/quasar/fork-rehearsal`

Returns signaling + braid index + readiness checks + `next_steps`.

Append `?persist=1` to write `status.json` for dashboards.

---

## 5. Roadmap after Phase 4

| Phase | Focus |
|-------|-------|
| **Phase 5** (proposed) | Consensus braid validation in `validation.cpp` when fork `active` |
| **Parallel** | Mainnet start-height vote, exchange operator sign-off |

---

*Bloodstone · QUASAR Phase 4 · July 2026*