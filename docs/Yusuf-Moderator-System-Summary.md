# Bloodstone × Blurt — Moderator Brief for Yusuf

**Prepared for:** Yusuf (moderator & X writer)  
**From:** Bloodstone team  
**Date:** July 8, 2026  
**Live coordinator:** https://bloodstonewallet.mytunnel.org  
**Latest release:** v0.24.0-beta (Wave N)

---

## One-liner (pin this)

**Blurt owns truth. Bloodstone owns memory.** Together they form a censorship-resistant stack where posts are proven on-chain, files live on a mesh of edge nodes (including Raspberry Pis), and everything syncs back—even when the internet only comes back for a minute.

---

## What the system is

Think of it as **two layers built to work together:**

| Piece | Role | Plain English |
|-------|------|---------------|
| **Blurt** | Trust & social layer | Public ledger for posts, identity, and verifiable publishing |
| **Bloodstone** | Memory & mesh layer | Stores video, chunks, compute jobs, and AR assets across many small machines |
| **Convergence stack** | The glue | APIs, Pi fleet, payments, offline sync, and the live coordinator |

**Official vision:** *Sovereign Mesh 2030 — Blurt trust anchor + Bloodstone memory fabric*

**Tagline:** *Autonomous, self-healing nervous system — identity owns truth, hardware owns the network.*

**Who it’s for:** Bloggers, creators, off-grid operators, Pi hobbyists, and anyone who doesn’t want one company’s server to be the single point of failure for their content.

---

## The six layers (simple map)

1. **Identity** — Human and AI agents register on the mesh  
2. **Trust / publishing** — Provenance anchors tie Blurt posts to mesh files  
3. **Memory fabric + DTN** — Offline bundles, gossip, satellite handoff, planetary quorum  
4. **Edge DePIN** — Storage, compute, bandwidth, and on-device AI routing  
5. **Economy** — BLURT/STONE memo rails (`storage:`, `compute:`, `bandwidth:`) plus atomic swaps  
6. **Ambient UI** — Condenser embeds, offline reader, spatial WebXR  

All of this is **beta and live** on the coordinator—not a white paper only.

---

## What we shipped in ~two days (July 7–8, 2026)

This was not one bug fix. It was **fourteen convergence waves** and **sixteen beta releases** (v0.9 → v0.24), plus docs, fixes, and partner materials.

### Day 1 — Align the blueprint

- Matched the **Symbiotic Vision** white paper to what actually runs in production  
- Audited gaps: Pi fleet docs, payment enforcement, gossip, satellite uplink, AI routing  
- Synced public GitLab releases with the live coordinator  

### Day 2 — Ship in waves (Pacific time)

**Trust & mesh foundation (Waves A–G)**

| Release | Wave | What it does |
|---------|------|--------------|
| v0.9.0-beta | A — Trust | Digital provenance: prove where content came from |
| v0.10.0-beta | B — Agents | Machine/AI agent identities on the mesh |
| v0.11.0-beta | C — DTN | Offline bundles—zip up state, sync later |
| v0.12.0-beta | D — Spatial | AR/3D scenes tied to Blurt posts |
| v0.13.0-beta | C+ | DTN hardening: dedup, retry, flush windows |
| v0.14.0-beta | mDNS | Pi nodes announce themselves on LAN |
| v0.15.0-beta | E — TLS | Encrypted Pi-to-Pi sync + stuck-bundle alerts |
| v0.16.0-beta | F — Scale | Compute job manifests + replication auto-heal |
| v0.17.0-beta | G — Pi fleet | Real payment enforcement + Pi Fleet Playbook |

**Scale & uplink (Waves H–I)**

| Release | Wave | What it does |
|---------|------|--------------|
| v0.18.0-beta | H — Gossip | Nodes discover each other beyond the local network |
| v0.19.0-beta | I — Starlink handoff | Brief uplink triggers automatic flush of queued bundles |

**Advanced convergence (Waves J–N)**

| Release | Wave | What it does |
|---------|------|--------------|
| v0.20.0-beta | J | Offline Condenser reader |
| v0.21.0-beta | K | Planetary DTN quorum (multi-region rollup) |
| v0.22.0-beta | L | BLURT↔STONE bridge + atomic HTLC swaps |
| v0.23.0-beta | M | On-device AI routing (Pi, Android, LAN llama.cpp) |
| v0.24.0-beta | N | Coordinator AI HTTP dispatch + callback delivery |

**Live roadmap string:** `Wave A–M ✓ · Wave N: coordinator AI dispatch ✓`

---

## Standout stories Yusuf can write about

### 1. “Starlink isn’t the product—handoff is”

We wrote a partner document for Blurt answering: *“Starlink is just broadband—why is that groundbreaking?”*

