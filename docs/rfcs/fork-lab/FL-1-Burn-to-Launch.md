# FL-1 — Burn-to-Launch (Burn-Triggered Automated Launch)

**Status:** Draft filed · provisional ID FL-1  
**Source of truth:** RFQ v1.5 §2, §3, §3a, §4, §5, Decisions #1–#10, #13–#14  
**Constitution:** Subordinate; Art. X applies (platform capability — universal)

## 1. Summary

A creator burns a fixed amount of STONE to a **provably unspendable per-draft address**. After confirmation, automation provisions the fork registry entry and listing. Public framing: **burn-triggered automated launch** — not “trustless.”

## 2. Mechanism (from RFQ only)

- **100% burn** — no treasury split.  
- **Validate before burn** — draft → validate → freeze fee → issue burn address → burn.  
- **Keyless burn address** — Hash160 commitment, Base58Check version 63 (`S…`); locked DOMAIN_SEP layout (RFQ §3a).  
- **Derive** salt/magic/ports from burn txid (deterministic).  
- **Provision** in separate `bloodstone-fork-registry` at `coins/<TICKER>/` (no `core/` prefix).  
- **Manual txid reconciliation** mandatory if watcher misses burns.  
- **Pricing:** STONE-denominated only in user-facing copy.

## 3. Art. VII compliance (answers)

1. **Ledger:** No second consensus; STONE chain remains only ledger for burns.  
2. **State:** Registry is off-chain application state, not consensus per-entity balances.  
3. **Measurement:** Fee uses height + difficulty gate (RFQ §3c), not a price oracle.  
4. **Proof class:** Burn is Class A (on-chain math). Registry bot is operational trust (disclosed).  
5. **Scope of claims:** “Automated” ≠ trustless; repo availability remains trusted.  
6. **Value:** Launch fee is burned; no n-of-m fee extraction in this mechanism.  
7. **Funding:** Ops funded by optional add-ons (RFQ Decision #2), not launch fee.  
8. **Actors:** No new consensus actors.  
9. **Punishment:** No slash/ban consensus. Abuse handling is off-chain human path.  
10. **Falsification:** WP0 verifier proves keylessness independently.  
11. **Hierarchy:** Mechanism here; parameters in RFQ; sequencing in Roadmap.  
12. **Freeze/scope:** Does not alter core-chain consensus rules.  
13. **Neutrality (Art. X / Q13):** Launch path is **identical for every fork**. No coin-specific launch perk. Naming is “Fork Lab / burn-to-launch,” not coin-branded.

## 4. Build packages

| WP | Role |
|----|------|
| **WP0** | Burn address deriver + **verifier** (shipped) |
| **WP1** | Watcher + provisioner pipeline (**demand-gated** — do not rush without launch demand) |

## 5. Open parameters (must clear before broad production)

- Confirmation depth **N** (suggested 6 or 12)  
- Independent third-party WP0 skeptic run  

---

*FL-1 · RFQ v1.5 · Constitution v1.3*
