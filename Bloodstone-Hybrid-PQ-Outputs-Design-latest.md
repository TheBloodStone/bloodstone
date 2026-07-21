# Bloodstone Hybrid PQ Outputs — Design (Phase B)

**Document version:** 1.0  
**Date:** 2026-07-19  
**Status:** Design + offline prototype — **not activated on mainnet**  
**Depends on:** [Bloodstone-Quantum-Readiness.md](Bloodstone-Quantum-Readiness.md) (Phase A)

---

## 1. Goal

Define a **hybrid spend path** for STONE:

> To spend coins locked to a hybrid output, the spender must provide **both**:
>
> 1. A valid **classical** secp256k1 ECDSA (or Schnorr, later) signature, **and**  
> 2. A valid **post-quantum** signature under a NIST-track algorithm (target: **ML-DSA / Dilithium**).

An attacker who only breaks ECDSA (e.g. future large-scale Shor) **cannot** move hybrid funds without also forging the PQ signature. An attacker who only breaks the PQ scheme still needs the classical key (defense in depth during migration).

This phase ships:

| Deliverable | Location |
|-------------|----------|
| This design | `/downloads/Bloodstone-Hybrid-PQ-Outputs-Design.md` |
| Offline prototype CLI | `/root/bloodstone-pq-hybrid/` (demo commitment + dual-verify) |

**Not in this phase:** consensus activation, production addresses on mainnet, exchange support.

---

## 2. Threat model

| Adversary | Classical-only output | Hybrid output |
|-----------|----------------------|---------------|
| Classical thief (stolen WIF) | Can spend | Can spend if they also have PQ secret |
| Quantum adversary (breaks ECDSA only) | Can spend once pubkey exposed | **Cannot** spend without PQ forge |
| Quantum adversary (breaks PQ only) | N/A | Still needs classical key |
| Harvest-now / decrypt-later on backups | WIF dump = total loss | Both secrets required |

**Does not protect:** users who keep hybrid coins on a single online hot wallet with both keys; supply-chain malware; social engineering.

---

## 3. Design principles

1. **Opt-in migration** — existing P2PKH / witness outputs remain valid indefinitely until a later deprecation vote.  
2. **No custom crypto** — PQ half tracks NIST PQC (ML-DSA primary; SLH-DSA/SPHINCS+ optional for long-term archives).  
3. **Hash commitments until spend** — the output commits to digests of both public keys so neither full pubkey sits naked in the UTXO set.  
4. **Weight honesty** — PQ signatures are large; fee policy must price witness bytes correctly.  
5. **One-way upgrade** — once funds move into hybrid, spending back to pure classical is allowed (user choice) but discouraged in UX copy.  
6. **Prototype may use a hash-based stand-in** for the PQ arm offline; consensus code will use ML-DSA only.

---

## 4. Address / output construction

### 4.1 Key material

```
classical_sk, classical_pk   // secp256k1 (same as today)
pq_sk, pq_pk                 // ML-DSA-65 (target) or archive SLH-DSA
```

### 4.2 Commitment (what goes on-chain in the scriptPubKey)

Define:

```
c_hash = HASH160( classical_pk_compressed )     // 20 bytes
q_hash = HASH160( pq_pk_serialized )            // 20 bytes
commit = HASH256( 0x01 || c_hash || q_hash )    // versioned hybrid commit, 32 bytes
```

### 4.3 Proposed scriptPubKey (conceptual)

**Option A — Witness program (preferred long-term)**  
SegWit-style version `N` (TBD, reserved; not v0/v1 Taproot without BIP coordination):

```
OP_N  <32-byte commit>
```

Interpreted by consensus as: “hybrid spend; see witness stack.”

**Option B — P2SH-wrapped redeem script (easier early testnet)**

```
redeem = OP_DUP OP_HASH160 <c_hash> OP_EQUALVERIFY OP_CHECKSIG
         OP_SWAP OP_HASH160 <q_hash> OP_EQUALVERIFY OP_CHECK_PQ_SIG
scriptPubKey = OP_HASH160 <HASH160(redeem)> OP_EQUAL
```

`OP_CHECK_PQ_SIG` is a **new opcode** (or soft-fork reinterpretation of a SUCCESS code / Tapleaf version) that:

1. Pops `pq_sig`, `pq_pk`  
2. Checks `HASH160(pq_pk) == q_hash` committed in the leaf  
3. Verifies ML-DSA over the same sighash as classical

### 4.4 Human address encoding (proposal)

- New Bech32 HRP **or** version nibble under existing `stone1`  
- Draft: `stone1` + witness version `k` + program = `commit` (32 bytes)  
- Explorers display badge: **Hybrid PQ**  

