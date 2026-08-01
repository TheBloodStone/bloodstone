# Fork Lab RFC series — filing location

**Provisional numbering:** `FL-1` … `FL-5` (does not collide with RFC-010/011).  
**Final numbers:** assign when merged into the main RFC index if desired.

## Where RFCs live (this VPS / public downloads)

| Location | Purpose |
|----------|---------|
| **Source of truth (workspace)** | `/root/bloodstone-docs/rfcs/fork-lab/` |
| **Public download** | `https://bloodstone.rocks/downloads/rfcs/fork-lab/` |
| **Index** | [INDEX.md](INDEX.md) · [INDEX on rocks](https://bloodstone.rocks/downloads/rfcs/fork-lab/INDEX.md) |

## Hierarchy (Constitution Art. IX)

1. **Constitution** — principles (incl. Art. X Platform Neutrality)  
2. **RFCs** (this folder) — mechanism  
3. **Build Spec / RFQ v1.5** — implementation parameters  
4. **Code / WP deliverables** — build  

RFCs **reference** Art. X; they do not restate the whole Article.

## How to file a new Fork Lab RFC

1. Copy an existing `FL-*.md` template structure.  
2. Answer **every** Constitution Art. VII question, including **Q13 (neutrality)**.  
3. Point `Source of truth` at the RFQ section(s) that specify the mechanism — **do not invent mechanism**.  
4. Drop the file here and copy to `/var/www/bloodstone/downloads/rfcs/fork-lab/`.  
5. Add a row to `INDEX.md`.  

## Deferred (not invented)

| Topic | Why deferred |
|-------|----------------|
| **PQ Cover Layer** | Named in neutrality cases / Decision #15, but **no mechanism section in RFQ v1.5**. Needs a written mechanism before an RFC (Art. V.4 ground truth). |

## Related

- RFQ: https://bloodstone.rocks/downloads/Bloodstone-Fork-Lab-Burn-to-Launch-RFQ-v1.5.md  
- Constitution: https://bloodstone.rocks/downloads/Bloodstone-Protocol-Constitution.md (v1.3)  
