# Bloodstone Development Roadmap

**Version:** 2.2
**Status:** Living implementation roadmap
**Authority:** Subordinate to the **Bloodstone Protocol Constitution** (current: **v1.3**; hierarchy Const. Art. IX.1)
**Date:** August 2026
**Supersedes:** v2.1

**Changes in v2.2:**
- **Track E — Fork Lab** sequencing added (below H1 / Vault; does not steal Track A capacity).
- **Constitution v1.3** referenced (Art. **X Platform Neutrality** ratified — was pending in early v2.2 drafts).
- **Fork Lab RFCs FL-1…FL-5** filed under `docs/rfcs/fork-lab/` and public downloads.
- **Platform salvage removed**; Goblin Magic = LRGK-only canary.
- **WP0** burn verifier shipped; **WP1** burn pipeline **shipped** (demand call 2026-08-01; vertical slice closed 2026-08-01: watcher timer, manual reconcile, provision artifacts).
- **WP1.5** fee curve live; **WP2** catalog + MFQ two-speed **shipped** (2026-08-01); **WP3** registry bot is next.
- Hierarchy reminder: Const → RFC → RFQ/Build Spec → code (Art. IX).

**Changes in v2.1:**
- **Naming corrected:** RAL is the **Reward Accounting Layer** throughout (authority: RFC-010).
- **Duplicated principles removed** and replaced with Constitution references (Art. IX.2).
- **Hierarchy diagram aligned** to Constitution Art. IX.1.
- **Constitutional compliance gate** added to decision gates (Art. VII).
- Status detail updated (H1 boundary, EPP conservation work).

---

# Purpose

This document defines **what Bloodstone is building next** and in what order.

It contains implementation sequencing, priorities, milestones, dependencies, research tracks, and operational status.

It contains **no** protocol philosophy, architectural principles, governance, or prohibitions. Those exist exclusively in the Bloodstone Protocol Constitution and are referenced here, never restated.

If this roadmap conflicts with the Constitution, **the Constitution prevails** (Const. Art. IX.3 — subordination applies whether or not it is declared).

---

# Document Hierarchy

Per Constitution Article IX.1:

```
Bloodstone Protocol Constitution   — what Bloodstone is
              │
              ▼
Bloodstone Development Roadmap     — what Bloodstone is building next  ← this document
              │
              ▼
RFCs                               — how a mechanism works
              │
              ▼
Build Specifications               — how engineers implement it
              │
              ▼
Code                               — operational truth
```

Fact flows upward; authority flows downward (Const. Art. IX.5).

---

# Current Architecture

Architectural direction has converged and is **frozen for current implementation work**. "Frozen" means do not reopen without new evidence; it is not a constitutional status (Const. Art. IX.4).

Remaining work is implementation, measurement, validation, and research — not further architectural redesign.

```
Mining
    │
    ▼
Existing Multi-Algorithm Pool
    │
    ├───────────────────────────────┐
    ▼                               ▼
Current Production            WRP (observability)
                                    │
                                    ▼
                        Future Chain Anchoring
                                    │
                                    ▼
                   DWV (Deterministic Work View)
                                    │
                                    ▼
              RAL (Reward Accounting Layer)
                                    │
                                    ▼
              Future Settlement Covenants
              (separate covenant family — Const. A.1)
```

---

# Architectural Status

| Component | Status |
|---|---|
| Multi-algorithm mining | Production |
| H1 consensus transition | **Active** — boundary crossing pending |
| Treasury Vault | Architecture frozen; build pending |
| EPP Phase 1 | Implemented (pool layer, flag OFF); conservation polish pending |
| WRP | Prototype specification complete (RFC-011) |
| DWV | Architecture frozen (RFC-010) |
| RAL | Research architecture frozen |
| Settlement Covenants | Future research |
| Class B (attested rewards) | Deferred |

---

# Implementation Streams

## Track A — Core Chain

**Purpose:** maintain and evolve the blockchain itself.

Includes consensus, networking, wallets, mining, releases, upstream merges, security.

**Priority:** highest (Const. Art. IV.3).

---

## Track B — Vault & Settlement

