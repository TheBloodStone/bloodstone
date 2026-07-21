# Bloodstone Use Case White Paper

**Who the network is for, what problems it solves, and how people use it today**

**Document version:** 1.0 · July 2026  
**Audience:** Users, partners, integrators, exchanges, operators, grant reviewers  
**Related docs:** *How the Network Works* · *Decentralized Network White Paper* · *Symbiotic Vision* · *Economic Model* · *Reseller Platform*

---

## Executive Summary

Bloodstone is a **proof-of-work cryptocurrency and edge infrastructure stack** designed so ordinary people—not only data centers—can help secure a ledger, earn STONE, store and move content, and keep services running when a single cloud host fails.

The use case is not “another coin with a wallet.” It is a **practical decentralization path**:

1. **Mine with what you already own** — phones, PCs, Bitaxe/ASIC hardware, and home Pi fleets.
2. **Optionally validate truth locally** — run a pruned or full node on a phone or desktop so your household does not have to trust a remote server for chain state.
3. **Hold and use STONE** — web wallet, Qt, and desktop GUIs for receive, send, staking, gifts, swaps, and stablecoin rails.
4. **Host and move data at the edge** — chain mesh, DTN bundles, and Blurt-anchored provenance so media and files survive outages and censorship pressure.
5. **Pay for real resources** — USDT-first commercial rails and a reseller/referral program that settle work back into the network economy.

This paper describes **who uses Bloodstone**, **what job each persona is hiring the stack to do**, and **which paths are live in July 2026** versus roadmap.

---

## 1. The Problem Space

| Failure mode of “centralized crypto infra” | What users experience | Bloodstone response |
|---------------------------------------------|----------------------|---------------------|
| Pool and API live only in one region | Mining dies when the VPS reboots | Multi-host stratum + LAN household nodes + device fleet offload |
| Wallets require trusting a remote balance API | Users cannot verify history offline | Optional local `bloodstoned`, ElectrumX, explorer, desktop wallet+node |
| Content lives on one CDN | Posts and video vanish under pressure or cost | Chain mesh chunks, DTN store-and-forward, Blurt provenance anchors |
| Only industrial miners can participate | Phones and home PCs are locked out | Multi-algo pool (Neoscrypt, Yespower, ROD, SHA256d) + Android fleet miner |
| DePIN projects demand opaque operator keys | Customers fear frozen funds | Trust-minimized payment routers; keys stay with users on-chain |

**One-sentence thesis:** *Bloodstone turns idle and household hardware into miners, validators, mesh peers, and optional commercial resource providers—while keeping user-held keys as the source of truth for money.*

---

## 2. Core Use Case (Product North Star)

### 2.1 Primary use case

> **A person installs the Bloodstone miner app (or desktop/web miner), pastes a STONE payout address they control, mines through the pool (or a home LAN node), receives STONE over time, and can spend, stake, gift, or swap that STONE through a wallet—without needing to operate a data center.**

Everything else in the stack either **makes that loop safer** (local nodes, consensus witnesses, QUASAR defense), **makes it more useful** (mesh storage, Blurt publishing, USDT monetization), or **makes it more distributable** (reseller, referral, Pi fleets).

### 2.2 Secondary use cases (same stack)

| # | Use case | Outcome |
|---|----------|---------|
| A | **Household mining mesh** | One full/pruned phone hosts stratum; other phones mine on Wi‑Fi with lower latency |
| B | **Consensus volunteer** | User validates chain without hosting miners (consensus / consensus-witness modes) |
| C | **Self-custody web wallet** | Register, receive, send, history, staking, gifts, USDT rails—keys remain exportable |
| D | **Disaster / offline village mesh** | Pi/Android DTN bundles keep content moving when the internet drops |
| E | **Creator provenance** | Anchor media hashes and mesh roots so deepfakes and silent edits can be challenged |
| F | **Commercial DePIN front door** | Customers pay USDT for storage/bandwidth/compute; providers earn STONE-linked rewards |
| G | **Reseller / referral distribution** | Partners sell access with branded storefronts; revenue router splits without holding balances |

---

## 3. Personas and Jobs-to-Be-Done

### 3.1 Everyday miner (phone-first)

**Job:** Earn STONE with spare phone capacity while charging on Wi‑Fi.  
**Success:** Shares accepted, payouts arrive to an address they control, app survives Android battery killers.  
**Touchpoints:** Android Fleet Miner APK, web OTA UI, pool dashboard, payout address from web or Qt wallet.  
**Fit today:** **Strong** — primary production path.

### 3.2 Household operator

**Job:** One plugged-in device becomes the home mining hub so other phones stay as light LAN clients.  
**Success:** Local stratum on Wi‑Fi, optional pruned/full chain sync, fallback to online pool if the hub is offline.  
**Touchpoints:** Local node modes (LAN client, pruned, full, mesh federation), mDNS LAN discovery.  
**Fit today:** **Strong** on Android LAN; improves as more full nodes exist globally.

### 3.3 Desktop / ASIC operator

