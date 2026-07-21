# Founder alignment + community referral

*July 2026 · Structure for long-term STONE role participation*

---

## Overview

Three pillars for a founding / long-term aligned member:

| # | Pillar | What it is |
|---|--------|------------|
| **1** | STONE long-term alignment | Conservative initial grant + monthly tranches for continued valuable participation |
| **2** | USDT trail + active | Perpetual residual trail (survives retirement) + separate active work stream |
| **3** | Community referral | One program for team and external promoters — global sales force |

Commercial billing remains **USDT-first** (see `Bloodstone-USDT-Monetization-Model.md`). These pillars sit in the **waterfall** before residual team roles and the STONE provider pool.

---

## Waterfall (gross commercial USDT)

```
1. Gross USDT from customer
2. Community referral cut (if referral_code)
3. Founding-member trail (perpetual %)
4. Founding-member active stream (only if participation active)
5. Residual → core team roles (ops/core/bd/stone/…) + STONE provider pool
```

---

## 1) STONE long-term alignment

**Philosophy:** skin in the token, not a dump. Earn-out style.

| Parameter | Default | Env |
|-----------|---------|-----|
| Initial alignment | 50,000 STONE | `FOUNDER_STONE_INITIAL` |
| Monthly tranche | 5,000 STONE | `FOUNDER_STONE_MONTHLY_TRANCHE` |
| Horizon | 24 months | `FOUNDER_STONE_TRANCHE_MONTHS` |
| Cap | initial + monthly×months | `FOUNDER_STONE_ALIGNMENT_CAP` |
| Beneficiary | (set) | `FOUNDER_STONE_ADDRESS` |

Monthly tranches release only while `FOUNDER_PARTICIPATION_ACTIVE=1` (continued valuable participation). Ops schedules via:

`POST /api/data-sales/alignment/tranche` with `{"kind":"monthly"}` or `{"kind":"initial"}`.

---

## 2) USDT trail + active participation

### Trail (perpetual)

- **Default:** 2% of gross commercial USDT (`FOUNDER_USDT_TRAIL_PCT`)
- **Survives retirement** — does not require active work flag
- **Rationale (finance trail):** residual on revenue attracted because the project is elevated / clients arrive organically, not only from your direct sales calls
- Wallet: `FOUNDER_USDT_TRAIL_WALLET`

### Active participation stream

- **Default:** 5% of gross while active (`FOUNDER_USDT_ACTIVE_PCT`)
- Stops or zeros when `FOUNDER_PARTICIPATION_ACTIVE=0`
- Wallet: `FOUNDER_USDT_ACTIVE_WALLET` (can match trail wallet)

| State | Effective founder USDT % |
|-------|---------------------------|
| Active | trail + active = **7%** (defaults) |
| Retired / inactive | trail only = **2%** |

Optional: keep a `stone` role in `MONETIZE_TEAM_SPLIT` as base ops share, or set it to `0` if trail+active fully replace it.

---

## 3) Community referral program

One code system for **internal team and external promoters**.

| Parameter | Default | Env |
|-----------|---------|-----|
| Referral cut | 5% of referred commercial USDT | `REFERRAL_USDT_PCT` |
| Earn window | 12 months from first payment | `REFERRAL_EARN_MONTHS` |

### Register a promoter

```http
POST /api/data-sales/referral/register
{
  "owner_label": "alice",
  "usdt_wallet": "0x...",
  "stone_address": "S...",
  "channel": "community"
}
```

### Customer pays with code

```http
POST /api/data-sales/usdt/claim
{
  "usdt_txid": "0x...",
  "product": "storage",
  "units": 10,
  "stone_address": "S...",
  "referral_code": "ABC123"
}
```

---

## Worked example ($100 USDT, no referral, founder active)

| Slice | Approx (defaults) |
|-------|-------------------|
| Trail 2% | $2.00 |
| Active 5% | $5.00 |
| Residual $93 | → team roles % + provider STONE pool |

With a 5% referral code first: $5 to referrer, then trail/active on $95, then residual.

---

## APIs

| Endpoint | Purpose |
|----------|---------|
| `GET /api/data-sales/alignment` | Full structure + defaults |
| `GET /api/data-sales/alignment/waterfall?usdt=100&ref=CODE` | Preview cuts |
| `POST /api/data-sales/alignment/tranche` | Schedule STONE tranche |
| `POST /api/data-sales/referral/register` | Create promoter code |
| `GET /api/data-sales/monetization` | Embeds `founder_alignment` |

Page: `/data/` → **Founder alignment structure**

---

## Negotiation knobs (not code law)

Defaults are **conservative starting points** for discussion:

- Raise/lower trail vs active split  
- Shorten/lengthen STONE earn-out  
- Tighten referral % or months  
- Always leave residual for providers (capacity must get paid)

---

*Bloodstone · Founder alignment & referral v1.0 · July 2026*
