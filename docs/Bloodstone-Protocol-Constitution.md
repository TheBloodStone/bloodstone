# The Bloodstone Protocol Constitution

**Version:** 1.3
**Status:** Governing document — the highest authority in the Bloodstone documentation hierarchy
**Date:** July 2026
**Supersedes:** v1.2
**Changes in v1.3:** Article X (Platform Neutrality) added — ratifies the Fork Lab neutrality principle as a foundational governance rule; platform capabilities are universal and neutrally named, coin capabilities belong to their coin, and neutrality cannot be overridden by later coin-specific addition. Article VII compliance test gains a neutrality question (Q13); Article VIII.4 adds X to the foundational set. This is an amendment, not a clarification (Art. VIII.2): it adds an enforceable Article. Justification: a recurring structural need to prevent platform capture by individual coins, surfaced during Fork Lab integration.
**Changes in v1.2:** Appendix A.6 added — worked example clarifying that Article I.3 restricts *consensus*, not the protocol, from measuring the world, using EPP to show the observer/consensus layer split. Clarification only; no Article altered.
**Changes in v1.1:** Article IX added (document hierarchy and chain of authority, previously asserted from below rather than defined from above); freeze status clarified as non-constitutional; references to the subordinate execution document made explicit as the *Bloodstone Development Roadmap*; Appendix A.1 strengthened to remove ambiguity on Treasury Vault scope.

**Authority:** Every subordinate document — the Bloodstone Development Roadmap, all RFCs, all build specifications, and all implementations — is subordinate to this Constitution. Where any of them conflicts with this document, the Constitution governs and the conflicting provision is invalid until amended.

---

## Preamble

This document records the principles Bloodstone has arrived at through sustained adversarial design review, and which it intends to hold permanently. It is not a plan, a roadmap, or a status report. Those change. This does not.

Its purpose is practical, not ceremonial: **it is the test against which every future proposal is evaluated.** A proposal that violates an Article is rejected on that basis alone, without needing to relitigate the reasoning. Several of these Articles exist because a plausible, well-argued, multiply-endorsed proposal was accepted and later found to be wrong. They are scar tissue, and they are load-bearing.

---

## What this document is, and is not

| This Constitution contains | It does not contain |
|---|---|
| Principles intended to outlive every current participant | Priorities, queues, or schedules |
| Prohibitions that hold regardless of expedience | Research status or completion state |
| Tests a proposal must pass | Named technologies, versions, or parameters |
| The chain of authority and the process by which decisions become binding | Anything expected to change with measurement |

Everything excluded belongs to a subordinate document: the **Bloodstone Development Roadmap** (sequencing, priorities, status), **RFCs** (mechanism and specification), or **build specifications** (implementation detail). All may change freely without amending this Constitution.

---

# Article I — Ledger and Consensus

**I.1 — One canonical ledger.**
The blockchain is the only ledger. No protocol layer may introduce a second ledger, a secondary consensus system, a sharechain, or any other independent mechanism for establishing canonical ordering. All layers derive their authority from the existing chain.

**I.2 — Derived, not stored.**
State that can be reconstructed must be reconstructed, not stored as authority. The relationship between the chain and any derived view is the relationship between transactions and the UTXO set: the chain records commitments; participants compute the rest.

**I.3 — Consensus verifies mathematics; it never measures the world.**
Consensus may verify signatures, hashes, structure, amounts, and commitments. It may never measure latency, geography, location, bandwidth, effort, reputation, or any other physical or social property. Where such properties matter, consensus verifies *attestations about* them and never their truth.

**I.4 — No account-style consensus state.**
In a UTXO architecture, consensus must not maintain mutable per-participant balances, counters, nonces, or sequence numbers. Outputs are created and spent. Any mechanism requiring the chain to track a running per-entity value is prohibited; the equivalent function must be achieved by commitment and verification, not by stored state.

**I.5 — Frozen-small consensus.**
Every consensus feature is a permanent maintenance liability and a permanent increase in the cost of adopting upstream security fixes. Consensus additions must be minimal, fixed in scope, and non-programmable. General-purpose covenant languages, configurable policy engines, and extensible scripting surfaces are prohibited.

---

# Article II — Trust and Verification

**II.1 — Proof classes are permanent and never mix.**
Every contribution to the protocol is one of two kinds, and the distinction is structural, not descriptive:

- **Class A — Self-verifying.** The artifact proves itself. Anyone can verify it; nobody can forge it without performing the work. Invalid artifacts are rejected outright.
- **Class B — Attested.** The claim is an assertion about the world, verifiable only through signatures on an attestation. A false-but-well-formed attestation passes every syntactic check.

