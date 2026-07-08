# Bloodstone Treasury & Concentration Disclosure

**Addendum to the Economic Model White Paper**  
**July 2026 · v1.0 (draft)**  
**Audience:** Partners, integrators, and community  
**Snapshot height:** 9,704 (indexed 8 July 2026)

---

## Executive summary

Bloodstone launched in June 2026 with a **199,999,998 STONE** genesis premine paid to a single public address. That output was **spent and re-split** into project-operational wallets during the first weeks of mainnet. As of block **9,704**, on-chain supply is **~200.97 million STONE** (~970,400 STONE from PoW at 100 STONE/block; the remainder is treasury-derived).

**Concentration today is high.** The top three addresses hold **~77.1%** of supply; the top ten hold **~96.0%**. This is not a broad holder base — it reflects **project treasury custody** that has not yet been disbursed at scale.

This addendum publishes what we know now: genesis history, a labeled wallet registry, allocation buckets, a 12–24 month disbursement framework, and partner-facing rails. It does **not** claim on-chain vesting or trustless treasury contracts — those do not exist yet.

---

## 1. Scope and methodology

| Item | Detail |
|------|--------|
| Data source | Full UTXO scan via Bloodstone Core RPC (`scantxoutset` + address index) |
| Rich list | Live at https://bloodstonewallet.mytunnel.org/#rich-list |
| Supply basis | Sum of unspent outputs at tip (~200,970,398 STONE at height 9,704) |
| Wallet labels | Derived from genesis documentation, `mine` / `webuser*` wallet exports, and operational knowledge |
| Update cadence | Re-publish within **30 days** of any treasury move **≥ 1M STONE**, or quarterly, whichever is sooner |

**Limitation:** Individual signatory names behind multi-key or offline custody are **not** included in v1.0. A v1.1 addendum will attach named controllers where legally permissible.

---

## 2. Genesis premine

| Field | Value |
|-------|-------|
| Amount | 199,999,998 STONE |
| Genesis address | `SZNtmBMyx2Cr9VMrj5vk5EYTUn1naedu5N` (P2PKH) |
| Genesis block hash | `df04225074039e630dad825b24818a695462bd19cd585131a0568f50e9bf71d0` |
| Coinbase message | `22/Jun/2026: Bloodstone independent chain relaunch` |
| Legacy precedent | Same premine magnitude as SpaceXpanse ROD; **new chain, no inherited UTXO set** |
| Custody change vs ROD | Single P2PKH treasury output instead of legacy 2-of-4 multisig |

### 2.1 Post-genesis distribution

The genesis address **no longer appears in the top 25** by balance at height 9,704. The premine was moved into **multiple project-operational addresses** between genesis and block ~1,500 (first documented `mine` wallet backup at height 1,510).

This was an **operational split**, not a public sale or airdrop. No on-chain vesting schedule was encoded at genesis.

---

## 3. Concentration snapshot (height 9,704)

| Metric | Value |
|--------|-------|
| Total on-chain STONE | 200,970,398 |
| PoW minted (era 0, 100 STONE/block) | ~970,400 (~0.48% of supply) |
| Treasury-derived (approx.) | ~200,000,000 (~99.5%) |
| Addresses with balance | 49 |
| Addresses scanned (index) | 6,196 |
| Top 1 holder | 30.27% |
| Top 3 holders | **77.09%** |
| Top 10 holders | **96.02%** |

### 3.1 Why this matters for partners

High rich-list concentration does **not** mean anonymous whales control float. Today it primarily means **undisbursed project treasury** sitting in a handful of cold and operational wallets. Partners should still treat this as an economic risk until disbursement is visible on-chain — but the remedy is **published outflows**, not assuming OTC purchases from independent holders.

### 3.2 Dilution vs decentralization

Era-0 PoW will mint **~1.04 billion STONE** after the **1,000 STONE fork at block 12,000** (see Halving Schedule). If treasury wallets are static, premine share of **total supply** falls toward **~16%** by end of era 0.

**Issuance alone does not decentralize control** if the same entity captures PoW payouts or treasury never moves. This disclosure focuses on **intended treasury outflows**, not only inflation math.

---

## 4. Wallet registry (top holders)

Statuses: **Cold** = long-hold reserve; **Operational** = day-to-day disbursement; **Earmarked** = allocated bucket, not yet spent down; **Spent** = genesis output fully distributed.

