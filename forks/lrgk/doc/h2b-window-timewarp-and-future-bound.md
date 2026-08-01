# H2b — Window-level timewarp rule + joint future bound (pre-H1)

**Status:** Analysis only — **no H1 code**  
**Date:** 2026-07-20  
**Prior H2 accepted:** rolling DGW (not epochs), per-lane binding, MTP shared unchanged, cross-algo isolation (shared MTP only), DGW ±3× clamp is not a timewarp fix, vault covenant frozen, Phase H separate PR  
**This pass (reviewer corrections):** (1) prove adjacent-block rule fails against the DGW lever; (2) corrected rule that binds `nActualTimespan`; (3) joint `{TIMEWARP_MIN_WINDOW_SECONDS, MAX_FUTURE_BLOCK_TIME}` with false-positive analysis; (4) regtest scenarios for **window-level** rejection  

**Code baseline:** `src/pow.cpp` `GetNextWorkRequired`, `src/chain.h` MTP / `MAX_FUTURE_BLOCK_TIME`, `src/validation.cpp` `ContextualCheckBlockHeader`.

---

## 0. Scope confirmations (unchanged)

- v1.2 = delta; vault covenant **frozen**.  
- Phase H **separate PR**.  
- **Do not lock 270** as a BIP94 adjacent bound for H1.  
- **Do not write H1 code** until the pair and rule form below are locked by review.

---

## 1. What DGW actually divides by

From `GetNextWorkRequired` (`pow.cpp`), same-algo window `nPastBlocks = 24`:

```text
// walk 24 same-algo ancestors; pindexLast = newest, pindexFirst = oldest
nActualTimespan = pindexLast->GetBlockTime() - pindexFirst->GetBlockTime();
nTargetTimespan = 24 * GetTargetSpacing(algo, nextHeight);  // multi-algo mainnet: 24*270 = 6480
// clamp nActualTimespan to [T/3, 3T] = [2160, 19440]
bnResult *= nActualTimespan;
bnResult /= nTargetTimespan;
```

| Quantity | Value (multi-algo mainnet) | Role |
|----------|----------------------------|------|
| Per-algo spacing `S` | 270 s | Lane slot |
| Window size `N` | 24 | Same-algo headers |
| Target timespan `T` | 6480 s | What formula *expects* |
| Clamp floor | 2160 s (`T/3`) | Max ease **3×** per step |
| Clamp ceiling | 19440 s (`3T`) | Max harden **3×** per step |

**Difficulty eases** when the **post-clamp** timespan is below `T`.  
The **lever** is the **window endpoint spread** `newest − oldest` over **24 same-algo** headers — **not** the gap between two adjacent same-algo headers alone.

Adjacent gaps only matter insofar as they *sum* into that endpoint delta. A rule that only floors one step cannot force the sum.

---

## 2. Adjacent-block rule: attack/defense trace (rule fails)

### 2.1 Proposed (H2) adjacent rule — insufficient

```text
For new same-algo block B with previous same-algo ancestor P:
  B.nTime >= P.nTime - BOUND   // e.g. BOUND = 270, or even 7200
```

This only limits how far **backward** one step may jump relative to the previous same-algo stamp.  
The compression attack moves **forward** as little as MTP allows — always `≥ P.nTime - BOUND`.

### 2.2 Concrete worked attack (satisfies adjacent rule; still drives difficulty down)

**Assumptions (consensus-legal under current rules):**

- Attacker dominates **one** lane (e.g. SHA256d) — Verge-class.  
- Other lanes idle (worst case for MTP: every tip is attacker’s SHA256d block).  
- MTP: each new tip must have `nTime > prev.GetMedianTimePast()` (`validation.cpp`).  
- Adjacent rule active with `BOUND = 270` (or `BOUND = 7200` — same outcome).  
- `S = 270`, `T = 6480`, clamp floor `T/3 = 2160`.  
- Attacker hashrate high enough that PoW is not the bottleneck once difficulty eases.

**Phase 1 — form a 24-block same-algo window with minimal endpoint span**

