# Bloodstone × Blurt — Chain Mesh Send & Use

*July 2026 · v1.0 · For Blurt backend operators and integrators*

Practical guide: partner publish token, uploading files to Chain Mesh, serving them in Blurt posts and players, and optional S3 → mesh mirroring.

**Coordinator:** `https://bloodstonewallet.mytunnel.org`  
**Network Data Portal (manual tests):** `https://bloodstonewallet.mytunnel.org/mining/network-data`

---

## Executive summary

Bloodstone issues Blurt a **partner publish token** for the Chain Mesh storage layer. With it, Blurt can upload files, register manifests, and serve verified downloads to users — without a Bloodstone admin browser session.

- **Writes** under `assets/blurt/…` require the partner token.
- **Reads and playback** are public (no token).

This document intentionally does **not** contain the live token. Bloodstone delivers it out-of-band (secure channel, vault share, or ops handoff).

---

## 1. Partner publish token

Store the issued secret only in **server-side** secrets (environment variables, vault, CI). Rotate immediately if leaked. Never commit to git, embed in frontend JavaScript, or publish to Chain Mesh or public downloads.

### How to send the token

| Method | Example |
|--------|---------|
| HTTP header (recommended) | `X-Chain-Mesh-Publish-Token: <your-token>` |
| JSON body | `"publish_token": "<your-token>"` |
| Environment variable | `CHAIN_MESH_PUBLISH_TOKEN=<your-token>` |

### What the token allows

| Allowed | Not allowed |
|---------|-------------|
| Upload chunks via `POST /api/chain-mesh/partner/upload` | Write keys outside `assets/blurt/` (e.g. `downloads/`, arbitrary `assets/`) |
| Publish manifests via `POST /api/chain-mesh/partner/publish-asset` | Bypass admin review for non-Blurt community uploads |
| Overwrite an existing `assets/blurt/…` key (new revision, same URL path) | Access Bloodstone miner admin panel or wallet keys |
| Optional BSM1 on-chain anchor per file | Unlimited file size without coordinator limit configuration |

---

## 2. Chain Mesh in one page

Files are split into **256 KiB** content-addressed chunks (SHA-256 hash per chunk). A **manifest** records chunk order, whole-file SHA-256, Merkle root, MIME type, and display name. The coordinator catalogs manifests; mesh peers (phones, PCs, VPS) replicate chunks and can serve them on LAN port **18341**.

| Action | Meaning |
|--------|---------|
| **Send** | Upload chunks + publish manifest at a stable `asset_key` |
| **Use** | `GET` manifest metadata or download URL (public, no token) |
| **Replace** | Publish again at the same `asset_key` (new revision, same URL path) |

---

## 3. Asset key naming (Blurt namespace)

Every Blurt file must live under `assets/blurt/`. Pick a layout and keep it consistent so posts can embed predictable URLs.

| Pattern | Example | Use case |
|---------|---------|----------|
| `assets/blurt/s3/<s3-key>` | `assets/blurt/s3/uploads/user42/clip.mp4` | S3 mirror cron (default) |
| `assets/blurt/media/<post_id>/<file>` | `assets/blurt/media/99182/screen.mp4` | Direct backend upload |
| `assets/blurt/users/<account>/<file>` | `assets/blurt/users/alice/avatar.png` | Per-user namespace |
| `assets/blurt/hls/<id>/seg000.ts` | `assets/blurt/hls/live42/seg000.ts` | Optional HLS segments (roadmap) |

**Rule:** `asset_key` must start with `assets/blurt/`. The partner API rejects any other prefix even with a valid token.

---

## 4. How to send files to the mesh

### 4.1 Option A — S3 → Mesh mirror cron (recommended if you already use S3)

Keep Blurt's S3 bucket as the primary upload path. A cron job copies new or changed objects into the mesh for integrity, replication, and optional on-chain anchors.

