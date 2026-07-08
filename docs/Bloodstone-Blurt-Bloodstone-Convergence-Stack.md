# Blurt–Bloodstone Convergence Stack

**Vision:** Sovereign Mesh 2030 — Blurt trust anchor + Bloodstone memory/compute fabric on home hardware.  
**Updated:** July 2026

---

## Layer map (live APIs)

| Layer | Name | Status | API |
|-------|------|--------|-----|
| 0 | Sovereign Identity (Blurt keys) | Live | Partner token + `required_posting_auths` |
| 1 | Trust Anchor (provenance + blogging) | Beta | `POST /api/convergence/provenance/anchor` · `GET /api/convergence/provenance/verify` |
| 2 | Sharded Media (Chain Mesh) | Live | `GET /api/chain-mesh/v2/manifest` |
| 3 | Edge Serving (Pi/Android fleet) | Live | `POST /api/chain-mesh/v2/providers` |
| 4 | Economic Alignment (BLURT→STONE credits) | Beta | `GET /api/convergence/storage/quota` |
| 5 | Local Condenser UI | Beta | `GET /api/convergence/condenser/embed` · `/convergence/embed/{author}/{post_id}` |

**Stack status:** `GET /api/convergence/status`

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
- Storage outpost transfer scan

---

*Blurt + Bloodstone = your content, your mesh, your economics.*