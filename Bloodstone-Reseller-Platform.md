# Bloodstone reseller, referral & trustless payments

*July 2026 · Megadrive product conversation*

---

## Trust model — no held keys

Commercial stablecoin payments on EVM use **`BloodstoneRevenueRouter`**:

1. User `approve` + `pay(token, amount, referrer, referralBps, memoHash)`
2. Contract **pulls and immediately splits** USDT/USDC
3. **Zero balance** left in contract (rounding → last payee / provider pool)
4. After deploy: **`lockPayees()` + `renounceOwnership()`** — no operator key can redirect funds

Source: `/root/bloodstone-contracts/contracts/BloodstoneRevenueRouter.sol`

Apps **must not hardcode** addresses forever. Read:

`GET /api/network/payment-config`

---

## Roles

| Role | Frontend | Backend | Network buy | Commission |
|------|----------|---------|-------------|------------|
| **End user** | SSO + calculator + projections | Bloodstone hosts identity | Self-provision via public addresses | — |
| **Referrer** | Branded or `?ref=` Bloodstone URL + dashboard | Referral codes/earnings | **No** operator purchase UI | **2.5%–5%** by stake/volume |
| **Bulk provider** | Full branded storefront (template) + dashboards | Tenants, gateways, FX | **Yes** STONE or USDT/USDC | Wholesale **5%→15%** discount |

### Bulk provider rules

- Hold/stake STONE (min env `RESELLER_STAKE_MIN_STONE`, governance-variable)
- Discount starts **5%**, grows toward **15%**
- Payouts only after **≥10 unique tenants** and min revenue (anti self-bulk gaming)
- Can use Stripe/PayPal/etc. for *their* clients; settle to network in STONE/USDT/USDC
- FX: manual rate or provider API (e.g. xe.com)

### Referrer rules

- Public program, anyone can refer
- **Not** a reseller — capped **2.5%–5%**
- Dashboard + referral link
- Clients self-provision from network API addresses

---

## UI requirements (shipped scaffold)

- SSO: Google, GitHub, LinkedIn (demo mode until OAuth secrets set)
- Resource **calculator**: sliders + numeric inputs, USDT + local currency
- **Usage projections** for users and bulk operators
- Bulk: brand (logo/color/about) + “Powered by Bloodstone Network”
- Standard network explainer pages on storefront

App: `https://…/reseller/` (service on `:8897`)

---

## APIs

| Endpoint | Purpose |
|----------|---------|
| `GET /api/network/payment-config` | Public auditable addresses + policy |
| `GET /reseller/api/calculator` | Quote line items |
| `GET /reseller/api/project-usage` | Forward projections |
| `POST /reseller/api/register` | Create bulk/referrer org |
| `GET /reseller/dash/<slug>/` | Operator dashboard |
| `GET /reseller/s/<slug>/` | End-user storefront |

---

## Deploy checklist

1. Deploy `BloodstoneRevenueRouter` on Ethereum (or chosen EVM)
2. `lockPayees()` → `renounceOwnership()`
3. Set `BLOODSTONE_REVENUE_ROUTER=0x…` in env
4. Confirm `/api/network/payment-config` shows router
5. Configure OAuth client IDs; set `RESELLER_SSO_DEMO=0`

---

*Bloodstone · Reseller platform v1.0 · July 2026*
