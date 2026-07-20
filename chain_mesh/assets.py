"""Publish and retrieve arbitrary files via chain mesh + optional on-chain anchor."""

from chain_mesh.security import public_error
import hashlib
import os
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db
from chain_mesh.anchor import anchor_asset_on_chain
from chain_mesh.asset_chunker import chunk_asset_file, file_sha256, guess_mime
from chain_mesh.config import (
    CHUNK_SIZE,
    MAX_ASSET_PUBLISH_BYTES,
    MAX_ASSET_PUBLISH_CHUNKS,
)
from chain_mesh.merkle import asset_id_for_key, merkle_root
from chain_mesh.store import chunk_exists, get_chunk, sha256_bytes


def normalize_asset_key(asset_key: str) -> str:
    key = (asset_key or "").strip().lstrip("/")
    if not key or ".." in key or key.startswith("."):
        raise ValueError("invalid asset_key")
    if not (key.startswith("downloads/") or key.startswith("assets/")):
        raise ValueError("asset_key must start with downloads/ or assets/")
    if len(key) > 240:
        raise ValueError("asset_key too long")
    return key


def _validate_chunk_manifest(chunks: List[Dict[str, Any]], *, file_size: int) -> List[Dict[str, Any]]:
    if not chunks:
        raise ValueError("chunks required")
    if len(chunks) > MAX_ASSET_PUBLISH_CHUNKS:
        raise ValueError(f"too many chunks (max {MAX_ASSET_PUBLISH_CHUNKS})")
    ordered = sorted(chunks, key=lambda c: int(c.get("file_offset") or 0))
    expected_offset = 0
    normalized: List[Dict[str, Any]] = []
    for idx, chunk in enumerate(ordered):
        h = str(chunk.get("chunk_hash") or chunk.get("hash") or "").strip().lower()
        offset = int(chunk.get("file_offset") or 0)
        size = int(chunk.get("size") or 0)
        if len(h) != 64:
            raise ValueError(f"invalid chunk hash at index {idx}")
        if offset != expected_offset:
            raise ValueError(f"chunk offset mismatch at index {idx}")
        if size <= 0 or size > CHUNK_SIZE + 4096:
            raise ValueError(f"invalid chunk size at index {idx}")
        if not chunk_exists(h):
            raise ValueError(f"missing chunk on coordinator: {h[:16]}…")
        data = get_chunk(h)
        if data is None or len(data) != size:
            raise ValueError(f"chunk size mismatch for {h[:16]}…")
        if sha256_bytes(data) != h:
            raise ValueError(f"chunk hash mismatch for {h[:16]}…")
        normalized.append(
            {
                "chunk_hash": h,
                "file_offset": offset,
                "size": size,
            }
        )
        expected_offset += size
    if expected_offset != int(file_size):
        raise ValueError("chunk sizes do not sum to file_size")
    return normalized


def publish_asset(
    abs_path: str,
    *,
    asset_key: str,
    display_name: str = "",
    version: str = "",
    mime_type: Optional[str] = None,
    anchor: bool = True,
    anchor_wallet: Optional[str] = None,
) -> Dict[str, Any]:
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(abs_path)
    key = asset_key.strip().lstrip("/")
    if not key:
        raise ValueError("asset_key required")

    chunks = chunk_asset_file(abs_path, asset_key=key, store=True)
    if not chunks:
        raise ValueError("no chunks produced")

    hashes = [c["chunk_hash"] for c in chunks]
    root = merkle_root(hashes)
    aid = asset_id_for_key(key)
    fhash = file_sha256(abs_path)
    fsize = os.path.getsize(abs_path)
    name = display_name or os.path.basename(abs_path)
    mime = guess_mime(abs_path, mime_type)

    reg = mesh_db.register_asset(
        asset_id=aid,
        asset_key=key,
        display_name=name,
        mime_type=mime,
        version=version,
        file_size=fsize,
        file_sha256=fhash,
        merkle_root=root,
        chunks=chunks,
    )

    result: Dict[str, Any] = {
        "ok": True,
        "asset_id": aid,
        "asset_key": key,
        "display_name": name,
        "mime_type": mime,
        "version": version,
        "file_size": fsize,
        "file_sha256": fhash,
        "merkle_root": root,
        "chunk_count": len(chunks),
        "chunks": chunks,
        **reg,
    }

    if anchor:
        try:
            anchor_result = anchor_asset_on_chain(
                asset_key=key,
                merkle_root=root,
                wallet=anchor_wallet,
            )
            mesh_db.update_asset_anchor(
                aid,
                anchor_txid=anchor_result["txid"],
                anchor_height=anchor_result.get("anchor_height") or 0,
                anchor_confirmations=anchor_result.get("confirmations") or 0,
            )
            result["anchor"] = anchor_result
        except Exception as exc:
            result["anchor"] = {"ok": False, "error": public_error(exc)}

    return result


