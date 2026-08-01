# STONE Flag Day Checklist — July 9 stepped schedule

**Doc version:** 1.1  
**Date:** 2026-08-01  
**Scope:** Bloodstone mainnet (**STONE only**). Not AZURE/LRGK.  
**Policy:** [Halving Schedule](https://bloodstone.rocks/downloads/Bloodstone-Halving-Schedule.md)  
**Release notes:** [Core 0.7.7](https://bloodstone.rocks/downloads/Bloodstone-Core-0.7.7-Flag-Day-Release-Notes.md)

## Locked numbers

| Item | Value |
|------|--------|
| First hard break | **STONE height 394,470** (Year 2 → 1,000 STONE) |
| **Upgrade-by height H** | **380,000** (recommended margin) |
| Target release | **Bloodstone Core 0.7.7** |
| Today (~18k) | Still **100**/block — history matches Year 1 |

---

## Checklist

### 1. Decide — **done**

- [x] Ship July 9 ladder as **consensus** (not pool-only).
- [x] Activation / upgrade-by: **H = 380,000** (break at **394,470**).
- [x] Release name: **0.7.7**.
- [x] Public one-liner ready (below).

### 2. Build code — **done (source)**

- [x] `GetBlockSubsidy` stepped path when `nBlocksPerYear > 0`.
- [x] Mainnet params: `nBlocksPerYear=394470`, `qseBaseSubsidy=200`, no mid-year jump at 12000.
- [x] Version **0.7.7** in `configure.ac`.
- [ ] **Compile** release binaries (Linux seed + any Windows pack).
- [ ] Publish tarball/deb/zip + **SHA256** to downloads.
- [ ] Bump downloads index / portal version badges.

### 3. Announce (after binaries live)

- [ ] Discord + operators: upgrade by **380,000**.
- [ ] Pool operators and public seeds.
- [ ] Explorer / wallet RPC hosts.
- [ ] Optional: listings / exchanges.

### 4. Pre-flight (before H)

- [ ] Seed nodes on **0.7.7**.
- [ ] Pool node on **0.7.7**.
- [ ] Tip still 100 STONE until Year 2.
- [ ] Monitor peers / orphan rate.

### 5. Flag day (through 394,470)

- [ ] Majority upgraded by **380,000**.
- [ ] Watch staff at **394,470** (first 1000-STONE blocks).
- [ ] Confirm single tip; subsidy **1,000**.

### 6. After

- [ ] Release notes: flag day complete.
- [ ] AZURE only if you change AZURE later (separate height).

---

## Operator paste

> **STONE flag day:** Upgrade to Bloodstone **0.7.7** by block **380,000** (hard break at **394,470**). Year 2 is **1,000 STONE**; old nodes stay at 100 and will fork.  
> Schedule: https://bloodstone.rocks/downloads/Bloodstone-Halving-Schedule.md  
> Checklist: https://bloodstone.rocks/downloads/Bloodstone-STONE-Flag-Day-Checklist.md  
> Notes: https://bloodstone.rocks/downloads/Bloodstone-Core-0.7.7-Flag-Day-Release-Notes.md

---

## Ladder (reminder)

```
Y1=100 → Y2–3=1000 → 750 → 500 → 350 → 250 → 200 forever (QSE)
```

Year length ≈ **394,470** blocks (~80 s design).

---

*v1.1 — source ready; binaries + announce still open*
