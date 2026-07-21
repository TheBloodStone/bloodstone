# LRGK block reward & halving schedule

**Document version:** v1.0  
**Chain:** LRGK mainnet (independent of Bloodstone)  
**Updated:** 2026-07-19

## Design targets

| Parameter | Value |
|-----------|--------|
| Block reward (era 0) | **500 LRGK** per block |
| Target average block time | **3 minutes** (180 seconds) between network blocks |
| PoW algorithms | neoscrypt, yespower, sha256d (multi-algo) |
| Per-algo target spacing | **540 s** (so three algos ≈ one block every 180 s) |
| Halving interval | **1,054,080 blocks** |
| Mid-chain subsidy jump | **None** (Bloodstone’s 1000@12000 disabled) |

## Bug that was fixed (APK / host 1.0.30)

Older LRGK binaries still carried SpaceXpanse/Bloodstone **POST_ICO** gating:

- Until height **9910**, `GetBlockSubsidy()` returned **1 LRGK** (not 500).
- Block times used Bloodstone spacing.

**Fix:** POST_ICO from **height 0**, full **500 LRGK** subsidy, per-algo spacing **540 s**.

**Operator note:** Early blocks mined under the 1-LRGK rule are not compatible. The public seed was reset to a fresh tip under the 500-LRGK rules. Upgrade phone APK to **1.0.30+** and reset/resync the on-device chain.

## Halving schedule (eras 0–4)

```text
reward(height) = 500 >> floor(height / 1_054_080)
```

| Era | Heights (start) | Reward / block | LRGK issued in era |
|-----|-----------------|----------------|--------------------|
| 0 | 0 | **500** | 527,040,000 |
| 1 | 1,054,080 | **250** | 263,520,000 |
| 2 | 2,108,160 | **125** | 131,760,000 |
| 3 | 3,162,240 | **62.5** | 65,880,000 |
| 4 | 4,216,320 | **31.25** | 32,940,000 |

**Cumulative after era 4:** 1,021,140,000 LRGK (plus genesis/premine if any).

### Calendar estimate at 3-minute average blocks

| Interval | ≈ Duration |
|----------|------------|
| One year | ~175,200 blocks |
| One halving era (1,054,080 blocks) | **≈ 6.02 years** |
| Eras 0–4 combined | **≈ 30.1 years** |

## After era 4 (height ≥ 5,270,400)

Inflation-era formula inherited from SpaceXpanse/Bloodstone, **scaled to the 500 LRGK base** (not legacy 800 ROD). Per-block subsidy is the era inflation amount ÷ 1,054,080 (rounded to 0.01 LRGK).

## Verify

```bash
# coinbasevalue should be 50000000000 (500 LRGK in satoshis)
lrgk-cli creatework "<L…address>" sha256d
```

## Links

- APK 1.0.30: https://bloodstonewallet.mytunnel.org/downloads/lrgk-full-node-android-1.0.30.apk  
- Latest APK: https://bloodstonewallet.mytunnel.org/downloads/lrgk-full-node-android-latest.apk  
- This doc: https://bloodstonewallet.mytunnel.org/downloads/LRGK-Halving-Schedule.md  
- Latest alias: https://bloodstonewallet.mytunnel.org/downloads/LRGK-Halving-Schedule-latest.md  