def asset_manifest_payload(asset_key: str) -> Dict[str, Any]:
    asset = mesh_db.get_asset(asset_key=asset_key)
    if not asset:
        return {"ok": False, "error": "asset not found"}
    chunks = []
    for c in asset["chunks"]:
        h = c["chunk_hash"]
        chunks.append(
            {
                **c,
                "coordinator_has": chunk_exists(h),
                "peer_count": len(mesh_db.peers_for_chunk(h)),
            }
        )
    return {
        "ok": True,
        "asset_id": asset["asset_id"],
        "asset_key": asset["asset_key"],
        "display_name": asset["display_name"],
        "mime_type": asset["mime_type"],
        "version": asset["version"],
        "file_size": asset["file_size"],
        "file_sha256": asset["file_sha256"],
        "merkle_root": asset["merkle_root"],
        "chunk_count": asset["chunk_count"],
        "anchor_txid": asset.get("anchor_txid"),
        "anchor_height": asset.get("anchor_height"),
        "created_at": asset["created_at"],
        "chunks": chunks,
    }


def publish_asset_manifest(
    *,
    asset_key: str,
    display_name: str = "",
    version: str = "",
    mime_type: str = "",
    file_size: int,
    file_sha256: str,
    merkle_root_hex: str,
    chunks: List[Dict[str, Any]],
    anchor: bool = True,
    anchor_wallet: Optional[str] = None,
) -> Dict[str, Any]:
    """Register a mesh asset from pre-uploaded content-addressed chunks."""
    key = normalize_asset_key(asset_key)
    fsize = int(file_size)
    if fsize <= 0 or fsize > MAX_ASSET_PUBLISH_BYTES:
        raise ValueError(f"file_size must be 1..{MAX_ASSET_PUBLISH_BYTES}")

    fhash = (file_sha256 or "").strip().lower()
    if len(fhash) != 64:
        raise ValueError("file_sha256 must be 64 hex chars")

    root = (merkle_root_hex or "").strip().lower()
    if len(root) != 64:
        raise ValueError("merkle_root must be 64 hex chars")

    normalized = _validate_chunk_manifest(chunks, file_size=fsize)
    hashes = [c["chunk_hash"] for c in normalized]
    computed_root = merkle_root(hashes)
    if computed_root != root:
        raise ValueError("merkle_root does not match chunk hashes")

    blob = b"".join(get_chunk(c["chunk_hash"]) or b"" for c in normalized)
    if len(blob) != fsize:
        raise ValueError("reconstructed size mismatch")
    if hashlib.sha256(blob).hexdigest() != fhash:
        raise ValueError("file_sha256 does not match chunk data")

    aid = asset_id_for_key(key)
    mime = (mime_type or "application/octet-stream").strip()[:120]
    name = (display_name or os.path.basename(key))[:200]
    version_label = (version or "")[:64]

    reg = mesh_db.register_asset(
        asset_id=aid,
        asset_key=key,
        display_name=name,
        mime_type=mime,
        version=version_label,
        file_size=fsize,
        file_sha256=fhash,
        merkle_root=root,
        chunks=normalized,
    )

    result: Dict[str, Any] = {
        "ok": True,
        "asset_id": aid,
        "asset_key": key,
        "display_name": name,
        "mime_type": mime,
        "version": version_label,
        "file_size": fsize,
        "file_sha256": fhash,
        "merkle_root": root,
        "chunk_count": len(normalized),
        "chunks": normalized,
        **reg,
    }

    if anchor:
        try:
            anchor_result = anchor_asset_on_chain(
                asset_key=key,
                merkle_root=root,
                wallet=anchor_wallet,
            )
            mesh_db.update_asset_anchor(
                aid,
                anchor_txid=anchor_result["txid"],
                anchor_height=anchor_result.get("anchor_height") or 0,
                anchor_confirmations=anchor_result.get("confirmations") or 0,
            )
            result["anchor"] = anchor_result
        except Exception as exc:
            result["anchor"] = {"ok": False, "error": public_error(exc)}

    return result


