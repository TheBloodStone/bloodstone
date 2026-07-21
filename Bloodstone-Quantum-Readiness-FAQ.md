# Bloodstone Quantum Readiness — FAQ

**Version:** 1.0 · **2026-07-19**  
Companion to [Bloodstone Quantum Readiness v2](Bloodstone-Quantum-Readiness.md).

---

### Is Bloodstone quantum-proof?

**No.** No Bitcoin-family UTXO coin is fully quantum-proof on-chain today. We are **quantum-aware** and migration-ready, not quantum-proof.

### What is the real risk?

After you **spend**, your public key is on-chain. A future large quantum computer using **Shor’s algorithm** could target that key. **Reusing spent addresses** for new deposits is the main avoidable mistake. PoW hashes are a secondary (Grover) concern, not the first failure mode.

### Does multi-algo mining or QUASAR make us safe from quantum computers?

**No.** Multi-algo diversifies **ASIC / hardware** risk. **QUASAR** hardens **reorg / 51% economics**. Neither replaces post-quantum **signatures**.

### What should I do today?

1. Generate a **new** receive address for important deposits.  
2. Prefer **`stone1…` (bech32)** when offered.  
3. Do **not** reuse addresses marked **Spent**.  
4. Never share WIF / seeds.  
5. Keep large balances off the web hot wallet when possible.

### What about hybrid / PQ addresses (`bshybrid1…`)?

They are **pre-activation / experimental**. The web wallet can generate offline hybrid material for education and **rejects** sending STONE to `bshybrid1…` until a soft-fork activates hybrid spends. Do **not** fund them on mainnet.

### Will there be a hard fork for quantum?

**Not planned as a panic hard fork.** The intended path is a **BIP9 soft-fork** (version bit **4**, `hybrid_pq_spends`) with a migration window — classical stays valid until users move. See [Phase C](Bloodstone-Hybrid-PQ-Phase-C-Activation.md) and [Phase D](Bloodstone-Hybrid-PQ-Phase-D-InNode.md).

### Which PQ algorithm?

Target is **NIST ML-DSA-65** (FIPS 204) alongside classical ECDSA in a hybrid spend — not a custom curve. Offline reference tools already use real ML-DSA-65.

### Where is the long form?

[Bloodstone-Quantum-Readiness.md](Bloodstone-Quantum-Readiness.md)

---

*Bloodstone · Quantum FAQ v1.0 · 2026-07-19*