Until activation, the prototype uses a **non-network** string:

```
bshybrid1q...<bech32 of commit>
```

so it cannot be confused with spendable mainnet addresses.

---

## 5. Spend / sighash

### 5.1 Message

Both signatures sign the **same** transaction digest:

```
msg = SignatureHash(tx, input_index, hybrid_script, amount, SIGHASH_ALL)
```

(or Taproot-equivalent sighash once specified).

### 5.2 Witness stack (Option A sketch)

```
<ecdsa_sig> <classical_pk> <ml_dsa_sig> <ml_dsa_pk>
```

Validation order:

1. Parse hybrid commit from scriptPubKey  
2. Recompute commit from provided keys; must match  
3. Verify ECDSA  
4. Verify ML-DSA  
5. Both must succeed  

### 5.3 Malleability

- ECDSA low-S rules unchanged  
- PQ signature encoding: fixed-size, non-malleable canonical form per NIST draft  
- No mixed SIGHASH types in first version (ALL only)

---

## 6. Weight and fees

| Item | Approx. size |
|------|----------------|
| ECDSA sig + compressed pubkey | ~100 bytes |
| ML-DSA-65 public key | ~2 KB |
| ML-DSA-65 signature | ~3 KB |
| **Witness total (order of)** | **~5–6 KB** |

Implications:

- Hybrid spends cost **materially more** than classical  
- Policy: recommend hybrid for **cold / long-horizon** funds, not micropayments  
- Block weight accounting must count PQ witness bytes fully (no discount fantasy)

---

## 7. Wallet UX (when implemented)

1. **Create hybrid receive** — generates classical + PQ keypair; stores both encrypted  
2. **Backup** — both secrets required; export format documents dual material  
3. **Send** — if input is hybrid, wallet attaches dual witness  
4. **Migration wizard** — “Move spendable to hybrid” (user-initiated)  
5. **Warnings** — hybrid → classical send shows “reduces quantum resistance”

Phase A badges (unused / spent) remain the first line of defense for classical addresses.

---

## 8. Activation sketch (Phase C — future)

1. Deploy non-verifying nodes that **relay** unknown witness versions harmlessly where possible  
2. Soft-fork: define hybrid program version + ML-DSA verify  
3. BIP9/QUASAR-bit style signaling if desired  
4. Explorers, web wallet, miner change-address policy  
5. Exchange deposit support only after stable testnet burn-in  

No activation parameters in this document (heights / thresholds TBD).

---

## 9. Offline prototype (this repo)

Path: `/root/bloodstone-pq-hybrid/`  
Download: [bloodstone-pq-hybrid-prototype-1.0.tar.gz](bloodstone-pq-hybrid-prototype-1.0.tar.gz)

```bash
cd /root/bloodstone-pq-hybrid
python3 hybrid_demo.py demo
python3 hybrid_demo.py verify --file /tmp/hybrid-demo.json
```

What it proves:

1. Build versioned hybrid **commitment** from classical pubkey + PQ pubkey  
2. Encode `bshybrid1…` display string  
3. Sign a message with **ECDSA (secp256k1)** + **hash-based WOTS-style PQ stand-in**  
4. Dual-verify: both must pass; removing either signature fails  

**Important:** The WOTS-style arm is a **real hash-based** one-time signature (quantum-resistant in the hash model) used for structure and education. **Mainnet will use ML-DSA**, not this WOTS toy. Keys are **one-time** in the demo — do not reuse WOTS keys.

---

## 10. Security notes for implementers

- Never reuse WOTS keys (demo). ML-DSA is many-time.  
- Side-channel safe PQ verify in C++ (constant-time libraries).  
- Cache PQ verify cost; DoS: limit hybrid inputs per tx initially.  
- Test vectors: empty sighash, wrong order, key mix-and-match, commit mismatch.  
- Quantum readiness doc must stay honest: hybrid is **defense in depth**, not magic.

---

## 11. Open questions (Phase C prep)

1. Witness version number assignment  
2. ML-DSA parameter set (44 vs 65 vs 87) vs block size  
3. Taproot leaf vs bare witness program  
4. Interaction with name scripts / Namecoin-style ops if any  
5. Hardware wallet support timeline  
6. Whether cold hybrid is mandatory for treasury after date X  

---

## 12. Changelog

| Ver | Date | Notes |
|-----|------|--------|
| 1.0 | 2026-07-19 | Initial Phase B design + offline dual-sig prototype |

---

*Bloodstone · Hybrid PQ Outputs Design v1.0 · Phase B · not consensus-activated*