def assets_catalog_payload(*, limit: int = 50) -> Dict[str, Any]:
    return {"ok": True, "assets": mesh_db.list_assets(limit=limit)}


def writable_keys_payload(*, limit: int = 200, prefix: str = "") -> Dict[str, Any]:
    """Mesh asset keys that can be replaced by publishing a new revision."""
    pref = (prefix or "").strip().rstrip("/")
    if pref:
        items = mesh_db.search_assets(prefix=pref, limit=limit)
    else:
        items = mesh_db.list_assets(limit=limit)
    keys: List[Dict[str, Any]] = []
    for row in items:
        key = str(row.get("asset_key") or "").strip()
        if not key:
            continue
        keys.append(
            {
                "asset_key": key,
                "display_name": row.get("display_name") or "",
                "version": row.get("version") or "",
                "file_size": int(row.get("file_size") or 0),
                "mime_type": row.get("mime_type") or "",
                "chunk_count": int(row.get("chunk_count") or 0),
                "anchor_txid": row.get("anchor_txid") or "",
                "overwrite": True,
                "user_writable": key.startswith("assets/"),
                "admin_only": key.startswith("downloads/"),
            }
        )
    return {
        "ok": True,
        "keys": keys,
        "count": len(keys),
        "note": (
            "Publish or submit with the same asset_key to replace the current revision. "
            "assets/ keys are open to user submissions; downloads/ requires admin publish token."
        ),
    }


def update_asset_metadata_payload(
    asset_key: str,
    *,
    display_name: Optional[str] = None,
    version: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        asset = mesh_db.update_asset_metadata(
            asset_key,
            display_name=display_name,
            version=version,
        )
    except KeyError:
        return {"ok": False, "error": "asset not found"}
    return {
        "ok": True,
        "asset_key": asset["asset_key"],
        "display_name": asset["display_name"],
        "version": asset["version"],
        "file_size": asset["file_size"],
        "file_sha256": asset["file_sha256"],
        "merkle_root": asset["merkle_root"],
        "updated_at": asset["created_at"],
    }


def asset_versions_payload(asset_key: str, *, limit: int = 20) -> Dict[str, Any]:
    versions = mesh_db.list_asset_versions(asset_key, limit=limit)
    if not versions:
        asset = mesh_db.get_asset(asset_key=asset_key)
        if not asset:
            return {"ok": False, "error": "asset not found"}
    return {"ok": True, "asset_key": asset_key.strip(), "versions": versions}


_PREVIEW_TEXT_TYPES = frozenset(
    {
        "text/plain",
        "text/html",
        "text/css",
        "text/markdown",
        "application/json",
        "application/javascript",
        "text/javascript",
        "application/xml",
        "text/xml",
    }
)
_PREVIEW_IMAGE_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"}
)
_PREVIEW_MAX_TEXT = 256 * 1024
_PREVIEW_MAX_IMAGE = 2 * 1024 * 1024


