"""User mesh asset submissions — queued for admin approval before chain publish."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db
from chain_mesh import assets as mesh_assets


def normalize_user_asset_key(asset_key: str) -> str:
    key = mesh_assets.normalize_asset_key(asset_key)
    if key.startswith("downloads/"):
        raise ValueError("user uploads must use assets/ keys (downloads/ is admin-only)")
    if not key.startswith("assets/"):
        raise ValueError("user uploads must start with assets/")
    return key


def submit_asset_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Queue a user upload for admin review (does not register on chain mesh)."""
    key = normalize_user_asset_key(str(payload.get("asset_key") or ""))
    fsize = int(payload.get("file_size") or 0)
    fhash = str(payload.get("file_sha256") or "").strip().lower()
    root = str(payload.get("merkle_root") or "").strip().lower()
    chunks = list(payload.get("chunks") or [])

    if fsize <= 0 or fsize > mesh_assets.MAX_ASSET_PUBLISH_BYTES:
        raise ValueError(f"file_size must be 1..{mesh_assets.MAX_ASSET_PUBLISH_BYTES}")
    if len(fhash) != 64:
        raise ValueError("file_sha256 must be 64 hex chars")
    if len(root) != 64:
        raise ValueError("merkle_root must be 64 hex chars")

    normalized = mesh_assets._validate_chunk_manifest(chunks, file_size=fsize)
    hashes = [c["chunk_hash"] for c in normalized]
    from chain_mesh.merkle import merkle_root

    computed_root = merkle_root(hashes)
    if computed_root != root:
        raise ValueError("merkle_root does not match chunk hashes")

    row = mesh_db.create_pending_submission(
        asset_key=key,
        display_name=str(payload.get("display_name") or ""),
        mime_type=str(payload.get("mime_type") or "application/octet-stream"),
        version=str(payload.get("version") or ""),
        file_size=fsize,
        file_sha256=fhash,
        merkle_root=root,
        chunks=normalized,
        anchor_requested=bool(payload.get("anchor", True)),
        submitter_address=str(payload.get("submitter_address") or payload.get("stone_address") or ""),
        submitter_device_id=str(payload.get("device_id") or payload.get("submitter_device_id") or ""),
        submitter_note=str(payload.get("note") or payload.get("submitter_note") or ""),
    )
    return {
        "ok": True,
        "pending": True,
        "submission_id": row["id"],
        "status": row["status"],
        "asset_key": row["asset_key"],
        "display_name": row["display_name"],
        "file_size": row["file_size"],
        "chunk_count": row["chunk_count"],
        "message": "Submitted for admin review. It will appear on the chain mesh after approval.",
    }


def pending_submissions_payload(*, status: str = "pending", limit: int = 50) -> Dict[str, Any]:
    items = mesh_db.list_pending_submissions(status=status, limit=limit)
    return {"ok": True, "submissions": items, "count": len(items)}


def pending_submission_payload(submission_id: int) -> Dict[str, Any]:
    row = mesh_db.get_pending_submission(submission_id)
    if not row:
        return {"ok": False, "error": "submission not found"}
    return {"ok": True, "submission": row}


def approve_submission_payload(
    submission_id: int,
    *,
    reviewed_by: str = "admin",
    anchor: Optional[bool] = None,
    anchor_wallet: Optional[str] = None,
) -> Dict[str, Any]:
    row = mesh_db.get_pending_submission(submission_id)
    if not row:
        return {"ok": False, "error": "submission not found"}
    if row["status"] != "pending":
        return {"ok": False, "error": f"submission already {row['status']}"}

    anchor_flag = row["anchor_requested"] if anchor is None else bool(anchor)
    result = mesh_assets.publish_asset_manifest(
        asset_key=row["asset_key"],
        display_name=row["display_name"],
        version=row["version"],
        mime_type=row["mime_type"],
        file_size=int(row["file_size"]),
        file_sha256=row["file_sha256"],
        merkle_root_hex=row["merkle_root"],
        chunks=list(row.get("chunks") or []),
        anchor=anchor_flag,
        anchor_wallet=anchor_wallet,
    )
    updated = mesh_db.update_pending_submission_status(
        submission_id,
        status="approved",
        reviewed_by=reviewed_by,
        published_asset_id=str(result.get("asset_id") or ""),
    )
    return {
        "ok": True,
        "approved": True,
        "submission_id": submission_id,
        "submission": updated,
        "publish": result,
    }


def reject_submission_payload(
    submission_id: int,
    *,
    reason: str = "",
    reviewed_by: str = "admin",
) -> Dict[str, Any]:
    row = mesh_db.get_pending_submission(submission_id)
    if not row:
        return {"ok": False, "error": "submission not found"}
    if row["status"] != "pending":
        return {"ok": False, "error": f"submission already {row['status']}"}

    updated = mesh_db.update_pending_submission_status(
        submission_id,
        status="rejected",
        reviewed_by=reviewed_by,
        rejection_reason=(reason or "rejected by admin").strip(),
    )
    return {
        "ok": True,
        "rejected": True,
        "submission_id": submission_id,
        "submission": updated,
    }