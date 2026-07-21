# Bloodstone Mesh File Lookup v1

Resolve which **chunks** hold a mesh file so clients download **only those chunks** — not the full chain, not the whole coordinator catalog.

---

## How it works

```
1. BSM1 on-chain (optional)     → merkle_root + asset_id_prefix in OP_RETURN
2. Mesh catalog (coordinator)   → asset_key → ordered chunk hash list
3. GET /lookup                  → compact chunk list { h, o, s }
4. GET /chunk/<hash> per row    → 256 KiB content-addressed blob
5. Concatenate by offset        → verify file_sha256
```

**You never sync the blockchain to download a mesh file.** A pruned node is unrelated to file fetch. Lookup + chunk GET is sufficient.

---

## API endpoints

### Per-asset lookup (recommended)

```
GET /api/chain-mesh/asset/<asset_key>/lookup
GET /api/chain-mesh/asset/<asset_key>/lookup?range=0-1048575
```

### Universal query

```
GET /api/chain-mesh/lookup?key=<asset_key>
GET /api/chain-mesh/lookup?txid=<BSM1_txid>
GET /api/chain-mesh/lookup?merkle_root=<hex>
GET /api/chain-mesh/lookup?key=<key>&range=500-
```

### Chunk download

```
GET /api/chain-mesh/chunk/<chunk_hash>
```

### Full-file proxy (optional)

```
GET /api/chain-mesh/asset/<asset_key>/download
```

---

## Lookup response (example)

```json
{
  "ok": true,
  "protocol": "mesh-file-lookup-v1",
  "asset_key": "downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx",
  "file_size": 15437,
  "file_sha256": "abc123…",
  "merkle_root": "abc123…",
  "chunk_size": 262144,
  "chunk_count": 1,
  "chunks_needed": 1,
  "bytes_needed": 15437,
  "partial": false,
  "chunks": [
    { "i": 0, "h": "abc123…", "o": 0, "s": 15437 }
  ],
  "anchor": {
    "magic": "BSM1",
    "txid": "0a76402c…",
    "merkle_root": "abc123…"
  },
  "endpoints": {
    "chunk": "https://bloodstonewallet.mytunnel.org/api/chain-mesh/chunk/{chunk_hash}",
    "download": "https://bloodstonewallet.mytunnel.org/api/chain-mesh/asset/…/download"
  }
}
```

| Field | Meaning |
|-------|---------|
| `h` | chunk SHA-256 (content address) |
| `o` | byte offset in reconstructed file |
| `s` | chunk byte length |
| `partial` | true when `range` query trimmed chunk list |
| `bytes_needed` | sum of chunk sizes to fetch (may exceed range length) |

---

## On-chain link (BSM1)

BSM1 OP_RETURN commits **merkle_root** (52 bytes). The **chunk list** lives in the mesh catalog; lookup resolves:

```
BSM1 txid  →  anchor index  →  merkle_root  →  asset_key  →  chunks[]
```

Verify integrity: reconstruct file → SHA-256 must match `file_sha256` and BSM1 `merkle_root`.

---

## Client tools (in downloads)

### Python

```bash
export BLOODSTONE_COORDINATOR=https://bloodstonewallet.mytunnel.org

# Lookup only
python3 mesh-file-lookup.py --key downloads/foo.docx --json

# Partial range (VOD segment)
python3 mesh-file-lookup.py --key assets/blurt/s3/video.mp4 --range 0-1048575 --json

# Fetch chunks and reconstruct
python3 mesh-file-lookup.py --key downloads/foo.docx --fetch -o foo.docx

# Resolve by BSM1 anchor
python3 mesh-file-lookup.py --txid 0a76402c… --fetch -o verified.bin
```

### JavaScript

```javascript
import { lookupMeshFile, fetchMeshFileFromLookup } from "./mesh-file-lookup.js";

const coordinator = "https://bloodstonewallet.mytunnel.org";
const lookup = await lookupMeshFile({
  coordinator,
  assetKey: "downloads/Bloodstone-Chain-Mesh-Storage-White-Paper.docx",
});

const bytes = await fetchMeshFileFromLookup(lookup, { coordinator });
// bytes is Uint8Array — only lookup.chunks_needed chunks were fetched
```

---

## Overwrite by key

Republishing the same `asset_key` updates the lookup chunk list. Clients should re-run lookup after `version` or `file_sha256` changes.

---

## Files

| File | Purpose |
|------|---------|
| `mesh-file-lookup.py` | CLI lookup + chunk fetch |
| `mesh-file-lookup.js` | Browser / Node client library |
| `Bloodstone-Mesh-File-Lookup.md` | This document |

*Downloads only — not chain-mesh anchored · July 2026*