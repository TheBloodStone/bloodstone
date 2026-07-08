# Bloodstone Halving Schedule

**July 2026 · v1.0**  
**Network:** Bloodstone mainnet (STONE)  
**Live schedule API:** `https://bloodstonewallet.mytunnel.org/mining/api/pool/subsidy-schedule`

---

## Executive summary

Bloodstone proof-of-work issuance follows a **two-phase monetary schedule** inherited from SpaceXpanse ROD consensus:

1. **Halving phase (eras 0–4)** — the block subsidy is cut in half every **1,054,080 blocks** (~2.7 years at ~80 s mean block time).
2. **Inflation phase (eras 5–63)** — instead of further halvings, each era mints a calculated inflation tranche spread evenly across the interval (~**2.956%** growth per era, factor **1.02956**).
3. **End of PoW (era 64+)** — block subsidy reaches **0**; no further PoW minting.

Bloodstone relaunched in **June 2026** with a **100 STONE** era-0 reward. A scheduled consensus upgrade at **block 12,000** raises the subsidy base to **1,000 STONE** for all subsequent halving math. Blocks below height 12,000 remain valid at 100 STONE.

As of this document (tip height **~9,626**, July 2026), the network is still in **era 0** at **100 STONE** per block. The 1,000 STONE fork activates in approximately **2,374 blocks**.

---

## How the halving index works

| Constant | Value | Meaning |
|----------|-------|---------|
| `nSubsidyHalvingInterval` | **1,054,080** | Blocks per era |
| `initialSubsidy` | **100 STONE** (pre-fork) / **1,000 STONE** (post block 12,000) | Era-0 base reward |
| Inflation factor | **1.02956** | ~2.956% per era after era 4 |
| Inflation base coins | **1,833,823,998** | Legacy ROD inflation curve anchor |
| Genesis premine | **199,999,998 STONE** | One-time treasury allocation (not PoW) |

**Halving index (era):**

```
era = floor(blockHeight / 1,054,080)
```

**Eras 0–4 (halving phase):**

```
subsidy = effectiveInitialSubsidy >> era
```

Where `effectiveInitialSubsidy` is **100 STONE** for heights 1–11,999 and **1,000 STONE** for heights ≥ 12,000.

**Eras 5–63 (inflation phase):**

The legacy SpaceXpanse formula computes an inflation tranche for the era, then divides it across 1,054,080 blocks. When the initial subsidy differs from legacy **800 ROD**, issuance is scaled:

```
scale = effectiveInitialSubsidy / 800
subsidy = (inflationTranche / 1,054,080) × scale
```

For the **1,000 STONE** post-fork base, `scale = 1.25`. For the original **100 STONE** relaunch base, `scale = 0.125`.

**Era 64+:** subsidy = **0**.

---

## 1,000 STONE fork at block 12,000

| Item | Detail |
|------|--------|
| Activation height | **12,000** |
| Pre-fork subsidy | **100 STONE** per block (heights 1–11,999) |
| Post-fork subsidy | **1,000 STONE** per block (heights ≥ 12,000, era 0) |
| Chain compatibility | All pre-fork blocks remain valid; no genesis change |
| Halving math | Eras 1–4 halve from the **1,000 STONE** base |

### Era 0 minting split (with fork)

| Segment | Blocks | Rate | STONE minted |
|---------|--------|------|--------------|
| Pre-fork | 1 – 11,999 | 100 STONE | **1,199,900** |
| Post-fork | 12,000 – 1,054,079 | 1,000 STONE | **1,042,080,000** |
| **Era 0 total** | 1,054,080 PoW blocks | — | **~1.043 billion STONE** |

---

## Halving schedule — eras 0–4 (post-fork, 1,000 STONE base)

Approximate calendar years assume **~80 s** mean block time from the June 2026 genesis. Adjust if network block times change.

| Era | Start block | Subsidy / block | Phase | STONE minted (era) | Approx. year |
|-----|-------------|-----------------|-------|-------------------|--------------|
| 0 | 1 | 100 → **1,000**¹ | Halving | ~1.043 B | 2026 |
| 1 | 1,054,080 | **500** | Halving | ~528 M | ~2029 |
| 2 | 2,108,160 | **250** | Halving | ~265 M | ~2031 |
| 3 | 3,162,240 | **125** | Halving | ~132 M | ~2034 |
| 4 | 4,216,320 | **62.5** | Halving | ~66 M | ~2037 |

¹ Era 0 uses **100 STONE** until block 12,000, then **1,000 STONE** for the remainder of the era.

### Milestones from current tip (~9,626)

| Event | Block height | Blocks remaining |
|-------|--------------|----------------|
| 1,000 STONE fork | 12,000 | ~2,374 |
| Era 1 halving (500 STONE) | 1,054,080 | ~1,044,454 |
| Era 5 inflation begins | 5,270,400 | ~5,260,774 |

---

## Inflation phase — eras 5+ (scaled for 1,000 STONE base)

