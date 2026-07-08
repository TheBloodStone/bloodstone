"""Split immutable block files into content-addressed chunks."""

import os
from typing import Dict, List

from chain_mesh.config import CHUNK_SIZE, DATADIR, SHARD_SOURCES
from chain_mesh.store import chunk_id_for, put_chunk


def _discover_sources() -> List[str]:
    found: List[str] = []
    for rel in SHARD_SOURCES:
        path = os.path.join(DATADIR, rel)
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            found.append(rel)
    blocks_dir = os.path.join(DATADIR, "blocks")
    if os.path.isdir(blocks_dir):
        for name in sorted(os.listdir(blocks_dir)):
            if name.startswith("blk") and name.endswith(".dat"):
                rel = f"blocks/{name}"
                if rel not in found:
                    path = os.path.join(DATADIR, rel)
                    if os.path.isfile(path) and os.path.getsize(path) > 0:
                        found.append(rel)
            if name.startswith("rev") and name.endswith(".dat"):
                rel = f"blocks/{name}"
                if rel not in found:
                    path = os.path.join(DATADIR, rel)
                    if os.path.isfile(path) and os.path.getsize(path) > 0:
                        found.append(rel)
    return sorted(set(found))


def chunk_source_file(rel_path: str, *, store: bool = True) -> List[Dict]:
    """Return chunk metadata for one datadir-relative file."""
    abs_path = os.path.join(DATADIR, rel_path)
    if not os.path.isfile(abs_path):
        return []
    size = os.path.getsize(abs_path)
    chunks: List[Dict] = []
    with open(abs_path, "rb") as fh:
        offset = 0
        while offset < size:
            data = fh.read(CHUNK_SIZE)
            if not data:
                break
            chunk_hash = chunk_id_for(rel_path, offset, data)
            if store:
                put_chunk(data, expected_hash=chunk_hash)
            chunks.append(
                {
                    "chunk_hash": chunk_hash,
                    "source_file": rel_path.replace("\\", "/"),
                    "file_offset": offset,
                    "size": len(data),
                }
            )
            offset += len(data)
    return chunks


def build_all_chunks(*, store: bool = True) -> List[Dict]:
    out: List[Dict] = []
    for rel in _discover_sources():
        out.extend(chunk_source_file(rel, store=store))
    return out