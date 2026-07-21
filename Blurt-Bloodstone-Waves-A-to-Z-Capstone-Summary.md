# Blurt x Bloodstone Convergence Stack
## Complete Work Summary - Wave A through Capstone Z

**Document version:** 1.1  
**Date:** July 8, 2026  
**Latest release:** v0.36.0-beta (Wave Z - Capstone)  
**Live coordinator:** https://bloodstonewallet.mytunnel.org  
**Stack status API:** https://bloodstonewallet.mytunnel.org/api/convergence/status  
**Formatted Word edition:** https://bloodstonewallet.mytunnel.org/downloads/Blurt-Bloodstone-Waves-A-to-Z-Capstone-Summary.docx

---

## Executive summary

Over the Blurt-Bloodstone convergence program, the team shipped **26 named waves (A-Z)** across **28 beta releases** (v0.9.0-beta through v0.36.0-beta), building a sovereign mesh stack that connects Blurt's censorship-resistant social layer with Bloodstone's memory fabric, edge DePIN economics, and on-device AI routing.

**Capstone Z** completes the tenant sovereign mesh: cross-region fleet quorum rollup, unified reconcile cycles, coordinator dispatch with tenant route hints, and a single dashboard view of the entire tenant fleet.

**Vision:** *Sovereign Mesh 2030 - Blurt trust anchor + Bloodstone memory fabric. Autonomous, self-healing nervous system - identity owns truth, hardware owns the network.*

---

## The six convergence layers

| Layer | Name | Primary waves | Status |
|-------|------|---------------|--------|
| 0 | Sovereign Identity (human + AI agents) | B | Beta |
| 1 | Trust Anchor (provenance + blogging) | A | Beta |
| 2 | Memory Fabric + DTN sync | C, C+, E, H, I, K | Beta |
| 3 | Edge DePIN (storage + compute + bandwidth + AI) | F, G, M-Z | Beta |
| 4 | Circulatory Economy (STONE + BLURT memo rails) | G, L | Beta (enforced) |
| 5 | Ambient UI (Condenser + Spatial WebXR) | D, J | Beta |

---

## Wave-by-wave release history

### Foundation - Trust, identity, and offline mesh (Waves A-G)

| Release | Wave | Summary |
|---------|------|---------|
| v0.9.0-beta | **A - Trust** | Digital provenance anchor (`bloodstone_provenance/v1`). Verifiable link between Blurt posts and mesh assets; trust badges in Condenser embeds. |
| v0.10.0-beta | **B - Agents** | Machine/AI agent identity manifests (`bloodstone_agent/v1`). Register autonomous creators with capability tags and STONE payout addresses. |
| v0.11.0-beta | **C - DTN** | Delay-tolerant networking bundles (`bloodstone-dtn-bundle-v1`). Portable 72-hour sync capsules for offline Pi nodes. |
| v0.12.0-beta | **D - Spatial** | Spatial WebXR manifests and AR overlays (`bloodstone_spatial_manifest/v1`). 3D scenes tied to Blurt posts; spatial data in DTN bundles. |
| v0.13.0-beta | **C+** | DTN hardening: deduplication, retry on failed upload, scheduled flush windows, peer discovery, bundle cleanup. |
| v0.14.0-beta | **mDNS** | LAN peer discovery via `_bloodstone-dtn._tcp` and `_bloodstone-ai._tcp` - nodes find neighbors without manual IP configuration. |
| v0.15.0-beta | **E - TLS & alerts** | Encrypted HTTPS peer sync (port 8443) and forward-queue alerts when bundles are stuck pending or failed. |
| v0.16.0-beta | **F - Scale** | Compute job manifests (`bloodstone_compute_job/v1`), replication auto-heal, QUASAR-friendly confirmation policy. |
| v0.17.0-beta | **G - Pi fleet** | **Memo rail enforcement** for storage, compute, and bandwidth. Pi Fleet Playbook published; no credits, no service. |

### Scale, uplink, and planetary mesh (Waves H-L)

| Release | Wave | Summary |
|---------|------|---------|
| v0.18.0-beta | **H - Gossip** | DTN gossip protocol (`bloodstone_dtn_gossip/v1`). Peer and bundle rumor exchange beyond mDNS. |
| v0.19.0-beta | **I - Starlink handoff** | Satellite/LTE opportunistic uplink (`bloodstone_dtn_starlink/v1`). Auto-flush queued bundles when brief connectivity returns. |
| v0.20.0-beta | **J - Offline Condenser** | Offline-first social reader (`bloodstone_condenser_offline/v1`). Local feed playback without public internet. |
| v0.21.0-beta | **K - Planetary quorum** | Multi-region DTN quorum rollup (`bloodstone_dtn_planetary/v1`). Cross-region heal via gossip snapshots. |
| v0.22.0-beta | **L - Bridge swap** | BLURT <-> STONE atomic swap intents (`bloodstone_bridge_swap/v1`). HTLC-style bridge with enforcement. |

