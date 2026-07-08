# Blurt × Bloodstone: What We Built (July 7–8, 2026)

**A plain-language summary for everyday readers**  
**Pacific Time (PT)** · Coordinator: https://bloodstonewallet.mytunnel.org

---

## The big picture in one minute

**Blurt** is a social network where posts and identity live on a public blockchain-style ledger. **Bloodstone** is the storage and mesh network that keeps files, videos, and data alive across many small computers (including Raspberry Pis).

Over the last two days, we connected them into one system—the **Blurt–Bloodstone Convergence Stack**—so that:

- Content posted on Blurt can be **proven, stored, and played back** from the mesh  
- Small offline nodes can **sync up** when the internet returns  
- Creators can **pay for storage, compute, and bandwidth** with simple payment notes (memos)  
- A fleet of Pi devices can run the network at the edge  

By the end of **Tuesday, July 8**, we shipped **Waves A through I** (eleven major beta releases from v0.9 through v0.19) and published everything live.

---

## What “steps” mean here

Each **step** is a wave of work: design → build → test on the live server → publish to GitLab → turn on for real users. Think of it like updating an app, except each update also adds a new piece of the decentralized internet.

---

## Monday, July 7, 2026 (Pacific)

### Planning and alignment

| Step | What we did (simply) |
|------|----------------------|
| 1 | Reviewed the **Symbiotic Vision** plan—how Blurt (trust + social) and Bloodstone (storage + mesh) fit together |
| 2 | Mapped each layer (identity, publishing, mesh, edge devices, payments, viewer apps) to code that already runs on the live server |
| 3 | Identified gaps: Pi fleet instructions, payment enforcement, gossip between nodes, satellite uplink |
| 4 | Prepared to publish missing beta release pages on GitLab so the public changelog matches what is actually running |

**Reader takeaway:** Monday was mostly “make sure the blueprint matches reality” before a big push on Tuesday.

---

## Tuesday, July 8, 2026 (Pacific)

Most of the engineering shipped **Tuesday morning, Pacific time** (roughly 6:00–8:00 AM PT). Below is the work in the order we completed it.

### Morning: Foundation and trust (Layers 0–1)

| Release | Wave | What it does (everyday words) |
|---------|------|-------------------------------|
| **v0.9.0-beta** | **A — Trust** | **Prove where content came from.** When someone publishes on Blurt, we can anchor a “digital receipt” so readers see a trust badge in embeds |
| **v0.10.0-beta** | **B — Agents & edge work** | **Register AI and machine identities** on the mesh, and lay groundwork for paying edge nodes for compute and bandwidth |

### Morning: Offline mesh and AR (Layers 2 & 5)

| Release | Wave | What it does (everyday words) |
|---------|------|-------------------------------|
| **v0.11.0-beta** | **C — DTN sync** | **Zip up mesh state into portable bundles** so Pi nodes can swap data while offline (72-hour window) |
| **v0.12.0-beta** | **D — Spatial / AR** | **3D and AR scenes** tied to Blurt posts; spatial data rides along in offline bundles |
| **v0.13.0-beta** | **C+ hardening** | **Make offline sync reliable:** deduplication, retry when upload fails, scheduled “flush” windows, peer discovery, cleanup |
| **v0.14.0-beta** | **mDNS** | **Pi nodes announce themselves on the local network** so neighbors find each other without typing IP addresses |

### Mid-morning: Security, scale, and economics

| Release | Wave | What it does (everyday words) |
|---------|------|-------------------------------|
| **v0.15.0-beta** | **E — TLS & alerts** | **Encrypted HTTPS between Pi nodes** (port 8443) and **alerts** when too many bundles are stuck pending or failed |
| **v0.16.0-beta** | **F — Scale** | **Compute job manifests** on the mesh, **auto-heal** when copies of files are missing, and exchange-friendly **QUASAR** confirmation policy |
| **v0.17.0-beta** | **G — Pi fleet & payments** | **Turn on real payment rules** (storage / compute / bandwidth) and ship a **Pi Fleet Playbook**—a how-to for running edge nodes |

### Late morning: Mesh growth and satellite uplink

| Release | Wave | What it does (everyday words) |
|---------|------|-------------------------------|
| **v0.18.0-beta** | **H — Gossip** | **Nodes share peer lists with each other** beyond the local network—like word-of-mouth discovery for the mesh |
| **v0.19.0-beta** | **I — Starlink handoff** | When a **brief satellite or LTE uplink** appears, the node **automatically uploads queued bundles** to the coordinator—even outside normal flush schedules |

### Documentation and public materials (Tuesday)

