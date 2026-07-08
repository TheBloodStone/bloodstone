"""Deterministic chunk assignment — each node backs up a fair slice by node ID hash."""

import hashlib
import os
from typing import Any, Dict, List, Optional

BACKUP_PCT = int(os.environ.get("CHAIN_MESH_BACKUP_PCT", "10"))
ASSIGNMENT_ALGO = "node_id_hash_v1"


def _normalize_node_id(node_id: str) -> str:
    return (node_id or "").strip().lower()


def _normalize_chunk_hash(chunk_hash: str) -> str:
    return (chunk_hash or "").strip().lower()


def assignment_bucket(node_id: str, chunk_hash: str) -> int:
    """Return 0–99 bucket for (node_id, chunk_hash)."""
    node = _normalize_node_id(node_id)
    chunk = _normalize_chunk_hash(chunk_hash)
    if not node or not chunk:
        return 100
    digest = hashlib.sha256(f"{node}:{chunk}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def node_should_store_chunk(
    node_id: str,
    chunk_hash: str,
    backup_pct: Optional[int] = None,
) -> bool:
    """True when this node is responsible for backing up the chunk."""
    pct = BACKUP_PCT if backup_pct is None else max(1, min(100, int(backup_pct)))
    return assignment_bucket(node_id, chunk_hash) < pct


def chunks_for_node(
    node_id: str,
    chunks: List[Dict[str, Any]],
    backup_pct: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Filter manifest chunks to those assigned to node_id."""
    return [
        c
        for c in chunks
        if node_should_store_chunk(
            node_id,
            str(c.get("chunk_hash") or ""),
            backup_pct=backup_pct,
        )
    ]


def assignment_info(backup_pct: Optional[int] = None) -> Dict[str, Any]:
    pct = BACKUP_PCT if backup_pct is None else max(1, min(100, int(backup_pct)))
    return {
        "algo": ASSIGNMENT_ALGO,
        "backup_pct": pct,
        "note": (
            "Each node stores chunks where sha256(node_id:chunk_hash) mod 100 "
            f"is less than {pct}. No central coordinator assigns slots."
        ),
    }