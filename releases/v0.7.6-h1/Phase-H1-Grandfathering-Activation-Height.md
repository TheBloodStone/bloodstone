# H1 grandfathering — activation height *H* **FROZEN**

**Status:** **FROZEN**  
**Frozen:** 2026-07-20  
**Tip at freeze:** **13869**  
**Activation height *H*:** **17000**  
**Package:** Bloodstone Core **v0.7.6** (height-gated H1)

---

## Scan fact (both rules)

| Check | Result |
|--------|--------|
| Window-min if applied from genesis | **741** early-chain hits → gate **mandatory** |
| Future A / B (1800s proxies) | **0 / 0** |
| Full report | `h1-nonretroactivity-scan-latest.md` |

## Frozen design

| Height | Window-min reject | Future stamp bound |
|--------|-------------------|--------------------|
| `nHeight < 17000` | off (grandfathered) | **7200** s |
| `nHeight >= 17000` | **on** (`timewarp-dgw-window`) | **1800** s |

```text
tip_at_freeze = 13869
buffer ≈ 3.3 days × ~960 blocks/day
H = 17000
```

Regtest / testnet / signet: `nH1TimewarpActivationHeight = 0` (always on).

## Operator / Cexius

- Upgrade to **v0.7.6** (or later) **before** height **17000**.
- Not a relaunch — balances and deposit addresses unchanged.
- Soft-fork framing: new rules from *H* forward; history below *H* unchanged.
- Vault bit-5 is a **separate later** flag-day.

## Qt / end-user wallets (setup summary)

| Setup | Upgrade? |
|-------|----------|
| Exchange / pool / self-hosted **full node** | **Yes** before 17000 |
| **Core Qt** that embeds or runs local `bloodstoned` | **Yes** (node component must match) |
| **Web wallet** only | **No** app upgrade; operators upgrade servers |
| Keys / watch-only via remote upgraded RPC | No forced migration |

Full detail: [Phase-H1-Who-Must-Upgrade.md](Phase-H1-Who-Must-Upgrade.md)

## Downloads

- https://bloodstonewallet.mytunnel.org/downloads/bloodstone-node-0.7.6-h1-timewarp-linux-x86_64.tar.gz  
- https://bloodstonewallet.mytunnel.org/downloads/bloodstone-node-h1-timewarp-linux-x86_64-latest.tar.gz  
