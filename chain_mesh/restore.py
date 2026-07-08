"""Restore node block files from the chain mesh coordinator."""

import os
import shutil
import subprocess
from typing import Dict, List, Optional, Tuple

from chain_mesh.config import CLI, CONF, DATADIR
from chain_mesh import db as mesh_db
from chain_mesh.store import chunk_exists, get_chunk, put_chunk


def _stop_node() -> None:
    try:
        subprocess.run(
            [CLI, f"-conf={CONF}", "stop"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    subprocess.run(["systemctl", "stop", "bloodstoned"], check=False)


def _missing_chunks(manifest: Dict) -> List[Dict]:
    missing = []
    for chunk in manifest.get("chunks") or []:
        h = chunk["chunk_hash"]
        if not chunk_exists(h):
            missing.append(chunk)
    return missing


def _write_chunk_to_file(chunk: Dict, data: bytes) -> None:
    rel = chunk["source_file"]
    dest = os.path.join(DATADIR, rel)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    offset = int(chunk["file_offset"])
    size = int(chunk["size"])
    if len(data) != size:
        raise ValueError(f"chunk size mismatch for {chunk['chunk_hash']}")
    mode = "r+b" if os.path.isfile(dest) else "wb"
    with open(dest, mode) as fh:
        if mode == "wb" and offset > 0:
            fh.seek(offset - 1)
            fh.write(b"\x00")
        fh.seek(offset)
        fh.write(data)


def restore_from_mesh(
    *,
    require_complete: bool = True,
    stop_node_first: bool = True,
) -> Dict:
    """Rebuild blocks/*.dat from coordinator chunk store."""
    mesh_db.init_db()
    manifest = mesh_db.get_current_manifest()
    if not manifest:
        return {"ok": False, "error": "no manifest published"}

    missing = _missing_chunks(manifest)
    if missing and require_complete:
        return {
            "ok": False,
            "error": "coordinator missing chunks",
            "missing_count": len(missing),
            "missing_hashes": [c["chunk_hash"] for c in missing[:10]],
        }

    if stop_node_first:
        _stop_node()

    restored = 0
    bytes_written = 0
    for chunk in manifest.get("chunks") or []:
        data = get_chunk(chunk["chunk_hash"])
        if data is None:
            continue
        _write_chunk_to_file(chunk, data)
        restored += 1
        bytes_written += len(data)

    return {
        "ok": restored > 0,
        "restored_chunks": restored,
        "bytes_written": bytes_written,
        "block_height": manifest["block_height"],
        "best_block_hash": manifest["best_block_hash"],
        "missing_count": len(missing),
    }


def ingest_uploaded_chunks(chunks: List[Tuple[str, bytes]]) -> Dict:
    stored = 0
    for chunk_hash, data in chunks:
        try:
            put_chunk(data, expected_hash=chunk_hash)
            stored += 1
        except ValueError:
            continue
    return {"stored": stored}


def local_coverage() -> Dict:
    manifest = mesh_db.get_current_manifest()
    if not manifest:
        return {"complete": False, "have": 0, "need": 0}
    need = len(manifest["chunks"])
    have = sum(1 for c in manifest["chunks"] if chunk_exists(c["chunk_hash"]))
    return {
        "complete": have == need,
        "have": have,
        "need": need,
        "block_height": manifest["block_height"],
    }