"""Export and import Time Capsule / chain mesh data as portable backup files."""

import io
import json
import os
import time
import zipfile
from typing import Any, Dict, List, Optional, Tuple

from chain_mesh import db as mesh_db
from chain_mesh.manifest import current_manifest
from chain_mesh.restore import ingest_uploaded_chunks
from chain_mesh.store import chunk_exists, get_chunk, put_chunk

BACKUP_FORMAT = "bloodstone-mesh-backup-v1"
MAX_BACKUP_UPLOAD_BYTES = int(
    os.environ.get("CHAIN_MESH_MAX_BACKUP_UPLOAD", str(512 * 1024 * 1024))
)


def _now() -> int:
    return int(time.time())


def backup_manifest() -> Dict[str, Any]:
    """Metadata for the current coordinator capsule backup."""
    manifest = current_manifest()
    if not manifest:
        return {"ok": False, "error": "no manifest published"}
    chunks = manifest.get("chunks") or []
    have = sum(1 for c in chunks if chunk_exists(c["chunk_hash"]))
    return {
        "ok": True,
        "format": BACKUP_FORMAT,
        "best_block_hash": manifest["best_block_hash"],
        "block_height": int(manifest["block_height"]),
        "chunk_count": len(chunks),
        "total_bytes": int(manifest["total_bytes"]),
        "coordinator_chunks": have,
        "complete": have == len(chunks),
        "updated_at": int(manifest["created_at"]),
    }


def build_capsule_zip() -> Tuple[bytes, str]:
    """Zip manifest + raw chunk blobs for offline backup."""
    manifest = current_manifest()
    if not manifest:
        raise FileNotFoundError("no manifest published")
    chunks = manifest.get("chunks") or []
    missing = [c for c in chunks if not chunk_exists(c["chunk_hash"])]
    if missing:
        raise ValueError(
            f"coordinator missing {len(missing)} chunks; archive incomplete"
        )

    height = int(manifest["block_height"])
    stamp = time.strftime("%Y%m%d", time.gmtime(int(manifest["created_at"])))
    filename = f"bloodstone-time-capsule-{height}-{stamp}.zip"

    meta = {
        "format": BACKUP_FORMAT,
        "kind": "time_capsule",
        "exported_at": _now(),
        "best_block_hash": manifest["best_block_hash"],
        "block_height": height,
        "chunk_count": len(chunks),
        "total_bytes": int(manifest["total_bytes"]),
        "manifest_id": int(manifest["id"]),
    }
    manifest_export = {
        "best_block_hash": manifest["best_block_hash"],
        "block_height": height,
        "chunk_count": len(chunks),
        "total_bytes": int(manifest["total_bytes"]),
        "chunks": chunks,
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest_export, indent=2))
        zf.writestr("backup-meta.json", json.dumps(meta, indent=2))
        zf.writestr(
            "README.txt",
            "Bloodstone Time Capsule backup\n"
            "Restore: python3 /root/chain-mesh-import-backup.py this-file.zip\n"
            "Or upload via Network Data Portal → Restore mesh backup.\n",
        )
        for chunk in chunks:
            h = chunk["chunk_hash"]
            data = get_chunk(h)
            if data is None:
                raise ValueError(f"missing chunk data: {h}")
            zf.writestr(f"chunks/{h}.bin", data)
    return buf.getvalue(), filename


def _parse_backup_json(data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Tuple[str, bytes]]]:
    fmt = str(data.get("format") or "")
    if fmt != BACKUP_FORMAT:
        raise ValueError(f"unsupported backup format: {fmt or 'unknown'}")
    manifest = data.get("manifest") or {}
    chunks_raw = data.get("chunks") or []
    pairs: List[Tuple[str, bytes]] = []
    for item in chunks_raw:
        if not isinstance(item, dict):
            continue
        h = str(item.get("chunk_hash") or "").strip().lower()
        raw_b64 = item.get("data_b64") or item.get("data")
        if not h or not raw_b64:
            continue
        import base64

        blob = base64.b64decode(raw_b64, validate=True)
        pairs.append((h, blob))
    if not pairs and not manifest.get("chunks"):
        raise ValueError("backup contains no chunks")
    return manifest, pairs


def _parse_backup_zip(raw: bytes) -> Tuple[Dict[str, Any], List[Tuple[str, bytes]]]:
    if len(raw) > MAX_BACKUP_UPLOAD_BYTES:
        raise ValueError("backup file too large")
    pairs: List[Tuple[str, bytes]] = []
    manifest: Dict[str, Any] = {}
    with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
        names = zf.namelist()
        if "manifest.json" in names:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        for name in names:
            if not name.startswith("chunks/") or not name.endswith(".bin"):
                continue
            h = os.path.basename(name)[:-4].strip().lower()
            if len(h) != 64:
                continue
            pairs.append((h, zf.read(name)))
    if not pairs:
        raise ValueError("zip backup contains no chunk files")
    return manifest, pairs


def import_backup_bytes(
    raw: bytes,
    *,
    content_type: str = "",
    store_coordinator: bool = True,
) -> Dict[str, Any]:
    """Ingest a mesh backup (JSON or zip) into the coordinator chunk store."""
    if len(raw) > MAX_BACKUP_UPLOAD_BYTES:
        raise ValueError("backup file too large")

    manifest: Dict[str, Any] = {}
    pairs: List[Tuple[str, bytes]] = []

    if raw[:1] == b"{":
        data = json.loads(raw.decode("utf-8"))
        manifest, pairs = _parse_backup_json(data)
    elif raw[:2] == b"PK":
        manifest, pairs = _parse_backup_zip(raw)
    else:
        raise ValueError("backup must be JSON or zip")

    if store_coordinator:
        result = ingest_uploaded_chunks(pairs)
    else:
        result = {"stored": 0}
        for h, blob in pairs:
            try:
                put_chunk(blob, expected_hash=h)
                result["stored"] = int(result.get("stored", 0)) + 1
            except ValueError:
                continue

    mesh_db.init_db()
    return {
        "ok": True,
        "stored_chunks": int(result.get("stored") or 0),
        "total_chunks_in_backup": len(pairs),
        "block_height": int(manifest.get("block_height") or 0),
        "best_block_hash": str(manifest.get("best_block_hash") or ""),
    }


def import_backup_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Import from JSON API body (device export or zip uploaded as base64)."""
    import base64

    raw_b64 = str(payload.get("data_b64") or payload.get("backup_b64") or "").strip()
    if raw_b64:
        raw = base64.b64decode(raw_b64, validate=True)
        return import_backup_bytes(raw, store_coordinator=True)

    if payload.get("format") == BACKUP_FORMAT:
        manifest, pairs = _parse_backup_json(payload)
        if not pairs:
            chunks_meta = manifest.get("chunks") or payload.get("chunks") or []
            for item in chunks_meta:
                if not isinstance(item, dict):
                    continue
                h = str(item.get("chunk_hash") or "").strip().lower()
                raw_b64 = item.get("data_b64")
                if h and raw_b64:
                    import base64

                    pairs.append((h, base64.b64decode(raw_b64, validate=True)))
        result = ingest_uploaded_chunks(pairs)
        return {
            "ok": True,
            "stored_chunks": int(result.get("stored") or 0),
            "total_chunks_in_backup": len(pairs),
            "block_height": int(manifest.get("block_height") or payload.get("block_height") or 0),
            "best_block_hash": str(
                manifest.get("best_block_hash") or payload.get("best_block_hash") or ""
            ),
        }
    raise ValueError("backup payload required (data_b64 or format bloodstone-mesh-backup-v1)")