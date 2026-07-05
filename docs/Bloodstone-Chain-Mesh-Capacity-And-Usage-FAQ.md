# Bloodstone Chain Mesh — Capacity, Chain Sync & Key Overwrite FAQ

*July 2026 · Technical reference (downloads only — not chain-mesh anchored)*

---

## Executive Summary

This document answers three common questions about Bloodstone Chain Mesh:

1. **How much data can the mesh hold relative to the entire coin supply?**
2. **Can mesh be used so you don't have to download the whole chain to get files?**
3. **Can files in the mesh be changed/overwritten using a stable key?**

**Short answers:** Mesh capacity is **not capped by STONE supply in consensus** — it scales with coordinator and peer disk plus economics. **Mesh files** are fetched independently of chain sync; **pruned nodes** still need tip sync but not full history. **Yes**, republishing with the same `asset_key` replaces the current revision.

---

## 1. How Much Data Can Be Stored in the Mesh vs. the Entire Coin Supply?

### 1.1 No consensus link between STONE supply and mesh bytes

There is **no rule in Bloodstone consensus** that ties mesh storage capacity to total coin supply. The blockchain stores manifests and optional BSM1 anchors — **not raw file bytes**. Capacity is limited by:

- Coordinator VPS disk
- Mesh peers willing to replicate chunks (`CHAIN_MESH_BACKUP_PCT`, default 10%)
- Per-file policy limits (operator-configurable)
- Storage economics (STONE/ETH billing — proposed/operator-funded)

### 1.2 Hard policy limits (per file, defaults)

| Setting | Default | Effect |
|---------|---------|--------|
| `CHAIN_MESH_MAX_ASSET_BYTES` | 64 MiB | Maximum size of one published file |
| `CHAIN_MESH_MAX_ASSET_CHUNKS` | 256 | Maximum chunks per file |
| `CHAIN_MESH_CHUNK_SIZE` | 256 KiB | 256 × 256 KiB = **64 MiB** max at default settings |

Operators can raise limits per tenant (e.g. Blurt: 256 MiB–1 GiB per file). That is infrastructure policy, **not a protocol ceiling**.

### 1.3 Live mesh snapshot (July 2026 coordinator)

| Metric | Value |
|--------|-------|
| Catalogued assets | 29 |
| Total catalogued file bytes | ~137 MiB |
| Coordinator chunk files | ~1,536 |
| Chain manifest (Time Capsule shards) | ~17 MiB (68 chunks) |

Current usage is modest. The practical ceiling is **disk + replication + economics**, not coin supply.

### 1.4 Economic framing (if storage were funded from STONE)

At the proposed partner rate **€0.019/GiB-month** (~**€19.5/TiB-month**):

| Supply reference | Approx. STONE | Illustrative storage @ €0.01/STONE |
|------------------|---------------|-------------------------------------|
| Era-0 PoW mint | ~105 million | ~€1.05M budget → **~54 TiB-month** |
| Premine (treasury) | ~200 million | ~€2M budget → **~100+ TiB-month** |

*Illustrative only — STONE spot price varies; no automatic allocation exists in code today.*

### 1.5 What actually limits growth

- **Peer replication** — each device backs a hash-selected subset of chunks (~10% by default)
- **Per-device announce cap** — `CHAIN_MESH_MAX_CHUNKS_PER_DEVICE` (default 32 chunks ≈ 8 MiB announced)
- **Overflow server** — hot/large bytes when mesh policy or replication lag requires spill
- **Billing** — partner quotas, cover cost on overflow (see Storage Cost Comparison Proposal)

**Bottom line:** The network could host **terabytes to petabytes** if enough STONE/ETH funds disk and peers replicate. Coin supply does not define a fixed mesh quota in consensus.

---

## 2. Can Mesh Avoid Downloading the Whole Chain to Get Files?

### 2.1 Yes — for mesh files

Mesh **assets** (APKs, white papers, Blurt media, etc.) are **independent** of blockchain sync:

```
GET /api/chain-mesh/asset/<asset_key>/download
GET /api/chain-mesh/chunk/<chunk_hash>
```

