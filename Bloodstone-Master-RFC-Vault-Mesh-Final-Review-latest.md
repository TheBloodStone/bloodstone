# Bloodstone Master RFC — Final Enhanced Review (Vault + Mesh + Quantum Context)

**Document version:** 1.0  
**Date:** 2026-07-19  
**Status:** Review / direction confirmation — **not a build prompt**, **not consensus-activated**  
**Scope:** Master RFC review chain (including cascade critique of the vault nonce), mesh signing-key / PQ strategy, and answers to Claude’s six questions, informed by the ongoing Bloodstone quantum-hardening conversation.

**Note on sources:** The Discord message  
`https://discord.com/channels/@me/1494290396115636297/1528351530766307460`  
and any zip attached there could **not** be opened from the review environment (DM/attachment auth-gated). This document is based on the Master RFC text provided in chat, the mesh signing-key strategy text, the quantum ladder conversation, and Bloodstone consensus/docs on the ops host.

---

# Final enhanced review (red-team + adopt/reject)

## What I agree with (carry forward)

### A. Mesh: identity ≠ value (from the first strategy block)

This is the right **near-term** “quantum-hardened” story that does **not** require a coin soft-fork:

| Principle | Verdict |
|-----------|---------|
| Signing key holds **zero balance**; rewards go to a **separate vault** | **Adopt.** Attacker who breaks the mesh signing key gets **impersonation**, not **theft**. |
| **ML-DSA (or other NIST PQ) on mesh proofs only** | **Adopt as headline-true today.** Mesh is app-layer; main-chain hybrid remains multi-release consensus work. |
| **Rotate mesh signing keys** often; bond/stake lives in vault domain | **Adopt.** Cheap rotation shrinks impersonation window. |
| **DA fraud / Sybil / collusion > quantum** for mesh near-term | **Adopt and state plainly.** Rank: retrievability + economic challenges first; PQ on mesh second. |
| Threat-model rows: (a) mesh exposed signing keys, (b) DA fraud as higher probability | **Adopt.** Fits Quantum Readiness Tier 0–1 + QUASAR orthogonality from this conversation. |

That does **not** make the **coin** quantum-proof. It correctly places a true PQ claim on **storage proofs**, not STONE UTXOs.

**Principle restated:** the key that is forced to be public should never be the key that holds money.

- **Split identity from value.** The proof-signing key does one job — sign storage challenges — and carries zero balance. Rewards it earns are paid out to a separate reward vault (a hash-protected cold address, ideally a vault type under the RFC). An attacker who fully breaks the signing key — classically today or with a quantum computer later — gets nothing to steal. The worst they can do is impersonate the node (reputation / rewards-routing), not theft.
- **Adopt post-quantum signatures at the mesh layer right now — for free (relative to consensus).** Caution about ML-DSA on the main chain is correct: consensus, witness bloat, hard to change. Mesh storage proofs are application-layer, not consensus-layer — not Bitcoin transactions; a protocol the team controls. You can sign mesh proofs with ML-DSA today: no soft-fork, no block-weight concern, no migration window. The mesh is where PQ crypto is cheap. If you want a “quantum-hardened” headline that is true **today**, it lives here — not the coin, the storage proofs.
- **Rotate signing keys cheaply and often.** Because the signing key holds no value, rotating costs little more than re-registration. Frequent rotation shrinks the window in which any single exposed key is useful for impersonation. Pair rotation with the node’s stake/bond so impersonation also requires owning economic stake — which lives in the reward vault, not the signing key.

**Non-quantum mesh risks (QUASAR’s department) are bigger near-term.** Quantum is not the mesh’s first problem. Real trustless-storage attacks include:

- Nodes claiming to store data they’ve discarded (needs proof-of-retrievability challenges, not only proof-of-storage-once),
- Sybil nodes faking capacity,
- Colluding nodes covering for each other.

Those are economic/consensus problems — what QUASAR, staking, and challenge frequency address. Quantum key exposure is a real hole to close with the separation above, but ranked by likelihood × impact over the next few years, **data-availability fraud sits above quantum**. Worth stating plainly in the threat doc so investment does not over-weight the exotic risk while the mundane one is unguarded.

**Two additions to the threat model:**

