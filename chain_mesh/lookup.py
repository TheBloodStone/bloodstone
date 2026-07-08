"""Mesh file lookup — map asset keys / BSM1 anchors to chunk hashes for partial fetch."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from chain_mesh import db as mesh_db
from chain_mesh.assets import asset_manifest_payload, parse_bytes_range
from chain_mesh.config import CHUNK_SIZE
from chain_mesh.store import chunk_exists


def _compact_chunk_row(chunk: Dict[str, Any], *, index: int) -> Dict[str, Any]:
    return {
        "i": index,
        "h": str(chunk.get("chunk_hash") or "").strip().lower(),
        "o": int(chunk.get("file_offset") or 0),
        "s": int(chunk.get("size") or 0),
    }


def chunks_overlapping_range(
    chunks: List[Dict[str, Any]],
    start: int,
    end: int,
) -> List[Dict[str, Any]]:
    """Return chunk rows whose byte span intersects [start, end] inclusive."""
    selected: List[Dict[str, Any]] = []
    for idx, chunk in enumerate(chunks):
        offset = int(chunk.get("file_offset") or 0)
        size = int(chunk.get("size") or 0)
        if size <= 0:
            continue
        chunk_end = offset + size - 1
        if chunk_end < start or offset > end:
            continue
        selected.append({**chunk, "_index": idx})
    return selected


def file_lookup_payload(
    asset_key: str,
    *,
    byte_range: Optional[Tuple[int, int]] = None,
    public_root: str = "",
) -> Dict[str, Any]:
    """
    Compact lookup record: which chunks hold the file, without chunk bytes.
    Clients fetch only listed chunks via GET /api/chain-mesh/chunk/<hash>.
    """
    manifest = asset_manifest_payload(asset_key)
    if not manifest.get("ok"):
        return manifest

    key = str(manifest.get("asset_key") or asset_key).strip()
    all_chunks = sorted(
        list(manifest.get("chunks") or []),
        key=lambda c: int(c.get("file_offset") or 0),
    )
    file_size = int(manifest.get("file_size") or 0)

    range_start = 0
    range_end = file_size - 1 if file_size > 0 else 0
    partial = False
    if byte_range is not None:
        range_start, range_end = byte_range
        partial = True
        selected = chunks_overlapping_range(all_chunks, range_start, range_end)
    else:
        selected = [{**c, "_index": i} for i, c in enumerate(all_chunks)]

    compact = []
    bytes_needed = 0
    for row in selected:
        idx = int(row.get("_index", 0))
        compact.append(_compact_chunk_row(row, index=idx))
        bytes_needed += int(row.get("size") or 0)

    coordinator_has = sum(1 for row in selected if row.get("coordinator_has"))
    root = (public_root or "").rstrip("/")
    encoded_key = key.replace(" ", "%20")

    endpoints = {
        "lookup": f"/api/chain-mesh/asset/{encoded_key}/lookup",
        "manifest": f"/api/chain-mesh/asset/{encoded_key}",
        "chunk": "/api/chain-mesh/chunk/{chunk_hash}",
        "download": f"/api/chain-mesh/asset/{encoded_key}/download",
        "peers": "/api/chain-mesh/chunk/{chunk_hash}/peers",
    }
    if root:
        endpoints = {k: (root + v if v.startswith("/") else v) for k, v in endpoints.items()}

    anchor = None
    if manifest.get("anchor_txid"):
        anchor = {
            "magic": "BSM1",
            "txid": manifest.get("anchor_txid"),
            "height": manifest.get("anchor_height"),
            "merkle_root": manifest.get("merkle_root"),
            "note": "On-chain BSM1 commits merkle_root; chunk list resolved from mesh catalog.",
        }

    return {
        "ok": True,
        "protocol": "mesh-file-lookup-v1",
        "asset_id": manifest.get("asset_id"),
        "asset_key": key,
        "display_name": manifest.get("display_name"),
        "mime_type": manifest.get("mime_type"),
        "version": manifest.get("version"),
        "file_size": file_size,
        "file_sha256": manifest.get("file_sha256"),
        "merkle_root": manifest.get("merkle_root"),
        "chunk_size": CHUNK_SIZE,
        "chunk_count": len(all_chunks),
        "chunks_needed": len(compact),
        "bytes_needed": bytes_needed,
        "partial": partial,
        "byte_range": (
            {"start": range_start, "end": range_end, "length": range_end - range_start + 1}
            if partial
            else None
        ),
        "chunks": compact,
        "availability": {
            "coordinator_chunks": coordinator_has,
            "coordinator_complete": coordinator_has == len(selected) and len(selected) > 0,
        },
        "anchor": anchor,
        "endpoints": endpoints,
        "usage": (
            "1) GET lookup → chunk hashes. "
            "2) GET /api/chain-mesh/chunk/<h> per hash (or LAN peer). "
            "3) Concatenate by file_offset; verify file_sha256."
        ),
    }


def file_lookup_by_merkle_root(
    merkle_root: str,
    *,
    byte_range: Optional[Tuple[int, int]] = None,
    public_root: str = "",
) -> Dict[str, Any]:
    root = (merkle_root or "").strip().lower()
    if len(root) != 64:
        return {"ok": False, "error": "merkle_root must be 64 hex chars"}
    asset = mesh_db.get_asset_by_merkle_root(root)
    if not asset:
        return {"ok": False, "error": "no mesh asset for merkle_root", "merkle_root": root}
    result = file_lookup_payload(
        asset["asset_key"],
        byte_range=byte_range,
        public_root=public_root,
    )
    if result.get("ok"):
        result["resolved_via"] = "merkle_root"
    return result


def file_lookup_by_anchor_txid(
    txid: str,
    *,
    byte_range: Optional[Tuple[int, int]] = None,
    public_root: str = "",
) -> Dict[str, Any]:
    from chain_mesh import anchor_index

    entry = anchor_index.get_anchor((txid or "").strip().lower())
    if not entry:
        return {"ok": False, "error": "anchor txid not indexed", "txid": txid}
    merkle = (entry.get("merkle_root") or "").strip().lower()
    asset_key = (entry.get("asset_key") or "").strip()
    if asset_key:
        result = file_lookup_payload(asset_key, byte_range=byte_range, public_root=public_root)
    else:
        result = file_lookup_by_merkle_root(merkle, byte_range=byte_range, public_root=public_root)
    if result.get("ok"):
        result["resolved_via"] = "anchor_txid"
        result["anchor_txid"] = entry.get("txid")
        result["anchor_height"] = entry.get("block_height")
    return result


def parse_lookup_range_header(range_header: str, file_size: int) -> Optional[Tuple[int, int]]:
    try:
        return parse_bytes_range(range_header, file_size)
    except ValueError:
        return None