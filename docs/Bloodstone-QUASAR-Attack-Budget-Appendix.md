# Bloodstone QUASAR — Attack Budget Appendix

**Companion to:** [51% Defense White Paper](./Bloodstone-QUASAR-51-Percent-Defense-White-Paper.md)  
**Updated:** July 2026

---

## 1. Purpose

This appendix quantifies the **marginal cost** of attacking Bloodstone under QUASAR Phases 1–3. It is a planning document for exchanges and node operators — not a formal security proof.

---

## 2. Attack surfaces and budgets

| Surface | Naïve 51% model | QUASAR-adjusted budget |
|---------|-----------------|------------------------|
| SHA256d lane only | Rent ASIC hashrate | Down-weighted in chain work; braid skew triggers deferred finality |
| Single-algo dominance | Control one retarget | Triple-purpose mining keeps other lanes producing blocks |
| Sybil HTTP nodes | Spin up VPS fleet | Witness capsules require sync + mesh anchor fees |
| Fake LAN presence | Spoof headers | mDNS echo quorum needs real residential subnets |
| Exchange crediting | Race shallow reorg | Witness + braid policy bumps confirmations to 20 |
| Large spend during attack | Drain hot wallet | Phase 3 enforcement halts/deferrs by amount tier |

---

## 3. Epoch braid economics

An attacker renting SHA256d can skew **one epoch** (default 10 blocks ≈ 15 minutes) before:

- Braid status → `deferred` (SHA256d ≥ 85%, CPU braid < 10%)
- Deposit confirmations → 20 blocks
- Medium spends (≥ 100 STONE) → deferred
- Large spends (≥ 10,000 STONE) → halted

**Sustained** takeover requires winning weighted work across **all three** algorithms simultaneously — not just the SHA256d lane.

---

## 4. Witness + LAN multiplier

| Signal | Quorum | Effect on attacker |
|--------|--------|-------------------|
| Mesh witness capsules | 3 independent tips | Split detection halts crediting |
| LAN echo | 2+ subnets agree | Split-brain halts spends |
| Tripwire | SHA256d surge + orphan shadow | Defers all medium+ spends 30 min |

Each layer is **independent** — compromising one does not bypass the others.

---

## 5. Phase 3 enforcement tiers

| Amount (STONE) | Healthy braid | Deferred braid | Tripwire active |
|----------------|---------------|----------------|-----------------|
| < 100 | Allow | Allow | Allow |
| 100 – 9,999 | Allow | Defer (15 min) | Defer (30 min) |
| ≥ 10,000 | Allow* | Halt | Defer |

\*Large spends also require witness quorum ≥ 3 when status is `pending`.

---

## 6. Operator recommendations

1. Set `QUASAR_ENFORCEMENT_MODE=policy` on portal, miner-web, and wallet services
2. Sync braid index every upkeep cycle (`BLOODSTONE_QUASAR_BRAID_SYNC=1`)
3. Monitor `/api/quasar/alerts` for tripwire events
4. Do not lower confirmation floors during `deferred` braid epochs
5. Plan fork activation only after testnet rehearsal and exchange sign-off

---

## 7. References

- [Phase 3 Braid Finality Proposal](./Bloodstone-QUASAR-Phase3-Braid-Finality-Proposal.md)
- [Witness-Aware Confirmation Guide](./Bloodstone-QUASAR-Witness-Aware-Confirmation-Guide.md)
- Live status: `/api/quasar/status`