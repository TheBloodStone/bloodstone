"""Wave V — fleet-wide tenant snapshot quorum (N-of-M peer agreement)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from chain_mesh import db as mesh_db

QUORUM_FORMAT = "bloodstone_tenant_fleet_quorum/v1"
QUORUM_ENABLE = os.environ.get("TENANT_FLEET_QUORUM_ENABLE", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)
QUORUM_ENFORCE = os.environ.get("TENANT_FLEET_QUORUM_ENFORCE", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
QUORUM_N = max(1, int(os.environ.get("TENANT_FLEET_QUORUM_N", "2")))
QUORUM_M = max(QUORUM_N, int(os.environ.get("TENANT_FLEET_QUORUM_M", "3")))
VOTE_TTL_SEC = max(300, int(os.environ.get("TENANT_FLEET_QUORUM_VOTE_TTL_SEC", "3600")))


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def _node_id() -> str:
    return (os.environ.get("DTN_NODE_ID") or "pi-edge").strip()[:64]


def init_tenant_quorum_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tenant_fleet_votes (
                vote_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                blurt_author TEXT NOT NULL,
                reporter_node_id TEXT NOT NULL DEFAULT '',
                rails_hash TEXT NOT NULL DEFAULT '',
                rails_json TEXT NOT NULL DEFAULT '{}',
                stone_address TEXT NOT NULL DEFAULT '',
                signature TEXT NOT NULL DEFAULT '',
                reported_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tenant_fleet_votes_lookup
                ON tenant_fleet_votes(tenant_id, blurt_author, rails_hash, reported_at DESC);

            CREATE TABLE IF NOT EXISTS tenant_fleet_quorum (
                tenant_id TEXT NOT NULL,
                blurt_author TEXT NOT NULL,
                rails_hash TEXT NOT NULL DEFAULT '',
                votes_found INTEGER NOT NULL DEFAULT 0,
                quorum_n INTEGER NOT NULL DEFAULT 2,
                quorum_m INTEGER NOT NULL DEFAULT 3,
                satisfied INTEGER NOT NULL DEFAULT 0,
                rails_json TEXT NOT NULL DEFAULT '{}',
                stone_address TEXT NOT NULL DEFAULT '',
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (tenant_id, blurt_author)
            );
            """
        )


def _normalize_author(value: str = "") -> str:
    return (value or "").lstrip("@").lower().strip()[:64]


def rails_hash(snapshot: Dict[str, Any]) -> str:
    rails = snapshot.get("rails") if isinstance(snapshot.get("rails"), dict) else {}
    body = {
        "tenant_id": str(snapshot.get("tenant_id") or "").strip()[:64],
        "blurt_author": _normalize_author(str(snapshot.get("blurt_author") or "")),
        "stone_address": str(snapshot.get("stone_address") or "").strip(),
        "rails": rails,
    }
    raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def record_snapshot_votes(
    snapshots: List[Dict[str, Any]],
    *,
    reporter_node_id: str = "",
) -> Dict[str, Any]:
    if not QUORUM_ENABLE:
        return {"ok": True, "skipped": True, "reason": "TENANT_FLEET_QUORUM_ENABLE off"}
    from chain_mesh import tenant_fleet_sign as tsign

    init_tenant_quorum_db()
    reporter = (reporter_node_id or _node_id()).strip()[:64]
    now = _now()
    expires = now + VOTE_TTL_SEC
    recorded = 0
    skipped = 0
    with _conn() as conn:
        for snap in snapshots or []:
            if not isinstance(snap, dict):
                skipped += 1
                continue
            ok, _ = tsign.verify_snapshot(snap)
            if not ok:
                skipped += 1
                continue
            author = _normalize_author(str(snap.get("blurt_author") or ""))
            tid = str(snap.get("tenant_id") or "").strip()[:64]
            if not author or not tid:
                skipped += 1
                continue
            rh = rails_hash(snap)
            vote_id = hashlib.sha256(
                f"{tid}:{author}:{rh}:{reporter}:{int(snap.get('signed_at') or snap.get('updated_at') or now)}".encode(
                    "utf-8"
                )
            ).hexdigest()
            rails = snap.get("rails") if isinstance(snap.get("rails"), dict) else {}
            conn.execute(
                """
                INSERT INTO tenant_fleet_votes (
                    vote_id, tenant_id, blurt_author, reporter_node_id, rails_hash,
                    rails_json, stone_address, signature, reported_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(vote_id) DO UPDATE SET
                    reported_at = MAX(reported_at, excluded.reported_at),
                    expires_at = MAX(expires_at, excluded.expires_at)
                """,
                (
                    vote_id,
                    tid,
                    author,
                    reporter,
                    rh,
                    json.dumps(rails, separators=(",", ":")),
                    str(snap.get("stone_address") or "").strip(),
                    str(snap.get("signature") or "").strip(),
                    now,
                    expires,
                ),
            )
            recorded += 1
    rollup = update_quorum_state()
    return {
        "ok": True,
        "recorded": recorded,
        "skipped": skipped,
        "quorum": rollup,
    }


