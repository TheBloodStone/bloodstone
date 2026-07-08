# Blurt–Bloodstone Convergence Stack

**Vision:** Sovereign Mesh 2030 — Blurt trust anchor + Bloodstone memory/compute fabric on home hardware.  
**Updated:** July 2026

---

## Layer map (live APIs)

| Layer | Name | Status | API |
|-------|------|--------|-----|
| 0 | Sovereign Identity (human + AI agents) | Beta | `POST /api/convergence/agent/register` · `GET /api/convergence/agent/verify` |
| 1 | Trust Anchor (provenance + blogging) | Beta | `POST /api/convergence/provenance/anchor` · `GET /api/convergence/provenance/verify` |
| 2 | Memory Fabric + DTN sync | Beta | `GET /api/convergence/dtn/export` · `POST /api/convergence/dtn/import` |
| 3 | Edge DePIN (storage + compute + bandwidth) | Beta | `POST /api/chain-mesh/v2/providers` (roles) |
| 4 | Circulatory Economy (memo rails) | Beta | `GET /api/convergence/depin/quota` · storage/compute/bandwidth |
| 5 | Ambient UI (Condenser + Spatial WebXR) | Beta | `GET /api/convergence/spatial/embed` · `/convergence/spatial/{author}/{scene_id}` |

**Stack status:** `GET /api/convergence/status`

---

## Layer 0 — AI agent identity

Blurt `custom_json` id: `bloodstone_agent/v1`

Machine identity manifest: Blurt author + STONE payout address + capability tags (`publish`, `compute`, `storage`, `bandwidth`, `sensor`, `provenance`, `relay`).

```bash
curl -s -X POST https://bloodstonewallet.mytunnel.org/api/convergence/agent/register \
  -H 'Content-Type: application/json' \
  -d '{
    "blurt_author":"megadrive",
    "stone_address":"STONE1YourAddressHere",
    "agent_id":"field-reporter-01",
    "capabilities":["publish","compute","provenance"],
    "display_name":"Field Reporter Bot"
  }'
```

Verify indexed agent:

```bash
curl -s 'https://bloodstonewallet.mytunnel.org/api/convergence/agent/verify?agent_id=field-reporter-01'
```

Autonomous publish scaffold (agent + blog manifest + memo rail hints):

```bash
curl -s -X POST https://bloodstonewallet.mytunnel.org/api/convergence/agent/publish-flow \
  -H 'Content-Type: application/json' \
  -d '{"blurt_author":"megadrive","stone_address":"STONE1...","post_id":"agent-dispatch-01","title":"Autonomous dispatch"}'
```

---

## Layer 1 — Trust Anchor (digital provenance)

Blurt `custom_json` id: `bloodstone_provenance/v1`

Post-Truth Engine: anchor content hash + mesh merkle root on Blurt; verify against live Chain Mesh manifest.

```bash
curl -s -X POST https://bloodstonewallet.mytunnel.org/api/convergence/provenance/anchor \
  -H 'Content-Type: application/json' \
  -d '{
    "author":"megadrive",
    "asset_key":"assets/blurt/media/my-article/video.mp4",
    "content_sha256":"<64-hex-sha256>",
    "title":"Field capture",
    "device_id":"pi-edge-01"
  }'
```

Response includes `blurt_custom_json` for Blurt broadcast, `badge_html` for Condenser embeds, and `verify_url`.

Verify (mesh + indexed anchor):

```bash
curl -s 'https://bloodstonewallet.mytunnel.org/api/convergence/provenance/verify?asset_key=assets/blurt/media/my-article/video.mp4'
```

Condenser embed pages (Layer 5) show the provenance badge when mesh media resolves.

---

## Layer 1 — Blog post manifests

Blurt `custom_json` id: `bloodstone_post_manifest/v1`

Stores **pointers only** — media lives on Chain Mesh (`assets/blurt/media/<post_id>/…`).