| Block | `nTime` | Δ vs prev same-algo | Adjacent check (`≥ P − BOUND`) | MTP (`> median of last 11`) |
|-------|---------|---------------------|--------------------------------|-----------------------------|
| A₁ | `t₀` | — | n/a | ✓ (genesis/setup) |
| A₂ | `t₀ + 1` | +1 | `+1 ≥ −BOUND` ✓ | ✓ (strictly increasing chain) |
| A₃ | `t₀ + 2` | +1 | ✓ | ✓ |
| … | … | +1 each | ✓ | ✓ |
| A₂₄ | `t₀ + 23` | +1 | ✓ | ✓ |

**Window endpoints when tip is A₂₄:**

```text
span = A₂₄.nTime − A₁.nTime = 23 s
```

**Next SHA256d block A₂₅’s required bits** (`GetNextWorkRequired` from tip A₂₄):

```text
nActualTimespan_raw = 23
nActualTimespan_clamped = max(23, 2160) = 2160
ease factor = 2160 / 6480 = 1/3  →  difficulty up to 3× easier
```

**Adjacent rule never fired.** Every hop was `+1 s`, far from any backdate floor.

**Phase 2 — successive rolling windows (ratchet)**

DGW is **rolling**: every new same-algo tip recomputes from the trailing 24.

| Window (newest…oldest) | Endpoint times | Raw span | After clamp | Difficulty vs prior step |
|------------------------|----------------|----------|-------------|---------------------------|
| A₁…A₂₄ | `t₀` … `t₀+23` | 23 | 2160 | ≤ **3× easier** |
| A₂…A₂₅ | `t₀+1` … `t₀+24` | 23 | 2160 | ≤ **another 3× easier** |
| A₃…A₂₆ | `t₀+2` … `t₀+25` | 23 | 2160 | ≤ **another 3× easier** |
| … | keep +1 s/step | 23 | 2160 | until **powLimit** |

**Numeric illustration (order of magnitude, ignoring compact-bits granularity):**

- After ~4 full ease steps at clamp floor: difficulty multiplies by up to `(1/3)⁴ ≈ 1/81`.  
- Wall-clock endpoint time consumed for those ~4×24 same-algo blocks if stamped +1 s: on the order of **~100 s** of *timestamp* progression, not ~4×2160 s of real window honesty.  
- Once near powLimit, block production is wall-clock-bound only by hashrate at minimum difficulty — **vault block-denominated delays compress** in real time.

**Phase 3 — still works under interleaving**

If neo/yespower produce tips, MTP is mixed. Attacker still only needs each SHA256d stamp `> MTP(prev tip)`. They can still pack the **24 SHA256d** `nTime`s tightly (small positive steps on the **same-algo subsequence**). Adjacent same-algo rule still allows +1 s steps. Window endpoint spread for SHA256d can still approach ~23 s.

### 2.3 Defense status of adjacent-only rule

| Criterion | Result |
|-----------|--------|
| Prevents backdating vs previous same-algo stamp | Yes (by construction) |
| Constrains `nActualTimespan = newest − oldest` | **No** |
| Stops successive rolling 3× ease under +1 s cadence | **No** |
| **Verdict** | **Insufficient — do not ship as primary H1 rule** |

**Why “adjacent floor implies window floor” is false:**  
A lower bound of the form `B ≥ P − BOUND` allows `B = P + 1`. Summing 23 such steps yields endpoint span ≈ 23, not `24×S − 24×BOUND`. The inequality only *restrains rewind*; compression is a *forward packing* attack.

---

## 3. Corrected rule: bind the quantity DGW divides by

### 3.1 Primary consensus rule (recommended)

When a new block `B` of algo `A` is validated, and at least **24** same-algo blocks exist **including `B` as newest**:

```text
let newest = B
let oldest = 24th same-algo ancestor counting B as #1
             (same walk GetNextWorkRequired uses: GetLastAncestorWithAlgo)
let span   = newest.nTime - oldest.nTime
let T      = 24 * GetTargetSpacing(A, height)   // 6480 on multi-algo mainnet

// Reject artificial compression of the DGW window:
require span >= TIMEWARP_MIN_WINDOW_SECONDS

// Optional symmetric hygiene (slow / “inflate then crash” games):
require span <= TIMEWARP_MAX_WINDOW_SECONDS
```

**Enforcement semantics (analysis, not code):**

| Place | Role |
|-------|------|
| **`ContextualCheckBlockHeader`** (with or beside `fCheckBits`) | Consensus gate: compressed window → **reject block**, chain cannot advance |
| **Mirror awareness in `GetNextWorkRequired` path** | Defense in depth; primary is reject-at-header, not “accept + clamp only” |