**Purpose:** trust-minimized movement of value.

**Current work:** Treasury Vault implementation, covenant verification, falsification, testing.

**Future work:** settlement mechanisms consuming RAL outputs are introduced as **separate covenant types**, each with its own RFC, threat model, and adversarial review. They do not extend the Treasury Vault (Const. A.1).

---

## Track C — Deterministic Work Infrastructure

**Purpose:** make mining work observable before making it consensus-verifiable.

**Stages:**
1. Work Relay Protocol (WRP)
2. Chain anchoring
3. Deterministic Work View (DWV)
4. Reward Accounting Layer (RAL)
5. Future consensus verification

This entire stream is measurement-driven (Const. Art. V.4).

---

## Track D — Future Attestation Systems

**Purpose:** research Class B contribution systems — EPP, storage, compute, AI inference, other observable services.

Class B trust handling is governed by Constitution Art. II.1–II.3; no Class B mechanism proceeds toward consensus until its trust assumptions are documented and reviewed.

---

# Current Priority Queue

## Priority 1 — H1 Mainnet Transition
**Status:** Active
**Objective:** safely complete the H1 consensus boundary crossing.
**Gate detail:** activation at the scheduled height; node coverage confirmed across template sources and exchange; boundary watch staffed at crossing; post-activation stability check.
**Success:** stable production chain, no partition, exchange continuity.

## Priority 2 — Treasury Vault
**Status:** Implementation pending
**Objective:** deliver the frozen treasury covenant exactly as specified. No scope expansion. No generalized settlement (Const. A.1).

## Priority 3 — WRP Phase 1
**Status:** Ready after H1 + Vault
**Objective:** observability only.
**Measure:** batching, bandwidth, relay behaviour, storage, Merkle construction, interoperability.
**Explicitly excluded:** consensus, payouts, canonical ordering, DWV reconstruction, anchor selection.

## Priority 4 — Phase 1 Measurements
**Objective:** produce operational evidence.
**Expected outputs:** optimal batching, storage costs, relay behaviour, bandwidth and latency profiles, implementation interoperability.
These become inputs to later protocol decisions.

## Priority 5 — Anchor Selection
Begins only after Phase 1 metrics exist.
**Candidates:** coinbase commitment, commitment transaction, dedicated output, future covenant mechanism.
**Objective:** the smallest viable anchoring mechanism consistent with Const. Art. I.1.

## Priority 6 — Deterministic Work View
Once anchoring exists: deterministic reconstruction, canonical ordering, equivocation handling, window determinism. DWV is derived (Const. Art. I.2).

## Priority 7 — Reward Accounting Layer
Deterministic accounting from the reconstructed work view. Accounting and settlement remain separate concerns (Const. Art. III.1).

## Priority 8 — Future Settlement Covenants
If RAL requires trust-minimized settlement, introduce dedicated covenant types — each with its own RFC, adversarial review, threat model, and implementation (Const. A.1).

## Priority 9 — Class B Research
Research only: EPP, observer systems, attested services, future decentralized infrastructure. Trust inheritance governed by Const. Art. II.2.

---

# Research Backlog

Open research topics:

- chain anchoring mechanism
- commitment encoding
- batching optimisation
- relay efficiency
- privacy of payout identities in relayed commitments
- deterministic work windows
- fraud proofs
- equivocation handling
- multi-algorithm weighting (including validation of the cross-algo redistribution figure — Const. Art. III.6)
- EPP dishonest-but-valid detection (Class B gate)
- EPP service-reward calibration
- future settlement covenant design

Research does not imply implementation approval (Const. Art. V.1).

---

# Outstanding Implementation Items

Small items carried against completed work:

| Item | Component | Notes |
|---|---|---|
| Conservation polish v1.2 | EPP Phase 1 | Roll-forward ledger, verifier earmarking, conservation invariant — resume after H1 |
| Sub-unit remainder handling | EPP Phase 1 | Carry remainders in roll-forward ledger; assert exact conservation, not epsilon-tolerant |
| §10 criterion sequencing | RFC-011 | "Identical work window reconstruction" is a Phase 2 criterion (requires an anchor), not Phase 1 |
| Payout-identity privacy | RFC-011 | Named in backlog; design constraint before broad relay |

