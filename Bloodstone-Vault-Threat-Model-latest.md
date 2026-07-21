# Bloodstone Native Vault — Threat Model & Non-Goals

**Document version:** 1.2  
**Date:** 2026-07-20  
**Status:** Phase 0 landing (docs only) · authoritative product rules in **Bloodstone Vault Build Spec v1.2** (v1.1 vault covenant body remains frozen; v1.2 adds §15 hygiene / Phase H)  
**Chain:** Bloodstone mainnet lineage (`bloodstone-chain` / `bloodstoned`)  
**Messaging:** quantum-**aware**, migration-**ready** — **not** “quantum-proof”

This document lands Build Spec **§10** (threat model), **§13** (never-do), and **§14** (falsification adjudication) from the frozen vault body, plus **§15.1** Phase H cross-reference (v1.2), and residual notes required by Work Order Phase 0. Where this doc and the frozen vault covenant conflict, **the frozen covenant wins**.

---

## 1. Design goal (reminder)

Funds at rest are protected by **hash-hidden public keys** and a **consensus covenant** such that no key compromise — classical or quantum — can silently or instantly drain the treasury. Every exit is **slow**, **loud**, **destination-committed**, **cancellable**, and **value-conserving** (v1.1: no exit may leak value to fees beyond a de-minimis cap).

Timelock arithmetic uses Bloodstone’s **~90 s mean any-block time** (multi-algo): consensus floor **960** blocks (~24 h), wallet-recommended minimum **2880** (~3 d), wallet default **6720** (~7 d). Never use 10-minute-block arithmetic.

**§15.1 / Phase H dependency (value-bearing vault gate — Build Spec v1.2):**  
Per-algo DGW timewarp would let an attacker **compress block cadence** on a dominated lane and shrink every **block-denominated** clawback / delay window in wall-clock time. Spec **v1.2 §15.1** therefore requires the timewarp fix **before** bit-5 value-bearing vaults.

| Gate item | Status | Evidence |
|-----------|--------|----------|
| H1 window-span header reject + `MAX_FUTURE_BLOCK_TIME=1800` | **Signed off 2026-07-20** (code + tests) | Branch `phase-h1-h3-timewarp-window`; locks `{TIMEWARP_MIN_WINDOW=2160, MAX_FUTURE=1800}` |
| H3 unit suites green (single binary) | **Signed off** | `timewarp_tests` + `dualalgo_tests` — see `Phase-H1-H3-Sign-Off.md` |
| H1 **merged + active on network** | **Pending (flag-day)** | Path locked: **coordinated flag-day** (not relaunch). **Hold merge/deploy** until **Cexius** inputs (notice, contact, upgrade ACK) + activation height *H*. Gate **not discharged** until rules are live on peers including exchange nodes. |
| Vault covenant (v3/v4, U1–U4) | **Still frozen** | Separate PR; this row does **not** implement vault code |
| H4/H5 (64-byte-tx ban, validation bound) | Open, **non-blocking** for vault | Genesis hygiene before mainnet |

**Recording for the vault final-gate checklist:**  
- **Now:** H1/H3 is **signed off** (logic + green suites).  
- **§15.1 flips to discharged only after** merge **and** nodes actually run the new header rules (no mixed 7200s / no-window peers).  
Timelock floor **960 blocks ≈ 24 h** then retains wall-clock meaning because same-algo endpoint cadence can no longer be packed to ~1 s steps under consensus.

---

## 2. Threat model summary (spec §10)

| Threat | Status | Notes |
|--------|--------|--------|
| **Shor (ECDSA/Schnorr)** | Mitigated at rest | Unspent vault addresses expose only hashes (Grover-class preimage on the hash — infeasible). Per-use unvault/guardian keys; **shared-policy unvault pubkey residual** documented in §4. Timelock turns mempool-race theft into a **visible, clawable** event. |
| **Operational seed compromise** | Bounded | Hot float lost. Treasury unvault proposal is **public** → alert → guardians claw back to the **terminal recovery domain** (whitelist makes even the proposal harmless). Mandatory: monitoring + push alerting; days-scale delay so cold material is reachable. |
| **Fee-drain (v1.1)** | **Closed (U3)** | Was: route vault value to miner as unbounded fee (self-mine / pool collusion; Bloodstone’s cheap SHA256d lane makes self-mining realistic). Now: every covenant spend must enforce `sum(inputs) − sum(outputs) ≤ MAX_COVENANT_FEE`. |
| **Destination substitution (v1.1)** | **Closed (U2 + U4)** | Was: non-`SIGHASH_ALL` unvault signature + post-sign rewrite of destination/outputs. Now: covenant sigs **must** be `SIGHASH_ALL`; consensus **recomputes** staged commitment and exact output set. |
| **Multi-input value merge (v1.1)** | **Closed (U1)** | Was: two covenant inputs, one staged binding only one policy — value from the second absorbed into fee/outputs. Now: **exactly one** covenant (v3/v4) input per tx. |
| **Destination compromise** | Accepted residual | Attacker who **owns** the committed destination sweeps after legitimate arrival. Bounded by WebAuthn second-device verification, small float, post-arrival sweep. No perfect on-chain fix. |
| **Open-destination re-proposal residual (v1.1)** | Documented residual | Attacker with unvault key on an **open-destination** vault can force proposal→race cycles. Each cycle either completes to a committed destination or is clawed to recovery; value evacuates **monotonically** to the recovery-seed domain (bounded, converging — **not** unbounded livelock; see §5). Prefer **whitelisting**, monitor, migrate on detection. |
| **Silent compromise** | Universal limit | Copied keys emit no signal until used, in every cryptosystem. Architecture bounds blast radius; it does **not** detect. |
| **Consensus bug freezing funds** | Top audit priority | Vault-path bugs that brick funds are reputationally worse than theft. Clawback paths get **test coverage equal to** spend paths. Genesis near-zero-value window is the free battle-test. |
| **Upstream Core merge cost** | Process risk | Every bespoke consensus feature raises perpetual Bitcoin-Core-merge cost — standing argument for **frozen-small**. |
| **Griefing / DoS** | Bounded | Parallel staging flood and repeated proposals are operational load terminating in recovery. **No per-UTXO nonce** (see §3). |