You fetch **only that file's chunks** — or a **byte Range** slice for HTML5 video (206 Partial Content). You do **not** need the full chain to download a mesh file.

### 2.2 Chain history — Time Capsule (different path)

Time Capsule archives block files to mesh so nodes can run a **pruned tip** (~550 MiB local) instead of retaining full history on disk:

> *History lives in the federated mesh so new nodes sync a pruned tip (~550 MiB) instead of downloading the full chain.*

### 2.3 Comparison table

| Goal | Need full chain download? |
|------|---------------------------|
| Download a mesh file (APK, doc, video) | **No** — asset/chunk API only |
| Run a pruned node + wallet | **No** — ~550 MiB pruned state + P2P tip sync |
| Restore old blocks from Time Capsule | Pull **mesh chunks**, not full historical chain sync |
| Validate entire chain from genesis (classic) | **Yes** — traditional full sync |

**Mesh is for files and archived blocks — not a complete replacement for pruned-node sync.**

### 2.4 VOD note

Recorded video on mesh uses the **HTTP Range proxy** (July 2026): browsers request `Range: bytes=…` and the coordinator loads only the chunk slices needed — not the entire file or chain.

---

## 3. Can You Change Files in the Mesh With a Key?

### 3.1 Yes — overwrite by `asset_key`

Publishing again with the **same `asset_key`** replaces the current catalog revision. The coordinator:

1. Accepts new content-addressed chunks
2. **UPDATE**s the existing `chain_assets` row for that key
3. Replaces the chunk manifest for that asset
4. Optionally anchors a new BSM1 tx for the new Merkle root

### 3.2 Writable keys API

```
GET /api/chain-mesh/writable-keys?prefix=assets/
```

Response includes `"overwrite": true` for each key. Official note:

> *Publish or submit with the same asset_key to replace the current revision. `assets/` keys are open to user submissions; `downloads/` requires admin publish token.*

### 3.3 Namespace rules

| Key prefix | Who can overwrite | Method |
|------------|-------------------|--------|
| `assets/...` | Users (submit → admin approve) or partner publish token (`assets/blurt/...`) | Republish same key |
| `downloads/...` | Admin / `CHAIN_MESH_PUBLISH_TOKEN` only | Republish same key (e.g. APK version bump) |

### 3.4 What “overwrite” means in practice

- The **URL/key stays stable** — e.g. `assets/blurt/s3/uploads/screen.mp4`
- The **bytes change** — new `file_sha256`, new Merkle root, new chunk list
- **Old chunks** may remain on disk (content-addressed dedup) until garbage-collected
- **Revision history** — optional BSM1 on-chain anchors per publish; catalog shows current version label

### 3.5 Example flows

**Admin APK update:**

```
downloads/bloodstone-miner-android-1.3.36.apk  →  same key, new file bytes, version label updated
```

**Blurt partner media:**

```
assets/blurt/s3/uploads/user123/video.mp4  →  partner token + publish-upload + publish-asset
```

**User submission (review queue):**

```
assets/my-creator-id/photo.jpg  →  submit-asset; admin approves; later resubmit same key to replace
```

---

## 4. Quick Reference

| Question | Answer |
|----------|--------|
| Mesh capped by coin supply? | **No** (consensus); economics + disk cap practical scale |
| Default max per file? | **64 MiB** (raiseable per tenant) |
| Get files without full chain? | **Yes** for mesh assets |
| Still need some chain data for a node? | **Yes** — pruned tip (~550 MiB), not full history |
| Overwrite file by key? | **Yes** — same `asset_key` replaces current revision |
| `assets/` vs `downloads/`? | Users/partners vs admin-only |

---

## 5. Related Documents

- [Chain Mesh Storage White Paper](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx)
- [Mesh File Upload White Paper](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Mesh-File-Upload-White-Paper.docx)
- [Storage Cost Comparison Proposal](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Storage-Cost-Comparison-Proposal.md)
- [S3 + Mesh Integration Operations Guide](https://bloodstonewallet.mytunnel.org/downloads/Bloodstone-Blurt-S3-Mesh-Integration-Operations-Guide.docx)

---

*Document version: 1.0 · July 2026 · Downloads only (not chain-mesh anchored)*