---

# Milestone Progress

| Milestone | Status |
|---|---|
| Protocol Constitution v1.1 | Complete |
| Architecture convergence | Complete |
| Treasury Vault RFC | Complete |
| EPP architecture | Complete |
| RFC-010 DWV | Complete |
| RFC-011 WRP | Complete |
| RAL architecture | Complete |
| H1 transition | **Active** |
| Treasury Vault build | Pending |
| WRP prototype | Pending |
| Operational measurements | Pending |
| Anchor selection | Pending |
| DWV reconstruction | Future |
| RAL implementation | Future |
| Settlement covenants | Future |
| Class B systems | Research |

---

# Decision Gates

No stage advances on architectural enthusiasm alone.

| Stage | Evidence required |
|---|---|
| **Every RFC** | Constitution Art. VII compliance test answered in full |
| H1 complete | Stable production network post-boundary |
| Vault | Independent review, falsification, and testing |
| WRP | Operational measurements published |
| Anchor | Measurement-driven selection |
| DWV | Deterministic reconstruction demonstrated |
| RAL | Deterministic accounting verified |
| Settlement | Separate covenant RFC approved and falsified |
| Class B | Dedicated trust model and adversarial review completed |

---

# Near-Term Sequence

```
H1 boundary crossing
        ↓
H1 stability confirmed
        ↓
Treasury Vault build
        ↓
EPP conservation polish (resume)
        ↓
WRP Phase 1 prototype
        ↓
Measurements → anchor selection
```

Nothing in Tracks C or D competes with Track A or the Vault build for builder capacity.

---

*Bloodstone Development Roadmap v2.1 — a living implementation roadmap governed by the Bloodstone Protocol Constitution (current v1.2).*


# Track E — Fork Lab (Launchpad / Application Layer)

**Capacity rule:** Track E does **not** compete with H1 or Treasury Vault for core-chain builders (Art. IV.3).

| Item | Status |
|------|--------|
| Build Spec / RFQ v1.5 | **Frozen** · [downloads](https://bloodstone.rocks/downloads/Bloodstone-Fork-Lab-Burn-to-Launch-RFQ-v1.5.md) |
| WP0 keyless burn + verifier | **Shipped** · skeptic instructions · [WP0](https://bloodstone.rocks/downloads/Bloodstone-Fork-Lab-Burn-WP0.md) |
| WP1 burn-triggered pipeline | **Shipped** · fee freeze · 48h open-min · watcher timer · manual reconcile · provision artifacts · [status](https://bloodstone.rocks/downloads/Fork-Lab-WP1-Status.md) |
| WP1.5 fee decay curve | **Shipped** (enabled; inert until first STEP_BLOCKS boundary) · [fee-curve API](https://bloodstone.rocks/api/fork-lab/fee-curve) |
| WP2 catalog + MFQ two-speed | **Shipped** · runtime catalog + pack publisher + installer train · MFQ 0.2.34 remote catalog · [status](https://bloodstone.rocks/downloads/Fork-Lab-WP2-Status.md) |
| WP3 registry repo bot | **Next** (auto-push coins/ when volume justifies) |
| Platform salvage | **Removed** (FL-4 = lifecycle hygiene only) |
| Goblin Magic | **LRGK canary only** (not platform) |
| RFC series FL-1…FL-5 | **Filed** · [index](https://bloodstone.rocks/downloads/rfcs/fork-lab/INDEX.md) |
| Art. X neutrality | **In Constitution v1.3** |
| PQ Cover RFC | **Deferred** (no RFQ mechanism section) |
| Ward Mesh rename | **In progress** (user-facing; URLs `/azure-spells/` kept) |
| WP0 independent skeptic run | **Open** (external machine only — not operator VPS) |

**Source of truth for mechanisms:** RFCs + RFQ. This roadmap only sequences work.

**Track E next (no audit required):** WP3 — automated `coins/<TICKER>/` push to bloodstone-fork-registry + Chain-Mesh mirror when launch volume justifies (manual provision OK until then).

---