---

## 3. Nonce cascade (why there is no vault nonce)

Reviewer pressure sometimes asks for a per-UTXO sequence number or “proposal nonce” so that parallel proposals can be ordered or invalidated.

**This design will never add a vault nonce / sequence number / per-UTXO counter** (global prohibition; frozen-small).

**Cascade if a nonce were introduced (v0.3 §0.1 analysis, retained):**

1. Nonce is **consensus state** — either encoded in the UTXO (breaks pure spend/create), or tracked off-chain (not enforceable), or stored in a new account-style index (forbidden).
2. Increment rules create **race** and **griefing** surfaces (force-increment to brick a path; reorg desync).
3. “Cancel by nonce” competes with **guardian clawback**, which already terminates value into the recovery domain without new state.
4. Once present, product pressure expands the nonce into a general mutable policy control — the opposite of immutability.

**Griefing without nonce (accepted):** worst case is one-shot forced evacuation toward the recovery domain (procedural fix: retire compromised addresses; migrate). Parallel open-destination re-proposals are **bounded** by geometric shrinkage of remaining vault value under same-policy change rules (U1 + U4).

---

## 4. Shared unvault-pubkey residual (§7)

All UTXOs at one vault address share `unvault_pubkey_hash`. The **first** unvault proposal that reveals the unvault pubkey exposes that key for **remaining** funds under the same policy.

| Vault type | Residual |
|------------|----------|
| **Whitelisted** (`dest_count > 0`) | Exposed key cannot redirect outside the list — residual is grief / monitoring noise. |
| **Open-destination** (`dest_count = 0`) | Clawback race covers theft attempts after exposure; residual is the re-proposal pattern in §2. |

**Wallet-only mitigation:** offer policy rotation after N unvaults (hygiene). **Not** a consensus counter.

---

## 5. Open-destination re-proposal residual (bounded)

Falsification claim HY3 asserted an unbounded, uncancellable loop of propose → clawback → re-propose.

**Adjudication (v1.1 §14):** the loop does **not** close as unbounded theft or livelock:

1. Guardian Path B sends funds to the **recovery-seed domain**, which the operational unvault key **cannot** re-propose under the old vault policy.
2. Same-policy change (if any) **shrinks** geometrically under fee + staged amounts; value evacuates **monotonically**.
3. Sequence **terminates** with funds safe in recovery (or completed to a committed destination).

**Rejected “fix”:** re-bounding Path B clawback with an upper time limit. Unbounded clawback is **defender-favorable** (works after expiry of an uncompleted proposal). Re-bounding would strand funds in staged outputs.

**Hardening already in v1.1:** U1 + U4 guarantee one staged output shape per proposal; prefer whitelist vaults for treasury.

---

## 6. Universal anti-theft rules U1–U4 (v1.1 load-bearing)

Applied to **every** v3/v4 covenant spend (Phase 1 consensus). Treat as first-class, not polish.

| ID | Rule | Closes |
|----|------|--------|
| **U1** | Exactly **one** covenant (v3 or v4) input per transaction | Multi-input value merge (Grok Sequence B) |
| **U2** | Every covenant-satisfying signature uses **`SIGHASH_ALL` only** | Post-sign destination/output rewrite (Grok Sequence A) |
| **U3** | `sum(inputs) − sum(outputs) ≤ MAX_COVENANT_FEE` | Fee-drain to miner (DeepSeek / Gemini) |
| **U4** | Full output set matches the path’s permitted set **exactly** (recomputed commitments; **nothing else**) | Fake staged commitment / extra outputs (Qwen) |

