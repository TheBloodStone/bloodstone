# FL-2 — Fee Decay (Maturity-Based, Oracle-Free)

**Status:** Draft filed · provisional ID FL-2  
**Source of truth:** RFQ v1.5 §3c, Decision #14  
**Constitution:** Art. X (universal fee schedule for all forks)

## 1. Summary

Launch fee decays with **STONE chain height** in fixed steps, with a **difficulty gate** and a permanent **floor**. No USD oracle. Fee is **frozen at draft open**.

## 2. Mechanism (from RFQ)

- Anchor: STONE post-genesis height (design clock ~90s/block).  
- **STEP_BLOCKS = 350,640** (design-year at ~90s).  
- START → decay per step → **FLOOR 100,000 STONE** (never below).  
- Difficulty gate prevents free launches on a thin/slow network.  
- Child-coin eras / absolute child heights must **not** be used.

## 3. Art. VII (incl. Q13)

1–3. Height and difficulty are chain mathematics / parameters, not external price.  
4–5. Fee amount is application policy, not consensus Class A claim about markets.  
6–7. Conservation: burned STONE leaves circulation; decay only lowers future requirement.  
8–9. No new actors; no punishment.  
10. Falsify step length against live block times before treating decay as “yearly.”  
11–12. Subordinate to RFQ constants.  
13. **Neutrality:** Same curve for every draft; no coin gets a special platform fee.

## 4. Build status

Decay **enabled** in ops but **inert until first step boundary**. Do not re-open constants without measurement.

## 5. ⚠ Gates

- Empirically confirm STEP_BLOCKS intent vs live network.  
- User-facing copy: **STONE only**, no bare “$20/$100” prices.

---

*FL-2 · RFQ v1.5 · Constitution v1.3*