1. User uploads in Blurt UI → Blurt backend PUTs to S3 (unchanged).
2. Cron runs `blurt-s3-mesh-mirror.py` on Blurt or Bloodstone infrastructure.
3. Script reads S3 object, chunks it, uploads via partner APIs, publishes manifest.
4. Mesh key defaults to `assets/blurt/s3/<original-s3-key>`.
5. State file tracks S3 ETag — skips unchanged objects on the next run.

**Environment:**

```bash
export AWS_ACCESS_KEY_ID=…
export AWS_SECRET_ACCESS_KEY=…
export AWS_REGION=eu-central-1
export CHAIN_MESH_PUBLISH_TOKEN=<your-token>
export BLOODSTONE_COORDINATOR=https://bloodstonewallet.mytunnel.org
```

**Example cron:**

```bash
python3 blurt-s3-mesh-mirror.py \
  --bucket YOUR_BUCKET \
  --prefix uploads/ \
  --mode remote \
  --state-file /var/lib/blurt/s3-mesh-mirror.json
```

Useful flags: `--dry-run`, `--force`, `--no-anchor`, `--limit N`, `--max-bytes N`.

See also: [S3 + Mesh Integration Operations Guide](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Blurt-S3-Mesh-Integration-Operations-Guide.docx).

### 4.2 Option B — Direct partner HTTP API (Blurt backend)

Two-step flow: upload all chunks, then register the manifest.

**Step 1 — Upload chunks**

```http
POST https://bloodstonewallet.mytunnel.org/api/chain-mesh/partner/upload
Content-Type: application/json
X-Chain-Mesh-Publish-Token: <your-token>
```

```json
{
  "device_id": "blurt-backend",
  "peer_kind": "partner",
  "chunks": [
    { "chunk_hash": "<sha256-hex>", "data_b64": "<base64>" }
  ]
}
```

Upload in **batches of 2 chunks** per request (~1 MiB JSON limit on strict proxies). Chunk size is 256 KiB except the last piece.

**Step 2 — Publish manifest**

```http
POST https://bloodstonewallet.mytunnel.org/api/chain-mesh/partner/publish-asset
Content-Type: application/json
```

```json
{
  "publish_token": "<your-token>",
  "asset_key": "assets/blurt/media/99182/screen.mp4",
  "display_name": "screen.mp4",
  "mime_type": "video/mp4",
  "file_size": 168820736,
  "file_sha256": "<hex>",
  "merkle_root": "<hex>",
  "anchor": true,
  "chunks": [
    { "chunk_hash": "…", "file_offset": 0, "size": 262144 }
  ]
}
```

Compute chunk hashes and Merkle root with the same algorithm as the mirror script, or request a reference implementation from Bloodstone.

### 4.3 Option C — Network Data Portal (manual test)