**Answer:** Starlink is only the wire. The innovation is **DTN store-and-forward + opportunistic handoff**—the mesh queues work offline and pushes it upstream the instant any brief uplink appears.

**Downloads:**

- https://bloodstonewallet.mytunnel.org/downloads/Blurt-Starlink-Handoff-Response.md  
- https://bloodstonewallet.mytunnel.org/downloads/Blurt-Starlink-Handoff-Response.docx  

### 2. On-device AI on a Pi mesh (Waves M → N)

Not “AI in the cloud only.” Inference jobs can run on:

- Pi + llama.cpp  
- Android (TFLite) via LAN heartbeat  
- Coordinator fallback with HTTP callback when uplink is up  

**Live APIs:**

- `/api/convergence/ai/status`  
- `/api/convergence/ai/submit`  
- `/api/convergence/ai/dispatch`  
- `/api/convergence/ai/callback`  

### 3. QUASAR page fixed same day

`/quasar/` returned 404 because nginx wasn’t proxying it. Added proxy rules; verified **200** on the public URL.

### 4. We dogfood reliability

AI dispatch endpoints initially caused worker saturation (circular status probes, long timeouts). Fixed same session: fast validation, more workers, lightweight `/health` probes, uplink cache. Status now responds in ~0.13s.

---

## Soundbites for X (copy-paste ready)

1. *“Blurt proves the post. Bloodstone keeps the file alive. The mesh does the rest.”*

2. *“We didn’t build ‘Starlink integration.’ We built: queue while offline, flush when the sky opens.”*

3. *“Fourteen waves in two days. From provenance anchors to on-device AI routing on Raspberry Pis.”*

4. *“Your inference job doesn’t need AWS. It can run on the Pi in your shed, your Android on LAN, or queue until Starlink blinks on.”*

5. *“Censorship resistance isn’t a slogan—it’s chunks, bundles, gossip, and memo rails that enforce payment and replication.”*

6. *“v0.24.0-beta: coordinator AI dispatch is live. Edge nodes submit; coordinator executes; callback delivers the result.”*

---

## Suggested X thread (7 posts)

**Post 1 — Hook**  
“We shipped 14 convergence waves in ~48 hours. Here’s what Blurt × Bloodstone actually is—and why it matters for creators who don’t trust single servers. 🧵”

**Post 2 — The split**  
“Blurt = trust layer (who said what, on-chain). Bloodstone = memory fabric (files, video, mesh). Convergence = the APIs + Pi fleet that bind them.”

**Post 3 — Offline-first**  
“Nodes zip up state into DTN bundles. No uplink? Work queues locally. Uplink returns—even 60 seconds of Starlink—and handoff flushes automatically.”

**Post 4 — Economics**  
“Storage, compute, bandwidth paid via simple memos on BLURT→STONE rails. No credits, no service. Edge DePIN with enforcement.”

**Post 5 — AI at the edge**  
“Wave M/N: inference routes to local llama.cpp, Android TFLite, or coordinator dispatch with HTTP callback. Not cloud-only AI.”

**Post 6 — Proof it’s real**  
“Live coordinator: bloodstonewallet.mytunnel.org — status, DTN export/import, AI routing, bridge swaps, spatial embeds. Beta, not vapor.”

**Post 7 — CTA**  
“Pi Fleet Playbook + docs on GitLab. If you run edge nodes or write about sovereign media—this stack is built for you. Questions welcome.”

---

## Key links

| Resource | URL |
|----------|-----|
| Coordinator status | https://bloodstonewallet.mytunnel.org/api/convergence/status |
| AI routing status | https://bloodstonewallet.mytunnel.org/api/convergence/ai/status |
| QUASAR | https://bloodstonewallet.mytunnel.org/quasar/ |
| Starlink handoff doc | https://bloodstonewallet.mytunnel.org/downloads/Blurt-Starlink-Handoff-Response.md |
| This brief (MD) | https://bloodstonewallet.mytunnel.org/downloads/Yusuf-Moderator-System-Summary.md |
| This brief (DOCX) | https://bloodstonewallet.mytunnel.org/downloads/Yusuf-Moderator-System-Summary.docx |
| GitLab release | v0.24.0-beta |

---

## Tone guidance for Yusuf

**Do say:** offline-first, provenance, edge mesh, Pi fleet, creator sovereignty, BLURT+STONE economy  

**Don’t say:** “we invented Starlink” or “blockchain solves everything”  

**Angle:** Practical infrastructure for people who publish where networks are flaky and trust is earned, not assumed.

---

## Closing line for articles

*In two days we went from aligned blueprint to fourteen live waves—including planetary quorum, atomic bridge swaps, and on-device AI routing on edge hardware. Blurt holds the truth; Bloodstone holds the memory; the mesh holds the line when the uplink doesn’t.*

---

*Bloodstone LLC · Convergence coordinator · July 8, 2026*