**Job:** Push serious hashrate (CPU Neoscrypt/Yespower/ROD or SHA256d ASIC/SV2).  
**Success:** Stable stratum jobs, fair share accounting, merge-mining where supported.  
**Touchpoints:** cpuminer-opt kits, Bitaxe forwarders, SV2 template provider, multi-algo pool workers.  
**Fit today:** **Strong** for pool mining; SV2/auxpow continuously tuned.

### 3.4 Wallet user

**Job:** Hold STONE safely, send/receive, stake, redeem gifts, swap, and optionally touch USDT rails.  
**Success:** Login works, balances match chain reality, private keys can be exported; web login can be limited without seizing on-chain funds.  
**Touchpoints:** bloodstone-wallet-web, Qt, wallet-node GUI, explorer, faucet (where enabled).  
**Fit today:** **Strong** for STONE custody and transfers; commercial USDT paths evolving.

### 3.5 Mesh / content operator

**Job:** Keep files and livestream-related assets available across personal devices and Blurt anchors.  
**Success:** Chunks replicate, DTN flushes when peers return, provenance verifies.  
**Touchpoints:** Chain mesh APIs, Blurt custom_json provenance, Condenser embeds, Pi fleet packages.  
**Fit today:** **Beta / lab-to-field** — rails live; planetary peer count still scaling.

### 3.6 Bulk provider / referrer

**Job:** Sell network capacity or refer customers without becoming a custodian of user crypto keys.  
**Success:** Calculator quotes, storefront branding, on-chain revenue router splits, referral dashboards.  
**Touchpoints:** Reseller app (`/reseller/`), `BloodstoneRevenueRouter`, payment-config API.  
**Fit today:** **Scaffold + commercial design** — deploy checklist documented.

### 3.7 Network defender / witness

**Job:** Help the chain reject lies and 51% theater.  
**Success:** Witness signaling, braid-aware confirmation guidance, fork rehearsal tooling when needed.  
**Touchpoints:** QUASAR phases, witness docs, coordinator federation ops.  
**Fit today:** **Phased live** (defense stack through Phase 5 research/implementation track).

---

## 4. End-to-End User Journeys

### Journey 1 — “Mine tonight, hold keys”

1. Create or import a STONE address (web wallet, Qt, or external tool).
2. Install **Bloodstone miner** on Android (or use desktop/web miner).
3. Paste payout address → Start mining → connect to pool.
4. Phone submits **shares**; pool accumulates work toward payouts.
5. User checks balance in wallet / explorer; can send, stake, or hold.
6. Optional: enable **local node** modes later for household hosting or consensus.

**Value delivered:** Low-friction entry; no need to sync a full chain before first share.

### Journey 2 — “Home Wi‑Fi mining hub”

1. One device: Full or pruned **local node**, keep charging, finish sync.
2. Other devices: **LAN client** mode; auto-discover hub stratum.
3. If hub is busy/syncing: clients fall back to **online pool**.
4. Optional mesh federation pins block backups for recovery.

**Value delivered:** Lower latency, less dependence on a distant VPS for job sourcing, household resilience.

### Journey 3 — “Creator anchors truth”

1. Produce media or document.
2. Hash content; anchor via **provenance** API + Blurt custom_json.
3. Store shards on chain mesh / DTN peers.
4. Readers verify badge/embed; offline regions resync when links return.

**Value delivered:** Censorship-resistant publishing with cryptographic continuity—not merely social likes.

### Journey 4 — “Pay USDT, power the mesh”

1. Customer prices storage/bandwidth/compute (calculator).
2. Pays USDT on EVM through configured treasury/router.
3. Team split (ops/core/bd/…) then remainder maps into **provider STONE pool**.
4. Providers with attested STONE holdings may earn tier bonuses.

**Value delivered:** Familiar commercial payment (USDT) funding decentralized work (STONE-denominated providers).

---

## 5. Product Surface Map (What “Using Bloodstone” Means)

| Layer | What the user touches | Use-case role |
|-------|----------------------|---------------|
| **Chain core** | `bloodstoned`, Qt, RPC | Truth, consensus, wallets |
| **Pool** | Stratum workers, dashboards | Share tracking, payouts |
| **Android fleet miner** | Capacitor APK + OTA web UI | Phone mining, local node, LAN |
| **Miner web / portal** | Dashboards, downloads | Onboarding, status, OTA |
| **Wallet web** | Accounts, send/receive, stake, gifts, swap, USDT | Self-custody UX |
| **Explorer / faucet / electrumx** | Lookup, test funds, light clients | Discovery and tooling |
| **Chain mesh + DTN** | Chunks, bundles, mDNS | Storage & offline sync |
| **Blurt convergence** | Provenance, agents, embeds | Social/trust anchor |
| **Reseller / contracts** | Storefronts, revenue router | Distribution & monetization |
| **QUASAR / federation** | Witness, coordinator ops | Security & multi-operator growth |

---

## 6. Fit Matrix (July 2026)