1. A **Chain-Mesh** row: signing keys are permanently exposed → mitigate by holding **zero value** on them, **PQ-signing at the mesh layer**, and **rotation**.
2. An honest note that **mesh data-availability fraud** is the higher-probability threat and is **QUASAR / economic-layer** work.

### B. Master RFC process: HY3’s three catches

HY3 earned a final-reviewer seat. Catching Grok’s timelock math error (72 blocks misread as multi-day under wrong block-time assumptions), rejecting the consensus-enforced byte cap as self-contradictory, and downgrading the “cold destination derivation rule” from cryptographic guarantee to wallet UX convention — those are real red-team findings. The third especially: Qwen through Gemini had talked each other into believing a wallet-side derivation rule “cryptographically neutralizes” hot-device malware, which it doesn’t, since a rootkit spoofs whatever the display shows. HY3 was right on all three; all three corrections are adopted **in direction** (with Bloodstone-specific block-time correction under Q1).

| Catch | Verdict |
|-------|---------|
| Grok’s 72-block “3 days” using wrong block time | **Correct direction** — but HY3’s own **10 min/block** is also wrong for Bloodstone (see Q1). |
| Consensus byte cap self-contradictory | **Adopt HY3** — no consensus byte cap. |
| Cold destination derivation is **UX**, not crypto vs rootkit | **Adopt HY3** — second-device / out-of-band verification remains primary. |

### C. Nonce cascade (the big call)

**The vault nonce should be removed entirely.** The UTXO analysis is right:

- Proposal **spends** the vault UTXO → that UTXO is gone → **no replay** against it.
- Clawback moves value into **recovery-controlled** domain → compromised operational key cannot re-propose a loop.
- Worst case is **one-shot forced evacuation**, not perpetual paralysis.
- “Nonce in UTXO + mutate state” is **account-model** language; on UTXO chains it’s either meaningless (fresh UTXO nonce 0) or a **new consensus state machine** you don’t want.
- Ongoing deposit grief is fixed by **retiring the published address**, not a per-UTXO nonce.

**How the cascade happened:** ChatGPT proposed “sequence numbers” against replay-griefing; Qwen formalized a nonce; Grok, DeepSeek, Gemini, and HY3 each adopted it with escalating confidence (“mandatory,” “closes the dominant operational attack”) because prior reviews felt like verification. They were not.

**Worse, the nonce as specified is incoherent for this architecture.** “Stored in the UTXO, increments on every action” is account-model thinking — UTXOs are immutable; you spend them and create new ones. Since each fresh vault UTXO would carry nonce 0, the check “proposal must supply nonce+1” is always trivially satisfiable — it adds literally zero security while adding novel consensus-tracked state and a permanent migration liability (the same class of problem as the rejected byte cap). Pseudocode that “mutates UTXO state to STAGED… Increment Vault UTXO.vault_nonce” confirms reviewers were reasoning about an account chain, not Bloodstone’s UTXO model.

**The residual grief** — new deposits keep arriving at the compromised vault address, each attackable as it lands — is untouched by a per-UTXO nonce. Mitigation is procedural: on detected compromise, retire the published vault address and migrate to a fresh policy.

**Verdict: remove the nonce entirely.** This is the natural “question 8: what would you remove” answer.

**Explicit answer to “overrule 6-0”:** **Yes — remove the nonce.** Consensus of reviewers is not verification.

### D. Other Master RFC corrections

| Issue | Verdict |
|-------|---------|
| Witness versions `0x50–0x53` | **Reject confabulation.** In Bitcoin-family segwit, witness versions occupy OP_0 through OP_16 — the space is 0 to 16. “0x50” (decimal 80) does not exist in that encoding. Use real segwit version space **OP_2…OP_16** (e.g. reserve **2–5** for PQ/vault experiments), not invented hex identifiers. |
| “Consensus validates only the hash” | **Dangerous incomplete.** The policy-hash design is good (P2WSH pattern), but at spend time the blob must be revealed and consensus must fully parse and enforce its fields: timelock, M-of-N, whitelist, recovery destination. If a coding agent takes “hash-only validation” literally, it builds a vault that enforces nothing. Related: wallets cannot add blob fields “without forks” under strict parsing — any schema change changes both hash and parse, which is why the version byte exists. Correct framing: **consensus owns the schema; wallets merely construct it; unknown versions are invalid.** |
| Recovery vault unspecified | **Must** be **recovery-seed domain only**. Nested vault with operational key in path = clawback fails. |
| Partial unvault change | **Lean change-to-same-`policy_hash`** (consensus-checkable). All-or-nothing is acceptable product choice if simpler. |
| Drop `TREASURY_MODE` | **Adopt.** Non-empty `allowed_destinations` enforces whitelist; empty = open. Retail/treasury = wallet UX. |
| Staged output type (destination + proposal height), no “mutate UTXO state” | **Adopt** for any build prompt. |
| Clawback fees from staged amount | **Adopt** so guardians don’t need the compromised hot wallet for fees. |