**Do not** rely only on the existing formula clamp: clamp **pretends** the timespan was 2160 when it was 23 — difficulty still eases 3×, and the bad headers **stay on chain**. Reject so the chain **cannot** advance under a compressed window.

### 3.2 Parameterization (multiples of `24 × S`)

| Symbol | Formula | Multi-algo (S=270) | Role |
|--------|---------|---------------------|------|
| **TIMEWARP_MIN_WINDOW_SECONDS** | **`T/3` = `24×S/3`** | **2160** | Align with **existing DGW clamp floor** — you may not *accept* a window tighter than the formula already pretends for max ease |
| **TIMEWARP_MAX_WINDOW_SECONDS** | **`3×T` = `24×S×3`** | **19440** | Align with clamp ceiling (optional H1 scope) |

**Stronger alternative:** `MIN = T/2 = 3240` (max ~2× average gap compression). If chosen, **raise DGW clamp floor to match** so reject floor and formula cannot diverge.

**Default recommendation to lock after review:**

```text
TIMEWARP_MIN_WINDOW_SECONDS = 2160   // required
TIMEWARP_MAX_WINDOW_SECONDS = 19440  // optional first H1; can ship MIN-only
```

### 3.3 Attack/defense with window floor MIN = 2160

**Attack (same as §2):** A₁…A₂₄ with +1 s steps, span = 23.  
**Defense:** `23 < 2160` → **REJECT** at consensus. No block, no retarget step, no ratchet.

**Attack (adapted to min legal window):** set times so span = 2160 exactly over 24 same-algo blocks (average gap ≈ 93.9 s between same-algo stamps).  
**Defense:** block **accepted**; DGW uses span 2160 → ease **at most 3× once per full window**. Attacker **cannot** produce 24 accepted same-algo blocks in 23 s of endpoint time; minimum endpoint span for a max-ease step is **2160 s (~36 min)**.

**Successive windows under the floor:**

| Window | Min legal span | Max ease per step | Wall-time cost of endpoint honesty |
|--------|----------------|-------------------|--------------------------------------|
| W1 | ≥ 2160 s | ≤ 3× | ≥ 2160 s of same-algo endpoint delta |
| W2 | ≥ 2160 s | ≤ 3× | another ≥ 2160 s (rolling; honest oldest advances) |
| Wk | ≥ 2160 s | ≤ 3× | ease rate-limited by **real** window time |

**Vault impact (order of magnitude):**

- Honest mean ~90 s any-block → 960 blocks ≈ 24 h.  
- Single-lane attacker at minimum legal window: 24 same-algo blocks need ≥ 2160 s endpoint span; if they also dominate tips, block rate ≤ ~24/2160 ≈ 1/90 s — same order as design mean, not 1 Hz.  
- They can still ease 3× per legal window and then speed up as difficulty falls — but each ease step requires **real** minimum window time, not fictional +1 s stamps.

**Recommendation:** set **both** reject floor and DGW clamp floor to the **same** `TIMEWARP_MIN_WINDOW_SECONDS` so “accepted window” and “computed timespan” cannot diverge.

### 3.4 Adjacent-block rule status after correction

| Rule | Keep as primary? | Role |
|------|------------------|------|
| Adjacent `B.nTime >= P.nTime − BOUND` | **No** | Insufficient against window compression (§2) |
| Window `span >= MIN` | **Yes** | Binds `nActualTimespan` directly |
| Adjacent as *optional extra* | Only if paired with reduced future window | Minor; not a substitute |

### 3.5 Interaction with shared MTP (unchanged architecture)

| Rule | Scope | What it constrains |
|------|-------|--------------------|
| MTP | Global last 11 tips (any algo) | `B.nTime > MTP(prev)` |
| Window MIN | Per-algo 24-endpoint spread | `nActualTimespan` for DGW |
| Future bound | Wall clock + `MAX_FUTURE_BLOCK_TIME` | How far ahead `nTime` may lead |

MTP forbids going backward vs the tip median; it does **not** force same-algo endpoint span ≥ 2160. Window rule is **additional** and **per-algo**. Other lanes cannot inject timestamps into `nActualTimespan`; they only move MTP.

---

## 4. Joint recommendation: `{window min, MAX_FUTURE_BLOCK_TIME}`