```bash
curl -s -X POST https://bloodstonewallet.mytunnel.org/api/convergence/blog/manifest \
  -H 'Content-Type: application/json' \
  -d '{"post_id":"my-article","author":"megadrive","asset_keys":["assets/blurt/media/my-article/video.mp4"],"title":"My Post"}'
```

Response includes `blurt_custom_json` for Blurt backend broadcast + `embed_html` for Condenser.

---

## Layer 2 — DTN sync bundles (Wave C)

Format: `bloodstone-dtn-bundle-v1` — portable capsule with Blurt anchor diffs + optional mesh chunks.

Default sync window: **72 hours** (`DTN_SYNC_WINDOW_SEC`). Pi nodes run offline, queue bundles, flush on brief uplink.

**Export** (metadata + optional base64 for small bundles):

```bash
curl -s 'https://bloodstonewallet.mytunnel.org/api/convergence/dtn/export?node_id=pi-edge-01&include_chunks=1'
```

**Download zip:**

```
/api/convergence/dtn/export/download?node_id=pi-edge-01
```

**Import** (coordinator or peer):

```bash
curl -s -X POST https://bloodstonewallet.mytunnel.org/api/convergence/dtn/import \
  -H 'Content-Type: application/json' \
  -d '{"data_b64":"<zip-bytes-base64>"}'
```

**Store-and-forward** (no continuous uplink):

```bash
# Queue bundle from peer
curl -s -X POST .../api/convergence/dtn/forward/submit -d '{"data_b64":"...","from_node_id":"pi-edge-02"}'

# Flush pending bundles when uplink returns
curl -s -X POST .../api/convergence/dtn/forward/flush
```

**Regional replication quorum** (N-of-M scaffold):

```bash
curl -s -X POST .../api/convergence/dtn/replication/check -d '{"region":"eu-west"}'
curl -s '.../api/convergence/dtn/replication/status?region=eu-west'
```

Bundle contents: `blurt-anchors.json`, `provenance-anchors.json`, `agent-identities.json`, `spatial-manifests.json`, optional `chunks/`.

### DTN hardening (v0.13+)

| Feature | Config / API |
|---------|----------------|
| SHA256 dedup | Automatic on import + queue |
| Flush windows | `DTN_FLUSH_WINDOWS_UTC=02:00-02:30,14:00-14:30` · `GET …/dtn/flush-window` |
| Retry + backoff | `DTN_MAX_RETRIES=5` · `DTN_RETRY_BACKOFF_SEC=60,300,900,3600,7200` |
| Bundle TTL | `DTN_BUNDLE_TTL_SEC=604800` (7 days) |
| Peer discovery | mDNS `_bloodstone-dtn._tcp` + LAN heartbeat + `DTN_PEER_URLS` |
| mDNS broadcast | `bloodstone-dtn-mdns.service` on Pi · `POST …/dtn/mdns/register` |
| Compaction | `POST …/dtn/compact` — prune delivered, dedupe pending |
| Unified upkeep | `POST …/dtn/upkeep` — expire, compact, discover, quorum, flush |
| Quorum heal | `POST …/dtn/replication/heal` — queue minimal chunk bundles |

Force flush outside window: `POST …/dtn/forward/flush` with `{"force":true}`.

---

## Layer 2 — Mesh anchors

Blurt `custom_json` id: `chain_mesh_anchor` (RFC 2.0-lite)

Publish flow: `POST /api/chain-mesh/partner/publish-asset` → returns `v2_lite.blurt_custom_json`.

Sync registry: `POST /api/chain-mesh/v2/blurt/sync` (automated via upkeep cron).

---

## Layer 4 — Storage credit rail

Send BLURT to `@bloodstone-storage` with memo:

```
storage:<STONE_ADDRESS>:<bytes>
```

Example: `storage:STONE1abc...xyz:1073741824` (1 GiB)

Or send BLURT without memo — credits `1 GB per 1 BLURT` (configurable via `STORAGE_BYTES_PER_BLURT`).

Check quota:

```bash
curl -s 'https://bloodstonewallet.mytunnel.org/api/convergence/storage/quota?stone_address=YOUR_STONE_ADDRESS'
```

