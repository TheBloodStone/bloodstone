"""Filesystem blob store for content-addressed chunks."""

import hashlib
import os
from typing import Optional

from chain_mesh.config import CHUNK_STORE, MAX_CHUNK_UPLOAD_BYTES


def _chunk_path(chunk_hash: str) -> str:
    h = (chunk_hash or "").strip().lower()
    if len(h) != 64 or not all(c in "0123456789abcdef" for c in h):
        raise ValueError("invalid chunk hash")
    sub = h[:2]
    return os.path.join(CHUNK_STORE, sub, h)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def chunk_id_for(source_file: str, offset: int, data: bytes) -> str:
    """Unique id per file slice (zero-filled regions share content but not offset)."""
    meta = f"{source_file}:{offset}:{len(data)}".encode("utf-8")
    return hashlib.sha256(meta + data).hexdigest()


def put_chunk(data: bytes, *, expected_hash: Optional[str] = None) -> str:
    if not data:
        raise ValueError("empty chunk")
    if len(data) > MAX_CHUNK_UPLOAD_BYTES:
        raise ValueError("chunk too large")
    digest = (expected_hash or sha256_bytes(data)).strip().lower()
    if expected_hash and len(digest) != 64:
        raise ValueError("invalid expected hash")
    path = _chunk_path(digest)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.isfile(path):
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    return digest


def get_chunk(chunk_hash: str) -> Optional[bytes]:
    path = _chunk_path(chunk_hash)
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as fh:
        return fh.read()


def chunk_exists(chunk_hash: str) -> bool:
    try:
        return os.path.isfile(_chunk_path(chunk_hash))
    except ValueError:
        return False


def stored_chunk_count() -> int:
    if not os.path.isdir(CHUNK_STORE):
        return 0
    total = 0
    for entry in os.scandir(CHUNK_STORE):
        if entry.is_dir():
            total += sum(1 for f in os.scandir(entry.path) if f.is_file())
    return total