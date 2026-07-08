"""Merkle root over hex chunk hashes (binary SHA-256 leaves)."""

import hashlib
from typing import List


def _leaf_bytes(chunk_hash: str) -> bytes:
    h = (chunk_hash or "").strip().lower()
    if len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
        raise ValueError(f"invalid chunk hash: {chunk_hash!r}")
    return bytes.fromhex(h)


def merkle_root(chunk_hashes: List[str]) -> str:
    """Build binary Merkle tree; duplicate last leaf if odd count."""
    if not chunk_hashes:
        raise ValueError("empty chunk list")
    layer = [_leaf_bytes(h) for h in chunk_hashes]
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        nxt = []
        for i in range(0, len(layer), 2):
            nxt.append(hashlib.sha256(layer[i] + layer[i + 1]).digest())
        layer = nxt
    return layer[0].hex()


def asset_id_for_key(asset_key: str) -> str:
    return hashlib.sha256((asset_key or "").encode("utf-8")).hexdigest()