| Deliverable | What it is |
|-------------|------------|
| **Symbiotic Vision white paper** (MD + Word + slides + infographic) | A partner-friendly explanation of the full stack |
| **Pi Fleet Playbook** (web download + install package) | Step-by-step guide to set up Raspberry Pi edge nodes |
| **19 GitLab beta release pages** | Public version history from v0.7.3 through v0.19.0-beta |
| **Live coordinator** | All APIs and enforcement flags verified at bloodstonewallet.mytunnel.org |

---

## How Blurt fits in—step by step

This is the **reader-friendly flow** we implemented across the two days:

### Step 1 — Post on Blurt
A creator publishes text or media on Blurt as usual.

### Step 2 — Anchor trust
The system records **provenance** (Wave A): a verifiable link between the Blurt post and mesh files.

### Step 3 — Store on the mesh
Files are chunked and stored across **Bloodstone mesh nodes** (Layer 2). Readers can stream video with normal playback (HTTP Range).

### Step 4 — Embed in Blurt (Condenser)
**Layer 5** provides embed HTML and standalone pages so Blurt’s Condenser editor can show mesh-hosted video and images.

### Step 5 — Pay with memos (BLURT → credits)
Creators send small **BLURT payments** with structured notes (memos), for example:
- `storage:<wallet>:<bytes>` — pay for storage space  
- `compute:<wallet>:<job_id>` — pay for compute work  
- `bandwidth:<wallet>:<bytes>` — pay for data transfer  

As of **Wave G**, these rules are **enforced**—no credits, no service.

### Step 6 — Sync offline (DTN)
Pi nodes in villages, studios, or disaster zones **queue bundles** while offline (Waves C, C+, E).

### Step 7 — Find neighbors (mDNS + gossip)
Nodes on the same LAN find each other (**mDNS**, Wave 14). Nodes farther apart learn about each other through **gossip** (Wave H).

### Step 8 — Upload when the internet returns
On a schedule (**flush windows**) or when **Starlink/satellite** briefly connects (Wave I), queued bundles **hand off** to the main coordinator.

### Step 9 — Stay healthy
Background **upkeep** (every ~5 minutes) syncs Blurt registry data, credits, DTN peers, gossip, and Starlink handoff.

---

## Payment rails (Layer 4)—simply

| You pay for | Memo looks like | Enforced since |
|-------------|-----------------|----------------|
| Storage | `storage:STONE123…:1000000` | v0.17 (Wave G) |
| Compute | `compute:STONE123…:job-abc` | v0.17 (Wave G) |
| Bandwidth | `bandwidth:STONE123…:5000000` | v0.17 (Wave G) |

Payments go to Blurt outpost accounts; the mesh **indexes** them and tracks remaining quota per STONE wallet.

---

## Pi fleet—what we gave operators

The **Pi Fleet Playbook** (Wave G) includes:

1. Install portal + mesh software on a Raspberry Pi  
2. Enable **mDNS** so the node advertises itself on the LAN  
3. Enable **TLS** for secure peer sync (HTTPS :8443)  
4. Turn on **memo enforcement** and DTN auto-heal  
5. Run **gossip** and **Starlink handoff** in background upkeep  

Downloads: https://bloodstonewallet.mytunnel.org/downloads/

---

## Where we ended up (July 8 evening, Pacific)

| Metric | Status |
|--------|--------|
| Latest release | **v0.19.0-beta** (Wave I) |
| Live roadmap | Waves **A–H** complete · Wave **I** (Starlink handoff) complete |
| Memo enforcement | **On** (storage, compute, bandwidth) |
| GitLab beta releases | **19** tagged versions with public release notes |
| DTN peers (lab) | ~8 registered peers |
| Symbiotic Vision docs | Published to downloads |

**Live check:** https://bloodstonewallet.mytunnel.org/api/convergence/status

---

## What’s next (not done in these two days)

- **Offline-first Condenser** — full social reader that works without the public internet  
- **Planetary-scale quorum** — many more nodes worldwide (2030+ horizon)  
- **Bridges and atomic swaps** — deeper STONE ↔ BLURT economy  

---

## Glossary

| Term | Plain meaning |
|------|----------------|
| **Blurt** | Censorship-resistant social layer; posts and accounts on a public chain |
| **Bloodstone / STONE** | Storage mesh and cryptocurrency for paying node operators |
| **Convergence** | The combined Blurt + Bloodstone product stack |
| **DTN** | “Delay-tolerant networking”—sync that works when the internet is spotty |
| **Mesh** | Many small nodes sharing files instead of one big data center |
| **Memo** | A short payment note attached to a BLURT transfer |
| **Pi fleet** | Raspberry Pi computers acting as local mesh edge nodes |
| **Gossip** | Nodes telling each other about other nodes |
| **Starlink handoff** | Uploading queued data during a short satellite connection |

---

*Prepared July 8, 2026 · Bloodstone LLC · For community, partners, and operators*