def update_quorum_state() -> Dict[str, Any]:
    if not QUORUM_ENABLE:
        return {"ok": True, "skipped": True}
    init_tenant_quorum_db()
    now = _now()
    checked = 0
    satisfied_count = 0
    with _conn() as conn:
        pairs = conn.execute(
            """
            SELECT DISTINCT tenant_id, blurt_author
            FROM tenant_fleet_votes
            WHERE expires_at >= ?
            """,
            (now,),
        ).fetchall()
        for pair in pairs:
            tid = str(pair["tenant_id"])
            author = str(pair["blurt_author"])
            checked += 1
            rows = conn.execute(
                """
                SELECT rails_hash, rails_json, stone_address, COUNT(DISTINCT reporter_node_id) AS voters
                FROM tenant_fleet_votes
                WHERE tenant_id = ? AND blurt_author = ? AND expires_at >= ?
                GROUP BY rails_hash
                ORDER BY voters DESC
                LIMIT 1
                """,
                (tid, author, now),
            ).fetchone()
            if not rows:
                continue
            voters = int(rows["voters"] or 0)
            satisfied = 1 if voters >= QUORUM_N else 0
            if satisfied:
                satisfied_count += 1
            conn.execute(
                """
                INSERT INTO tenant_fleet_quorum (
                    tenant_id, blurt_author, rails_hash, votes_found, quorum_n, quorum_m,
                    satisfied, rails_json, stone_address, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, blurt_author) DO UPDATE SET
                    rails_hash = excluded.rails_hash,
                    votes_found = excluded.votes_found,
                    quorum_n = excluded.quorum_n,
                    quorum_m = excluded.quorum_m,
                    satisfied = excluded.satisfied,
                    rails_json = excluded.rails_json,
                    stone_address = CASE WHEN excluded.stone_address != '' THEN excluded.stone_address ELSE stone_address END,
                    updated_at = excluded.updated_at
                """,
                (
                    tid,
                    author,
                    str(rows["rails_hash"]),
                    voters,
                    QUORUM_N,
                    QUORUM_M,
                    satisfied,
                    str(rows["rails_json"] or "{}"),
                    str(rows["stone_address"] or ""),
                    now,
                ),
            )
    return {
        "ok": True,
        "pairs_checked": checked,
        "pairs_satisfied": satisfied_count,
        "quorum": f"{QUORUM_N}-of-{QUORUM_M}",
    }


def apply_satisfied_bindings(*, limit: int = 50) -> Dict[str, Any]:
    if not QUORUM_ENABLE:
        return {"ok": True, "skipped": True, "reason": "quorum disabled"}
    from chain_mesh import bandwidth_tenant_quota as bw
    from chain_mesh import compute_tenant_quota as compute
    from chain_mesh import storage_tenant_quota as storage

    init_tenant_quorum_db()
    applied = 0
    skipped = 0
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT tenant_id, blurt_author, rails_json, stone_address
            FROM tenant_fleet_quorum
            WHERE satisfied = 1
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (max(1, min(200, int(limit))),),
        ).fetchall()
    for row in rows:
        try:
            rails = json.loads(str(row["rails_json"] or "{}"))
        except json.JSONDecodeError:
            skipped += 1
            continue
        if not isinstance(rails, dict):
            skipped += 1
            continue
        author = str(row["blurt_author"])
        tid = str(row["tenant_id"])
        addr = str(row["stone_address"] or "").strip()
        compute_r = rails.get("compute") if isinstance(rails.get("compute"), dict) else {}
        bw_r = rails.get("bandwidth") if isinstance(rails.get("bandwidth"), dict) else {}
        st_r = rails.get("storage") if isinstance(rails.get("storage"), dict) else {}
        touched = False
        if int(compute_r.get("flops_cap") or 0) > 0:
            compute.bind_tenant_author(
                tenant_id=tid,
                blurt_author=author,
                stone_address=addr,
                flops_cap=int(compute_r.get("flops_cap") or 0),
            )
            touched = True
        if int(bw_r.get("bytes_cap") or 0) > 0:
            bw.bind_tenant_author(
                tenant_id=tid,
                blurt_author=author,
                stone_address=addr,
                bytes_cap=int(bw_r.get("bytes_cap") or 0),
            )
            touched = True
        if int(st_r.get("bytes_cap") or 0) > 0:
            storage.bind_tenant_author(
                tenant_id=tid,
                blurt_author=author,
                stone_address=addr,
                bytes_cap=int(st_r.get("bytes_cap") or 0),
            )
            touched = True
        if touched:
            applied += 1
        else:
            skipped += 1
    return {"ok": True, "applied": applied, "skipped": skipped}


