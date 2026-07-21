# Bloodstone Quantum Readiness

**Document version:** 2.1  
**Date:** 2026-07-19  
**Status:** Quantum-**aware** hygiene + hybrid **design/tools** shipped · Native Vault **in build** (bit 5) · **mainnet hybrid PQ spends not activated** · **not a hard fork** · **not “quantum-proof”**

This is the partner-facing note for what quantum computers mean for STONE, what Bloodstone has shipped, and what is still research. It is **honest by design**.

---

## 1. What “quantum hardening” means here

For a Bloodstone-style chain (ECDSA P2PKH / bech32 + multi-algo PoW), quantum risk is mainly:

| Threat | Target | When it matters |
|--------|--------|-----------------|
| **Shor’s algorithm** | ECDSA / Schnorr private keys | Breaks **spent or exposed pubkeys** (address reuse, P2PK, anything that put the full pubkey on-chain) |
| **Grover’s algorithm** | Hash functions (SHA-256, etc.) | Only weakens PoW / address space ~half the bits — annoying, **not** “end of hashing” |
| **Harvest now, decrypt later** | Encrypted traffic, backups | Offline copies of **WIF / seeds / TLS dumps** |
| **Mesh proof-signing keys (exposed)** | Frequent mesh/DA proof signatures | Pubkeys are **on-wire often** — treat as **zero-balance** keys with **ML-DSA** (NIST) + **cheap rotation**; never put stake or treasury on the signing key. App-layer (Phase 4 mesh track), not hybrid PQ spends. |
| **Mesh DA fraud / gamification** | Storage proofs, capacity claims, reward markets | **Ranked above quantum for the mesh:** Sybil capacity, storage-once/retrievability, withholding, collusion, wash-storage, free-riding. Economic + integrity problem first; PQ signatures second. |

**PoW** (NeoScrypt / Yespower / SHA256d) is **not** the first thing to die. **Signatures and key reuse** are.

**QUASAR** (reorg defense, mesh, QSE, braid signaling) is **economic / consensus security**, not post-quantum crypto. It still helps overall resilience; it does **not** replace PQ signatures.

---

## 2. Practical ladder

### Tier 0 — Ops & hygiene (now, no fork)

| # | Action | Bloodstone status |
|---|--------|-------------------|
| 1 | Never reuse addresses after spending; UI loud about it | **Shipped** — web Receive badges (Unused / Used / Spent); primary spent warnings |
| 2 | Prefer types that hide pubkey until spend (P2WPKH / bech32) | **Shipped** — new web receives default to **bech32** (`stone1…`) when the node allows |
| 3 | Backup hygiene: encrypted backups; no plain WIF in chat/logs | **Ops + UX** — WIF shown once; docs stress “forever compromised if leaked” |
| 4 | Hot vs cold: minimize STONE on web/hot surfaces | **Ops policy** — see [Hot Wallet Quantum Ops](Bloodstone-Hot-Wallet-Quantum-Ops.md) |
| 5 | Document quantum readiness without over-claiming | **This doc + FAQ** |

### Tier 1 — Policy / product “quantum-aware” (weeks, no consensus break)

| # | Action | Bloodstone status |
|---|--------|-------------------|
| 1 | Spend limits / care for large outflows from hot paths | Swap monthly cap (e.g. 5k STONE/account+IP); send UX hygiene after spend |
| 2 | Address rotation: one-time receive, spent warnings | **Shipped** on web Receive; post-send reminder on Send |
| 3 | Multisig / coordinator bonds | **Docs live** — coordinator bond multisig ceremony & federation guides |
| 4 | Long-term vault (airgap / multi-party; covenant + PQ label later) | **In build** — Native Vault (bit 5 / v3–v4); see [vault threat model](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Vault-Threat-Model.md) |
| 5 | White paper / FAQ with honest phases | **This doc v2** + [FAQ](Bloodstone-Quantum-Readiness-FAQ.md) |

### Tier 2 — Hybrid addresses / soft-fork path (months, consensus work)

Industry direction for BTC-family:

1. **Hybrid outputs** — spend needs classical **and** PQ (e.g. ECDSA + **ML-DSA-65**)  
2. Commit / witness-v2 style designs so today’s wallets are not thrown away  
3. **Migration window** while classical remains valid  
4. Witness size + fees planned early (~5.3 KB dual-sig reference)

| Piece | Status |
|-------|--------|
| Hybrid design | [Outputs Design](Bloodstone-Hybrid-PQ-Outputs-Design.md) |
| BIP9 bit **4** reserved (`hybrid_pq_spends`) | [Phase C Activation](Bloodstone-Hybrid-PQ-Phase-C-Activation.md) — **NEVER_ACTIVE** mainnet |
| Offline ECDSA + ML-DSA-65 | [ML-DSA Reference](Bloodstone-Hybrid-PQ-ML-DSA-Reference.md) + selftest |
| Explorer `bshybrid1…` display | Shipped |
| Web send rejects hybrid destinations | Shipped |
| Wallet experimental hybrid lab | Receive page — **offline only** |
| In-node C++ verify / regtest spends | [Phase D](Bloodstone-Hybrid-PQ-Phase-D-InNode.md) — **not started in consensus** |

This is a **multi-release soft-fork program**, not a one-day patch. **Not a hard fork** when activated via BIP9.

### Tier 3 — Full post-quantum consensus (years)