### 4.1 Why the pair is coupled

Inherited **`MAX_FUTURE_BLOCK_TIME = 7200`** (`chain.h`) allows a header up to **+2 hours** ahead of adjusted network time.

| Interaction | Effect |
|-------------|--------|
| Future stamp then honest “now” | Previous same-algo at `now+F` makes honest next look up to **F seconds earlier** than that prev stamp — adjacent BIP94-style bounds need `BOUND ≥ F` to avoid FP, which guts the bound |
| Inflate `newest` | Stamp window endpoint at `now+F` → temporarily **large** `nActualTimespan` → hard difficulty, then later games when the inflated block ages out of the rolling window |
| BIP94 / testnet4 direction | Bitcoin tightened effective timewarp thresholds partly because a **loose future window** and a timewarp bound **interact** |

So: (a) what window floor survives honest skew given current F; (b) should Bloodstone also reduce F at genesis. Answer both together.

### 4.2 Question (a) — What bound survives honest clock skew?

**Load-bearing bound is the window MIN, not adjacent 270.**

| Source of skew | Typical scale | Interaction with window MIN |
|----------------|---------------|------------------------------|
| NTP / phone clock | seconds–low minutes | Negligible vs 2160 |
| Mining template `curtime` | seconds | Negligible |
| Pathological legal future stamp | up to **+F** | Dominates FP for *adjacent* rules; window MIN cares about **24-span**, not one-step backdate |
| Same-algo sparsity (other algos mine) | large **positive** gaps | Window MIN is a floor; large span OK (harder difficulty) |
| Honest Poisson bursts | short gaps possible | Expected same-algo span ~`T` under balanced hashrate; rare short tails already map to max ease via clamp |

**Window MIN = 2160 (`T/3`):**  
False positive only if an **honest** 24-block same-algo window has endpoint spread **below 2160 s**. That is already the regime where DGW would clamp to max ease today. Aligning reject with clamp means: you cannot publish a window the formula already treats as “impossibly short.” Expected honest span ≈ 6480 s ≫ 2160.

**Window MIN = 3240 (`T/2`):**  
Stricter on hashrate variance / bursts → more FP risk. Only if vault security wants less than 3× cadence compression.

**Adjacent BOUND = 270:**  
Does **not** survive +F future parents without FP when F ≫ 270 (current F=7200 → massive FP class). **Do not lock 270.**

### 4.3 Question (b) — Tighten `MAX_FUTURE_BLOCK_TIME` at genesis?

**Yes — recommended at genesis** (Phase H, jointly with window rule).

| Option | Value | Rationale |
|--------|-------|-----------|
| Current (reject for new genesis policy) | 7200 | Too loose vs ~90 s mean cadence (~80 mean any-blocks of “future”) |
| **Recommended** | **1800** (30 min) | ≫ normal skew; ≈ 20 mean any-blocks; operable if clock wrong briefly; matches “tighten with timewarp hygiene” direction |
| Aggressive | **900** (15 min) | Tighter; more ops risk on bad clocks / slow templates |
| Ultra (not recommended) | 270–540 | Collides with template latency and mild skew |

**Do not keep 7200** if shipping a serious window-timewarp regime — it re-opens newest-inflation games and makes any residual adjacent-style check unusable without huge BOUND.

### 4.4 Pair to lock (proposal)

```text
// Primary anti-DGW-timewarp control (binds nActualTimespan):
TIMEWARP_MIN_WINDOW_SECONDS   = 2160   // 24 * 270 / 3
TIMEWARP_MAX_WINDOW_SECONDS   = 19440  // 24 * 270 * 3  — optional first ship

// Joint future allowance (genesis tighten):
MAX_FUTURE_BLOCK_TIME         = 1800   // was 7200

// Explicitly NOT the primary control:
// adjacent BIP94-style BOUND (270 / 810 / 7200) — insufficient alone; do not lock 270
```

**Naming:** prefer `TIMEWARP_MIN_WINDOW_SECONDS` over `TIMEWARP_BOUND_SECONDS` so H1 does not reintroduce the insufficient adjacent-only BIP94 copy.

**One-line lock phrase:**  
**Load-bearing pair = {window min 2160, future 1800}.**

### 4.5 False-positive summary

