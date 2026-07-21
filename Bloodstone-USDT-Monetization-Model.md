# Bloodstone resource monetization — USDT first

*July 2026 · Commercial model (Megadrive / STONE team discussion)*

---

## Idea (plain language)

1. **Customers** (public + corporate) pay for storage, bandwidth, compute, and monthly upkeep in **USDT** on **EVM** (ERC-20 first — most accessible).
2. **Core team** gets an **immediate USDT split** by contracted role.
3. **What remains** of that USDT **buys STONE** at a published rate.
4. That **STONE** is distributed to **network resource providers**.
5. Providers who **hold more STONE** (attested on-chain) unlock modest **tier bonuses** (+5%, +X%) — fair, not a huge jump.
6. Early on the STONE/USDT rate is **fixed and favourable to adopters**; later it **floats** from an exchange price API.

Native **STONE treasuries** on `/data/` remain for mesh-native users. USDT is the commercial front door.

---

## Flow

```
Customer USDT (EVM treasury)
        │
        ├─► Team roles (ops / core / bd / stone / …)  — % of gross USDT
        │
        └─► Remainder USDT → STONE @ rate
                    │
                    └─► Provider pool
                              │
                              └─► + hold-to-earn tier bonus
```

---

## Default config (env)

| Variable | Default / meaning |
|----------|-------------------|
| `MONETIZE_USDT_TREASURY_EVM` | Central ERC-20 USDT receive address |
| `MONETIZE_USDT_PER_GIB` | `0.05` USDT / GiB storage |
| `MONETIZE_USDT_UPKEEP_PER_GIB_MONTH` | `0.005` USDT / GiB·month |
| `MONETIZE_USDT_PER_100MIB` | `0.02` USDT / 100 MiB |
| `MONETIZE_USDT_PER_GFLOP` | `0.01` USDT / GFLOP |
| `MONETIZE_STONE_USDT_RATE` | `0.0001` USDT per STONE (early fixed) |
| `MONETIZE_STONE_USDT_RATE_MODE` | `fixed` → later `float` |
| `MONETIZE_STONE_PRICE_API` | Optional JSON `{ "usdt_per_stone": n }` |
| `MONETIZE_TEAM_SPLIT` | `ops:15:,core:20:,bd:10:,stone:10:` |
| `MONETIZE_PROVIDER_TIERS` | `0:0,1000:5,10000:10,50000:15` |

### How to slot into the upside (e.g. STONE role)

Add your contracted role to `MONETIZE_TEAM_SPLIT`:

```bash
# role:percent:EVM_USDT_wallet
MONETIZE_TEAM_SPLIT=ops:15:0xOps...,core:20:0xCore...,bd:10:0xBd...,stone:10:0xYourWallet...
```

That percentage of **every commercial USDT receipt** is accounted to your role immediately.

Optional second upside: operate as a **resource provider** and hold STONE to earn **tier bonuses** on the provider pool.

---

## Worked example ($100 USDT)

With default 55% team / 45% provider and 0.0001 USDT/STONE:

| Slice | Amount |
|-------|--------|
| Team USDT | $55 |
| Provider pool USDT | $45 |
| STONE for providers | 450,000 STONE |

Provider with ≥1,000 STONE held: **+5%** on their distribution share, etc.

---

## APIs

| Endpoint | Purpose |
|----------|---------|
| `GET /api/data-sales/monetization` | Full model + team split + tiers + example |
| `GET /api/data-sales/usdt/quote?product=storage&units=10` | USDT quote + split preview |
| `POST /api/data-sales/usdt/claim` | Record USDT payment → team books + provider pool |
| `GET /api/data-sales/provider-tier?stone_held=5000` | Hold-to-earn tier lookup |

Page: `/data/` → **Commercial model — USDT first**

---

## Claim body (USDT)

```json
{
  "usdt_txid": "0x...",
  "product": "storage",
  "units": 10,
  "stone_address": "S..."
}
```

Products: `storage` | `upkeep` | `bandwidth` | `compute`

---

*Bloodstone · USDT monetization model v1.0 · July 2026*