**II.2 — Class B never inherits Class A trust.**
Entitlements derived from attested contributions are attestation-verified, never consensus-verified, and inherit the trust assumptions of their attesters. Any mechanism that routes Class B claims through infrastructure designed for Class A — and thereby lends them unearned credibility — is a protocol bug regardless of how convenient the unification appears. Type-level separation that dissolves at the payout level is a violation of this Article.

**II.3 — Security claims are scoped honestly.**
No claim of trustlessness, determinism, or dishonesty-resistance may be stated more broadly than it holds. Where a property applies to Class A only, it is stated as applying to Class A only.

**II.4 — Compromise is assumed silent.**
No design may depend on detecting that a key has been copied or an attester has lied. Copied keys emit no signal until used, and a well-formed false attestation is indistinguishable from a true one. Designs bound blast radius; they do not claim detection.

**II.5 — Reward the verifiable behaviour, never the claimed attribute.**
Incentives attach to what can be adversarially demonstrated, not to what a participant asserts about itself. Where an attribute is desirable but unverifiable, the protocol rewards the behaviour that attribute enables, or it does not reward it at all.

---

# Article III — Economics

**III.1 — Separation of accounting and settlement.**
"Who is entitled?" and "how is entitlement discharged?" are answered by different layers. Accounting mechanisms must be replaceable without altering settlement; settlement must not encode accounting policy.

**III.2 — No punitive enforcement.**
Bloodstone does not slash, confiscate, or destroy participant capital. Failed or dishonest service loses access to service and its rewards; it does not lose principal. Security is achieved by making honest participation the higher-yielding strategy for the same committed capital — not by penalty.

**III.3 — Incentive gradients, not prohibitions.**
Where behaviour must be discouraged, the protocol makes it less profitable rather than forbidding it. A rule that a determined participant can circumvent is weaker than an economic gradient that makes circumvention pointless.

**III.4 — Value conservation.**
Every mechanism that moves or allocates value must conserve it. Input must equal allocated output plus a bounded, explicitly-capped fee. Unbounded fees, unaccounted remainders, and silent leakage are prohibited; conservation must be assertable as an invariant.

**III.5 — No inflation for features.**
New protocol capabilities are funded by redistributing existing issuance, never by expanding it. Emission schedules are not a funding mechanism for product decisions.

**III.6 — Parameters are validated before they are hardened.**
No economic parameter may be frozen into consensus, a commitment scheme, or a published standard until it has been measured against operational data. Judgment figures are provisional by definition and must be labelled as such until validated.

---

# Article IV — Scope and Participants

**IV.1 — No new actor classes.**
The ecosystem consists of miners, full nodes, and observers. New protocol duties expand the responsibilities of an existing role; they never create a new participant type. Every additional actor class brings its own Sybil surface, incentive design, and failure modes, and the cost is rarely visible at proposal time.

**IV.2 — Ordinary participation is permissionless.**
Mining, running a node, and transacting require no stake, collateral, approval, registration, or reputation. Optional service roles may require a non-custodial commitment; base participation may not.

**IV.3 — Production stability outranks architectural progress.**
A running network with users and value is the first constraint. No research direction, however sound, justifies disrupting production. Prototypes run alongside production systems, never through them.

**IV.4 — Each layer has one responsibility.**
No layer performs another layer's function. Transport does not decide validity; validity does not decide economics; economics does not decide settlement; settlement does not measure the world.

---

# Article V — Process

**V.1 — Research, then adversarial review, then freeze, then build.**
No implementation begins from a design containing open conceptual questions. A build specification may only be written against a frozen design; writing one earlier silently invents the unresolved decisions and grants them the authority of a specification.

**V.2 — Design and criticism are separate roles.**
The party that authors a design does not ratify it. Every design and every implementation passes adversarial review by a party whose task is falsification, not improvement.

**V.3 — Consensus among reviewers is not verification.**
Agreement — including unanimous agreement — is evidence of plausibility, not correctness. Where reviewers converge, the convergence itself must be checked against first principles and against the system as it actually is.

**V.4 — Ground truth outranks paper.**
Measurements from the running system outrank any conclusion reached by analysis. Where a document and the codebase disagree, the codebase is correct and the document is amended. Assumed parameters are treated as unknown until measured.

**V.5 — Falsification over endorsement.**
The productive question is "find a case where this fails," not "is this good." Reviews are commissioned against specific claims, and a review that returns no findings is a valid and useful result.

**V.6 — Scope expansion is named when it occurs.**
Expansion is not prohibited, but it is stated. A proposal that broadens the system's remit must say so plainly rather than arriving as a natural consequence of the previous document.

---

# Article VI — Standing Prohibitions

