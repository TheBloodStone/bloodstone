# Bloodstone Hybrid PQ — Phase C Activation Spec

**Document version:** 1.0  
**Date:** 2026-07-19  
**Status:** Activation parameters + reference tooling — **mainnet not activated**  
**Depends on:** [Hybrid PQ Outputs Design](Bloodstone-Hybrid-PQ-Outputs-Design.md) · [Quantum Readiness](Bloodstone-Quantum-Readiness.md)

---

## 1. What Phase C delivers

| Item | Status |
|------|--------|
| BIP9 deployment slot **`hybrid_pq_spends`** (version bit **4**) | **Reserved in core** |
| Mainnet / testnet start time | **`NEVER_ACTIVE`** until community schedule |
| Regtest | **`ALWAYS_ACTIVE`** (for tooling / future consensus tests) |
| Witness program version | **Proposed v2** (see §3) |
| PQ algorithm | **ML-DSA-65** target; offline reference still uses WOTS stand-in until ML-DSA is linked in-node |
| Offline consensus-aligned serializer + vectors | `/root/bloodstone-pq-hybrid/hybrid_phase_c.py` |
| Explorer hybrid address type | Detect `bshybrid1…` as hybrid-display |
| Soft-fork live on mainnet | **Not yet** |

---

## 2. Version bits (miner signaling)

| Field | Value |
|-------|--------|
| Deployment name | `hybrid_pq_spends` |
| Enum | `Consensus::DEPLOYMENT_HYBRID_PQ` |
| Bit | **4** (QUASAR braid uses bit 3; Taproot bit 2) |
| Window | 2016 blocks (mainnet default) |
| Threshold | 1815 (90%) mainnet; 1512 (75%) testnet |
| Mainnet `nStartTime` | `NEVER_ACTIVE` |
| Mainnet `nTimeout` | `NO_TIMEOUT` (or set when campaign opens) |
| Regtest | `ALWAYS_ACTIVE` |

### Proposed campaign (when ready — **not started**)

| Milestone | UTC (proposal) | Notes |
|-----------|----------------|-------|
| Spec freeze | T0 | This doc + design v1.x frozen |
| Testnet signaling start | T0 + 90d | Bit 4 start time set on testnet |
| Regtest continuous CI | Ongoing | Vectors in CI |
| Mainnet signaling start | After testnet lock-in ≥ 1 retarget | Requires release notes |
| Lock-in | BIP9 rules | |
| Activation | Next retarget after lock-in + optional `min_activation_height` | |

Miners signal by setting version bit 4 once software supports hybrid validation (even if never-active until start time).

GBT name: **`hybrid_pq_spends`** (`deploymentinfo.cpp`).

---

## 3. Consensus rules (to implement in validation)

### 3.1 New output type

When `DeploymentActiveAfter(pindexPrev, …, DEPLOYMENT_HYBRID_PQ)`:

**Witness v2 keyhash program (proposal):**

```
scriptPubKey: OP_2  <32-byte hybrid_commit>
```

Where:

```
hybrid_commit = HASH256( 0x01 || HASH160(classical_pk) || HASH160(pq_pk) )
```

Same commitment as Phase B design.

### 3.2 Spend witness

```
stack: <ecdsa_sig> <classical_pk_compressed> <pq_sig> <pq_pk>
```

Validation:

1. Program is v2 length 32  
2. Recompute commit from keys; equal program  
3. ECDSA verify over BIP143-style sighash (or Bloodstone current sighash for the input type)  
4. PQ verify: **ML-DSA-65** over the **same** message digest  
5. Both required  

### 3.3 Policy limits (first release)

| Limit | Value | Reason |
|-------|-------|--------|
| Max hybrid inputs per tx | 4 | PQ verify CPU / DoS |
| Min fee rate hybrid | ≥ classical | Weight |
| Standardness | Hybrid outputs standard only after activation | Relay |

### 3.4 Pre-activation

- Nodes **must not** treat unknown v2 as always-true  
- Pre-activation: hybrid scriptPubKey is **non-standard** / rejected  
- Bit 4 may be set in block versions without effect until start time  

---

## 4. Software map

| Component | Phase C work |
|-----------|----------------|
| `consensus/params.h` | `DEPLOYMENT_HYBRID_PQ` enum |
| `deploymentinfo.cpp` | Name `hybrid_pq_spends` |
| `chainparams.cpp` | Bit 4; main NEVER; regtest ALWAYS |
| `script/` / interpreter | Future: `OP_CHECKPQSIG` or v2 program handler |
| `crypto/` | Link ML-DSA (liboqs or vendored) |
| Explorer | Recognize `bshybrid1` display type |
| Web wallet | Phase A hygiene; hybrid receive later |
| Offline tools | `hybrid_phase_c.py` vectors |

---

## 5. Reference tooling

```bash
/root/bloodstone-wallet-web/venv/bin/python3 \
  /root/bloodstone-pq-hybrid/hybrid_phase_c.py vectors
```

Produces `/tmp/bloodstone-hybrid-pq-vectors-v1.json` with:

- commitment  
- scriptPubKey hex (v2 program encoding)  
- witness stack hex  
- dual-verify result  
- negative tests (bad ECDSA, bad PQ, wrong commit)  

---

## 6. Explorer / partner guidance

- Treat `bshybrid1…` as **display-only hybrid prototype addresses** until mainnet activation.  
- After activation, mainnet addresses will use **`stone1` + witness version 2** (or final HRP decided at freeze).  
- Do not credit hybrid deposits until explorer and node both understand the type.

---

## 7. Explicit non-claims

- Hybrid PQ is **not active on mainnet**.  
- Offline demo PQ arm may still be **WOTS stand-in** until ML-DSA is linked in production node builds.  
- Reserving bit 4 does **not** change consensus validation of historical blocks.

---

## 8. Exit criteria for “Phase C complete → production campaign”

1. [x] Bit 4 reserved in tree  
2. [x] Activation doc + vectors  
3. [~] Offline **ML-DSA-65** dual-sig reference (`hybrid_mldsa.py`); C++ in-node still open  
4. [ ] Functional tests spend hybrid on regtest  
5. [ ] Testnet signaling campaign  
6. [ ] Explorer + wallet hybrid receive/send  
7. [ ] Exchange notices  

---

*Bloodstone · Hybrid PQ Phase C Activation v1.0 · 2026-07-19*