| Rank | Address | Balance (STONE) | % supply | Label | Bucket | Status |
|------|---------|-----------------|----------|-------|--------|--------|
| — | `SZNtmBMyx2Cr9VMrj5vk5EYTUn1naedu5N` | ~0 (not top 25) | — | Genesis premine (historical) | Genesis | **Spent** |
| 1 | `SaYQKHQrRMnjtbupzi1Bb9oEWe1rHf1jkk` | 60,834,404 | 30.27% | Treasury cold reserve (`webuser3` reserve path) | Core treasury — unallocated | Cold |
| 2 | `SkAsaotDaF2y8KqJdZaFs9hnpwmaCA7Equ` | 51,105,020 | 25.43% | Project custody — infrastructure reserve | Infrastructure & core development | Cold |
| 3 | `SPWDbxeVc9BGUepmT5FDECTKr8ucdu91Hh` | 45,003,400 | 22.39% | Treasury operational (`webuser2` reserve path) | Partner programs + ecosystem | Operational |
| 4 | `SarFkPCFripGoPSy6jKag8fYsKiMQhfP3L` | 11,000,000 | 5.47% | Earmarked grants wallet (`webuser7` export) | Community distribution / grants | Earmarked |
| 5 | `SNK6tDSHYVybJt5HTj5BSwb1PYhoSuZAz6` | 8,030,801 | 4.00% | Project custody — operational reserve | Infrastructure reserve | Operational |
| 6 | `SbqkZPjC2npdetcAo4PpG6g4vDnwe6Npcy` | 5,002,221 | 2.49% | Treasury sub-allocation (5M tranche) | Ecosystem grants | Earmarked |
| 7 | `SULPj2pzLuiZ9KKYiz4Gfif8wVPtXFhYGi` | 5,000,000 | 2.49% | Treasury sub-allocation (`webuser37` export) | Ecosystem grants | Earmarked |
| 8 | `ScDCPRunWLsKf4JyG8j1t3E4mkYaTFSVEV` | 4,987,950 | 2.48% | Treasury sub-allocation (5M tranche) | Partner programs (unassigned) | Earmarked |
| 9 | `SRJHN2SszzCGFRQnbSZJZ8buqoZ6CbQxAF` | 3,998,950 | 1.99% | Treasury sub-allocation (~4M tranche) | Liquidity / market making (reserve) | Earmarked |
| 10 | `SbqzoTuDp5ozPWCyj3ykY72TS6Wzk3YArB` | 2,000,115 | 1.00% | Operational float + early disbursement | Community distribution | Operational |
| 18 | `SNQ2mNsQSumv1P4QdiDqYz5sjCwdDTnbWV` | 66,601 | 0.03% | Pool operator wallet (`mine`, label=miner) | Pool operations (not treasury) | Operational |

**Note on ranks 2 and 5:** Not present in published wallet exports; labeled from operational custody mapping. Signatory-level attribution deferred to v1.1.

---

## 5. Allocation buckets (policy framework)

Total treasury envelope: **~200M STONE** (genesis premine, now distributed across registry wallets above).

| Bucket | Target share of premine | Purpose | Primary wallets (today) |
|--------|-------------------------|---------|-------------------------|
| Infrastructure & core development | 25–30% | Node, pool, mesh, Android/desktop miners, security, hosting | Rank 2, rank 5 (partial) |
| Ecosystem grants | 15–20% | Builders, mesh operators, storage replicators | Ranks 6–7, rank 4 (partial) |
| Partner programs | 15–20% | Bulk storage quotas, integrator allocations (e.g. Blurt) | Rank 3, rank 8 |
| Community distribution | 10–15% | Faucets, onboarding, mesh rebates, mining incentives | Ranks 4, 10 |
| Liquidity / market making | 5–10% | CEX/DEX routes when live | Rank 9 |
| Core treasury — unallocated | 15–25% | Strategic reserve; reduces only via published decisions | Rank 1 |

These are **target ranges**, not on-chain locks. Actual balances may drift until disbursement tooling and quarterly true-ups are in place.

---

## 6. Disbursement plan (12–24 months)

### 6.1 Principles

