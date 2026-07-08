"""Wave X — fleet gossip exchange for Blurt tenant manifest snapshots."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List

MANIFEST_GOSSIP_FORMAT = "bloodstone_tenant_manifest_gossip/v1"
MANIFEST_GOSSIP_ENABLE = os.environ.get("TENANT_MANIFEST_GOSSIP_ENABLE", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)
MANIFEST_GOSSIP_LIMIT = max(1, int(os.environ.get("TENANT_MANIFEST_GOSSIP_LIMIT", "10")))


def _now() -> int:
    return int(time.time())


def _node_id() -> str:
    return (os.environ.get("DTN_NODE_ID") or "pi-edge").strip()[:64]


def build_manifest_snapshots(*, limit: int = 0) -> List[Dict[str, Any]]:
    if not MANIFEST_GOSSIP_ENABLE:
        return []
    from chain_mesh import tenant_broadcast as tb

    lim = limit or MANIFEST_GOSSIP_LIMIT
    result = tb.list_local_broadcast_candidates(limit=lim)
    snaps: List[Dict[str, Any]] = []
    for manifest in result.get("manifests") or []:
        body = manifest.get("body") or {}
        if not body.get("blurt_author"):
            continue
        snaps.append(
            {
                "format": MANIFEST_GOSSIP_FORMAT,
                "node_id": _node_id(),
                "reported_at": _now(),
                "manifest_id": tb.TENANT_MANIFEST_ID,
                "body": body,
                "blurt_custom_json": {
                    "id": manifest.get("id"),
                    "json": manifest.get("json"),
                },
            }
        )
    return snaps


def ingest_manifest_snapshots(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not MANIFEST_GOSSIP_ENABLE:
        return {"ok": True, "skipped": True, "reason": "TENANT_MANIFEST_GOSSIP_ENABLE off"}
    from chain_mesh import tenant_broadcast as tb

    indexed = 0
    skipped = 0
    for snap in snapshots or []:
        if not isinstance(snap, dict):
            skipped += 1
            continue
        if str(snap.get("format") or "") != MANIFEST_GOSSIP_FORMAT:
            skipped += 1
            continue
        body = snap.get("body") if isinstance(snap.get("body"), dict) else {}
        if not body.get("blurt_author"):
            skipped += 1
            continue
        try:
            tb.index_manifest(
                body=body,
                source=f"gossip:{snap.get('node_id') or 'peer'}",
            )
            indexed += 1
        except Exception:
            skipped += 1
    return {"ok": True, "indexed": indexed, "skipped": skipped}


def status_payload() -> Dict[str, Any]:
    public = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    snaps = build_manifest_snapshots(limit=3)
    return {
        "ok": True,
        "format": MANIFEST_GOSSIP_FORMAT,
        "enabled": MANIFEST_GOSSIP_ENABLE,
        "snapshot_count": len(snaps),
        "limit": MANIFEST_GOSSIP_LIMIT,
        "apis": {
            "status": f"{public}/api/convergence/tenant/manifest/gossip/status",
            "snapshots": f"{public}/api/convergence/tenant/manifest/gossip/snapshots",
        },
    }