- Default addresses = PQ or hybrid with classical deprecated  
- Optional PoW parameter review only if the field standardizes something useful (do **not** invent “PQ PoW” for marketing)  
- Exchange / explorer / wallet ecosystem migration  

---

## 3. What fits Bloodstone specifically

| Area | Recommendation | Status |
|------|----------------|--------|
| Web wallet | Non-reuse, spent warnings, optional large-send care | **Live** |
| Android miner / LRGK | Hygiene messaging + independent chains; LRGK has public seed | LRGK peer live; BS miner hygiene is ongoing product work |
| Hot pools (swap, faucet, ads) | Low balances; multi-sig ops; rotate keys | Policy + partial caps; see ops note |
| QUASAR / braid | Keep shipping — orthogonal & valuable | Ongoing |
| Core node | Hybrid script as **future soft-fork**; no custom PQ curve | Spec + offline tools; consensus path open |
| Mining | Multi-algo diversifies ASIC risk; quantum ≠ main PoW issue | As designed |
| Messaging | **Quantum-aware / migration-ready** — never “quantum-proof” until hybrid/PQ spends exist | Enforced in this doc |

**Standards we follow (do not invent):**

- NIST PQC: **ML-DSA** (Dilithium), SLH-DSA (SPHINCS+), etc.  
- BTC-family hybrid / Taproot-leaf style proposals as they stabilize  

---

## 4. What we will **not** do

- Claim “quantum safe” because of multi-algo or QUASAR alone  
- Ship a random non-standard PQ scheme in production wallets  
- Panic-increase difficulty or “PQ PoW” for optics  
- Put PQ only on a phone miner while the web wallet is ECDSA-only with no migration story  
- Hard-fork the chain to force PQ overnight  

---

## 5. Shipped phases (build log)

| Phase | Goal | Consensus? | Status |
|-------|------|------------|--------|
| **A** | Non-reuse UX, docs, hot-wallet discipline | No | **Done** (web) |
| **B** | Hybrid design + offline dual-sig prototype | No | **Done** |
| **C** | Bit 4 reserved, activation spec, vectors, explorer | Soft-fork slot only | **Done tooling** — not mainnet-active |
| **C+** | Offline **ML-DSA-65** dual-sig | No | **Done offline** |
| **D0** | Selftest + experimental hybrid lab | No | **Done** |
| **D** | In-node ML-DSA + regtest | Soft-fork when activated | Roadmap |
| **E** | Default hybrid receives; treasury/exchange migration | Soft-fork / migration | Future |
| **VAULT** | Native vault covenant (witness v3/v4; BIP9 **bit 5** `vault_covenant`) | Soft-fork when activated | **In build** (Phase 0 docs landed; consensus Phase 1+) — **not** mainnet-active; **not** “quantum-proof” |

---

## 6. What users should do **today**

1. Use a **fresh receive address** for important new deposits (`stone1…` preferred).  
2. **Do not reuse** addresses you have already spent from.  
3. After spending, leave emptied addresses alone — generate a new one.  
4. Store WIFs offline; never post keys in Discord or support chats.  
5. Keep large holdings off hot web wallets; prefer cold / multi-sig when available.  
6. Ignore anyone claiming Bloodstone is “quantum-proof” today.  

---

## 7. One sentence for partners

> No Bitcoin-family coin is fully quantum-proof on-chain yet. We harden by **avoiding address reuse**, keeping **hot wallets small**, **multi-sig for treasury**, and **planning a hybrid (classical + post-quantum) spend path**. **QUASAR** protects against reorgs and 51% economics — **separate from quantum signatures**.

---

## 8. Related downloads

| Doc | Role |
|-----|------|
| [Quantum Readiness FAQ](Bloodstone-Quantum-Readiness-FAQ.md) | Short Q&A |
| [Hot Wallet Quantum Ops](Bloodstone-Hot-Wallet-Quantum-Ops.md) | Ops checklist for pools / web |
| [Hybrid PQ Outputs Design](Bloodstone-Hybrid-PQ-Outputs-Design.md) | Tier 2 design |
| [Hybrid PQ Phase C Activation](Bloodstone-Hybrid-PQ-Phase-C-Activation.md) | Bit 4 soft-fork slot |
| [Hybrid PQ ML-DSA Reference](Bloodstone-Hybrid-PQ-ML-DSA-Reference.md) | Offline dual-sig |
| [Hybrid PQ Phase D In-Node](Bloodstone-Hybrid-PQ-Phase-D-InNode.md) | C++ roadmap |
| [Vault Threat Model v1.1](Bloodstone-Vault-Threat-Model.md) | Native vault §10/§13/§14 (Phase 0) |
| [QUASAR 51% Defense White Paper](Bloodstone-QUASAR-51-Percent-Defense-White-Paper.md) | Orthogonal reorg defense |
| [Coordinator Bond Multisig Ceremony](Bloodstone-Coordinator-Bond-Multisig-Ceremony.md) | Treasury multi-party |

Offline tools (ops host): `/root/bloodstone-pq-hybrid/`  
Selftest: `bloodstone-hybrid-selftest.py`  
Web wallet: **Receive** (hygiene + hybrid lab) · **Send** rejects `bshybrid1…`

---

*Bloodstone · Quantum Readiness v2.0 · 2026-07-19 · quantum-aware, not quantum-proof*