### E. What survives into the final spec (endorsed list)

From the review chain, carry forward:

- The policy-hash commitment (with the parse-time clarification),
- Hybrid whitelisting resolved by simplification (list empty/non-empty; no `TREASURY_MODE` flag),
- Two-seed default with optional institutional third seed (deferred — see Q6),
- Second-device verification as the primary migration/destination mitigation (cold-derivation demoted to UX convention per HY3),
- Days-scale timelock (**pending / keyed to real Bloodstone block time** — see Q1),
- No byte cap,
- Multiple reserved PQ witness versions (**corrected to real version numbers 2–5**, not 0x50–0x53),
- All the “never do” exclusions,
- Full companion-work list — Chain-Mesh threat model with pinned audited ML-DSA library, wallet reference implementation, fuzzing/formal verification of both spend paths,

Plus additions:

- **Nonce removal**,
- **Recovery-vault domain specification**,
- **Change-handling rule**,
- **Clawback fee handling** (guardian clawback may deduct fees from the staged amount),
- **Explicit staged-output mechanics** (proposal tx creates a distinct staged output type committing to destination + proposal height — **no “state mutation” language** near the coding agent).

---

## What still needs tightening before a build prompt

1. **Timelock numbers must be recomputed for Bloodstone (~90 s mean), not 10-minute Bitcoin.**
2. **Mesh ML-DSA** is a **separate workstream** from **vault soft-fork** — don’t merge them into one “quantum vault” consensus PR.
3. **“Signing-only key” elegance** is mesh/treasury-ops; **vault unvault keys** are different keys with different threat models — keep diagrams separate so agents don’t put stake on the mesh signing key “by analogy.”
4. Discord zip was not reviewed here — if the zip reintroduces nonce / 0x50 / account-model pseudocode, **strip those before build**.

---

# Answers to the six questions

### 1) Bloodstone block time (per algo and effective average)?

From **consensus rules** (`MainNetConsensus::GetTargetSpacing` under **MULTI_ALGO** — current triple-algo regime):

| Algo | Target spacing (per algo) |
|------|---------------------------|
| SHA256d | **270 s** |
| NeoScrypt | **270 s** |
| Yespower | **270 s** |

Design intent in-code: **~90 s average** wall-clock between *any* block (three interleaved algo slots: 270/3).

Operator-facing design doc (halving schedule) also states mean block time **~80 s** — same order of magnitude; use **~80–90 s** for product/timelock math, **not** 10 minutes.

**Implications for windows (use 90 s mean unless you measure a different window):**

| Blocks | ≈ duration @ 90 s |
|--------|-------------------|
| 72 | **~1.8 hours** (not 12 h @ 10 min, not 3 days) |
| 480 | **~12 hours** |
| 1008 | **~25 hours (~1.05 days)** — not “7 days” |
| 2880 | **~3 days** |
| 6720 | **~7 days** |

**Spec rule:** define all vault delays as **`N = ceil(desired_seconds / mean_block_seconds)`** with `mean_block_seconds = 90` (or document measured EMA later). Never hardcode Bitcoin’s 10-minute calendar.

---

### 2) Sign off on removing the vault nonce?

**Yes. Remove it entirely.**

Consciously joining the overruling of the 6-0 cascade. UTXO spend + recovery-domain clawback already bounds the attack; the nonce adds consensus complexity and **zero** security on this architecture.

---

### 3) Recovery vault form?

**Plain hash-protected address in the recovery-seed domain** (the Master RFC lean).