Set `STORAGE_CREDIT_ENFORCE=1` to require credits on partner publish.

---

## Layer 4 — DePIN compute + bandwidth memo rails

Send BLURT to `@bloodstone-depin` (configurable via `BLURT_DEPIN_OUTPOST_ACCOUNT`):

**Compute** — credits FLOPS from BLURT amount (`COMPUTE_FLOPS_PER_BLURT`, default 1 GFLOP/BLURT):

```
compute:<STONE_ADDRESS>:<job_id>
```

Example: `compute:STONE1abc...xyz:inference-batch-42`

**Bandwidth** — credits relay bytes directly:

```
bandwidth:<STONE_ADDRESS>:<bytes>
```

Example: `bandwidth:STONE1abc...xyz:1073741824` (1 GiB relay quota)

Check combined DePIN quota:

```bash
curl -s 'https://bloodstonewallet.mytunnel.org/api/convergence/depin/quota?stone_address=YOUR_STONE_ADDRESS'
```

Per-rail endpoints: `/api/convergence/compute/quota` and `/api/convergence/bandwidth/quota`.

Provider registry supports roles: `storage`, `compute`, `bandwidth`, `sensor`, `coordinator`.

---

## Layer 5 — Spatial WebXR (Wave D)

Blurt `custom_json` id: `bloodstone_spatial_manifest/v1`

Spatial assets live under `assets/spatial/<scene_id>/model.glb` (glTF, USDZ supported).

**Create manifest** (geo-anchored AR overlay):

```bash
curl -s -X POST https://bloodstonewallet.mytunnel.org/api/convergence/spatial/manifest \
  -H 'Content-Type: application/json' \
  -d '{
    "scene_id":"museum-exhibit",
    "author":"megadrive",
    "post_id":"field-report-01",
    "title":"Bronze age artifact",
    "model_format":"glb",
    "placement":"geo",
    "geo":{"lat":51.5074,"lon":-0.1278,"alt_m":12,"heading_deg":90}
  }'
```

**WebXR embed page** (model-viewer + View in AR):

```
/convergence/spatial/megadrive/museum-exhibit
```

**AR overlay API** — nearby scenes or Blurt post anchor:

```bash
curl -s 'https://bloodstonewallet.mytunnel.org/api/convergence/spatial/overlay?lat=51.5074&lon=-0.1278&radius_m=500'
curl -s 'https://bloodstonewallet.mytunnel.org/api/convergence/spatial/overlay?author=megadrive&post_id=field-report-01'
```

DTN bundles include `spatial-manifests.json` for offline Pi sync.

---

## Condenser embed (Layer 5)

**API** — mesh embed fragment + Pi-hostable page:

```bash
curl -s 'https://bloodstonewallet.mytunnel.org/api/convergence/condenser/embed?author=megadrive&post_id=my-article&title=My%20Post'
```

**Standalone page** (iframe-friendly):

```
/convergence/embed/megadrive/my-article
```

Paste `embed_html` from the API into Blurt Condenser, or use `embed_html` from the blog manifest API. Direct playback:

```
/api/chain-mesh/asset/assets/blurt/media/<post_id>/video.mp4/download
```

Supports HTTP Range — HTML5 `<video>` compatible.

---

## Upkeep

`/root/sync-blurt-convergence.py` runs on upkeep cycle:
- Blurt registry sync (`chain_mesh_anchor` scan)
- Provenance anchor sync (`bloodstone_provenance/v1` scan)
- Agent identity sync (`bloodstone_agent/v1` scan)
- Spatial manifest sync (`bloodstone_spatial_manifest/v1` scan)
- Storage outpost transfer scan (`@bloodstone-storage`)
- DePIN outpost transfer scan (`@bloodstone-depin` — compute + bandwidth memos)
- DTN unified upkeep (`upkeep_dtn`) when `DTN_AUTO_FLUSH=1` — compact, peer discovery, quorum, windowed flush

---

*Blurt + Bloodstone = your content, your mesh, your economics.*