| Use case | Fit | Notes |
|----------|-----|-------|
| Phone pool mining + STONE payout | **Strong** | Default onboarding story |
| Household LAN node + multi-phone mining | **Strong** | Modes documented in *How the Network Works* |
| Desktop CPU mining multi-algo | **Strong** | Neoscrypt / Yespower / ROD |
| ASIC SHA256d / SV2 | **Strong / evolving** | Template freshness and auxpow under active ops |
| Self-custody STONE wallet | **Strong** | Web + Qt + node GUIs |
| Staking / gifts / internal swaps | **Live** | Wallet-web features |
| Mesh storage & DTN offline village | **Strong rails, scaling peers** | Best “resilience” story for field demos |
| Blurt provenance / eternal publishing | **Beta** | APIs live; UX still maturing |
| USDT commercial DePIN + reseller | **Designed + scaffold** | Payment router trust model specified |
| Planetary autonomous AI agents | **Roadmap (Layer 6)** | Identity scaffold first |

---

## 7. Economic Shape of the Use Case

Bloodstone’s use cases only stay coherent if incentives match work:

- **Miners** earn STONE for securing the chain (pool shares → payouts; subsidy schedule documented separately).
- **Node operators** earn *resilience and sovereignty* first; mesh/DePIN rails aim to attach **storage/compute/bandwidth** memos and USDT-funded provider pools over time.
- **Wallet users** need keys they control; **account bans on web login must never seize on-chain funds**—private keys remain the user’s recovery path.
- **Commercial customers** can enter with **USDT** while the network’s native unit remains **STONE**.
- **Referrers / bulk providers** distribute access without becoming key custodians when using the revenue router pattern.

For detailed issuance, treasury concentration, and halving, see the *Economic Model* and *Treasury Disclosure* papers.

---

## 8. What Bloodstone Is *Not* (Scope Boundaries)

Clarity protects the brand and the use case:

| Not the primary claim | Why |
|-----------------------|-----|
| A fully trustless global CDN at planetary scale *today* | Mesh peers are live but not yet “millions of nodes” |
| A bank that can reverse on-chain payments | Chain settlement is irreversible; web accounts only gate *hosted UX* |
| A single-algorithm ASIC-only project | Multi-algo by design for inclusive hashrate |
| A pure social network | Blurt is the social/trust companion; Bloodstone is money + memory + mining fabric |
| “Set and forget cloud mining with guaranteed ROI” | Mining is probabilistic work; hardware and power costs are user-side |

---

## 9. Success Metrics for the Use Case

Operators and partners can judge progress with simple, honest measures:

1. **Active unique payout addresses** earning from the pool  
2. **Share of hashrate** from phones / LAN nodes vs central bridge  
3. **Count of pruned/full nodes** reachable beyond the primary VPS  
4. **Mesh chunk replication quorum** (e.g., 2-of-3) health  
5. **Wallet users** who export keys or run non-custodial clients  
6. **USDT → provider STONE** volume once commercial enforcement is on  
7. **Time-to-first-share** for a new Android install on Wi‑Fi  

---

## 10. Recommended Onboarding Paths

### Fastest path (recommended for new users)

Miner app → pool mining → web or Qt wallet for custody → explore staking/gifts later.

### Resilience path

One household full/pruned node → LAN clients → mesh federation → optional consensus-only devices.

### Creator / partner path

Blurt account linkage → provenance anchor → mesh host → Condenser embed → optional reseller storefront.

### Commercial path

Read payment-config → quote calculator → USDT pay → monitor provider settlement → stake/hold STONE for tiers.

---

## 11. Conclusion

Bloodstone’s use case is **inclusive proof-of-work plus edge infrastructure**:

- **Earn** with everyday hardware.  
- **Verify** with optional local nodes.  
- **Hold and move** value with self-custody wallets.  
- **Remember and republish** with mesh + Blurt provenance.  
- **Commercialize** carefully with USDT front doors and non-custodial payment splits.

The stack is deliberately **incremental**. July 2026 prioritizes mining, nodes, wallets, and mesh rails that already run; deeper planetary scale and closed-loop DePIN yield remain a measured path, not a marketing fantasy.

**Bottom line for any stakeholder:** if your goal is to put real work, real verification, and real user-held value on hardware people already own—Bloodstone is built for that job.

---

## Appendix A — Related reading

| Document | Focus |
|----------|--------|
| *How the Bloodstone Network Works* | Plain-language miner/node modes |
| *Decentralized Network White Paper* | Node roles and longevity |
| *Economic Model White Paper* | Incentives and issuance shape |
| *Symbiotic Vision White Paper* | Blurt × Bloodstone 2027–2035 horizon |
| *Reseller Platform* | Referral / bulk provider rails |
| *USDT Monetization Model* | Commercial USDT → STONE flow |
| *QUASAR 51% Defense White Paper* | Consensus attack resistance |
| *Chain Mesh Storage White Paper* | Storage architecture |

## Appendix B — Document control

| Field | Value |
|-------|--------|
| Title | Bloodstone Use Case White Paper |
| Version | 1.0 |
| Date | July 2026 |
| Status | Public / partner-ready |
| Maintainer | Bloodstone docs |
| Public download (docx) | https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Use-Case-White-Paper.docx |
| Public download (md) | https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Use-Case-White-Paper.md |
| Latest alias | https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Use-Case-White-Paper-latest.docx |

---

*Bloodstone · Use Case White Paper v1.0 · July 2026*
