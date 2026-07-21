# Bloodstone Issuance Schedule (Stepped + QSE)

**July 2026 · v2.0**  
**Network:** Bloodstone mainnet (STONE)  
**Live schedule API:** `https://bloodstonewallet.mytunnel.org/mining/api/pool/subsidy-schedule`

---

## Executive summary

Bloodstone PoW issuance is a **stepped annual schedule** ending in a permanent tail called **QUASAR Security Emission (QSE)** — not classic 50% halvings forever.

| Phase | Subsidy / block | Duration |
|-------|-----------------|----------|
| **Year 1** | **100 STONE** | 1 issuance year |
| **Years 2–3** | **1,000 STONE** | 2 issuance years |
| **Year 4** | **750 STONE** | 1 year |
| **Year 5** | **500 STONE** | 1 year |
| **Year 6** | **350 STONE** | 1 year |
| **Year 7** | **250 STONE** | 1 year |
| **Year 8+** | **200 STONE** base forever | **QSE tail** |

```
Genesis
  100          year 1
  1000         years 2–3
    ↓
  750
    ↓
  500
    ↓
  350
    ↓
  250
    ↓
  200 forever   ← QUASAR Security Emission (QSE)
```

**Why this shape:** softer step-downs after the growth years avoid a harsh year-4 cliff from the first layout, while keeping a permanent security budget instead of driving subsidy to zero.

---

## Constants

| Constant | Value | Meaning |
|----------|-------|---------|
| Mean block time (design) | **~80 s** | Target spacing |
| Blocks per issuance year | **394,470** | `round(365.25 × 86400 / 80)` |
| Year-1 subsidy | **100 STONE** | Bootstrap |
| Growth subsidy | **1,000 STONE** | Years 2–3 |
| QSE base | **200 STONE** | Year 8+ floor |
| Genesis premine | **199,999,998 STONE** | One-time (not PoW) |

**Issuance year index (0-based):**

```
yearIndex = floor(blockHeight / 394470)
```

**Human year** = `yearIndex + 1`.

---

## Full height schedule

| Human year | Year index | Start height | End height (excl.) | Subsidy / block | Phase |
|------------|------------|--------------|--------------------|-----------------|-------|
| 1 | 0 | 0 | 394,470 | **100** | Bootstrap |
| 2 | 1 | 394,470 | 788,940 | **1,000** | Growth |
| 3 | 2 | 788,940 | 1,183,410 | **1,000** | Growth |
| 4 | 3 | 1,183,410 | 1,577,880 | **750** | Step-down |
| 5 | 4 | 1,577,880 | 1,972,350 | **500** | Step-down |
| 6 | 5 | 1,972,350 | 2,366,820 | **350** | Step-down |
| 7 | 6 | 2,366,820 | 2,761,290 | **250** | Step-down |
| 8+ | ≥7 | 2,761,290 | ∞ | **200** (QSE) | Tail forever |

Approximate calendar years assume ~80 s mean block time from genesis. Wall-clock dates slide if block times differ.

### Pre-ICO historical note

Before the post-ICO fork height, consensus still pays **1 STONE** (legacy SpaceXpanse rule). After post-ICO, the stepped table above applies. Pool payouts always prefer the **actual coinbase** for confirmed blocks.

---

## Why 200? (QSE economics)

At **~80 s** blocks:

- ≈ **394,470 blocks / year**
- **200 STONE / block** → ≈ **78.9 million STONE / year** tail mint

Against an early circulating base near **~201 million** (premine-centric figure used in policy discussion), that is on the order of **~39% annual issuance initially**, then **declines as circulating supply grows**.

> **Discord note (9 Jul 2026):** an intermediate estimate used ≈39,400 blocks/year (10× low for 80 s blocks) and therefore quoted ≈7.9M STONE/year ≈ **3.9%**. The **agreed ladder still uses 200 forever**; the corrected arithmetic at true block rate is above. If governance later targets ~4% of early supply, QSE base would be ~**20 STONE** — that is a parameter choice, not a change to the step shape.

For a DePIN security network, a permanent tail is intentional: long-run security should not depend only on fees on day one. A growing share of miner income is still expected from **transaction fees** and **commercial mesh services** (storage, bandwidth, compute) outside the consensus subsidy.

---

## QUASAR Security Emission (QSE)

**Name:** QUASAR Security Emission · **Short:** **QSE**

QSE is the **year-8+ tail** (base **200 STONE**/block). Design intent beyond a flat floor:

```
Target Security Score
        ↓
   Above target  →  reward stays flat (base QSE)
   Below target  →  reward automatically rises
```

**Candidate score inputs** (objectively measurable over time):

