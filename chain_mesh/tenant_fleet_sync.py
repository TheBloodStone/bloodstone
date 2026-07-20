"""Wave T — fleet-wide tenant binding sync via DTN bundles + gossip."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db

SYNC_FORMAT = "bloodstone_tenant_fleet_sync/v1"


def _tenant_sync_enable() -> bool:
    return os.environ.get("TENANT_FLEET_SYNC_ENABLE", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def _default_tenant() -> str:
    return (os.environ.get("DTN_DEFAULT_TENANT") or "bloodstone").strip()[:64] or "bloodstone"


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def resolve_author_for_stone(
    stone_address: str,
    *,
    tenant_id: str = "",
) -> str:
    """Resolve blurt_account from tenant bindings when only stone_address is known."""
    addr = (stone_address or "").strip()
    if not addr:
        return ""
    from chain_mesh import compute_tenant_quota as compute

    tid = (tenant_id or _default_tenant()).strip()[:64] or _default_tenant()
    compute.init_tenant_quota_db()
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT blurt_account FROM compute_tenant_bindings
            WHERE tenant_id = ? AND stone_address = ?
            ORDER BY updated_at DESC LIMIT 1
            """,
            (tid, addr),
        ).fetchone()
    return str(row["blurt_account"]) if row else ""


def collect_tenant_snapshots(*, tenant_id: str = "", limit: int = 50) -> List[Dict[str, Any]]:
    from chain_mesh import bandwidth_tenant_quota as bw
    from chain_mesh import compute_tenant_quota as compute
    from chain_mesh import storage_tenant_quota as storage

    if not _tenant_sync_enable():
        return []
    tid = (tenant_id or _default_tenant()).strip()[:64] or _default_tenant()
    lim = max(1, min(200, int(limit)))
    compute.init_tenant_quota_db()
    bw.init_tenant_quota_db()
    storage.init_tenant_quota_db()
    snaps: List[Dict[str, Any]] = []
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT tenant_id, blurt_account, stone_address, flops_cap, updated_at
            FROM compute_tenant_bindings
            WHERE tenant_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (tid, lim),
        ).fetchall()
        for row in rows:
            snaps.append(
                {
                    "format": SYNC_FORMAT,
                    "tenant_id": str(row["tenant_id"]),
                    "blurt_account": str(row["blurt_account"]),
                    "stone_address": str(row["stone_address"]),
                    "rails": {
                        "compute": {"flops_cap": int(row["flops_cap"] or 0)},
                    },
                    "updated_at": int(row["updated_at"] or 0),
                    "node_id": (os.environ.get("DTN_NODE_ID") or "pi-edge").strip()[:64],
                }
            )
        bw_rows = conn.execute(
            """
            SELECT tenant_id, blurt_account, stone_address, bytes_cap, updated_at
            FROM bandwidth_tenant_bindings
            WHERE tenant_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (tid, lim),
        ).fetchall()
        bw_map = {
            (str(r["tenant_id"]), str(r["blurt_account"])): dict(r) for r in bw_rows
        }
        st_rows = conn.execute(
            """
            SELECT tenant_id, blurt_account, stone_address, bytes_cap, updated_at
            FROM storage_tenant_bindings
            WHERE tenant_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (tid, lim),
        ).fetchall()
        st_map = {
            (str(r["tenant_id"]), str(r["blurt_account"])): dict(r) for r in st_rows
        }
    for snap in snaps:
        key = (snap["tenant_id"], snap["blurt_account"])
        bw_row = bw_map.get(key)
        st_row = st_map.get(key)
        if bw_row:
            snap["rails"]["bandwidth"] = {"bytes_cap": int(bw_row.get("bytes_cap") or 0)}
            snap["updated_at"] = max(snap["updated_at"], int(bw_row.get("updated_at") or 0))
        if st_row:
            snap["rails"]["storage"] = {"bytes_cap": int(st_row.get("bytes_cap") or 0)}
            snap["updated_at"] = max(snap["updated_at"], int(st_row.get("updated_at") or 0))
    from chain_mesh import tenant_fleet_sign as tsign

    return tsign.sign_snapshots(snaps)


def ingest_tenant_snapshots(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    from chain_mesh import bandwidth_tenant_quota as bw
    from chain_mesh import compute_tenant_quota as compute
    from chain_mesh import storage_tenant_quota as storage

    from chain_mesh import tenant_fleet_sign as tsign

    if not _tenant_sync_enable():
        return {"ok": True, "skipped": True, "reason": "TENANT_FLEET_SYNC_ENABLE off"}
    accepted, rejected = tsign.filter_verified_snapshots(snapshots)
    recorded = 0
    skipped = 0
    for snap in accepted:
        if not isinstance(snap, dict):
            skipped += 1
            continue
        author = (snap.get("blurt_account") or "").lstrip("@").lower().strip()
        if not author:
            skipped += 1
            continue
        tid = (snap.get("tenant_id") or _default_tenant()).strip()[:64]
        addr = str(snap.get("stone_address") or "").strip()
        rails = snap.get("rails") if isinstance(snap.get("rails"), dict) else {}
        compute_r = rails.get("compute") if isinstance(rails.get("compute"), dict) else {}
        bw_r = rails.get("bandwidth") if isinstance(rails.get("bandwidth"), dict) else {}
        st_r = rails.get("storage") if isinstance(rails.get("storage"), dict) else {}
        if int(compute_r.get("flops_cap") or 0) > 0:
            compute.bind_tenant_author(
                tenant_id=tid,
                blurt_account=author,
                stone_address=addr,
                flops_cap=int(compute_r.get("flops_cap") or 0),
            )
        if int(bw_r.get("bytes_cap") or 0) > 0:
            bw.bind_tenant_author(
                tenant_id=tid,
                blurt_account=author,
                stone_address=addr,
                bytes_cap=int(bw_r.get("bytes_cap") or 0),
            )
        if int(st_r.get("bytes_cap") or 0) > 0:
            storage.bind_tenant_author(
                tenant_id=tid,
                blurt_account=author,
                stone_address=addr,
                bytes_cap=int(st_r.get("bytes_cap") or 0),
            )
        if any(
            int((r or {}).get("flops_cap") or (r or {}).get("bytes_cap") or 0) > 0
            for r in (compute_r, bw_r, st_r)
        ):
            recorded += 1
        else:
            skipped += 1
    return {
        "ok": True,
        "recorded": recorded,
        "skipped": skipped,
        "rejected": len(rejected),
        "rejections": rejected[:5],
    }


def resolve_tenant_context(
    *,
    blurt_account: str = "",
    tenant_id: str = "",
    stone_address: str = "",
) -> Dict[str, str]:
    author = (blurt_account or "").lstrip("@").lower().strip()
    tid = (tenant_id or _default_tenant()).strip()[:64] or _default_tenant()
    return {
        "tenant_id": tid,
        "blurt_account": author,
        "stone_address": (stone_address or "").strip(),
    }


def status_payload() -> Dict[str, Any]:
    snaps = collect_tenant_snapshots(limit=5)
    public = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    return {
        "ok": True,
        "format": SYNC_FORMAT,
        "enabled": _tenant_sync_enable(),
        "default_tenant": _default_tenant(),
        "snapshot_count": len(snaps),
        "apis": {
            "status": f"{public}/api/convergence/tenant/fleet/status",
            "snapshots": f"{public}/api/convergence/tenant/fleet/snapshots",
            "sign_status": f"{public}/api/convergence/tenant/fleet/sign/status",
            "quorum_status": f"{public}/api/convergence/tenant/fleet/quorum/status",
            "dashboard": f"{public}/convergence/tenant",
        },
    }