These follow from the Articles above and are restated for use as a checklist. None may be waived for convenience, urgency, or elegance.

The protocol will never:

1. Introduce a second consensus, sharechain, or independent canonical ordering mechanism.
2. Maintain account-style mutable per-entity state in consensus.
3. Adopt a general-purpose or extensible covenant scripting language.
4. Allow consensus to measure any physical or social property.
5. Treat an attested (Class B) contribution as if it were self-verifying (Class A).
6. Slash, confiscate, or destroy participant capital.
7. Require stake, collateral, or approval for ordinary participation.
8. Permit uncapped fees or unconserved value in any allocation mechanism.
9. Fund features through new issuance.
10. Create a new participant class where an existing role could absorb the duty.
11. Freeze an unvalidated parameter into consensus or a published standard.
12. Claim a security property more broadly than it demonstrably holds.
13. Begin implementation from a design with unresolved conceptual questions.
14. Disrupt production systems for research purposes.
15. Grant any coin platform-level advantage — a coin-specific payout, feature, perk, or priority — or make a platform capability non-universal.

---

# Article VII — Compliance Test for Proposals

Every RFC must answer these questions explicitly. An RFC that cannot is not ready for review.

1. **Ledger:** Does this introduce any mechanism for canonical ordering other than the existing chain? *(Art. I.1)*
2. **State:** Does consensus store anything that changes per-entity over time? *(Art. I.4)*
3. **Measurement:** Does consensus verify any claim about the physical world? *(Art. I.3)*
4. **Proof class:** Which contributions are Class A and which are Class B, and where is the boundary enforced — including at payout? *(Art. II.1, II.2)*
5. **Scope of claims:** Which stated security properties hold only for Class A? *(Art. II.3)*
6. **Value:** What is the conservation invariant, and what caps the fee? *(Art. III.4)*
7. **Funding:** Is any new issuance required? *(Art. III.5)*
8. **Parameters:** Which values are judgment figures not yet validated against data? *(Art. III.6)*
9. **Actors:** Does this require a participant type that does not already exist? *(Art. IV.1)*
10. **Production:** What is the impact on the running network if this fails? *(Art. IV.3)*
11. **Maturity:** Which questions remain conceptually open, and does the document claim readiness to build? *(Art. V.1)*
12. **Falsification:** What specific claim should reviewers attempt to break? *(Art. V.5)*
13. **Neutrality:** Does this grant any coin-specific payout, feature, perk, or priority, or otherwise make a platform capability non-universal? *(Art. X)*

---

# Article VIII — Amendment

**VIII.1** This Constitution is amended only by explicit, versioned revision, never by implication, precedent, or the accumulated momentum of subordinate documents.

**VIII.2** An amendment must state which Article changes, what replaces it, and what evidence justifies the change. Convenience, schedule pressure, and architectural elegance are not evidence.

**VIII.3** A proposal that requires an Article to be amended must say so in its own text. Silent conflict is a defect in the proposal, not a permission.

**VIII.4** Articles I.1, I.3, II.1, II.2, III.2, IV.2, and X are considered foundational. Amending them changes what Bloodstone is, not merely how it works, and should be treated accordingly.

---

# Article IX — Documentation Hierarchy and Chain of Authority

**IX.1 — The hierarchy.**
Authority flows downward and is defined here, not asserted from below:

```
Bloodstone Protocol Constitution   — what Bloodstone is
              │
              ▼
Bloodstone Development Roadmap     — what Bloodstone is building next
              │
              ▼
RFCs                               — how a mechanism works
              │
              ▼
Build Specifications               — how engineers implement it
              │
              ▼
Code                               — operational truth (Art. V.4)
```

**IX.2 — Single source per concern.**
Each concern is authoritative in exactly one document. Principles, prohibitions, and governance exist only in this Constitution. Sequencing, priorities, and status exist only in the Bloodstone Development Roadmap. Mechanism exists only in RFCs. A subordinate document restating a principle rather than referencing it is a defect, because duplicated text drifts and the drifted copy is the one people read.

**IX.3 — Subordination is not optional or self-declared.**
A subordinate document is bound by this Constitution whether or not it says so. Omitting a subordination clause does not create independence.

**IX.4 — "Frozen" is not a constitutional status.**
Architecture freezes, specification freezes, and scope freezes are properties of RFCs and the Roadmap. They mean "do not reopen without new evidence" — not "unamendable." Only Articles of this Constitution require formal amendment (Art. VIII). Freeze language must never accumulate constitutional weight through repetition.

**IX.5 — Code outranks documents on fact; the Constitution outranks code on intent.**
Where a document describes the system incorrectly, the code is correct and the document is amended (Art. V.4). Where the code violates an Article, the code is wrong and must be changed. Fact flows upward; authority flows downward.

