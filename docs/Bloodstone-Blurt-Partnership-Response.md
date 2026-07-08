# Bloodstone Response to Blurt — Tokenomics, Storage Economics & Multi-Algo Security

**July 2026 · v1.0**  
**Audience:** Blurt Core team  
**Subject:** STONE concentration, storage economics, and 51% attack surface

---

## Executive summary

Thank you for laying this out clearly. We take these concerns seriously — especially coming from a team that deliberately reduced its own holdings from ~15% to ~7% because you believe broad ownership matters. That is the standard we want partners to hold us to.

This document is our current, honest position: what is already designed and deployed, what changes the dilution math materially from your model, and what we have not yet published but should.

---

## On concentration and your dilution math

Your concern is valid. At block ~9,687, on-chain supply is ~201M STONE, and the top three addresses hold roughly **30% + 25% + 22% ≈ 77%** of circulating supply. If Blurt paid for storage in STONE, you would be buying into a market where a small number of wallets dominate float today.

### Two clarifications on the dilution timeline

**1. The genesis treasury is a single, public address.**

The June 2026 relaunch allocated **199,999,998 STONE** in one coinbase output to:

`SZNtmBMyx2Cr9VMrj5vk5EYTUn1naedu5N`

This is documented in our Development Journey and Economic Model white papers. We have not yet published a formal wallet-by-wallet disclosure tying rich-list entries to named entities — that is a gap we intend to close.

**2. Your “100 STONE/block for 4+ years” model understates near-term PoW issuance.**

Mainnet is still in era 0 at **100 STONE/block**, but a **scheduled consensus upgrade at block 12,000** raises the era-0 base to **1,000 STONE** for the remainder of the era (blocks 12,000–1,054,079). Era 0 PoW issuance alone is projected at **~1.04 billion STONE** — versus **~200M** from the premine.

Even if treasury wallets did not move, premine share of total supply after era 0 would fall toward **~16%**, not ~50%+, before the first halving.

Your directional concern (concentration matters for utility-token economics) is right; the **timeline to meaningful dilution is shorter** than a flat 100 STONE/block model suggests — provided PoW participation continues and treasury is not simply re-accumulating mined coins.

We also hear the deeper point: **dilution from mining ≠ decentralization of control** if the same entities capture PoW payouts or treasury never disburses. Issuance alone is not enough.

---

## 1. Treasury strategy (~200M STONE)

### What exists today

One genesis treasury output (~200M STONE). There is **no on-chain automated vesting contract** yet. Disbursement is operational, not trustlessly encoded.

### Planned allocation buckets (working framework)

| Bucket | Purpose |
|--------|---------|
| Infrastructure & core development | Node, pool, mesh coordinator, Android/desktop miners, security maintenance |
| Ecosystem grants | Third-party builders, LAN/mesh operators, storage replicators |
| Partner programs | Structured allocations for integrations (e.g. Blurt bulk storage quotas) paid from treasury or fresh issuance — **not** requiring partners to buy float from top holders |
| Liquidity / market making | As needed when CEX/DEX routes exist |
| Community distribution | Faucets, onboarding, mesh replication rebates, mining participation |

We agree a **published treasury policy** (addresses, buckets, and disbursement cadence) is a prerequisite for a serious storage partnership. We will prepare that as a short addendum to the Economic Model white paper.

---

## 2. Decentralization roadmap

### Mechanisms already in code or operation

- **PoW issuance** — multi-algorithm mining open to phones, browsers, CPUs, and ASICs via a unified pool
- **Per-address pool weight cap (75%)** — no single payout address can hold more than three-quarters of an open round
- **Cross-algo subsidies (35%)** — a block found on one algorithm shares STONE with miners on the others
- **Staking pool slice (1% of every block)** — routes value to long-term stakers, not only active hashers
- **Mesh / LAN participation** — storage replication and local full nodes spread infrastructure beyond our VPS

### What we are committing to publish

- Treasury wallet labeling (team / foundation / operational / unallocated)
- Target ranges for treasury disbursement over the next 12–24 months
- Partner-facing structure so Blurt (or any integrator) can prepay storage in STONE via a **designated outpost account** without sourcing large blocks from the rich list

Your path from 15% → 7% is a useful benchmark. We are not there yet on transparency or demonstrated outflow, and we do not want to pretend otherwise.

---

## 3. Storage economics — avoiding “captive token” dynamics

If Blurt integrates STONE for mesh storage, we do **not** want you buying float exclusively from concentrated holders.

### Proposed rails (Blurt Mesh Storage partnership draft)

- **Bulk partner quota** — Blurt pays a monthly STONE amount (spot-equivalent to your current ~€22.80 / 1.2 TB benchmark) into a Bloodstone outpost; users receive quota without hitting the open market
- **BLURT → STONE memo rail** — `storage:<STONE_ADDRESS>:<bytes>` so Blurt can fund storage without OTC purchases from whales
- **Mesh replication rebates** — STONE flows to peers who store chunks, not only to the coordinator

### Important honesty

Per-GB storage billing in STONE is **proposed**, not fully live in code today. Mesh coordination is operational; automated quota debits and peer replication incentives are on the roadmap. A partnership would help define those rules with a real customer — but we will not represent them as already trustless on-chain.

### Structural protections for Blurt

- Contracted bulk rate, not spot market dependency
- Option to denominate invoices in BLURT with STONE credited at payment time
- No requirement to accumulate STONE from the top three wallets

---

