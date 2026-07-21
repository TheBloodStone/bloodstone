# Google Drive Mesh Storage — Partner Handout

**Bloodstone Network · July 2026**  
*What you provide, what the network does, and how you get paid in STONE*

---

## In one sentence

You authorize Bloodstone to store **content-addressed mesh chunks** in a folder on **your Google Drive**. Buyers pay **STONE** (or **USDT**) for storage; after protocol splits, the residual funds a **provider pool** that pays **STONE** to capacity providers — including Drive partners linked to a **STONE address**.

---

## 1. What connecting Google Drive actually does

When a partner completes **Connect Google Drive**:

1. **Google OAuth** — Bloodstone requests `drive.file` only (files *this app* creates; not a full Drive scan).
2. **Folder** — Creates or reuses `BloodstoneMeshStorage` on the partner’s Drive.
3. **Provider registration** — Registers you as a mesh **storage** provider bound to the **STONE address** you entered (payout identity).
4. **Chunk replication** — Mesh data is split into ~256 KiB content-addressed chunks. New chunks can be mirrored to your Drive as `{sha256}.chunk` files.
5. **Recovery** — If the coordinator lacks a chunk locally, it can fetch it from a partner Drive that holds that hash, re-cache it, and serve the network.
6. **Disconnect** — You can revoke access anytime; the network stops using your Drive.

### What this is *not*

| Not this | Instead |
|----------|---------|
| Full blockchain node / miner | Storage capacity only |
| Access to personal photos/docs | Only the app-created folder |
| Fixed monthly salary | Earnings scale with demand + your share of the provider pool |
| Unlimited free cloud for others | Optional capacity caps + Google quotas apply |

**Live proof:** after the first successful connect, status showed `partner_count ≥ 1`, active Drive storage, and chunk replicas under `BloodstoneMeshStorage`.

---

## 2. How money flows (buyer → provider)

### Published STONE rates (mesh-native)

| Product | Rate | Buyer gets |
|---------|------|------------|
| Storage write credit | **1 STONE / GiB** | Prepaid upload/store capacity |
| Storage upkeep | **0.1 STONE / GiB · month** | Keep retained data online (30-day grace) |
| Bandwidth (related) | 1 STONE / 100 MiB | Transfer credit |
| Compute (related) | 1 STONE / GFLOP | Job credits |

**USDT commercial rail (optional):** ~0.05 USDT/GiB write, ~0.005 USDT/GiB·month upkeep — same waterfall after conversion.

### Revenue waterfall (same % on USDT and STONE)

```
Buyer pays STONE or USDT
        │
        ▼
Referral cut (if any)
        │
        ▼
Founder trail (~2%) + founder active (~5% when active)
        │
        ▼
Residual ──► ~55% team roles
        └──► ~45% PROVIDER POOL  ──► STONE to capacity providers
                                      (nodes, Pi, Android mesh, Drive partners)
        │
        ▼
Hold-to-earn tiers: hold more STONE → modest bonus (+5% / +10% / +15%
at 1,000 / 10,000 / 50,000 STONE held)
```

### Worked example — 100 STONE storage revenue

| Stage | Amount (illustrative) |
|-------|------------------------|
| Gross | 100 STONE |
| Founder trail + active (~7%) | 7 STONE |
| Residual | 93 STONE |
| Team (~55%) | ~51 STONE |
| **Provider pool (~45%)** | **~42 STONE** |
| Your share | Pro-rata of pool by capacity & policy |

Exact splits follow live monetization config — always verify [data-sales rates](https://bloodstonewallet.mytunnel.org/data-sales/).

---

## 3. How a Drive partner receives payment

| Step | Detail |
|------|--------|
| **1. Identity** | STONE address (`S…`) entered at connect = payout destination |
| **2. Earn role** | Google proves Drive quota; STONE address is who gets paid |
| **3. Stay useful** | Keep OAuth authorized; leave free space; allow API pull/push |
| **4. Buyer demand** | Storage/upkeep purchases fund the pool |
| **5. Distribution** | Coordinator allocates provider pool → credits your STONE address |
| **6. Wallet** | Hold or spend STONE in Qt / web wallet / Android miner |

**Important:** Payment is **STONE on Bloodstone mainnet**, not Google Pay and not USD in Drive. Early partners seed capacity; earnings grow as buyers buy write credit and pay upkeep on retained data.

---

## 4. Setup checklist (5–10 minutes)

1. Create/get a **STONE address**
2. Open **https://bloodstonewallet.mytunnel.org/data-sales/gdrive/**
3. Enter STONE address → **Connect Google Drive** → **Allow**
4. (If Google app is in **Testing**) ensure your Gmail is a **Test user** on the OAuth consent screen
5. Confirm `BloodstoneMeshStorage` exists and status `partner_count` increases
6. Optional: set a **capacity cap** (bytes)
7. Optional: hold STONE for **hold-to-earn** tier bonuses

---

## 5. Links

| Resource | URL |
|----------|-----|
| Connect Drive | https://bloodstonewallet.mytunnel.org/data-sales/gdrive/ |
| Rates & economics | https://bloodstonewallet.mytunnel.org/data-sales/ |
| Status JSON | https://bloodstonewallet.mytunnel.org/mining/api/chain-mesh/gdrive/status |
| Buyer claim API | https://bloodstonewallet.mytunnel.org/api/data-sales/claim |

---

## 6. Privacy & risk

| Topic | Fact |
|-------|------|
| Google scope | `drive.file` only |
| Data format | Hashed chunks, content-addressed |
| Disconnect | Anytime; revoke OAuth in Google account settings |
| Integrity | Chunk hashes detect tampering |
| Earnings | Demand-driven provider pool — not a salary |
| Quota | Google limits + optional partner cap |

---

## 7. FAQ

**Do I need a server or Pi?**  
No. Drive + STONE address is enough for this role.

**Can Bloodstone read my personal files?**  
No — only files created by this app under `BloodstoneMeshStorage`.

**When do I get paid?**  
When buyers fund storage/upkeep and distributions run to your linked STONE address. Amounts = pool size × your share.

**Testing mode?**  
Each partner Gmail must be a **Test user** until the OAuth app is published.

**Mining vs Drive?**  
Mining = hashpower. Drive = durable bytes. Both can earn STONE; meters differ.

---

*Handout reflects published policy and live mechanics as of July 2026. Verify live rates before commercial commitments.*