- Nested vault only if **all** unvault/recovery keys for that nest are **also** recovery-seed only — extra complexity with little gain for v1.
- After incident: funds sit on simple recovery address → deliberate re-vault under **new policy** when ready.

---

### 4) Partial unvaults?

**Change-back-to-same-`policy_hash`** (the Master RFC lean).

Consensus: change output must commit to the **identical policy commitment** as the vault being spent.  
Alternative all-or-nothing is OK as a **wallet policy** for simplicity, but consensus should allow same-policy change so partial withdrawals don’t force full evacuation.

---

### 5) Build target / structure?

| Item | Answer |
|------|--------|
| Codebase | Bloodstone is a **Bitcoin-family / Namecoin–Xaya lineage** node (ops tree: `bloodstone-chain` / `bloodstone-core` packaging as bloodstoned). Treat as **Core-like UTXO + multi-algo PoW**, not a greenfield account chain. |
| Segwit / bech32 | **Yes** — standard-style **legacy `S…` + bech32 `stone1…`**; web wallet already prefers **bech32** for hygiene. New output types should use **real witness versions (2+)**, not invented 0x50 tags. |
| Build prompt shape | **Phased work orders**, not one monolith: (0) threat model + non-goals, (1) consensus primitive + regtest vectors, (2) RPC/wallet construct & sign, (3) UX / second-device / recovery flows, (4) mesh signing-key separation + PQ mesh proofs **as a parallel track**. Suits Grok/aider and prevents nonce-style confabulation cascades. |

---

### 6) Seed count at launch?

**Two-seed only for genesis wallet; institutional third-seed deferred.**  
Pure wallet/UX; no consensus dependency. Defer is correct.

---

# Direction confirmation (for the build prompt)

**Confirmed direction:**

1. **No vault nonce.**
2. **Policy-hash vault** with full parse/enforce at spend; empty whitelist = open destinations.
3. **Staged unvault output** + guardian clawback to **recovery-seed plain address**; fees from staged value.
4. **Same-policy change** for partial unvaults.
5. **Timelocks in Bloodstone block-time** (~90 s mean → days = thousands of blocks, not Bitcoin 1008-as-week).
6. **Witness versions 2–5 reserved** for future PQ/vault experiments — not 0x50.
7. **Mesh PQ + zero-balance signing keys** = separate, shippable-now product story; **not** a substitute for main-chain hybrid PQ.
8. **Threat doc honesty:** mesh DA fraud > quantum for mesh; coin still “quantum-aware, not quantum-proof.”
9. **Phased build orders** against Bloodstone’s Core-like tree + standard bech32/segwit assumptions.

---

# Short answers (paste-back)

1. **~270 s per algo; ~80–90 s average any-block.** Timelocks must use that, not 10 min.  
2. **Yes — delete the nonce.**  
3. **Plain recovery-seed address (lean).**  
4. **Change to same policy_hash (lean).**  
5. **Bitcoin-family Bloodstone node, standard segwit/bech32; phased work orders.**  
6. **Two-seed at launch; third-seed later.**

---

# On the Discord zip

The Discord link and zip could **not** be fetched or unpacked from the review environment. If the zip is placed on the ops host (or re-uploaded in chat), it should be audited against the checklist: **remove nonce / fix witness versions / no account-model state mutation language**.

---

# Bottom line

The mesh **“signing-only PQ key + value elsewhere”** design is elegant and **true today**. The vault RFC survives only after **killing the nonce cascade**, fixing **witness versions** and **timelock math to ~90 s blocks**, and specifying **recovery domain + staged UTXO mechanics** in pure UTXO language.

**Related reading on downloads:**

- [Bloodstone Quantum Readiness](Bloodstone-Quantum-Readiness.md)  
- [Bloodstone Quantum Readiness FAQ](Bloodstone-Quantum-Readiness-FAQ.md)  
- [Bloodstone Hot Wallet Quantum Ops](Bloodstone-Hot-Wallet-Quantum-Ops.md)  
- [Bloodstone Hybrid PQ Phase D In-Node](Bloodstone-Hybrid-PQ-Phase-D-InNode.md)  
- QUASAR / coordinator multisig docs (orthogonal economic security)

---

*Bloodstone · Master RFC Vault + Mesh Final Review v1.0 · 2026-07-19*