## 4. 51% attack surface — consensus vs pool economics

This distinction matters: **pool payout rules ≠ consensus security.**

### What Bloodstone inherits (SpaceXpanse / Xaya multi-algo consensus)

This is **not** a DigiByte geometric-mean clone. It is the Xaya triple-algo weighting scheme:

| Layer | Mechanism |
|-------|-----------|
| Per-algorithm difficulty | Dark Gravity retargeting runs on **separate block streams per algo** (`GetNextWorkRequired` only considers ancestors with the same `PowAlgo`) |
| Algorithm work weighting | `powAlgoLog2Weight`: SHA256d = 6, Neoscrypt = 10, Yespower = 22 — SHA256d work is **deliberately down-weighted** in cumulative chain work vs CPU algorithms |
| Cross-algo timing normalization | `AvgTargetSpacing` and `GetBlockProofEquivalentTime` combine contributions from all three consensus algos (~270s target per algo, ~80–90s between blocks overall) |
| Longest-work chain rule | Best chain is selected on weighted `nChainWork`, not raw SHA256 hashrate alone |

We do **not** rely solely on the assumption that no single algorithm can be dominated. SHA256d dominance **does not translate 1:1 into chain-work dominance** the way it would on a single-algo SHA256 chain.

### What we do not have today

DigiByte-style geometric mean difficulty adjustment as a separate, named layer. The Economic white paper’s cross-algo **payout** subsidies and even-share rebalancing are **pool accounting** — they affect who gets paid, not which fork wins.

### SHA256d / rental-hashrate risk — candid assessment

You are right that rented SHA256 hashrate is cheaper per unit than attacking Bitcoin. Mitigations today:

- Down-weighted SHA256d chain work (consensus)
- Independent per-algo difficulty floors/ceilings
- Merge-mining (auxpow) path for SHA256 blocks
- Pool monitoring and operator visibility

### Roadmap items we are open to discussing

- Publishing a security appendix with worked examples (e.g. “X% SHA256d + Y% Neoscrypt required to outpace tip”)
- Stricter anchoring if SHA256d share of **chain work** (not just pool weight) exceeds thresholds
- Incentivizing Neoscrypt/Yespower full-node share alongside ASIC LAN forwarding

### Note on “four algorithms”

Consensus mainnet uses **three** PoW algorithms (SHA256d, Neoscrypt, Yespower). **ROD Neoscrypt** is a **fourth pool lane** for the auxiliary ROD chain — not a fourth independent consensus weight on Bloodstone mainnet.

---

## 5. Transparency

| Item | Status |
|------|--------|
| Genesis premine address | **Public** — `SZNtmBMyx2Cr9VMrj5vk5EYTUn1naedu5N` |
| Rich list | **Live** — https://bloodstonewallet.mytunnel.org/#rich-list |
| Top-wallet entity labels | **Not yet published** — gap acknowledged |
| Lock-up / vesting schedule | **Not on-chain** — see Treasury & Concentration Disclosure (draft) |
| Treasury & concentration disclosure | **Published (draft)** — [MD](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Treasury-and-Concentration-Disclosure.md) / [DOCX](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Treasury-and-Concentration-Disclosure.docx) |
| Halving / issuance schedule | **Published** — Halving Schedule MD/DOCX + `/mining/api/pool/subsidy-schedule` |

We have published a **Treasury & Concentration Disclosure** (v1.0 draft) covering wallet labels, allocation buckets, and a 12–24 month disbursement framework. Signatory-level naming remains deferred to v1.1.

---

## Our intent back to Blurt

We are not asking you to accept concentration as permanent, or to trust pool cleverness instead of consensus review. We are saying:

1. **Your economic concern is legitimate** — and it matches concerns we have internally.
2. **The issuance curve is more dilutive than a flat 100 STONE model** — but dilution alone is not decentralization.
3. **Consensus is stronger than “hope no algo dominates”** — with explicit per-algo retargeting and SHA256d down-weighting — but it is **not identical** to DigiByte’s geometric mean, and rented-hashrate risk deserves continued attention.
4. **A storage partnership should be structured** so Blurt is not a price-taker from three wallets.

We would welcome a follow-up call to walk through the consensus code paths (`powdata.cpp`, `chain.cpp`, `pow.cpp`) and to co-design treasury disbursement + Blurt bulk-storage rails so the economic foundation catches up to the technical one.

---

## References

| Document | URL |
|----------|-----|
| Bloodstone Economic Model White Paper (July 2026) | https://bloodstonewallet.mytunnel.org/downloads/ |
| Bloodstone Halving Schedule | https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Halving-Schedule.md |
| Blurt Mesh Storage Partnership draft | https://bloodstonewallet.mytunnel.org/downloads/ |
| Development Journey white paper | https://bloodstonewallet.mytunnel.org/downloads/ |
| Live rich list | https://bloodstonewallet.mytunnel.org/#rich-list |
| Subsidy schedule API | https://bloodstonewallet.mytunnel.org/mining/api/pool/subsidy-schedule |

### Blurt’s cited on-chain data

- Rich list at block ~9,687: supply ~200,968,698 STONE; top addresses ~30.27%, 25.43%, 22.39%
- Economic Model white paper: genesis premine 199,999,998 STONE; 100 STONE/block era-0 (pre–block 12,000 fork)
- Network white paper: four pool algorithms; three consensus PoW algorithms on mainnet

---

*Bloodstone · July 2026 · For partnership discussion with Blurt Core*