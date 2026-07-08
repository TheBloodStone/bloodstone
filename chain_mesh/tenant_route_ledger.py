"""Wave Y — tenant route assignment ledger + fleet gossip hints."""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db

LEDGER_FORMAT = "bloodstone_tenant_route_ledger/v1"
LEDGER_ENABLE = os.environ.get("TENANT_ROUTE_LEDGER_ENABLE", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)
LEDGER_GOSSIP_LIMIT = max(1, int(os.environ.get("TENANT_ROUTE_LEDGER_GOSSIP_LIMIT", "10")))


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def _default_tenant() -> str:
    return (os.environ.get("DTN_DEFAULT_TENANT") or "bloodstone").strip()[:64] or "bloodstone"


def _normalize_author(value: str = "") -> str:
    return (value or "").lstrip("@").lower().strip()[:64]


def _node_id() -> str:
    return (os.environ.get("DTN_NODE_ID") or "pi-edge").strip()[:64]


def init_route_ledger_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tenant_route_assignments (
                assignment_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                blurt_author TEXT NOT NULL DEFAULT '',
                job_id TEXT NOT NULL DEFAULT '',
                provider_id TEXT NOT NULL DEFAULT '',
                runtime TEXT NOT NULL DEFAULT '',
                hardware_kind TEXT NOT NULL DEFAULT 'cpu',
                route_status TEXT NOT NULL DEFAULT 'assigned',
                score REAL NOT NULL DEFAULT 0,
                node_id TEXT NOT NULL DEFAULT '',
                updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tenant_route_author
                ON tenant_route_assignments(tenant_id, blurt_author, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_tenant_route_job
                ON tenant_route_assignments(job_id, updated_at DESC);
            """
        )


def record_assignment(
    *,
    job: Dict[str, Any],
    provider: Dict[str, Any],
    tenant_spec: Optional[Dict[str, Any]] = None,
    score: float = 0.0,
    route_status: str = "assigned",
) -> Dict[str, Any]:
    if not LEDGER_ENABLE:
        return {"ok": True, "skipped": True, "reason": "TENANT_ROUTE_LEDGER_ENABLE off"}
    init_route_ledger_db()
    author = _normalize_author(str(job.get("blurt_author") or ""))
    tid = str(job.get("tenant_id") or _default_tenant()).strip()[:64] or _default_tenant()
    jid = str(job.get("job_id") or "").strip()
    pid = str(provider.get("provider_id") or "").strip()
    spec = tenant_spec if isinstance(tenant_spec, dict) else {}
    runtime = str(spec.get("runtime") or "").strip().lower()
    hw = str(spec.get("hardware_kind") or "cpu").strip().lower()
    now = _now()
    aid = hashlib.sha256(f"{tid}:{author}:{jid}:{pid}:{now}".encode("utf-8")).hexdigest()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO tenant_route_assignments (
                assignment_id, tenant_id, blurt_author, job_id, provider_id,
                runtime, hardware_kind, route_status, score, node_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                aid,
                tid,
                author,
                jid,
                pid,
                runtime,
                hw,
                str(route_status or "assigned")[:32],
                float(score or 0),
                _node_id(),
                now,
            ),
        )
    return {
        "ok": True,
        "assignment_id": aid,
        "tenant_id": tid,
        "blurt_author": author,
        "job_id": jid,
        "provider_id": pid,
        "runtime": runtime,
    }


def list_assignments(
    *,
    tenant_id: str = "",
    blurt_author: str = "",
    limit: int = 20,
) -> Dict[str, Any]:
    init_route_ledger_db()
    tid = (tenant_id or _default_tenant()).strip()[:64] or _default_tenant()
    author = _normalize_author(blurt_author)
    lim = max(1, min(100, int(limit)))
    with _conn() as conn:
        if author:
            rows = conn.execute(
                """
                SELECT * FROM tenant_route_assignments
                WHERE tenant_id = ? AND blurt_author = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (tid, author, lim),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM tenant_route_assignments
                WHERE tenant_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (tid, lim),
            ).fetchall()
    return {
        "ok": True,
        "format": LEDGER_FORMAT,
        "tenant_id": tid,
        "blurt_author": author,
        "count": len(rows),
        "assignments": [dict(r) for r in rows],
    }


def build_route_gossip_snapshots(*, limit: int = 0) -> List[Dict[str, Any]]:
    if not LEDGER_ENABLE:
        return []
    init_route_ledger_db()
    lim = limit or LEDGER_GOSSIP_LIMIT
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT tenant_id, blurt_author, job_id, provider_id, runtime,
                   hardware_kind, route_status, score, node_id, updated_at
            FROM tenant_route_assignments
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (lim,),
        ).fetchall()
    return [
        {
            "format": LEDGER_FORMAT,
            "node_id": _node_id(),
            "reported_at": _now(),
            **dict(row),
        }
        for row in rows
    ]


def ingest_route_snapshots(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not LEDGER_ENABLE:
        return {"ok": True, "skipped": True}
    init_route_ledger_db()
    recorded = 0
    skipped = 0
    for snap in snapshots or []:
        if not isinstance(snap, dict):
            skipped += 1
            continue
        if str(snap.get("format") or "") != LEDGER_FORMAT:
            skipped += 1
            continue
        jid = str(snap.get("job_id") or "").strip()
        if not jid:
            skipped += 1
            continue
        try:
            record_assignment(
                job={
                    "job_id": jid,
                    "tenant_id": snap.get("tenant_id"),
                    "blurt_author": snap.get("blurt_author"),
                },
                provider={"provider_id": snap.get("provider_id")},
                tenant_spec={
                    "runtime": snap.get("runtime"),
                    "hardware_kind": snap.get("hardware_kind"),
                },
                score=float(snap.get("score") or 0),
                route_status=str(snap.get("route_status") or "assigned"),
            )
            recorded += 1
        except Exception:
            skipped += 1
    return {"ok": True, "recorded": recorded, "skipped": skipped}


def status_payload() -> Dict[str, Any]:
    init_route_ledger_db()
    with _conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM tenant_route_assignments"
        ).fetchone()["c"]
    public = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    return {
        "ok": True,
        "format": LEDGER_FORMAT,
        "enabled": LEDGER_ENABLE,
        "assignments_total": int(total),
        "apis": {
            "status": f"{public}/api/convergence/tenant/route/ledger/status",
            "assignments": f"{public}/api/convergence/tenant/route/ledger/assignments",
        },
    }