"""Trustless Chain Mesh retrieval — verify chunks and manifests without trusting providers."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Tuple

from chain_mesh import mesh_providers as providers
from chain_mesh.store import chunk_exists, get_chunk, sha256_bytes


def verify_chunk_hash(chunk_hash: str, data: bytes) -> bool:
    h = (chunk_hash or "").strip().lower()
    if len(h) != 64 or not data:
        return False
    return sha256_bytes(data) == h


def verify_manifest_body(body: Dict[str, Any]) -> Dict[str, Any]:
    """RFC §6 — validate manifest fields and Merkle root over chunk list."""
    from chain_mesh.merkle import merkle_root

    errors: List[str] = []
    root = str(body.get("manifest_merkle_root") or "").strip().lower()
    fhash = str(body.get("file_sha256") or "").strip().lower()
    fsize = int(body.get("file_size") or 0)
    hashes = [str(h).strip().lower() for h in (body.get("chunk_hashes") or []) if h]
    if len(root) != 64:
        errors.append("invalid manifest_merkle_root")
    if len(fhash) != 64:
        errors.append("invalid file_sha256")
    if fsize <= 0:
        errors.append("invalid file_size")
    if not hashes:
        errors.append("empty chunk_hashes")
    computed_root = ""
    if hashes and not errors:
        try:
            computed_root = merkle_root(hashes)
            if computed_root != root:
                errors.append("merkle_root mismatch")
        except ValueError as exc:
            errors.append(str(exc))
    return {
        "ok": not errors,
        "errors": errors,
        "manifest_merkle_root": root,
        "file_sha256": fhash,
        "file_size": fsize,
        "chunk_hashes": hashes,
        "computed_merkle_root": computed_root,
    }


def fetch_chunk_local(chunk_hash: str) -> Optional[bytes]:
    if not chunk_exists(chunk_hash):
        return None
    return get_chunk(chunk_hash)


def retrieve_chunks_trustless(
    manifest: Dict[str, Any],
    *,
    chunk_sizes: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Fetch and verify all chunks for a v2 manifest.
    Uses coordinator chunk store today; provider list is consulted for metadata.
    """
    check = verify_manifest_body(manifest)
    if not check["ok"]:
        return {"ok": False, "error": "manifest invalid", "details": check}

    hashes: List[str] = check["chunk_hashes"]
    sizes = list(chunk_sizes or [])
    blobs: List[bytes] = []
    sources: List[Dict[str, Any]] = []

    for idx, ch in enumerate(hashes):
        data = fetch_chunk_local(ch)
        source = "coordinator"
        provider_ids = providers.providers_for_chunk(ch)
        if not provider_ids:
            provider_ids = list(manifest.get("provider_ids") or [])

        if data is None:
            return {
                "ok": False,
                "error": f"missing chunk {ch[:16]}…",
                "missing_index": idx,
                "provider_ids": provider_ids,
            }
        if not verify_chunk_hash(ch, data):
            return {
                "ok": False,
                "error": f"chunk hash mismatch at index {idx}",
                "provider_ids": provider_ids,
            }
        blobs.append(data)
        sources.append(
            {
                "index": idx,
                "chunk_hash": ch,
                "size": len(data),
                "source": source,
                "provider_ids": provider_ids,
            }
        )

    blob = b"".join(blobs)
    expected_size = int(check["file_size"])
    if len(blob) != expected_size and sizes:
        # tolerate explicit per-chunk sizes from coordinator manifest
        expected_size = sum(sizes)
    if len(blob) != expected_size:
        return {
            "ok": False,
            "error": "reassembled size mismatch",
            "expected": expected_size,
            "actual": len(blob),
        }
    digest = hashlib.sha256(blob).hexdigest()
    if digest != check["file_sha256"]:
        return {
            "ok": False,
            "error": "file_sha256 mismatch after reassembly",
            "computed": digest,
        }
    return {
        "ok": True,
        "file_size": len(blob),
        "file_sha256": digest,
        "chunk_count": len(hashes),
        "sources": sources,
        "verified": True,
    }