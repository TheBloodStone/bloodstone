# Bloodstone Core 0.7.7 — Flag-day prep (stepped issuance + QSE)

**Version:** 0.7.7  
**Date:** 2026-08-01  
**Network:** Bloodstone mainnet (STONE)  
**Policy:** [Halving / QSE schedule](https://bloodstone.rocks/downloads/Bloodstone-Halving-Schedule.md) (Discord 9 Jul 2026)  
**Ops:** [Flag day checklist](https://bloodstone.rocks/downloads/Bloodstone-STONE-Flag-Day-Checklist.md)

## Summary

Core **0.7.7** implements the July 9 **stepped subsidy ladder** in `GetBlockSubsidy` when `nBlocksPerYear > 0` (mainnet: **394,470**). This is the consensus code path for:

| Year | Reward / block |
|------|----------------|
| 1 | **100** STONE |
| 2–3 | **1,000** STONE |
| 4 | **750** |
| 5 | **500** |
| 6 | **350** |
| 7 | **250** |
| 8+ | **200** forever (QSE) |

Pre-POST_ICO heights still pay **1 STONE** (unchanged).

## Compatibility with history

Heights mined so far (after POST_ICO) are still **Year 1 @ 100 STONE** — same as 0.7.6 coinbase.  
**No reorg of past subsidy** when upgrading at today’s height (~18k).

## Flag day (required)

| Item | Value |
|------|--------|
| **First hard break vs 0.7.6** | STONE height **394,470** (Year 2 → **1,000**) |
| **Recommended upgrade-by height H** | **380,000** (safety margin) |
| **Who** | Every STONE full node (miners, pools, seeds, explorers, exchanges) |
| **AZURE / LRGK** | Not covered — separate chains |

**All nodes must run 0.7.7 (or later with this schedule) before height 394,470**, or the network splits.

## Operator paste

> **STONE flag day:** Upgrade to Bloodstone **0.7.7** by block **380,000** (hard break **394,470**). Year 2 reward is **1,000 STONE**; old nodes stay at 100 and will fork. Schedule: https://bloodstone.rocks/downloads/Bloodstone-Halving-Schedule.md · Checklist: https://bloodstone.rocks/downloads/Bloodstone-STONE-Flag-Day-Checklist.md

## Build / deploy status

| Item | Status |
|------|--------|
| `GetBlockSubsidy` stepped path | **In source** (`bloodstone-linux-build`, mirrored) |
| Version bump | **0.7.6 → 0.7.7** (`configure.ac`) |
| Unit tests | `validation_tests` stepped cases (rebuild to run) |
| Published production binaries | **Next** — compile + ship to downloads |
| Network announcement | **Next** — after binaries published |

## Next steps

1. Compile and publish 0.7.7 binaries + SHA256.  
2. Announce Discord / pools with height **380,000**.  
3. Upgrade seeds + pool node first; then public miners.  
4. Watch peers near H; confirm single tip through 394,470.

---

*Bloodstone Core 0.7.7 · stepped issuance + QSE · flag-day prep*
