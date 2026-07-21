# Bloodstone Hybrid PQ — Phase D (In-Node) Roadmap

**Document version:** 1.1  
**Date:** 2026-07-19  
**Status:** Soft-fork prep started (offline selftest + wallet lab) — **no consensus code path, no hard fork, mainnet not activated**  
**Depends on:** [Phase C Activation](Bloodstone-Hybrid-PQ-Phase-C-Activation.md) · [ML-DSA Reference](Bloodstone-Hybrid-PQ-ML-DSA-Reference.md) · [Hybrid design](Bloodstone-Hybrid-PQ-Outputs-Design.md)

---

## 1. Goal

Move hybrid classical + **ML-DSA-65** verification from the offline Python reference into **bloodstoned / lrgkd** so that:

1. Nodes can validate hybrid spends under BIP9 bit **4** (`hybrid_pq_spends`) when activated  
2. Wallets can eventually create hybrid receives and dual-signed spends  
3. Regtest CI can exercise lock-in / activation without mainnet risk  

Offline reference (shipped):

| Tool | Path |
|------|------|
| ECDSA + WOTS stand-in | `/root/bloodstone-pq-hybrid/hybrid_demo.py` |
| Phase C serializer / vectors | `/root/bloodstone-pq-hybrid/hybrid_phase_c.py` |
| ECDSA + **ML-DSA-65** | `/root/bloodstone-pq-hybrid/hybrid_mldsa.py` |
| Saved LRGK/core patches (bit 4) | `/root/bloodstone-pq-hybrid/patches/` |

Typical dual-sig witness ≈ **5.3 KB** (see ML-DSA reference).

---

## 2. Work packages

| WP | Deliverable | Notes |
|----|-------------|--------|
| **D0** | Offline selftest + wallet hybrid lab | **Done 2026-07-19** — not consensus |
| **D1** | Vendored or linked **ML-DSA-65** C/C++ (FIPS 204) | Prefer audited lib (e.g. liboqs / pqclean) over custom |
| **D2** | `script/interpreter` path for witness v2 hybrid commit | Match Phase C §3 stack layout — **soft fork only** when activated |
| **D3** | Mempool policy: weight, standardness, dust | Cap hybrid weight; reject oversized PQ blobs |
| **D4** | Wallet: hybrid address encode/decode + fund/sign | Lab encode **done**; fund/sign waits for D2 |
| **D5** | Regtest vectors ported from `hybrid_mldsa.py` | Selftest harness **done**; in-node regtest pending D1–D2 |
| **D6** | Testnet bit-4 campaign tooling | GBT name already `hybrid_pq_spends` when enum present |
| **D7** | Release notes + migration guide for exchanges | No mainnet start until D5 green |

### D0 shipped (this step — not a hard fork)

| Item | Path / URL |
|------|------------|
| Selftest | `/root/bloodstone-pq-hybrid/hybrid_selftest.py` |
| Offline ML-DSA dual-sig | `hybrid_mldsa.py` |
| Wallet lab | Web wallet **Receive → Experimental hybrid PQ lab** |
| Send guard | Rejects `bshybrid1…` destinations |
| Consensus | **Unchanged** — no mainnet activation, no HF |

### Suggested order

```
D1 → D2 → D5 → D3 → D4 → D6 → D7
```

Do not set mainnet `nStartTime` until D5 is CI-green and a published node release includes D1–D3.

---

## 3. BIP9 note (bit 4)

Phase C reserves:

- Enum: `Consensus::DEPLOYMENT_HYBRID_PQ`  
- Bit: **4**  
- Mainnet/testnet: `NEVER_ACTIVE` until campaign  
- Regtest: `ALWAYS_ACTIVE` when enum is compiled in  

**Host rebuild note (2026-07-19):** Adding `DEPLOYMENT_HYBRID_PQ` enlarges `Consensus::Params::vDeployments[]`. A partial object rebuild on a low-RAM host produced ABI-mismatched `lrgkd` binaries (segfault in libstdc++). Full tree rebuild required before shipping bit-4 in the **host** daemon. Canonical sources with hybrid reserved live under `/root/bloodstone-pq-hybrid/patches/`. Phone APK / difficulty work proceeds independently of bit-4 activation.

---

## 4. Acceptance criteria (Phase D “done” for testnet)

- [ ] Hybrid spend verifies on regtest with ML-DSA-65  
- [ ] Malleated classical or PQ half fails validation  
- [ ] Vectors match offline JSON (`bloodstone-hybrid-mldsa-vectors-v2.json`)  
- [ ] `getblockchaininfo` softforks lists `hybrid_pq_spends` when deployment present  
- [ ] No mainnet activation parameters set  

---

## 5. Out of scope for Phase D

- Removing ECDSA (hybrid only; classical remains for migration)  
- Changing PoW algorithms  
- Claiming “quantum-proof” network-wide  

---

## 6. Related links

- Downloads: https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Hybrid-PQ-Phase-D-InNode.md  
- ML-DSA offline: https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Hybrid-PQ-ML-DSA-Reference.md  
- Vectors: https://bloodstonewallet.mytunnel.org/downloads/bloodstone-hybrid-mldsa-vectors-v2.json  

---

*Bloodstone · Hybrid PQ Phase D In-Node v1.1 · 2026-07-19*