1. **No silent re-concentration** — treasury moves ≥ 1M STONE are announced with destination label and bucket.
2. **Partner-first rails** — integrators receive STONE from **designated outposts**, not OTC from cold reserves.
3. **Measurable reduction** — we track **top-3 % of supply** and **top-10 % of supply** each quarter.
4. **Blurt benchmark** — reduce partner dependence on spot float before bulk storage invoices go live.

### 6.2 Quarterly outflow targets (STONE)

| Period | Target gross outflow | Channels |
|--------|----------------------|----------|
| Q3 2026 | 2–5M | Mesh replication pilots, small builder grants, faucet |
| Q4 2026 | 5–10M | Partner outpost funding, ecosystem grants, community campaigns |
| H1 2027 | 15–25M | Blurt bulk quota (if contracted), LAN/mesh operator rebates |
| H2 2027 | 20–35M | Continued partner programs, liquidity seeding if markets exist |
| 2028 | 30–50M / year | Sustained grants + partner quotas; signatory disclosure v1.1 |

**Cumulative target:** **≥ 50M STONE** disbursed from treasury-labeled wallets by **July 2027**, **≥ 120M STONE** by **July 2028**, subject to partnership cadence and market conditions.

### 6.3 Concentration targets (top-3 % of total supply)

| Date | Target top-3 share | Notes |
|------|-------------------|-------|
| July 2026 (today) | ~77% | Baseline — pre-disbursement |
| January 2027 | ≤ 65% | First partner outpost flows visible |
| July 2027 | ≤ 55% | PoW dilution + ≥ 50M STONE disbursed |
| July 2028 | ≤ 40% | Era-0 PoW > 500M STONE; treasury policy mature |

These targets assume **no net treasury re-accumulation** from pool payouts to the same cold wallets. Pool operator wallets are excluded from treasury bucket accounting.

---

## 7. Partner outpost rail

Integrators (including Blurt) should **not** source large STONE blocks from rich-list addresses on the open market.

### 7.1 Designated partner outpost (proposed)

| Item | Detail |
|------|--------|
| Purpose | Ring-fenced STONE for bulk storage quotas and BLURT→STONE memo credits |
| Funding source | Rank 3 operational wallet and/or fresh partner bucket (rank 8) |
| Address | **To be published before first production invoice** (separate P2PKH; not a cold reserve) |
| BLURT memo format | `storage:<STONE_ADDRESS>:<bytes>` (per Mesh Storage Partnership draft) |
| Reporting | Monthly statement: opening balance, credits, debits, chunk bytes stored |

### 7.2 Blurt bulk quota illustration

At Blurt’s cited **~€22.80 / 1.2 TB / month** benchmark, a contracted bulk rate would be invoiced **against outpost balance**, not spot OTC. BLURT payment optional via outpost memo rail when live.

---

## 8. What is not on-chain today

| Item | Status |
|------|--------|
| Time-locked vesting contracts | **Not deployed** |
| Multisig treasury with published signers | **Not deployed** (genesis used single P2PKH) |
| On-chain bucket enforcement | **Not deployed** |
| Automated per-GB storage debits | **Proposed** — mesh coordination live; billing rules in progress |
| Individual signatory names | **Deferred to v1.1** |

---

## 9. Transparency commitments

| Commitment | Cadence |
|------------|---------|
| Rich list | Live (refreshed ~10 min TTL) |
| This disclosure | Updated quarterly or within 30 days of major treasury moves |
| Treasury move log | Publish TXIDs + destination labels for moves ≥ 1M STONE |
| Wallet registry | Amend when labels or buckets change |
| Signatory disclosure | v1.1 by **Q4 2026** |
| On-chain vesting proposal | RFC after first year of disbursement data |

---

## 10. Related documents

| Document | URL |
|----------|-----|
| Economic Model White Paper | https://bloodstonewallet.mytunnel.org/downloads/ |
| Blurt Partnership Response | https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Blurt-Partnership-Response.md |
| Halving Schedule | https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Halving-Schedule.md |
| Blurt Mesh Storage Partnership | https://bloodstonewallet.mytunnel.org/downloads/ |
| Live rich list | https://bloodstonewallet.mytunnel.org/#rich-list |
| Subsidy schedule API | https://bloodstonewallet.mytunnel.org/mining/api/pool/subsidy-schedule |

---

*Bloodstone · July 2026 · Addendum v1.0 (draft)*