---

# Article X — Platform Neutrality

**X.1 — Platform capabilities are universal and neutrally named.**
Any capability the platform provides is available to every fork on equal terms and is named neutrally, without reference to any particular coin. Platform-provided capabilities belong to the platform and appear on the platform's surface.

**X.2 — Coin capabilities belong to their coin.**
Any capability specific to a single coin belongs to that coin, lives on that coin's own surface, and is not presented as a platform capability. The boundary between "platform" and "coin" is the boundary between "available to all equally" and "belonging to one."

**X.3 — The platform never favours specific coins.**
The platform grants no coin-specific payout, feature, perk, priority, or preferential treatment of any kind. Neutrality is a property of the platform itself, not a default that individual decisions may depart from.

**X.4 — Neutrality cannot be overridden by later addition.**
This Article cannot be circumvented by introducing a coin-specific payout, feature, or perk at a later date, nor by any accumulation of individually-small exceptions. A proposal that would give one coin platform-level advantage is invalid under this Article regardless of how it is framed or when it is introduced.

**X.5 — Scope.**
This Article governs the relationship between the platform and the forks it serves. It is foundational (Art. VIII.4): amending it changes what the platform is. It already governs the following settled decisions, which are hereby rule-backed rather than conventional: platform defense capabilities are neutral platform mesh services, not coin-branded; post-quantum cover provisions are platform-neutral; and coin-specific lifecycle mechanisms (including salvage) run only on their own coin's off-platform surface, never as a platform feature.

---

# Appendix A — Standing Clarifications

Recorded to prevent recurring misreadings. These are interpretations of the Articles, not additions to them.

**A.1 — On the Treasury Vault and settlement.**
The Treasury Vault is a frozen, minimal covenant with a fixed and narrowly defined purpose. Future trust-minimized settlement mechanisms are expected to be introduced as **separate covenant types**, each with its own specification, threat model, and adversarial review. **Under no circumstance may the Treasury Vault evolve into a general-purpose settlement engine** — doing so would reconstruct precisely the extensible covenant surface prohibited by Article I.5, and would destroy the minimality that is the Vault's principal security property.

**A.2 — On "trustless."**
Only Class A contributions are trustless. Any pipeline carrying both classes is trustless only for its Class A inputs, and must be described that way.

**A.3 — On observers.**
Where new attestation duties arise, they are assigned to observers rather than to a new role (Art. IV.1). This does not resolve the detection problem inherent to Class B; it locates it.

**A.4 — On genesis-stage decisions.**
Choices that are free before a network carries value become expensive afterwards. The absence of migration cost is a temporary condition, and its expiry should be treated as a deadline for decisions that depend on it.

**A.5 — On naming.**
Where a mechanism is named in subordinate documents, the name is fixed by its RFC and used consistently everywhere. Divergent names for one mechanism across documents are a defect under Article IX.2, because they make conflict and duplication invisible.

**A.6 — On measurement layers (worked example: EPP).**
Article I.3 prohibits *consensus* from measuring the world. It does not prohibit the protocol from using measurements. The distinction is which layer performs the measurement:

| Layer | Does it measure? | What it handles |
|---|---|---|
| Observer | **Yes** — issues challenges, times responses, signs an attestation | The physical measurement |
| Consensus | **No** | Signature validity, quorum satisfaction, freshness, proof structure |

Edge Presence Proof is the worked example. Observers measure latency; consensus would verify only the *attestation about* that measurement, never re-run the timing. A validating node cannot reproduce a round-trip time recorded months earlier — which is precisely why Article I.3 is written as it is.

Three consequences follow, and they are the reason the Article is load-bearing rather than restrictive:

1. **The observer layer exists because of Article I.3.** If consensus could measure latency, no observer apparatus would be needed — participants would prove edge presence directly and consensus would check it. Every element of that machinery is a consequence of this Article, not an exception to it.
2. **Any mechanism relying on measurement is necessarily Class B** (Art. II.1), and its entitlements are attestation-verified only (Art. II.2). A measured property can never become consensus-verified by routing it through additional layers.
3. **The unsolved detection problem is structural, not incidental.** A well-formed attestation containing a false measurement passes every check consensus can perform. This follows directly from Article I.3 and cannot be engineered away at a higher layer; it can only be bounded economically (Art. II.4, III.3).

A proposal claiming consensus verification of a measured property has either mis-stated its claim (Art. II.3) or violated Article I.3.

---

*The Bloodstone Protocol Constitution v1.3 — one ledger, derived state, consensus verifies mathematics, attested never becomes self-verifying, no punishment, no new actors, a neutral platform, falsify before building.*