def ingest_with_quorum(snapshots: List[Dict[str, Any]], *, reporter_node_id: str = "") -> Dict[str, Any]:
    from chain_mesh import tenant_fleet_sync as tfleet

    vote_result = record_snapshot_votes(snapshots, reporter_node_id=reporter_node_id)
    if QUORUM_ENFORCE:
        apply_result = apply_satisfied_bindings()
        return {
            "ok": True,
            "enforce": True,
            "votes": vote_result,
            "applied": apply_result,
        }
    ingest_result = tfleet.ingest_tenant_snapshots(snapshots)
    apply_result = apply_satisfied_bindings()
    return {
        "ok": True,
        "enforce": False,
        "ingest": ingest_result,
        "votes": vote_result,
        "applied": apply_result,
    }


def build_quorum_snapshot() -> Optional[Dict[str, Any]]:
    if not QUORUM_ENABLE:
        return None
    from chain_mesh import tenant_fleet_sync as tfleet

    snaps = tfleet.collect_tenant_snapshots(limit=10)
    if not snaps:
        return None
    return {
        "format": QUORUM_FORMAT,
        "node_id": _node_id(),
        "reported_at": _now(),
        "quorum": f"{QUORUM_N}-of-{QUORUM_M}",
        "snapshot_count": len(snaps),
        "tenant_snapshots": snaps,
    }


def ingest_quorum_snapshots(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    recorded = 0
    for snap in snapshots or []:
        if not isinstance(snap, dict):
            continue
        if str(snap.get("format") or "") != QUORUM_FORMAT:
            continue
        tenant_snaps = [
            row for row in (snap.get("tenant_snapshots") or []) if isinstance(row, dict)
        ]
        reporter = str(snap.get("node_id") or "")
        result = record_snapshot_votes(tenant_snaps, reporter_node_id=reporter)
        recorded += int(result.get("recorded") or 0)
    apply = apply_satisfied_bindings()
    return {"ok": True, "snapshots_ingested": len(snapshots or []), "votes_recorded": recorded, "applied": apply}


def status_payload() -> Dict[str, Any]:
    init_tenant_quorum_db()
    now = _now()
    with _conn() as conn:
        votes = conn.execute(
            "SELECT COUNT(*) AS c FROM tenant_fleet_votes WHERE expires_at >= ?",
            (now,),
        ).fetchone()["c"]
        satisfied = conn.execute(
            "SELECT COUNT(*) AS c FROM tenant_fleet_quorum WHERE satisfied = 1",
        ).fetchone()["c"]
        tracked = conn.execute("SELECT COUNT(*) AS c FROM tenant_fleet_quorum").fetchone()["c"]
        sample = conn.execute(
            """
            SELECT tenant_id, blurt_author, votes_found, satisfied, updated_at
            FROM tenant_fleet_quorum
            ORDER BY updated_at DESC
            LIMIT 5
            """
        ).fetchall()
    public = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    return {
        "ok": True,
        "format": QUORUM_FORMAT,
        "enabled": QUORUM_ENABLE,
        "enforce": QUORUM_ENFORCE,
        "quorum": f"{QUORUM_N}-of-{QUORUM_M}",
        "vote_ttl_sec": VOTE_TTL_SEC,
        "active_votes": int(votes),
        "pairs_tracked": int(tracked),
        "pairs_satisfied": int(satisfied),
        "sample": [dict(r) for r in sample],
        "apis": {
            "status": f"{public}/api/convergence/tenant/fleet/quorum/status",
            "snapshots": f"{public}/api/convergence/tenant/fleet/quorum/snapshots",
        },
    }