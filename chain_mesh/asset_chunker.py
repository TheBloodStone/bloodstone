"""Chunk arbitrary files for chain mesh asset publishing."""

import hashlib
import mimetypes
import os
from typing import Dict, List, Optional

from chain_mesh.config import CHUNK_SIZE
from chain_mesh.store import put_chunk, sha256_bytes


def chunk_asset_file(
    abs_path: str,
    *,
    asset_key: str,
    store: bool = True,
) -> List[Dict]:
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(abs_path)
    size = os.path.getsize(abs_path)
    rel = f"assets/{asset_key.lstrip('/')}"
    chunks: List[Dict] = []
    with open(abs_path, "rb") as fh:
        offset = 0
        while offset < size:
            data = fh.read(CHUNK_SIZE)
            if not data:
                break
            chunk_hash = sha256_bytes(data)
            if store:
                put_chunk(data, expected_hash=chunk_hash)
            chunks.append(
                {
                    "chunk_hash": chunk_hash,
                    "source_file": rel.replace("\\", "/"),
                    "file_offset": offset,
                    "size": len(data),
                }
            )
            offset += len(data)
    return chunks


def file_sha256(abs_path: str) -> str:
    h = hashlib.sha256()
    with open(abs_path, "rb") as fh:
        while True:
            block = fh.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def guess_mime(abs_path: str, override: Optional[str] = None) -> str:
    if override:
        return override
    mime, _ = mimetypes.guess_type(abs_path)
    return mime or "application/octet-stream"