### On-device AI routing (Waves M-N)

| Release | Wave | Summary |
|---------|------|---------|
| v0.23.0-beta | **M - AI routing** | On-device AI routing scaffold (`bloodstone_ai_routing/v1`). Score local providers (Pi NPU, Android TFLite, llama.cpp); route inference jobs offline-first. |
| v0.24.0-beta | **N - Coordinator dispatch** | HTTP coordinator AI dispatch + callback delivery. Edge nodes submit; coordinator executes; results return via `/api/convergence/ai/callback`. |

### Fleet hardening and multi-tenant quotas (Waves O-R)

| Release | Wave | Summary |
|---------|------|---------|
| v0.25.0-beta | **O - Signed gossip + NPU detect** | HMAC-signed AI provider gossip snapshots (`bloodstone_ai_gossip_snapshot/v1`). Auto-detect Hailo/Coral NPU hardware on Pi edge nodes. |
| v0.26.0-beta | **P - Compute tenant** | Multi-tenant compute quota (`bloodstone_compute_tenant/v1`). Per-author FLOPS caps on shared Pi/STONE pools. |
| v0.27.0-beta | **Q - Inference shim + bandwidth** | llama.cpp inference shim on `:8081`, bandwidth tenant quota, fleet gossip signing enforcement. |
| v0.28.0-beta | **R - Storage tenant + DTN routes** | Multi-tenant storage quota. AI route assignments exported in DTN bundles (`ai-route-assignments.json`). |

### Tenant dashboard and fleet sync (Waves S-T)

| Release | Wave | Summary |
|---------|------|---------|
| v0.29.0-beta | **S - Tenant dashboard** | Unified multi-tenant dashboard (compute + bandwidth + storage). Blurt AI provider broadcast. ONNX/TFLite inference delegates in shim. |
| v0.30.0-beta | **T - Fleet sync** | Tenant binding sync via DTN bundles (`tenant-bindings.json`) and gossip (`tenant_snapshots`). AI broadcast queue; auto-tenant on submit. |

### Signed fleet, quorum, and NPU execution (Waves U-W)

| Release | Wave | Summary |
|---------|------|---------|
| v0.31.0-beta | **U - Signed tenant fleet** | HMAC-signed tenant fleet snapshots. Dashboard web UI at `/convergence/tenant`. NPU-aware inference shim. DTN auto-author resolution. |
| v0.32.0-beta | **V - Tenant quorum** | Fleet-wide tenant snapshot quorum (`bloodstone_tenant_fleet_quorum/v1`). N-of-M peer agreement before bindings apply. Blurt tenant manifest broadcast (`bloodstone_tenant_manifest/v1`). Hailo/Coral NPU execution (not just detection). |
| v0.33.0-beta | **W - Submit gate + NPU models** | Quorum-gated compute/AI submit (`TENANT_SUBMIT_QUORUM_REQUIRE`). Per-author NPU model bindings with probe validation. Dashboard quorum panel. |

### AI routing, gossip, and route ledger (Waves X-Y)

| Release | Wave | Summary |
|---------|------|---------|
| v0.34.0-beta | **X - Tenant AI routing** | Tenant NPU-aware AI provider scoring (`tenant_ai_route.py`). Manifest gossip across fleet. NPU model probe-on-bind. |
| v0.35.0-beta | **Y - Route ledger + upkeep** | Route assignment ledger (`bloodstone_tenant_route_ledger/v1`). Coordinator tenant dispatch with `tenant_route` payload. Unified tenant upkeep cycle (quorum, gossip, broadcast, registry). NPU probe-on-bind (`TENANT_NPU_PROBE_ON_BIND`). |

### Capstone - Sovereign tenant mesh (Wave Z)

| Release | Wave | Summary |
|---------|------|---------|
| v0.36.0-beta | **Z - Capstone** | **Tenant planetary quorum** (`bloodstone_tenant_planetary/v1`) - cross-region fleet quorum rollup via `tenant_planetary_snapshots`. **Tenant sovereign mesh** (`bloodstone_tenant_sovereign/v1`) - capstone status aggregating all tenant subsystems + `reconcile_sovereign_mesh()`. Coordinator dispatch uses inbound `tenant_route`, submit-gate check, route ledger on success. Dashboard Wave Z badge + sovereign summary panel. |

**Live roadmap string:** `Wave A-Y complete | Wave Z: tenant planetary quorum + sovereign mesh reconcile complete`

---

## Capstone Z - technical detail

