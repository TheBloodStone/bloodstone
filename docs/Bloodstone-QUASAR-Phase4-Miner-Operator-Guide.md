# Bloodstone QUASAR — Phase 4 Miner Operator Guide

**Audience:** Pool operators, solo miners, stratum integrators  
**Deployment:** `quasar_braid_finality` (version bit **3**)  
**Updated:** July 2026

---

## 1. What Phase 4 does

Phase 4 begins **fork rehearsal** for consensus-enforced epoch braid finality. Policy enforcement (Phase 3) stays live. Phase 4 adds:

- Miner **version-bit signaling** in block `nVersion`
- Signaling tracker API (`/api/quasar/signaling`)
- Testnet rehearsal coordinator (`/api/quasar/fork-rehearsal`)
- BIP9 deployment `quasar_braid_finality` in core (mainnet **defined**, testnet **started**)

Consensus braid rejection rules activate only after **lock-in** and a core build that includes the deployment.

---

## 2. Signal the fork

Set version bit **3** in mined blocks:

```
recommended_nVersion = 0x20000000 | (1 << 3) = 0x20000008
```

| Chain | Window | Threshold | Start |
|-------|--------|-----------|-------|
| Mainnet | 2016 blocks | 1815 (90%) | Not scheduled (`NEVER_ACTIVE`) |
| Testnet | 2016 blocks | 1512 (75%) | 2026-07-01 UTC |
| Regtest / Signet | 144–2016 | 75–90% | `ALWAYS_ACTIVE` (rehearsal) |

### bloodstoned / pool software

After upgrading to a core build with `quasar_braid_finality`:

- `getblocktemplate` includes `vbrequired` when deployment is `started`
- `getblockchaininfo` → `softforks.quasar_braid_finality` reports BIP9 state
- `getquasaractivation` returns deployment parameters

Until core is rebuilt, use the **software tracker** at `/api/quasar/signaling` (scans block versions via RPC).

---

## 3. Monitor signaling

```bash
curl -s https://bloodstonewallet.mytunnel.org/api/quasar/signaling | jq .
```

Key fields:

| Field | Meaning |
|-------|---------|
| `signaling_blocks` | Blocks with bit 3 set in current window |
| `threshold_blocks` | Blocks needed for lock-in |
| `state` | `defined`, `started`, `locked_in`, `active`, `failed` |
| `recommended_miner_version` | Set this in block template |

Rehearsal readiness:

```bash
curl -s https://bloodstonewallet.mytunnel.org/api/quasar/fork-rehearsal | jq .readiness
```

---

## 4. Operator checklist

1. **Sync braid index** — `python3 /root/sync-quasar-braid-index.py` on coordinator nodes
2. **Upgrade core** — build from `bloodstone-chain` / `bloodstone-core-src` with Phase 4 deployment
3. **Signal bit 3** — on testnet first; mainnet only after exchange sign-off
4. **Poll signaling** — every retarget window; alert if `state` stalls in `started`
5. **Halt large pool payouts** when braid is `deferred` (policy layer, independent of fork)
6. **Run rehearsal cron** — `python3 /root/rehearse-quasar-fork.py` (or upkeep handles it)

---

## 5. Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `QUASAR_FORK_BIT` | `3` | Version bit position |
| `QUASAR_FORK_WINDOW` | `2016` | Confirmation window |
| `QUASAR_FORK_THRESHOLD` | `1815` | Mainnet lock-in threshold |
| `QUASAR_FORK_THRESHOLD_TESTNET` | `1512` | Testnet threshold |
| `QUASAR_FORK_START_HEIGHT` | `0` | Height-gated start (software tracker) |
| `QUASAR_FORK_REHEARSAL_MODE` | `testnet` | Rehearsal label |

---

## 6. Related documents

- [Phase 3 Braid Finality Proposal](./Bloodstone-QUASAR-Phase3-Braid-Finality-Proposal.md)
- [Witness-Aware Confirmation Guide](./Bloodstone-QUASAR-Witness-Aware-Confirmation-Guide.md)
- [Attack Budget Appendix](./Bloodstone-QUASAR-Attack-Budget-Appendix.md)

---

*Bloodstone · QUASAR Phase 4 · July 2026*