def asset_preview_payload(asset_key: str) -> Dict[str, Any]:
    asset = mesh_db.get_asset(asset_key=asset_key)
    if not asset:
        return {"ok": False, "error": "asset not found"}
    mime = (asset.get("mime_type") or "").strip().lower()
    size = int(asset.get("file_size") or 0)
    base = {
        "ok": True,
        "asset_key": asset["asset_key"],
        "display_name": asset["display_name"],
        "mime_type": mime,
        "file_size": size,
        "preview_kind": "none",
    }
    if size <= 0:
        return {**base, "preview_kind": "empty"}

    if mime in _PREVIEW_IMAGE_TYPES and size <= _PREVIEW_MAX_IMAGE:
        blob = reconstruct_asset_bytes(asset_key)
        import base64

        return {
            **base,
            "preview_kind": "image",
            "data_b64": base64.b64encode(blob).decode("ascii"),
        }

    text_ok = mime in _PREVIEW_TEXT_TYPES or mime.startswith("text/")
    name = (asset.get("display_name") or asset.get("asset_key") or "").lower()
    if not text_ok and any(name.endswith(ext) for ext in (".txt", ".md", ".json", ".html", ".css", ".js", ".xml", ".log")):
        text_ok = True
    if text_ok and size <= _PREVIEW_MAX_TEXT:
        blob = reconstruct_asset_bytes(asset_key)
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError:
            text = blob.decode("utf-8", errors="replace")
        return {**base, "preview_kind": "text", "text": text}

    return {**base, "preview_kind": "binary", "note": "Download to view this file type."}


def asset_download_filename(asset_key: str) -> str:
    asset = mesh_db.get_asset(asset_key=asset_key)
    if not asset:
        raise FileNotFoundError(asset_key)
    name = (asset.get("display_name") or "").strip()
    if name:
        return name.replace("/", "_").replace("\\", "_")[:200]
    return (asset_key or "download").split("/")[-1] or "download"


def reconstruct_asset_bytes(asset_key: str) -> bytes:
    asset = mesh_db.get_asset(asset_key=asset_key)
    if not asset:
        raise FileNotFoundError(asset_key)
    file_size = int(asset["file_size"])
    return reconstruct_asset_byte_range(asset_key, 0, file_size - 1, asset=asset)


def parse_bytes_range(range_header: str, file_size: int) -> Optional[tuple]:
    """
    Parse an HTTP Range header (bytes=…) into (start, end) inclusive indices.
    Returns None when the header is absent or not a bytes range.
    Raises ValueError for syntactically invalid or unsatisfiable ranges.
    """
    if file_size <= 0:
        raise ValueError("empty file")
    header = (range_header or "").strip()
    if not header.lower().startswith("bytes="):
        return None
    spec = header[6:].strip()
    if "," in spec:
        raise ValueError("multiple ranges not supported")
    if spec.startswith("-"):
        suffix = int(spec[1:])
        if suffix <= 0:
            raise ValueError("invalid suffix range")
        start = max(0, file_size - suffix)
        end = file_size - 1
    else:
        if "-" not in spec:
            raise ValueError("invalid range")
        left, right = spec.split("-", 1)
        start = int(left) if left else 0
        end = int(right) if right else file_size - 1
    if start < 0 or end < start or start >= file_size:
        raise ValueError("range not satisfiable")
    end = min(end, file_size - 1)
    return start, end


def reconstruct_asset_byte_range(
    asset_key: str,
    start: int,
    end: int,
    *,
    asset: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Load only the chunk slices needed for [start, end] (inclusive)."""
    if start < 0 or end < start:
        raise ValueError("invalid range bounds")
    if asset is None:
        asset = mesh_db.get_asset(asset_key=asset_key)
    if not asset:
        raise FileNotFoundError(asset_key)
    file_size = int(asset["file_size"])
    if end >= file_size:
        raise ValueError("range not satisfiable")

    parts: List[bytes] = []
    for c in asset["chunks"]:
        chunk_start = int(c["file_offset"])
        chunk_end = chunk_start + int(c["size"]) - 1
        if chunk_end < start or chunk_start > end:
            continue
        data = get_chunk(c["chunk_hash"])
        if data is None:
            raise FileNotFoundError(f"missing chunk {c['chunk_hash']}")
        if len(data) != int(c["size"]):
            raise ValueError(f"chunk size mismatch {c['chunk_hash']}")
        slice_start = max(0, start - chunk_start)
        slice_end = min(len(data), end - chunk_start + 1)
        parts.append(data[slice_start:slice_end])
    blob = b"".join(parts)
    expected_len = end - start + 1
    if len(blob) != expected_len:
        raise ValueError("range reconstruction size mismatch")
    return blob


_STREAMABLE_MIME_PREFIXES = ("video/", "audio/")


def is_streamable_mime(mime_type: str) -> bool:
    mime = (mime_type or "").strip().lower()
    return mime.startswith(_STREAMABLE_MIME_PREFIXES)