### New modules

| Module | Format ID | Purpose |
|--------|-----------|---------|
| `tenant_planetary_quorum.py` | `bloodstone_tenant_planetary/v1` | Cross-region tenant fleet quorum rollup; gossips `tenant_planetary_snapshots` |
| `tenant_sovereign.py` | `bloodstone_tenant_sovereign/v1` | Capstone unified status + `reconcile_sovereign_mesh()` / `reconcile_fleet()` |

### Coordinator dispatch enhancements

- Extracts `tenant_route` from inbound dispatch payload (or resolves from job)
- Runs `check_submit_allowed()` before accepting inference jobs
- Records route ledger assignment on coordinator dispatch success
- Passes `tenant_spec` to `dispatch_inference_job()` for NPU-aware execution

### Unified upkeep (extended)

Each `upkeep_tenant()` cycle now includes:

1. Fleet quorum update + satisfied binding apply
2. Broadcast queue + registry sync
3. Manifest gossip snapshots
4. Route ledger gossip snapshots
5. Planetary tenant quorum rollup

Background sync (`sync-blurt-convergence.py`) calls `reconcile_sovereign_mesh()` after tenant upkeep.

### New APIs (Wave Z)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/convergence/tenant/planetary/status` | GET | Cross-region tenant quorum rollup status |
| `/api/convergence/tenant/planetary/snapshots` | GET | Build planetary gossip snapshots |
| `/api/convergence/tenant/sovereign/status` | GET | Capstone sovereign mesh summary + subsystems |
| `/api/convergence/tenant/sovereign/reconcile` | POST | Run full sovereign reconcile cycle |

### Gossip extensions

`dtn_gossip.build_exchange_payload()` now includes `tenant_planetary_snapshots`. Ingest records `tenant_planetary_votes_recorded` and triggers rollup update.

---

## Payment rails (Layer 4)

Enforced since Wave G (v0.17.0-beta):

| Rail | Memo format | Outpost account |
|------|-------------|-----------------|
| Storage | `storage:<STONE_ADDRESS>:<bytes>` | Blurt outpost |
| Compute | `compute:<STONE_ADDRESS>:<job_id>` | DePIN outpost |
| Bandwidth | `bandwidth:<STONE_ADDRESS>:<bytes>` | DePIN outpost |

Multi-tenant per-author caps (Waves P, Q, R) layer on top of wallet-level enforcement for Pi fleet operators sharing hardware.

---

## End-to-end content flow

1. Blurt post (truth)
2. Provenance anchor (Wave A)
3. Mesh chunks + manifest (Layer 2)
4. Condenser embed / offline reader (Waves D, J)
5. Memo payment (Wave G)
6. DTN bundle queue (Waves C, E)
7. Gossip peer discovery (Wave H)
8. Planetary quorum heal (Wave K)
9. Starlink/satellite handoff (Wave I)
10. Inference job submit (Wave F)
11. On-device AI routing (Wave M)
12. Coordinator dispatch (Wave N)
13. Tenant fleet sync + quorum (Waves T, V)
14. Tenant AI route + ledger (Waves X, Y)
15. Sovereign mesh reconcile (Wave Z)

---

## Key manifest and format IDs

| Format ID | Wave | Domain |
|-----------|------|--------|
| `bloodstone_provenance/v1` | A | Trust anchor |
| `bloodstone_agent/v1` | B | Agent identity |
| `bloodstone-dtn-bundle-v1` | C | DTN sync |
| `bloodstone_spatial_manifest/v1` | D | Spatial WebXR |
| `bloodstone_dtn_gossip/v1` | H | Peer gossip |
| `bloodstone_dtn_starlink/v1` | I | Satellite handoff |
| `bloodstone_condenser_offline/v1` | J | Offline reader |
| `bloodstone_dtn_planetary/v1` | K | Planetary DTN quorum |
| `bloodstone_bridge_swap/v1` | L | Atomic swaps |
| `bloodstone_ai_routing/v1` | M | AI routing |
| `bloodstone_ai_provider/v1` | M | AI provider manifests |
| `bloodstone_ai_gossip_snapshot/v1` | O | Signed gossip |
| `bloodstone_compute_job/v1` | F | Compute jobs |
| `bloodstone_tenant_fleet_quorum/v1` | V | Tenant quorum |
| `bloodstone_tenant_manifest/v1` | V | Tenant broadcast |
| `bloodstone_tenant_submit_gate/v1` | W | Submit gate |
| `bloodstone_tenant_route_ledger/v1` | Y | Route ledger |
| `bloodstone_tenant_planetary/v1` | Z | Tenant planetary quorum |
| `bloodstone_tenant_sovereign/v1` | Z | Sovereign mesh |

---

