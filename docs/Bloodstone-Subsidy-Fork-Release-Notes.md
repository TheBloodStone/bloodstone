# Bloodstone Core — Subsidy Schedule Fork Release Notes

**Draft · July 2026**  
**Target release:** Bloodstone Core **0.7.0** (consensus + pool alignment)  
**Network:** Bloodstone mainnet (STONE)  
**Genesis:** June 2026 independent chain relaunch  

---

## Summary

This release documents and hardens Bloodstone’s proof-of-work issuance schedule: **five halving eras** followed by a **long-run inflation phase**. It aligns Bloodstone Core consensus with the live relaunch parameters (**100 STONE** era-0 reward) and fixes a monetary discontinuity at **era 5** where legacy SpaceXpanse inflation math would otherwise jump the block subsidy from **~6.25 STONE** to **~52.95 STONE** despite Bloodstone’s lower initial reward.

The unified mining **pool already adapts** in software (July 2026): payouts and dashboard estimates read the on-chain subsidy via `getblockstats`. This core release makes the **chain** match the intended Bloodstone economics for later years.

---

## Why this fork matters

| Issue | Without fix | With 0.7.0 |
|--------|-------------|------------|
| Era 0–4 halvings | 100 → 50 → 25 → 12.5 → 6.25 STONE | Same (unchanged) |
| Era 5 subsidy (block 5,270,400+) | **~52.95 STONE** (800-ROD inflation curve) | **~6.62 STONE** (scaled to 100 STONE base) |
| Pool payout vs chain | Pool reads chain; estimates could diverge at era 5 | Chain and pool projections align |
| `POST_ICO` bootstrap | Legacy 55,560-block × 1 STONE phase (ROD) | Full schedule from block **1** on relaunch chain |

**Recommendation:** Deploy **0.7.0** to all full nodes and pool infrastructure **before block 5,270,400** (halving era 5). Earlier deployment is safe and documents the relaunch parameters in official source.

---

## Consensus changes (hard fork at era 5 inflation)

These changes are in `bloodstone-linux-build` and require a **network-wide node upgrade** before era 5 takes effect. Eras 0–4 remain compatible with current mainnet behaviour.

### 1. Initial PoW subsidy — `100 STONE`

```cpp
// chainparams.cpp (mainnet)
consensus.initialSubsidy = 100 * COIN;
```

Matches live relaunch coinbase outputs (verified at heights 1–8,000+).

### 2. Post-ICO fork height — block 1

```cpp
// consensus/params.h — MainNetConsensus
case Fork::POST_ICO:
    return height >= 1;
```

Bloodstone relaunch does not use the legacy 55,560-block × 1 STONE pre-ICO bootstrap.

### 3. Scaled inflation after era 4

```cpp
// validation.cpp — GetBlockSubsidy(), halvings > 4
if (consensusParams.initialSubsidy < 800 * COIN) {
    nSubsidy = nSubsidy * initialSubsidy / (800 * COIN);
}
```

Legacy SpaceXpanse formula still computes the inflation **tranche**, but issuance is scaled when `initialSubsidy` is below 800 ROD. For Bloodstone (`100 STONE`), scale factor = **0.125**.

**Halving interval** (unchanged): **1,054,080 blocks** per era.

---

## Subsidy schedule reference (Bloodstone 0.7.0)

Approximate calendar dates assume **~80 s** average block time (triple-algo mainnet, July 2026). Adjust if block times change.

| Era | Start block | Subsidy / block | Phase | Approx. year |
|-----|-------------|-----------------|-------|--------------|
| 0 | 1 | 100 STONE | Halving | 2026 |
| 1 | 1,054,080 | 50 STONE | Halving | ~2029 |
| 2 | 2,108,160 | 25 STONE | Halving | ~2031 |
| 3 | 3,162,240 | 12.5 STONE | Halving | ~2034 |
| 4 | 4,216,320 | 6.25 STONE | Halving | ~2037 |
| 5 | 5,270,400 | **~6.62 STONE** | Inflation (scaled) | ~2039 |
| 10 | 10,540,800 | **~7.66 STONE** | Inflation (scaled) | ~2053 |

Eras 5–63 continue with ~**2.956%** growth per era (factor **1.02956**), scaled for the 100 STONE base. Era **64+**: subsidy **0** (PoW issuance ends).

**Next halving (era 1):** block **1,054,080**.

---

## Pool changes (already deployed — no node upgrade required)

