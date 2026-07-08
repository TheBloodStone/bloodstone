"""Build and query the current chain mesh manifest."""

import json
import subprocess
from typing import Any, Dict, Optional

from chain_mesh.chunker import build_all_chunks
from chain_mesh.config import CLI, CONF
from chain_mesh import db as mesh_db


def _rpc_blockchain_info() -> Dict[str, Any]:
    try:
        raw = subprocess.check_output(
            [CLI, f"-conf={CONF}", "getblockchaininfo"],
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        return json.loads(raw.decode("utf-8"))
    except (subprocess.SubprocessError, json.JSONDecodeError, FileNotFoundError):
        return {}


def publish_manifest(*, store_chunks: bool = True) -> Dict[str, Any]:
    info = _rpc_blockchain_info()
    best_hash = str(info.get("bestblockhash") or "")
    height = int(info.get("blocks") or 0)
    current = current_manifest()
    if (
        current
        and best_hash
        and str(current.get("best_block_hash") or "") == best_hash
        and int(current.get("block_height") or 0) == height
    ):
        return {
            "manifest_id": int(current["id"]),
            "best_block_hash": best_hash,
            "block_height": height,
            "chunk_count": int(current.get("chunk_count") or 0),
            "total_bytes": sum(int(c.get("size") or 0) for c in current.get("chunks") or []),
            "skipped": True,
        }
    chunks = build_all_chunks(store=store_chunks)
    if not chunks:
        raise RuntimeError("no block files found to publish")
    manifest_id = mesh_db.set_current_manifest(
        best_block_hash=best_hash,
        block_height=height,
        chunks=chunks,
    )
    return {
        "manifest_id": manifest_id,
        "best_block_hash": best_hash,
        "block_height": height,
        "chunk_count": len(chunks),
        "total_bytes": sum(c["size"] for c in chunks),
    }


def current_manifest() -> Optional[Dict[str, Any]]:
    mesh_db.init_db()
    return mesh_db.get_current_manifest()