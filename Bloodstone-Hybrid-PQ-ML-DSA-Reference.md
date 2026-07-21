# Bloodstone Hybrid PQ — ML-DSA-65 Reference (post–Phase C)

**Version:** 1.1 · **2026-07-19**

## What changed

Phase C reserved BIP9 bit **4** (`hybrid_pq_spends`). The next engineering step adds a **real NIST ML-DSA-65** dual-sig offline path:

- Classical: ECDSA secp256k1  
- PQ: **ML-DSA-65** (FIPS 204 pure-Python reference, vendored)

## Run

```bash
/root/bloodstone-wallet-web/venv/bin/python3 \
  /root/bloodstone-pq-hybrid/hybrid_mldsa.py demo
```

Vectors: [bloodstone-hybrid-mldsa-vectors-v2.json](bloodstone-hybrid-mldsa-vectors-v2.json)

## Sizes (typical)

| Item | Bytes |
|------|------:|
| classical pk | 33 |
| classical sig | 64 |
| ML-DSA-65 pk | ~1952 |
| ML-DSA-65 sig | ~3309 |
| witness total | ~5.3 KB |

## Status

- Offline / reference only — **demo PASS** (ECDSA + ML-DSA-65, ~5.3 KB witness)  
- Mainnet soft-fork **not** activated  
- Node still needs C++ ML-DSA for consensus validation — see [Phase D In-Node](Bloodstone-Hybrid-PQ-Phase-D-InNode.md)  
- Vectors download: [bloodstone-hybrid-mldsa-vectors-v2.json](bloodstone-hybrid-mldsa-vectors-v2.json)

See also: [Phase C Activation](Bloodstone-Hybrid-PQ-Phase-C-Activation.md)
