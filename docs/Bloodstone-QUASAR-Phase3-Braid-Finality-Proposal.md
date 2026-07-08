# Bloodstone QUASAR — Phase 3 Braid Finality Proposal

**Status:** Policy layer live · consensus soft-fork research  
**Version:** 3.0  
**Updated:** July 2026

---

## 1. Summary

Phase 3 adds **persistent epoch braid indexing**, **spend enforcement policy**, and **RPC scaffolding** for an optional consensus soft-fork (`quasar_braid_finality`). This does **not** activate consensus rules until miners signal via version bits.

| Layer | What ships now | What waits for fork |
|-------|----------------|---------------------|
| Software policy | Braid index, enforcement API, wallet/swap gates | — |
| Node RPC | `getquasarbraid`, `getquasaractivation` (reads index file) | Reject invalid blocks at validation |
| Miner signaling | Deployment descriptor in `/api/quasar/activation` | 75% window over 1008 blocks |

---

## 2. Epoch braid index

The index lives at `{datadir}/indexes/braid/`:

```
indexes/braid/
  state.json          # last synced height, epoch metadata
  epochs/epoch-*.json # per-epoch braid vectors + status
  rpc-export.json     # consumed by getquasarbraid RPC
```

Sync via upkeep cron or manually:

```bash
python3 /root/sync-quasar-braid-index.py
```

API: `GET /api/quasar/braid-index` — append `?sync=1` to refresh from node RPC before returning.

---

## 3. Spend enforcement (policy gate)

`POST /api/quasar/enforcement/check` with body `{"amount_stone": 500}` returns:

| Field | Meaning |
|-------|---------|
| `allowed` | Whether spend may proceed under current policy |
| `action` | `allow`, `defer`, or `halt` |
| `reason` | Human-readable policy explanation |
| `mode` | `policy` (default), `strict`, or `off` |

Default thresholds (env-configurable):

- **Defer** at ≥ 100 STONE when braid is skewed/deferred or tripwire active
- **Halt** at ≥ 10,000 STONE when braid is deferred or witness/LAN split detected

Wallet swap pool (`bloodstone-wallet-web/swap_service.py`) enforces the same gate on STONE payouts unless `QUASAR_ENFORCEMENT_MODE=off`.

---

## 4. Soft-fork deployment descriptor

`GET /api/quasar/activation` and `getquasaractivation` RPC expose BIP9-style parameters:

| Parameter | Default | Notes |
|-----------|---------|-------|
| `deployment` | `quasar_braid_finality` | Version-bits name |
| `start_height` | `0` (unset) | Set via `QUASAR_FORK_START_HEIGHT` when ready |
| `timeout_height` | `0` | Abort window if not locked in |
| `threshold` | 750 / 1008 | 75% miner signaling |
| `state` | `defined` | `started`, `locked_in`, `active` after signaling |

**Consensus rule (proposed, not yet active):** reject blocks whose epoch braid vector fails continuity or deferred-finality restitch checks when fork state is `active`.

---

## 5. Integrator checklist

1. Poll `/api/quasar/status` — includes `braid_index`, `enforcement_mode`, `activation`
2. Poll `/api/quasar/braid-index` for historical epoch records
3. Before large withdrawals, call `/api/quasar/enforcement/check`
4. Run your own node; optionally sync braid index locally
5. Read [Witness-Aware Confirmation Guide](./Bloodstone-QUASAR-Witness-Aware-Confirmation-Guide.md)

---

## 6. Roadmap

1. **Now:** Policy enforcement + persistent index + RPC read path
2. **Next:** Miner operator guide, testnet fork rehearsal
3. **Later:** Version-bits activation on mainnet after exchange + pool operator review

See also: [Attack Budget Appendix](./Bloodstone-QUASAR-Attack-Budget-Appendix.md)