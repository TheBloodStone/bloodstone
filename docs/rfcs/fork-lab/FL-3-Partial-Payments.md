# FL-3 — Partial Payments (Cumulative-Threshold Burns)

**Status:** Draft filed · provisional ID FL-3  
**Source of truth:** RFQ v1.5 §3b  
**Constitution:** Art. X (same rules for every creator)

## 1. Summary

Creators may fund a draft’s burn address in **one or many transactions**. Watcher **sums confirmed UTXOs** to the draft address; fires when cumulative total ≥ **frozen fee**. No pooling of third-party funds, no refunds, no crowdfunding framing.

## 2. Mechanism (from RFQ)

- Open-minimum: **10% of frozen fee within 48h** or draft lapses.  
- Full window: **90 days** to reach threshold.  
- Stall policy: **expire draft + orphan burns** (STONE stays burned).  
- Reconciliation: idempotent per **draft/address**, not per single txid.

## 3. Art. VII (incl. Q13)

1–3. Only on-chain amounts to a known address; no exchange monitoring.  
4–5. Burns are irreversible Class A facts; “launch success” is app logic.  
6–7. No custody of third-party funds by operator for the burn itself.  
8–9. No consensus punishment.  
10. Falsify watcher cumulative logic with multi-tx fixtures.  
13. **Neutrality:** Same partial-pay rules for all drafts.

## 4. ⚠ Consumer-protection (hard build requirement)

**Orphaned burns are irreversible.** Point-of-send disclosure is **regulatory/consumer work, not optional UX**:

- User must see: multi-tx OK; miss threshold → STONE gone; no refund.  
- Manual reconciliation path still required when watcher is down.

---

*FL-3 · RFQ v1.5 · Constitution v1.3*