- number of miners  
- algorithm balance (multi-algo)  
- witness count  
- geographic diversity  
- LAN Echo participation  
- active mesh nodes  
- BSM anchors  

**Self-healing economy:** the protocol pays more when security weakens.

**Status:** base QSE (**200**) is in the issuance table. **Dynamic health multiplier** is staged:

1. **Now** — documented policy; pool can apply `BLOODSTONE_QSE_HEALTH_MULT` to *projections* only  
2. **Next** — off-chain score → ops/monitoring  
3. **Later** — consensus-verifiable inputs only (no gameable soft metrics in `GetBlockSubsidy`)

### What stays *out* of protocol subsidy

Do **not** carve fixed protocol % for storage, governance, monitoring, etc. unless cryptographically measurable on-chain.

Keep consensus simple:

1. **Block producer** earns the subsidy.  
2. **QUASAR bonuses** only for verifiable security contributions (multi-algo, witnesses, mesh availability, …).  
3. **Marketplace services** (storage / bandwidth / compute) earn from **commercial revenue**, not inflation.

**Positioning:** not merely “a chain with three mining algorithms” — a chain whose **monetary policy purchases security diversity**, not only raw hashpower.

---

## Projected PoW mint (pre-QSE years)

| Segment | Blocks | Rate | STONE minted (approx.) |
|---------|--------|------|-------------------------|
| Year 1 | 394,470 | 100 | **~39.4 M** |
| Years 2–3 | 788,940 | 1,000 | **~788.9 M** |
| Year 4 | 394,470 | 750 | **~295.9 M** |
| Year 5 | 394,470 | 500 | **~197.2 M** |
| Year 6 | 394,470 | 350 | **~138.1 M** |
| Year 7 | 394,470 | 250 | **~98.6 M** |
| **Years 1–7 total** | — | — | **~1.56 B** |
| Year 8+ each year | 394,470 | 200 | **~78.9 M / year** |

Plus genesis premine **~200 M**. Cumulative supply grows with QSE forever (by design).

---

## Supersedes prior layout

| Old (v1.0) | New (v2.0) |
|------------|------------|
| Halve every **1,054,080** blocks | Step every **~394,470** blocks (issuance year) |
| Jump to **1,000** at height **12,000** | Full **year 1 at 100**; **1,000** only in years **2–3** |
| Eras 0–4 binary halvings then inflation formula | Soft steps: 1000→750→500→350→250→**200 forever** |
| Era 64 subsidy → 0 | **No zero tail** — QSE continues |

Nodes must run Core with stepped `GetBlockSubsidy` **before** any leftover height-12000 fork logic would diverge. Pool formula (`pool_block_subsidy.py`) already follows v2.0 for projections; **confirmed payouts still use on-chain coinbase**.

---

## Pool and miner alignment

| Component | Role |
|-----------|------|
| `pool_block_subsidy.py` | Stepped schedule + QSE; reads live coinbase via RPC |
| `pool_db.distribute_block()` | Credits miners from actual coinbase + fees |
| Dashboard / API | `GET /mining/api/pool/subsidy-schedule` |

```bash
bloodstone-cli getblockstats <height> '["subsidy"]'
curl -sS "https://bloodstonewallet.mytunnel.org/mining/api/pool/subsidy-schedule" | python3 -m json.tool
```

---

## Reference implementation

- **Pool:** `/root/pool_block_subsidy.py`
- **Consensus:** `bloodstone-linux-build/src/validation.cpp` → `GetBlockSubsidy()`
- **Mainnet params:** `chainparams.cpp` → `nBlocksPerYear = 394470`, `qseBaseSubsidy = 200 * COIN`

| Env (pool) | Default | Purpose |
|------------|---------|---------|
| `BLOODSTONE_BLOCKS_PER_YEAR` | 394470 | Issuance year length |
| `BLOODSTONE_QSE_BASE_STONE` | 200 | Tail base |
| `BLOODSTONE_QSE_HEALTH_MULT` | 1.0 | Projection-only security boost (≥1) |
| `BLOODSTONE_QSE_HEALTH_MULT_MAX` | 2.0 | Cap on health boost |
| `BLOODSTONE_POST_ICO_HEIGHT` | 9910 | Pre-ICO 1 STONE rule boundary |

---

## Related

- Mining dashboard: `https://bloodstonewallet.mytunnel.org/mining/`
- Economic model / QUASAR materials under `/downloads/`
- EVM revenue router is separate (commercial rails), not PoW subsidy

---

*Policy locked from Discord discussion 9 Jul 2026 (stepped ladder + QSE naming + keep protocol rewards simple). Document v2.0 July 2026.*
