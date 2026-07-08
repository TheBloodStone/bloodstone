# Bloodstone Chain Mesh v2.0-Lite — System Overview

*July 2026 · Implementation guide aligned with [Megadrive's RFC](https://blurt.blog/rfc/@megadrive/rfc-bloodstone-chain-mesh-v2-0-lite-trustless-storage-layer-for-blurt)*

Bloodstone's response to Blurt RFC **v2.0-Lite**: a trustless storage layer that runs **alongside** the existing v1 coordinator. The mesh remains chunk plumbing; Blurt owns the manifest registry on Layer 1 (Blurt blockchain).

**Coordinator:** `https://bloodstonewallet.mytunnel.org`  
**Operator UI:** `https://bloodstonewallet.mytunnel.org/mining/network/blurt-mesh-v2`

---

## Executive summary

Megadrive's RFC asks to move from a centralized coordinator to:

- **Blurt Layer 1 registry** — manifests anchored via `custom_json` (`chain_mesh_anchor`)
- **DHT-based discovery** — no single server for chunk lookup
- **Independent storage providers** — Bloodstone is one provider among many
- **Trustless retrieval** — clients verify SHA-256 + Merkle root; no trust in any node

Bloodstone implemented **v2.0-Lite** as a hybrid: v1 coordinator and partner APIs stay live; v2 adds Blurt registry, provider registry, and cryptographic verification on top.

---

## RFC requirements → implementation

| RFC requirement | Bloodstone implementation |
|-----------------|---------------------------|
| Blurt Layer 1 registry (`custom_json` id `chain_mesh_anchor`) | `chain_mesh/blurt_registry_v2.py` |
| No coordinator for discovery — DHT + on-chain manifests | Manifest resolve: **Blurt registry first**, coordinator catalog fallback; provider registry as DHT placeholder |
| Independent storage providers | `chain_mesh/mesh_providers.py` — peer IDs, multiaddrs, chunk announcements |
| Trustless retrieval — verify hashes, don't trust providers | `chain_mesh/trustless_retrieval.py` |
| Bloodstone = software + optional provider | v1 coordinator remains; default provider registered; libp2p marked `dht_planned` |
| Hybrid with v1 | Partner publish still uses v1 catalog; v2 artifacts added on top |

---

## Two-layer architecture (RFC §10)

Megadrive's RFC separates **registry** (tenant-specific) from **chunk plane** (shared mesh).

### Layer 2 — Tenant registries

| Tenant | Registry | Properties |
|--------|----------|------------|
| **Blurt** | Blurt `custom_json` (`chain_mesh_anchor`) | Permanent, public, decentralized |
| **Other tenants** | Central DB, S3 JSON, private ledger, etc. | Mutable, private — mesh-agnostic |

Blurt resolves manifests from the Blurt chain (or Bloodstone's local index of those anchors). Other tenants may use the coordinator catalog or their own index.

### Layer 1 — Chunk plane (shared)

All tenants share:

- 256 KiB content-addressed chunks
- Coordinator chunk store (today)
- Provider registry + chunk-to-provider map (DHT placeholder)
- Planned: libp2p/Kademlia bootstrap nodes (read-only) + community storage daemons

The mesh does **not** care who uploaded a chunk or which registry indexes it. It stores `chunk_hash → data` and serves on request.

### Architecture diagram

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 2 — Registries (tenant-specific)                     │
│  ┌─────────────────────┐    ┌─────────────────────────────┐ │
│  │ Blurt custom_json   │    │ Bloodstone coordinator      │ │
│  │ chain_mesh_anchor   │    │ catalog (v1 fallback)       │ │
│  └──────────┬──────────┘    └──────────────┬──────────────┘ │
└─────────────┼──────────────────────────────┼────────────────┘
              │         resolve_manifest()   │
              └──────────────┬───────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  Layer 1 — Chunk plane                                      │
│  • Coordinator chunk store                                  │
│  • Provider registry (peer_id, multiaddr, chunk map)        │
│  • trustless_retrieval — verify SHA-256 + Merkle + file     │
│  • libp2p DHT — planned                                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Blurt anchor format (RFC §3.1)

Blurt backend broadcasts `custom_json` with id `chain_mesh_anchor` and JSON body version `2.0-lite`:

```json
{
  "v": "2.0-lite",
  "asset_key": "assets/blurt/media/99182/screen.mp4",
  "manifest_merkle_root": "<64-hex>",
  "file_sha256": "<64-hex>",
  "file_size": 168820736,
  "mime_type": "video/mp4",
  "provider_ids": ["bloodstone-coordinator-v1", "12D3KooW…"],
  "replication_factor": 3,
  "chunk_hashes": ["<sha256>", "..."],
  "uploader_signature": "",
  "timestamp": 1720000000
}
```

**Properties:** permanent in Blurt blocks, replicated to full nodes, publicly queryable, signed by uploader posting authority.

---

## Publish flow (RFC §5)

| Step | Action |
|------|--------|
| 1 | Blurt backend splits file into 256 KiB chunks |
| 2 | `POST /api/chain-mesh/partner/upload` (batches of 2 chunks) |
| 3 | `POST /api/chain-mesh/partner/publish-asset` — validates Merkle root + file SHA-256 |
| 4 | Bloodstone announces `chunk_hashes` to provider registry |
| 5 | Response includes **`v2_lite.blurt_custom_json`** — Blurt broadcasts to Layer 1 |
| 6 | Bloodstone indexes anchor locally for fast lookup |

### Trustless guarantee

Even if all providers are malicious, the client:

1. Verifies each chunk hash against the manifest
2. Verifies the manifest is anchored on Blurt (and signed by uploader)
3. Re-hashes the reassembled file and compares to `file_sha256`

---

## Retrieval flow (RFC §6)

1. **Resolve manifest** — Blurt registry → coordinator catalog fallback  
   `GET /mining/api/chain-mesh/v2/manifest?asset_key=…`
2. **Lookup providers** — `provider_ids` from manifest + chunk provider map
3. **Download chunks** — coordinator store today; direct provider fetch when DHT nodes ship
4. **Verify** — chunk SHA-256, Merkle root, final file SHA-256  
   `GET /mining/api/chain-mesh/v2/verify?asset_key=…`

| Threat | Mitigation |
|--------|------------|
| Provider serves corrupted data | Chunk hash verification |
| Wrong chunk order | Ordered `chunk_hashes` in manifest |
| Manifest tampered | Blurt on-chain anchor + uploader signature |
| Provider offline | Fallback to next `provider_id` in manifest |
| All providers offline | Manifest persists on Blurt; re-upload possible |

---

## API reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/mining/api/chain-mesh/v2/system` | GET | Architecture status, providers, layers |
| `/mining/api/chain-mesh/v2/manifest` | GET | Resolve manifest (`?asset_key=…`) |
| `/mining/api/chain-mesh/v2/verify` | GET/POST | Trustless chunk + file verification |
| `/mining/api/chain-mesh/v2/flow` | GET | Publish/retrieve phase diagram |
| `/mining/api/chain-mesh/v2/providers` | GET | List registered provider nodes |
| `/mining/api/chain-mesh/v2/providers` | POST | Register bootstrap or storage provider |
| `/mining/api/chain-mesh/v2/blurt/sync` | POST | Admin: index Blurt `chain_mesh_anchor` ops |
| `/mining/api/chain-mesh/partner/upload` | POST | Upload chunks (partner token) |
| `/mining/api/chain-mesh/partner/publish-asset` | POST | Publish manifest + v2 `custom_json` payload |

---

## Code modules

| Module | Role |
|--------|------|
| `chain_mesh/blurt_registry_v2.py` | Build/parse/index `chain_mesh_anchor` custom_json |
| `chain_mesh/mesh_providers.py` | Provider and bootstrap node registry; chunk announcements |
| `chain_mesh/trustless_retrieval.py` | Manifest validation; chunk + file verification |
| `chain_mesh/mesh_v2_lite.py` | Orchestration: resolve, publish hooks, system status |
| `chain_mesh/api.py` | HTTP payloads; partner publish extended with v2 artifacts |

---

## Phased rollout (RFC §11)

| Phase | Description | Status |
|-------|-------------|--------|
| **Phase 1** | Bloodstone primary provider + Blurt on-chain anchors | **Live** — partner publish returns `custom_json` |
| **Phase 2** | Blurt runs own storage provider VPS | Ready via `POST /v2/providers` |
| **Phase 3** | Community provider program | Same provider API |
| **DHT/libp2p** | Witness read-only bootstrap + storage daemons | Scaffolded; full libp2p daemon next |

### Phase 1 — Low risk (now)

- Upload to Bloodstone nodes via partner APIs
- Anchor manifests on Blurt via returned `custom_json`
- Include Bloodstone `provider_id` in manifests
- Verify everything client-side

### Phase 2 — Medium risk

- Blurt provisions dedicated VPS (not witness infra)
- Run Bloodstone storage daemon (or fork)
- Register node ID in manifests for critical files

### Phase 3 — Community

- Invite community provider nodes
- Include multiple `provider_ids` per manifest
- No single point of failure for chunk storage

---

## What Blurt backend does next

1. On each `partner/publish-asset` response, extract `v2_lite.blurt_custom_json`
2. Sign and broadcast as Blurt `custom_json` with posting authority (`required_posting_auths`)
3. Store `asset_key` in post metadata; serve via manifest lookup + verified chunk fetch
4. Optionally run read-only DHT bootstrap nodes on witness/community infra (RFC §4.1)
5. Optionally run a Blurt-operated storage provider (RFC §4.2)

---

## What Bloodstone cannot do (RFC §7.3)

- Modify or delete manifests on Blurt (Blurt owns the chain)
- Force clients to use only Bloodstone's provider
- Control Blurt's bootstrap nodes
- Hardfork or change Blurt

Bloodstone **can** open-source DHT/storage daemons, run an optional provider, and keep the coordinator as a compatibility layer.

---

## v1 vs v2.0-Lite comparison (RFC §9)

| Criteria | v1.0 (Bloodstone) | v2.0-Lite |
|----------|-------------------|-----------|
| Coordinator | Single server (SPOF for catalog) | Optional; Blurt registry authoritative |
| Manifest registry | Centralized API | Blurt `custom_json` + local index |
| Discovery | Centralized lookup | Provider registry + Blurt chain (DHT planned) |
| Trust model | Trust coordinator APIs | Trustless hash verification |
| Bloodstone dependency | Required for publish | Optional provider only |
| On-chain integration | BSM1 on Bloodstone (optional) | Blurt `custom_json` (primary for Blurt) |
| Blurt hardfork | No | No |
| Token usage | None | None |

---

## Related documents

| Document | URL |
|----------|-----|
| Megadrive RFC (source) | [blurt.blog/rfc/…](https://blurt.blog/rfc/@megadrive/rfc-bloodstone-chain-mesh-v2-0-lite-trustless-storage-layer-for-blurt) |
| Blurt send & use guide | [Bloodstone-Blurt-Mesh-Send-And-Use.md](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Blurt-Mesh-Send-And-Use.md) |
| Mesh storage partnership | [Bloodstone-Blurt-Mesh-Storage-Partnership-White-Paper.docx](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Blurt-Mesh-Storage-Partnership-White-Paper.docx) |
| Chain Mesh storage white paper | [Bloodstone-Chain-Mesh-Storage-White-Paper.docx](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx) |
| v2 operator UI | [blurt-mesh-v2](https://bloodstonewallet.mytunnel.org/mining/network/blurt-mesh-v2) |

---

*Document version: 1.0 · July 2026 · Bloodstone operator reference*