| Component | Change |
|-----------|--------|
| `pool_block_subsidy.py` | Mirrors `GetBlockSubsidy()`; reads live subsidy via RPC/`getblockstats` |
| `pool_db.distribute_block()` | Uses on-chain subsidy at block height when crediting miners |
| Dashboard | `subsidy_schedule` + halving era on next-block estimates |
| API | `GET /mining/api/pool/subsidy-schedule` |
| Config | `service-overrides.conf`: `BLOODSTONE_INITIAL_SUBSIDY_STONE=100`, `BLOODSTONE_INFLATION_SCALE=0.125` |

Pool payouts **today** follow whatever the chain pays. The inflation-scale env var affects **projections only** until 0.7.0 is active on-chain at era 5.

---

## Upgrade instructions

### Full node operators

1. Build or install **Bloodstone Core 0.7.0** (`bloodstoned`, `bloodstone-cli`, `bloodstone-qt`).
2. Restart the daemon on pool VPS, home nodes, and explorers.
3. Confirm subsidy at tip:
   ```bash
   bloodstone-cli getblockstats $(bloodstone-cli getblockcount) '["subsidy"]'
   ```
   Expect `"subsidy": 10000000000` (100 STONE in satoshis) during era 0.
4. Confirm pool API:
   ```bash
   curl -sS "https://bloodstonewallet.mytunnel.org/mining/api/pool/subsidy-schedule" | python3 -m json.tool
   ```

### Miners

- **No stratum or wallet changes** required for eras 0–4.
- Dashboard “next block” STONE estimates will track halvings automatically.
- After era 1, expect per-block gross pool revenue to drop ~50% unless price/hashrate compensates.

### Pool operator

- Remove or update `BLOODSTONE_BLOCK_REWARD_STONE` if set manually — it is now a **fallback only**.
- After 0.7.0 is network-wide at era 5, `projected_reward_stone` and chain subsidy should match.

---

## Compatibility and risks

- **Eras 0–4:** Compatible with Bloodstone relaunch mainnet (100 STONE reward). Upgrade is documentation + forward-fix for era 5.
- **Era 5+:** **Hard fork** if any miners still run pre-0.7.0 inflation (unscaled). A chain split at block 5,270,400 would produce different coinbase amounts; pools credit blocks from the chain they validate.
- **Do not** mix old inflation nodes with 0.7.0 nodes past era 4 — coordinate upgrade via pool announcements and downloads page.
- **Reorgs:** Recent anchors and pool settlements should wait for standard confirmations across halving boundaries.

---

## Files changed (reference)

| Area | Path |
|------|------|
| Subsidy logic | `bloodstone-linux-build/src/validation.cpp` |
| Mainnet params | `bloodstone-linux-build/src/chainparams.cpp` |
| Fork heights | `bloodstone-linux-build/src/consensus/params.h` |
| Pool resolver | `/root/pool_block_subsidy.py` |
| Pool payouts | `/root/pool_db.py` |
| Pool API | `bloodstone-miner-web/app.py` |
| Economic white paper | `bloodstone-docs/generate-economic-whitepaper.js` (v1.1) |

---

## Checklist before era 5 (block 5,270,400)

- [ ] Bloodstone Core **0.7.0** binaries on downloads page  
- [ ] Pool VPS and stratum services on 0.7.0  
- [ ] Public announcement (Discord / portal / mining dashboard banner)  
- [ ] Verify `subsidy_stone_chain` ≈ `subsidy_stone_projected` at era 4→5 boundary on testnet or regtest  
- [ ] Update `BLOODSTONE_BLOCK_REWARD_STONE` env only if RPC unavailable (emergency fallback)  

---

## Related documentation

- [Bloodstone Economic Model White Paper](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Economic-Model-White-Paper.docx) — §1.2 Halving schedule  
- [Mining dashboard](https://bloodstonewallet.mytunnel.org/mining/)  
- Live schedule API: `https://bloodstonewallet.mytunnel.org/mining/api/pool/subsidy-schedule`  

---

## Draft status

This document is a **draft** for operator review. Final release should include:

- Exact build version string and git tag (e.g. `v0.7.0`)  
- SHA256 checksums for `bloodstoned` / `bloodstone-qt` builds  
- Confirmed testnet regression height for era-4→5 transition  
- Official activation announcement date  

*Questions: pool operator via mining dashboard or Bloodstone portal support.*