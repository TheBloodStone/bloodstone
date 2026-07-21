# Bloodstone Hot Wallet — Quantum-Aware Ops Checklist

**Version:** 1.0 · **2026-07-19**  
**Audience:** Operators of web wallet, swap, faucet, ad-rewards, pool payouts  
**Goal:** Tier 0–1 hygiene — **no consensus change**

---

## Why hot wallets matter more under quantum threat models

Hot keys that **sign often** publish pubkeys repeatedly. Compromised WIFs or database dumps are “harvest now, break later” targets. Quantum does not create that problem — it **raises the long-term cost of sloppy ops**.

---

## Checklist

### Balances

- [ ] Keep **swap / faucet / ad-reward / pool** working balances at the **minimum** needed for a few days of ops  
- [ ] Sweep excess to **cold or multi-sig** on a schedule (weekly or after large inflows)  
- [ ] Document who can authorize top-ups  

### Keys & access

- [ ] No plain WIF in Discord, tickets, logs, or git  
- [ ] Encrypted wallet passphrases only in operator secret stores  
- [ ] Rotate payout / fund addresses after incidents or staff changes  
- [ ] Prefer **multi-sig** for treasury and coordinator bonds ([ceremony](Bloodstone-Coordinator-Bond-Multisig-Ceremony.md))  

### Product limits (examples already in stack)

- [ ] Swap: monthly STONE cap per account **and** IP (policy live)  
- [ ] Faucet / ads: rate limits remain on; do not raise hot float to “paper over” abuse  
- [ ] Web wallet: treat as **hot** — users should not park life savings there  

### Address hygiene on user-facing products

- [ ] Web Receive: spent / unused badges (live)  
- [ ] New receives: prefer **bech32**  
- [ ] Send: post-spend reminder not to reuse emptied addresses  
- [ ] Never accept `bshybrid1…` as a mainnet destination until soft-fork  

### Messaging

- [ ] Say **quantum-aware**, not quantum-proof  
- [ ] Point partners at [Quantum Readiness v2](Bloodstone-Quantum-Readiness.md)  

### Monitoring

- [ ] Alert if hot fund wallet balance exceeds a set ceiling  
- [ ] Alert on unexpected large outflows  
- [ ] Keep node RPC **not** public (localhost / ACL only)  

---

## Related

- [Quantum Readiness](Bloodstone-Quantum-Readiness.md)  
- [Quantum FAQ](Bloodstone-Quantum-Readiness-FAQ.md)  
- [Coordinator Bond Multisig](Bloodstone-Coordinator-Bond-Multisig-Ceremony.md)  

---

*Bloodstone · Hot Wallet Quantum Ops v1.0 · 2026-07-19*
