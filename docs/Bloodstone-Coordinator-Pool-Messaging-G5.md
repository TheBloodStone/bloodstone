# Bloodstone Coordinator — Pool Messaging (G5)

**Document version:** 1.0 · July 2026  
**Status:** Live — Federation Phase 5 (pool messaging clarity)  
**Public copy:** https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Coordinator-Pool-Messaging-G5.md  

**Related:**  
- [LAN Pool Coordinator Guide](Bloodstone-LAN-Pool-Coordinator-Guide.md)  
- [Multi-home exchange procedure](Bloodstone-Coordinator-Multi-Home-Exchange-Procedure.md)  
- [Live implementation notes](Bloodstone-Coordinator-Federation-Live-Implementation.md)  

---

## 1. Purpose (G5 exit)

Make it unmistakable for users and partners:

1. **Which host is the public internet pool**  
2. **Which path is household LAN pool** (no VPS)  
3. **Multi-home status URLs are not pool stratum**  
4. **No shared unpaid balances** across VPS operators or A↔B  

---

## 2. What is *not* federated

| Item | Rule |
|------|------|
| Share ledger / `pending_stone` | **Per pool host only** — never merge A and B unpaid balances |
| Stratum jobs | Served by the host you connect to |
| Payouts | Paid by the pool operator that accepted shares |
| Multi-home tip APIs | **Status / QUASAR only** — do not send hashrate there |

---

## 3. Public internet pool (COORD-A brand)

| Field | Value |
|-------|--------|
| Brand / portal | https://bloodstonewallet.mytunnel.org |
| Mining dashboard | https://bloodstonewallet.mytunnel.org/mining/ |
| Pool operator | Bloodstone ops (`bloodstone-ops`) on COORD-A |
| Host IP (stratum) | `64.188.22.190` |
| Neoscrypt | TCP **3437** |
| Yespower | TCP **3438** |
| SHA256d | TCP **3429** (TLS **3430** where configured) |
| ROD Neoscrypt label | **3440** |
| Payout | Per A pool rules / configured payout address |

**COORD-B (`LRGK.mytunnel.org` / `192.119.82.145`) is a lean status + witness peer.**  
It may run local stratum for *that host’s own* miners, but it is **not** the brand public pool for internet miners unless separately advertised as its own pool brand.

---

## 4. Household LAN pool (no VPS)

| Field | Value |
|-------|--------|
| Guide | https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-LAN-Pool-Coordinator-Guide.md |
| Also mirrored | https://LRGK.mytunnel.org/downloads/Bloodstone-LAN-Pool-Coordinator-Guide.md |
| Requirement | APK **1.3.84+**, ≥2 synced full/pruned nodes on Wi‑Fi, peer verify on **:18342** |
| Effect | Verified LAN coordinator stops relaying to VPS pool; jobs/shares/payout ledger local |
| Bitaxe | Phone LAN IP, port **3429**, password `x` (LAN pool) or `solo` |

LAN pool **pending balances are local SQLite** until the operator sends on-chain. They are **not** visible on COORD-A pool dashboards.

---

## 5. Multi-home status vs mining

| Endpoint | Use for mining? | Use for tip/policy? |
|----------|-----------------|---------------------|
| `https://bloodstonewallet.mytunnel.org/api/coordinator/status` | No | Yes |
| `https://bloodstonewallet.mytunnel.org/api/quasar/status` | No | Yes (full QUASAR) |
| `https://LRGK.mytunnel.org/api/quasar/status` | No | Yes (peer tip) |
| Stratum ports on A | **Yes** (public pool) | No |
| LAN stratum on phone | **Yes** (household) | No |

---

## 6. Operator directory (roster roles)

Signed roster: https://bloodstonewallet.mytunnel.org/downloads/coordinator-roster-latest.json  

| device_id | Roles (typical) | Pool meaning |
|-----------|-----------------|--------------|
| `coord-a-primary` | witness, status, downloads, catalog, pool, electrumx | **Public brand pool** + services |
| `coord-b-lrgk-01` | witness, status | **Status/witness peer only** — not brand pool |

If a future operator lists `pool` in roster roles, that means **their own** pool brand/ledger — never a shared federation share DB.

---

## 7. User-facing copy (paste-ready)

**Internet phone / ASIC pool miners:**  
Connect to the Bloodstone public pool on **bloodstonewallet.mytunnel.org** / **64.188.22.190** stratum ports. Rewards and pending balances are tracked **only** on that pool.

**Household:**  
Run two full/pruned nodes → LAN pool coordinator (see LAN guide). No VPS required after peer verify.

**Exchanges:**  
Poll multi-home **status** URLs for tip agreement (see multi-home procedure). Run **your own node** for deposit credit. Status multi-home ≠ pool federation.

---

## 8. G5 checklist

- [x] Public pool host/ports documented  
- [x] LAN guide published on A downloads  
- [x] LAN guide mirrored on B downloads  
- [x] Explicit “no cross-host unpaid balances”  
- [x] Status multi-home distinguished from stratum  
- [x] Roster role meaning for `pool` clarified  

---

## 9. Document history

| Version | Date | Notes |
|---------|------|-------|
| 1.0 | 2026-07-11 | G5 pool messaging clarity |

---

*Bloodstone LLC · G5 pool messaging · Companion to coordinator federation*