## Pi fleet operator checklist

1. Install portal + mesh on Raspberry Pi (Wave G playbook)
2. Enable mDNS LAN discovery (v0.14)
3. Enable TLS peer sync on :8443 (Wave E)
4. Turn on memo enforcement (Wave G)
5. Run gossip + Starlink handoff in upkeep (Waves H, I)
6. Register AI inference shim on :8081 (Wave Q)
7. Bind per-author tenant quotas (Waves P, Q, R)
8. Configure fleet quorum N-of-M (Wave V)
9. Set `AI_GOSSIP_SIGNING_KEY` for signed snapshots (Waves O, U)
10. Monitor sovereign mesh at `/api/convergence/tenant/sovereign/status` (Wave Z)

**Downloads:** https://bloodstonewallet.mytunnel.org/downloads/

---

## Test coverage

Smoke tests exist for Waves O through Z:

| Test file | Wave | Tests |
|-----------|------|-------|
| `test_ai_wave_o.py` | O | Signed gossip, NPU detect |
| `test_ai_wave_p.py` | P | Compute tenant quota |
| `test_ai_wave_q.py` | Q | Bandwidth tenant, inference shim |
| `test_ai_wave_r.py` | R | Storage tenant, DTN route export |
| `test_ai_wave_s.py` | S | Tenant dashboard, broadcast |
| `test_ai_wave_t.py` | T | Fleet sync, broadcast queue |
| `test_ai_wave_u.py` | U | Signed fleet, dashboard UI |
| `test_ai_wave_v.py` | V | Fleet quorum, manifest broadcast |
| `test_ai_wave_w.py` | W | Submit gate, NPU models |
| `test_ai_wave_x.py` | X | Tenant AI routing, manifest gossip |
| `test_ai_wave_y.py` | Y | Route ledger, unified upkeep |
| `test_ai_wave_z.py` | Z | Planetary quorum, sovereign reconcile |

Run: `python3 -m unittest chain_mesh.tests.test_ai_wave_*`

---

## Architecture at Capstone Z

**Blurt (trust anchor)** - posts, memos, custom_json manifests

**Coordinator** (`bloodstonewallet.mytunnel.org`) - convergence APIs, AI dispatch, tenant sovereign status

**Pi fleet edge nodes** - portal :8887, inference shim :8081, mDNS + TLS gossip, tenant quorum, route ledger, NPU execution, sovereign reconcile (upkeep every ~5 min)

Data flows down the stack via DTN bundles, gossip, and Starlink/satellite handoff between coordinator and edge nodes.

---

## Metrics at Capstone Z (July 8, 2026)

| Metric | Value |
|--------|-------|
| Beta releases shipped | v0.9.0 through v0.36.0-beta (28 tags) |
| Named waves complete | A through Z (26 waves + C+ and mDNS) |
| Memo enforcement | On (storage, compute, bandwidth) |
| AI routing wave label | Z |
| DTN sync wave label | Z |
| Tenant sovereign format | `bloodstone_tenant_sovereign/v1` |
| GitLab latest tag | `v0.36.0-beta` @ `d58a803` |

---

## Glossary

| Term | Meaning |
|------|---------|
| **Blurt** | Censorship-resistant social layer; posts and accounts on a public chain |
| **Bloodstone / STONE** | Storage mesh cryptocurrency; pays node operators |
| **Convergence** | Combined Blurt + Bloodstone product stack |
| **DTN** | Delay-tolerant networking - sync when internet is spotty |
| **DePIN** | Decentralized physical infrastructure - edge nodes earn for storage/compute/bandwidth |
| **Memo** | Short payment note on a BLURT transfer |
| **Gossip** | Nodes sharing peer lists and snapshots with each other |
| **Quorum** | N-of-M agreement before state is accepted |
| **Sovereign mesh** | Capstone tenant fleet status + reconcile (Wave Z) |
| **Tenant** | Per-Blurt-author resource binding on shared Pi hardware |

---

## Related documents

- Symbiotic Vision white paper: https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Symbiotic-Vision-White-Paper.md
- Pi Fleet Playbook: https://bloodstonewallet.mytunnel.org/downloads/
- Wave M design: https://bloodstonewallet.mytunnel.org/downloads/Wave-M-On-Device-AI-Routing-Design.md
- Starlink handoff response: https://bloodstonewallet.mytunnel.org/downloads/Blurt-Starlink-Handoff-Response.md
- July 7-8 work summary: https://bloodstonewallet.mytunnel.org/downloads/Blurt-Bloodstone-Work-Summary-Jul-7-8-2026.md

---

*Prepared July 8, 2026 - Bloodstone LLC - Blurt x Bloodstone Convergence Stack - Waves A-Z Capstone Summary*