| Scenario | MIN=2160 + FUT=1800 | Notes |
|----------|---------------------|--------|
| Honest ~270 s same-algo cadence | OK | span ≈ 6480 |
| Honest burst (short gaps) | OK if span ≥ 2160 | Same as today’s max-ease regime |
| Honest span 1500 s | **REJECT** | Today: ACCEPT + ease 3×; new rule forces stamp honesty / wait |
| Prev same-algo at +1800 future, next honest now | Window may still OK | Adjacent-only would need BOUND ≥ 1800; window rule is 24-span |
| Attacker +1 s × 24 (span 23) | **REJECT** | Main defense |
| Attacker span exactly 2160 | ACCEPT + max ease once | Must spend ≥ 2160 s of endpoint time |
| Newest at now+1801 | **REJECT** time-too-new | Future tighten |
| Clock skew 5–10 min | OK under FUT=1800 | |
| Clock skew > 30 min ahead | May fail time-too-new | Ops: fix NTP (acceptable trade) |

---

## 5. Regtest scenarios (window-level — for H3; not adjacent-only)

These demonstrate **window endpoint** rejection, not merely “adjacent backdate by BOUND.”

1. **Compressed window reject (per algo ×3):** Build 24 same-algo headers with endpoint span `T/3 − 1` (= **2159**) while each header passes MTP and bits under *old* rules; with H1, **expect REJECT** when the 24th (or the block that completes a sub-MIN window) is checked. Today: ACCEPT + ease.  
2. **Min legal window accept:** span **`== 2160`**, honest MTP; **ACCEPT**; next bits match DGW with timespan 2160 (max ease once).  
3. **Target window:** span **`≈ 6480`**; **ACCEPT**; mild/no ease.  
4. **Multi-step ease rate limit:** Attempt two successive rolling windows each with span 23 s; **first compressed tip REJECT**; cannot ratchet difficulty without waiting / honest stamps.  
5. **Cross-algo isolation:** Compress SHA256d window only; neo/yespower honest; SHA256d compressed tip **REJECT**; other lanes’ retargets unaffected when they produce honest spans.  
6. **Future-stamp with FUT=1800:** newest at `now+1801` → **REJECT** time-too-new; boundary at `now+1800` per equality rules (`>` vs `>=` as implemented).  
7. **Regression:** Random honest multi-algo mining with normal clocks → no unexpected rejects; retarget continues.  
8. **(Optional MAX)** span `> 19440` → REJECT if MAX shipped.  
9. **Adjacent red herring:** Blocks with `B.nTime = P.nTime + 1` but window span still ≥ 2160 → **ACCEPT** (proves H1 is not adjacent-bound).  
10. **Adjacent red herring fail case:** Blocks with `B.nTime = P.nTime + 1` filling span 23 → **REJECT on window**, not on adjacent (proves the defense is window-level).

---

## 6. Flags vs prior H2 / §15.1 (updated)

| Item | Prior H2 | This H2b |
|------|----------|----------|
| Adjacent BIP94-style rule | Proposed primary | **Insufficient** — attack trace §2 |
| Quantity to constrain | Implied period-end / adjacent | **`nActualTimespan = newest−oldest` over 24** |
| Bound 270 adjacent | Suggested default | **Do not lock**; wrong tool for DGW lever |
| DGW clamp ±3× | Not a full fix | Remains formula rate limit; **reject floor** makes clamp’s min **real** |
| Future 7200 | Flagged | **Tighten to 1800** jointly |
| Rolling / per-lane / MTP | Accepted | Unchanged |

---

## 7. What to lock before H1 (your call)

| Parameter | Proposal | Alt |
|-----------|----------|-----|
| Window min (**required**) | **2160** (`T/3`) | 3240 (`T/2`) stricter |
| Window max (optional) | **19440** (`3T`) | omit in first H1 |
| `MAX_FUTURE_BLOCK_TIME` | **1800** | 900 aggressive / **7200 rejected** |
| Adjacent-only rule | **Do not implement as primary** | optional later, not a substitute |
| DGW clamp floor | **Keep equal to window min** | — |

Once locked → H1/H3 only (separate PR, full rebuild if deployment bits change, vault covenant untouched). H0/H4/H5 as previously sequenced.

---

*H2b complete · no H1 code · primary rule = window MIN on nActualTimespan · joint pair = {2160, 1800} · adjacent 270 not locked*
