# FL-5 — Ward Mesh (Platform Defense Mesh; formerly “Azure Spells”)

**Status:** Draft filed · provisional ID FL-5  
**Source of truth:** RFQ v1.5 §12 (defense / Force Lance); Decision #15; Art. X  
**Constitution:** Art. X.1 — platform capability must be **neutrally named**

## 1. Summary

Multi-fork **defense mesh** (tip ring, counterstrike, heat reflection, etc.).  
**Platform-universal:** every fork can benefit; **AZURE is first peer in the mesh, not owner.**

Public name going forward: **Ward Mesh** (alt: Fork Shield).  
Legacy paths `/azure-spells/` and related APIs may remain for compatibility.

## 2. Why this needs an RFC more than PQ Cover (today)

RFQ **specifies** this system and Force Lance can **throttle the SHA256d lane**.  
Over-throttling degrades **mandatory STONE merge-mining** that Fork Lab economics assume.  
PQ Cover is neutrality-cited but **has no RFQ mechanism section** — deferred.

## 3. Mechanism (from RFQ §12 — do not invent beyond)

- Sister tip ring / ward stack (retail: Ward of Six naming).  
- **Force Lance** = active ward that can affect SHA256d.  
- Must not be marketed as AZURE-owned product.

## 4. Art. VII (incl. Q13)

1–3. Defense uses tips/attestations carefully; must not smuggle world-measurement into consensus.  
4–5. Claims limited to operational defense, not “unbreakable 51% immunity.”  
8–9. Rate caps and overrides are operational, not consensus punishment of miners by rule change.  
10. Falsify Force Lance trigger before enabling automated throttle.  
13. **Neutrality:** Capability is universal; **user-facing name must be coin-neutral (Art. X.1)**. AZURE-branded “Azure Spells” implies ownership → rename.

## 5. ⚠ Production safety gate (highest)

Before Force Lance may auto-throttle SHA256d in production:

| Requirement | Why |
|-------------|-----|
| Published **trigger threshold** | No silent policy |
| Published **rate cap** | Bound damage |
| **Manual override** | Ops + FSP scrutiny |
| Explicit merge-mine impact note | Mandatory STONE dual-job |

Until then: treat Lance as **disarmed / manual-only**.

## 6. Rename timing

**Do the user-facing rename now** (this pass or immediately after filing).  
URLs may stay `/azure-spells/` forever for links; titles, nav, and docs use **Ward Mesh**.

---

*FL-5 · RFQ v1.5 · Constitution v1.3*
