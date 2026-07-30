# Bloodstone Ecosystem Transparency Roadmap

**Status:** Phase 1 in progress (2026-07-30)  
**Audience:** auditors, community, builders  
**GitHub Project:** create public org Project **“Bloodstone Ecosystem Roadmap”** and mirror these cards (Component field + filtered views). Until the Project UI exists, **this file is the card source of truth.**

## Target table (industry-leading bar)

| Layer | Target |
|--------|--------|
| **Code** | GitHub first; VPS pulls to build |
| **Forks** | Monorepo paths (or clearly linked separate cores) |
| **Binaries** | SHA256 + commit + path + build script in manifest |
| **Process** | Public Project board for milestones |
| **Later** | Actions for verification/builds; signed manifests |

## Component field values

`Core Node` · `MFQ Wallet` · `Azure Fork` · `LRGK Fork` · `Infrastructure/Build`

## Cards (initial seven)

### 1. Document GitHub-first → VPS pull deploy flow
- **Component:** Infrastructure/Build  
- **Status:** **Done (2026-07-30)** — `AUDITOR-MAP.md` policy section  
- **Acceptance:** Policy is public and explicit; anti-patterns listed  

### 2. Add provenance fields to `mfq-daemons/manifest.json` (schema v2)
- **Component:** MFQ Wallet / Infrastructure/Build  
- **Status:** **Done (schema + live manifest v2 shell, 2026-07-30)**  
- **Acceptance:** Schema doc + portal manifest v2 with real SHA256 and provenance objects (placeholders allowed only for commits until trees land)  

### 3. Publish LRGK source tree into monorepo (`forks/lrgk`)
- **Component:** LRGK Fork  
- **Status:** **Stub only** — path reserved; full core not pushed yet (by design: structure before bulk dump)  
- **Acceptance:** Auditable tree + real `source_commit` in LRGK pack provenance  

### 4. Publish AZURE source tree into monorepo (`forks/azure`)
- **Component:** Azure Fork  
- **Status:** **Stub only** — path reserved  
- **Acceptance:** Auditable tree + real `source_commit` in AZURE pack provenance  

### 5. Unify `ops/build-mfq-fork-daemons` with `--coin`
- **Component:** Infrastructure/Build  
- **Status:** **Stub script present** — full implementation after source trees land  
- **Acceptance:** One entrypoint builds STONE/LRGK/AZURE packs from monorepo paths  

### 6. GitHub Actions Phase 1 — verify portal SHA256 vs manifest
- **Component:** Infrastructure/Build  
- **Status:** **Planned** (publish-only / verification first; not full MinGW matrix)  
- **Acceptance:** Workflow fails if zip hash ≠ manifest  

### 7. PGP / signed manifest + daemon zips
- **Component:** Infrastructure/Build  
- **Status:** **Planned** (after verification CI)  
- **Acceptance:** Published lead key; detatched signatures verifiable offline  

## Views (for GitHub Project UI)

| View | Filter idea |
|------|-------------|
| Roadmap | All open cards |
| Core | Component = Core Node |
| Forks | Azure Fork ∨ LRGK Fork |
| Build / Supply-chain | Infrastructure/Build |
| MFQ | MFQ Wallet |

## Notes

- Protocol principles remain in the **Protocol Constitution**, not this board.  
- Implementation sequencing for chain features remains in the **Development Roadmap**.  
- This document is **supply-chain and publication hygiene only**.