For one-off tests, open the [Network Data Portal](https://bloodstonewallet.mytunnel.org/mining/network-data). Production Blurt traffic should use **Option A or B** with the partner token — not the public community review queue.

---

## 5. How to use mesh files in Blurt

### 5.1 Public download URL (primary integration point)

```
GET https://bloodstonewallet.mytunnel.org/api/chain-mesh/asset/<asset_key>/download
```

Example:

```
https://bloodstonewallet.mytunnel.org/api/chain-mesh/asset/assets/blurt/s3/uploads/demo.mp4/download
```

Store `asset_key` in Blurt post metadata when the upload completes. Render posts with this HTTPS URL instead of (or alongside) the S3 URL during migration.

### 5.2 Video and audio embed (HTTP Range)

The download endpoint supports **Range** requests (`206 Partial Content`). HTML5 `<video>` and `<audio>` scrub and buffer the same way as S3 VOD.

```html
<video controls
  src="https://bloodstonewallet.mytunnel.org/api/chain-mesh/asset/assets/blurt/s3/uploads/screen.mp4/download">
</video>
```

| Query / header | Effect |
|----------------|--------|
| `Range: bytes=0-1048575` | `206 Partial Content` — first 1 MiB |
| No Range | `200 OK` full file, `Accept-Ranges: bytes` |
| `?inline=1` | `Content-Disposition: inline` for any MIME |
| `?attachment=1` | Force download attachment |

### 5.3 Metadata and search (no token)

```
GET /api/chain-mesh/asset/<asset_key>
GET /api/chain-mesh/search?q=blurt&limit=50
GET /api/chain-mesh/asset/<asset_key>/preview
```

Use metadata for file size, SHA-256, version label, chunk count, and optional on-chain anchor txid. Preview returns a text snippet or image thumbnail when supported.

### 5.4 Blurt traffic dashboard (public JSON)

```
GET https://bloodstonewallet.mytunnel.org/api/chain-mesh/partner/blurt/traffic
```

Human-readable page: [Blurt mesh traffic](https://bloodstonewallet.mytunnel.org/mining/blurt-mesh-traffic)

Weekly, monthly, and yearly stats for `assets/blurt/` downloads — useful for capacity planning and partner reporting.

### 5.5 Optional — users keep full files on device

Bloodstone miners and the Network Data Portal let end users **pin** a complete file plus all chunks on their phone or PC for offline backup and LAN sharing. No Blurt backend change is required; it is a client-side feature.

---

## 6. Updating and replacing files

Publish again at the **same** `asset_key` to ship a new version. The coordinator registers a new revision (new `file_sha256`, new chunk list). The download URL path stays the same; caches should key on ETag or `file_sha256`.

- **S3 mirror:** object ETag change triggers re-mirror on next cron run.
- **Direct API:** call `partner/publish-asset` with the same `asset_key` and new manifest.
- Optional `version` field in manifest helps Blurt show revision history in admin UI.

---

## 7. File size limits

Default coordinator policy is **64 MiB** per file (256 chunks × 256 KiB). Blurt tenant limits are raised for partner media — typically **256 MiB to 1 GiB** per file. Contact Bloodstone if a recording exceeds your configured cap.

```bash
CHAIN_MESH_MAX_ASSET_BYTES=268435456   # 256 MiB (example)
CHAIN_MESH_MAX_ASSET_CHUNKS=1024       # up to ~1 GiB at 256 KiB chunks
```

---

## 8. Security checklist

- Store `CHAIN_MESH_PUBLISH_TOKEN` only in server-side secrets — never in Blurt frontend JavaScript.
- Rotate the token if compromised; Bloodstone updates `secrets.conf` and sends a new value privately.
- Partner token cannot write outside `assets/blurt/` — community `assets/` still uses admin review.
- Downloads are public by design; do not put private keys or unencrypted credentials in mesh objects.
- Use HTTPS only; coordinator URL is `https://bloodstonewallet.mytunnel.org`.

---

## 9. Quick start checklist

| Step | Action | Owner |
|------|--------|-------|
| 1 | Save publish token in Blurt secrets (§1) | Blurt ops |
| 2 | Choose key layout (§3); test one file via partner API or mirror `--dry-run` | Blurt backend |
| 3 | Confirm download URL plays in HTML5 player (§5.2) | Blurt frontend |
| 4 | Deploy S3 mirror cron or wire backend upload adapter | Blurt backend |
| 5 | Swap post embeds from S3 URL to mesh download URL | Blurt frontend |
| 6 | Monitor `/api/chain-mesh/partner/blurt/traffic` | Both teams |

---

## 10. Related documents

| Document | URL |
|----------|-----|
| Blurt mesh storage partnership (economics & architecture) | [Bloodstone-Blurt-Mesh-Storage-Partnership-White-Paper.docx](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Blurt-Mesh-Storage-Partnership-White-Paper.docx) |
| S3 + mesh ops guide (mirror script, Range proxy, cron) | [Bloodstone-Blurt-S3-Mesh-Integration-Operations-Guide.docx](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Blurt-S3-Mesh-Integration-Operations-Guide.docx) |
| Chain Mesh storage white paper (protocol & peer model) | [Bloodstone-Chain-Mesh-Storage-White-Paper.docx](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx) |
| Mesh file upload white paper (chunking, manifests, anchors) | [Bloodstone-Mesh-File-Upload-White-Paper.docx](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Mesh-File-Upload-White-Paper.docx) |

For limit raises, token rotation, or integration review, contact Bloodstone via your existing Blurt partnership channel.