At block **5,270,400** (era 5), halving stops and inflation begins. With the **1,000 STONE** base and scale factor **1.25**, projected subsidies are:

| Era | Start block | Subsidy / block (projected) | STONE minted (era) | Approx. year |
|-----|-------------|----------------------------|-------------------|--------------|
| 5 | 5,270,400 | **~66.19** | ~70 M | ~2039 |
| 6 | 6,324,480 | **~68.14** | ~72 M | ~2042 |
| 7 | 7,378,560 | **~70.15** | ~74 M | ~2045 |
| 8 | 8,432,640 | **~72.23** | ~76 M | ~2047 |
| 9 | 9,486,720 | **~74.36** | ~78 M | ~2050 |
| 10 | 10,540,800 | **~76.56** | ~81 M | ~2053 |

Eras 5–63 continue with ~2.956% growth per era. Era **64+** ends PoW issuance (subsidy = 0).

### Chain vs projected at era 5 (Bloodstone Core 0.7.0)

Without the **0.7.0** inflation-scaling consensus fix, on-chain era-5 subsidy would follow the unscaled legacy ROD curve (~**52.95 STONE** at era 5 with the 1,000 STONE fork active). Bloodstone Core **0.7.0** scales inflation when `initialSubsidy < 800 STONE`, aligning chain and pool projections.

| Era | On-chain (pre-0.7.0) | Projected (0.7.0 scaled) |
|-----|----------------------|--------------------------|
| 5 | ~52.95 STONE | **~66.19 STONE** |
| 6 | ~54.51 STONE | **~68.14 STONE** |
| 7 | ~56.12 STONE | **~70.15 STONE** |

**Recommendation:** Deploy Bloodstone Core **0.7.0** network-wide before block **5,270,400**.

---

## Cumulative PoW supply (premine + projected issuance)

| Source | STONE |
|--------|-------|
| Genesis premine | 199,999,998 |
| Era 0 PoW (with 1,000 fork) | ~1,043,000,000 |
| Eras 1–4 PoW | ~991,000,000 |
| Eras 5–14 PoW (inflation) | ~799,000,000 |
| **Cumulative after era 14** | **~3.03 billion STONE** |

PoW issuance dominates long-run supply growth; the premine is a fixed one-time allocation.

---

## Pool and miner alignment

The unified mining pool reads the **on-chain subsidy** at each block height when crediting miners:

| Component | Role |
|-----------|------|
| `pool_block_subsidy.py` | Mirrors `GetBlockSubsidy()`; queries `getblockstats` via RPC |
| `pool_db.distribute_block()` | Credits miners using actual coinbase subsidy + fees |
| Dashboard | Shows halving era, next halving height, and subsidy projections |
| API | `GET /mining/api/pool/subsidy-schedule` |

**Miner impact at halvings:** gross per-block pool revenue drops ~50% at each era boundary (eras 0–4). Dashboard estimates update automatically; no stratum or wallet changes are required.

Verify live subsidy at any height:

```bash
bloodstone-cli getblockstats <height> '["subsidy"]'
```

```bash
curl -sS "https://bloodstonewallet.mytunnel.org/mining/api/pool/subsidy-schedule" | python3 -m json.tool
```

---

## Reference implementation

Authoritative subsidy logic lives in:

- **Pool resolver:** `/root/pool_block_subsidy.py`
- **Consensus:** `bloodstone-linux-build/src/validation.cpp` (`GetBlockSubsidy()`)
- **Mainnet params:** `bloodstone-linux-build/src/chainparams.cpp`

Environment overrides (pool / projections):

| Variable | Default | Purpose |
|----------|---------|---------|
| `BLOODSTONE_SUBSIDY_HALVING_INTERVAL` | 1054080 | Blocks per era |
| `BLOODSTONE_INITIAL_SUBSIDY_STONE` | 100 | Pre-fork era-0 base |
| `BLOODSTONE_INCREASED_SUBSIDY_HEIGHT` | 12000 | 1,000 STONE fork height |
| `BLOODSTONE_INCREASED_SUBSIDY_STONE` | 1000 | Post-fork era-0 base |
| `BLOODSTONE_INFLATION_FACTOR` | 1.02956 | Per-era inflation multiplier |
| `BLOODSTONE_INFLATION_SCALE` | auto (base/800) | Projection scaling for era 5+ |

---

## Related documentation

- [Bloodstone Economic Model White Paper](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Economic-Model-White-Paper.docx) — full STONE economics, pool waterfall, cross-algo incentives
- [Subsidy Fork Release Notes](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Subsidy-Fork-Release-Notes.docx) — Bloodstone Core 0.7.0 upgrade checklist
- [Subsidy Fork 1000 STONE White Paper](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Subsidy-Fork-1000-White-Paper.docx) — technical spec for the block 12,000 fork
- [Mining dashboard](https://bloodstonewallet.mytunnel.org/mining/)

---

*Document generated July 2026. Live tip height and rewards may differ — use the subsidy-schedule API for current values.*