`MAX_COVENANT_FEE` is an **absolute** chain parameter (not relative % of vault). Must exceed a legitimate 15-guardian Path B clawback at ceiling fee-rate; still negligible vs protected treasury. Final calibration: testnet (`// TODO: testnet-calibrate` in Phase 1).

---

## 7. What this design will never do (spec §13)

- No instant-spend path.  
- No amount-based timelock bypass.  
- No mutable covenant parameters.  
- No hot-key-adjustable timelock.  
- No general covenant scripting language.  
- No consensus byte cap (schema discipline bounds size).  
- No per-UTXO nonce or account-style consensus state.  
- No FIDO2 / WebAuthn / COSE parsing in consensus.  
- No chain-level un-receivable marking.  
- No non-NIST PQ. No “PQ PoW.”  
- No “quantum-proof” claims pre-hybrid PQ spends (bit 4 / witness v2 track — **not** this build).  
- **(v1.1)** No uncapped fees on covenant spends.  
- **(v1.1)** No non-`SIGHASH_ALL` covenant signatures.  
- **(v1.1)** No covenant transaction with more than one covenant input.  

---

## 8. §6 falsification round — adjudication (spec §14)

Six blind reviews attacked §6 with a single instruction: *find a valid transaction sequence that violates §6.*

### Adopted (real consensus defects → v1.1 fixes)

| Fix | Source | Defect | Resolution |
|-----|--------|--------|------------|
| **FIX-FEE** | DeepSeek + Gemini (independent) | Uncapped fee = value drain to miner under self-mining | **U3** |
| **FIX-SIGHASH** | Grok Build Sequence A | Unpinned sighash → destination substitution | **U2** |
| **FIX-BIND** | Qwen (+ ChatGPT “one staged” invariant) | Missing commitment recompute / “nothing else” | **U4** + commitment recompute |
| **U1** | Grok Build Sequence B | Multi-covenant-input merge | **U1** |

### Reframed / partially rejected

- **HY3 livelock:** not an unbounded theft loop; reframed as open-destination residual (§5). **Do not** re-bound Path B clawback.  
- **ChatGPT:** found no theft path and said so — calibration that post-fix §6 is closed rather than that panels invent defects.

### Residual open items (next pass, not Phase 0)

- Finalize `MAX_COVENANT_FEE` on testnet.  
- Confirm codebase sighash machinery cleanly rejects non-ALL on v3/v4 inputs (Phase 1 tests).

---

## 9. Quantum posture (vault build vs hybrid PQ)

| Track | Bit / witness | This vault build? |
|-------|---------------|-------------------|
| Vault covenant | BIP9 **bit 5** `vault_covenant`, witness **v3/v4** | **Yes** (soft-fork when activated) |
| Hybrid PQ spends | BIP9 **bit 4** `hybrid_pq_spends`, witness **v2** | **No** — do not touch |
| Mesh ML-DSA proofs | App-layer, zero-balance signing keys | **Separate** Phase 4 PR |

Block-weight / fee parameters should remain sized for **3–5 KB** PQ witnesses for future hybrid spends. NIST schemes only.

**Mesh (Phase 4 companion risk ranking):** storage-integrity and economic gamification of data-availability / proof markets are ranked **above** quantum for the mesh itself. Mesh proof-signing keys must hold **zero balance** and never stake value.

---

## 10. Spend paths (index only — full rules in frozen spec §6)

Exactly two vault paths and two staged paths; no third path.

| Object | Path | Summary |
|--------|------|---------|
| Vault v3 | 1 Unvault proposal | → one staged v4 (+ optional same-`policy_hash` change); SIGHASH_ALL; fee ≤ cap |
| Vault v3 | 2 Guardian clawback | → recovery script; M-of-N SIGHASH_ALL; fee ≤ cap |
| Staged v4 | A Completion | After `nHeight + timelock`; permissionless to committed dest; fee ≤ cap |
| Staged v4 | B Guardian clawback | **Any time until spent** (no upper bound); → recovery; fee ≤ cap |

Proposal height for staged coins is **`Coin.nHeight`** (existing UTXO metadata) — not a new consensus index.

---

## 11. Related documents

| Doc | Role |
|-----|------|
| Bloodstone Vault Build Spec v1.1 (FROZEN) | Authoritative consensus + wallet rules |
| [Bloodstone Quantum Readiness](../Bloodstone-Quantum-Readiness.md) (downloads) | Partner quantum ladder; includes VAULT row |
| Hybrid PQ Phase C / D docs | Bit 4 / witness v2 — orthogonal |
| Phase 4 mesh threat model | DA fraud + gamification (separate PR) |
| `h0-phase-h-scope.md` / `Phase-H1-H3-Sign-Off.md` | §15.1 Phase H timewarp — **H1/H3 signed off**; vault PR still separate |

---

*Bloodstone Native Vault · Threat Model v1.2 · Phase 0 · 2026-07-20 · §15.1 H1/H3 signed off · quantum-aware, not quantum-proof*
