"""Wave Z — cross-region tenant fleet quorum rollup via gossip snapshots."""

from __future__ import annotations

import hashlib
import os
import time
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db

TENANT_PLANETARY_FORMAT = "bloodstone_tenant_planetary/v1"
TENANT_PLANETARY_ENABLE = os.environ.get("TENANT_PLANETARY_ENABLE", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)
TENANT_PLANETARY_MIN_REGIONS = max(1, int(os.environ.get("TENANT_PLANETARY_MIN_REGIONS", "1")))
TENANT_PLANETARY_REGION_RATIO = min(
    1.0,
    max(0.1, float(os.environ.get("TENANT_PLANETARY_REGION_RATIO", "0.8"))),
)
TENANT_PLANETARY_VOTE_TTL_SEC = max(
    300, int(os.environ.get("TENANT_PLANETARY_VOTE_TTL_SEC", "7200"))
)
TENANT_PLANETARY_MAX_REGIONS = max(5, int(os.environ.get("TENANT_PLANETARY_MAX_REGIONS", "32")))

_LAST_ROLLUP: Dict[str, Any] = {}


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def _node_id() -> str:
    return (os.environ.get("DTN_NODE_ID") or "pi-edge").strip()[:64]


def _region() -> str:
    return (os.environ.get("DTN_DEFAULT_REGION", "global") or "global").strip()[:32]


def init_tenant_planetary_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tenant_planetary_regions (
                region TEXT PRIMARY KEY,
                source TEXT NOT NULL DEFAULT 'local',
                pairs_tracked INTEGER NOT NULL DEFAULT 0,
                pairs_satisfied INTEGER NOT NULL DEFAULT 0,
                pairs_under_quorum INTEGER NOT NULL DEFAULT 0,
                quorum_ratio REAL NOT NULL DEFAULT 0,
                peer_votes INTEGER NOT NULL DEFAULT 0,
                satisfied INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tenant_planetary_votes (
                vote_id TEXT PRIMARY KEY,
                reporter_node_id TEXT NOT NULL DEFAULT '',
                reporter_region TEXT NOT NULL DEFAULT '',
                target_region TEXT NOT NULL DEFAULT '',
                pairs_tracked INTEGER NOT NULL DEFAULT 0,
                pairs_satisfied INTEGER NOT NULL DEFAULT 0,
                pairs_under_quorum INTEGER NOT NULL DEFAULT 0,
                quorum_n INTEGER NOT NULL DEFAULT 2,
                quorum_m INTEGER NOT NULL DEFAULT 3,
                reported_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tenant_planetary_votes_region
                ON tenant_planetary_votes(target_region, reported_at DESC);
            """
        )


def _discover_regions() -> List[str]:
    from chain_mesh import dtn_sync as dtn

    dtn.init_dtn_db()
    init_tenant_planetary_db()
    regions = {_region()}
    with _conn() as conn:
        for row in conn.execute(
            "SELECT DISTINCT region FROM dtn_peers WHERE region != '' LIMIT ?",
            (TENANT_PLANETARY_MAX_REGIONS,),
        ).fetchall():
            regions.add(str(row["region"]).strip()[:32])
        for row in conn.execute(
            """
            SELECT DISTINCT target_region FROM tenant_planetary_votes
            WHERE expires_at >= ?
            LIMIT ?
            """,
            (_now(), TENANT_PLANETARY_MAX_REGIONS),
        ).fetchall():
            regions.add(str(row["target_region"]).strip()[:32])
        for row in conn.execute(
            "SELECT DISTINCT region FROM tenant_planetary_regions LIMIT ?",
            (TENANT_PLANETARY_MAX_REGIONS,),
        ).fetchall():
            regions.add(str(row["region"]).strip()[:32])
    return sorted(r for r in regions if r)[:TENANT_PLANETARY_MAX_REGIONS]


def _local_region_stats(region: str) -> Dict[str, Any]:
    from chain_mesh import tenant_fleet_quorum as tquorum

    tquorum.init_tenant_quorum_db()
    tquorum.update_quorum_state()
    with _conn() as conn:
        tracked = conn.execute(
            "SELECT COUNT(*) AS c FROM tenant_fleet_quorum"
        ).fetchone()["c"]
        satisfied = conn.execute(
            "SELECT COUNT(*) AS c FROM tenant_fleet_quorum WHERE satisfied = 1"
        ).fetchone()["c"]
    tracked_i = int(tracked)
    satisfied_i = int(satisfied)
    under = max(0, tracked_i - satisfied_i)
    ratio = (satisfied_i / tracked_i) if tracked_i else 1.0
    return {
        "pairs_tracked": tracked_i,
        "pairs_satisfied": satisfied_i,
        "pairs_under_quorum": under,
        "quorum_ratio": round(ratio, 4),
        "peer_votes": 0,
        "source": "local",
        "region": region,
    }


def _remote_region_stats(region: str) -> Dict[str, Any]:
    init_tenant_planetary_db()
    cutoff = _now() - TENANT_PLANETARY_VOTE_TTL_SEC
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT reporter_node_id, pairs_tracked, pairs_satisfied,
                   pairs_under_quorum, quorum_n, quorum_m, reported_at
            FROM tenant_planetary_votes
            WHERE target_region = ? AND expires_at >= ? AND reported_at >= ?
            ORDER BY reported_at DESC
            """,
            (region, _now(), cutoff),
        ).fetchall()
    if not rows:
        return {
            "pairs_tracked": 0,
            "pairs_satisfied": 0,
            "pairs_under_quorum": 0,
            "quorum_ratio": 0.0,
            "peer_votes": 0,
            "source": "unknown",
            "region": region,
        }

    by_reporter: Dict[str, Any] = {}
    for row in rows:
        rid = str(row["reporter_node_id"] or "")
        if rid and rid not in by_reporter:
            by_reporter[rid] = row

    votes = list(by_reporter.values())
    tracked = max(int(r["pairs_tracked"]) for r in votes)
    under = min(int(r["pairs_under_quorum"]) for r in votes)
    satisfied = max(0, tracked - under)
    ratio = (satisfied / tracked) if tracked else 0.0
    return {
        "pairs_tracked": tracked,
        "pairs_satisfied": satisfied,
        "pairs_under_quorum": under,
        "quorum_ratio": round(ratio, 4),
        "peer_votes": len(votes),
        "source": "gossip",
        "region": region,
    }


def _region_satisfied(stats: Dict[str, Any]) -> bool:
    tracked = int(stats.get("pairs_tracked") or 0)
    under = int(stats.get("pairs_under_quorum") or 0)
    ratio = float(stats.get("quorum_ratio") or 0)
    if tracked == 0:
        return int(stats.get("peer_votes") or 0) > 0
    if under == 0:
        return True
    return ratio >= TENANT_PLANETARY_REGION_RATIO


def build_quorum_snapshot() -> Dict[str, Any]:
    from chain_mesh import tenant_fleet_quorum as tquorum

    if not TENANT_PLANETARY_ENABLE:
        return {}
    tquorum.init_tenant_quorum_db()
    init_tenant_planetary_db()
    reg = _region()
    stats = _local_region_stats(reg)
    return {
        "format": TENANT_PLANETARY_FORMAT,
        "node_id": _node_id(),
        "region": reg,
        "pairs_tracked": stats["pairs_tracked"],
        "pairs_satisfied": stats["pairs_satisfied"],
        "pairs_under_quorum": stats["pairs_under_quorum"],
        "quorum_n": tquorum.QUORUM_N,
        "quorum_m": tquorum.QUORUM_M,
        "reported_at": _now(),
    }


def ingest_quorum_snapshots(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not TENANT_PLANETARY_ENABLE:
        return {"ok": True, "skipped": True, "votes_recorded": 0}
    init_tenant_planetary_db()
    now = _now()
    expires = now + TENANT_PLANETARY_VOTE_TTL_SEC
    recorded = 0
    skipped = 0

    for snap in snapshots or []:
        if not isinstance(snap, dict):
            skipped += 1
            continue
        fmt = str(snap.get("format") or TENANT_PLANETARY_FORMAT)
        if fmt != TENANT_PLANETARY_FORMAT:
            skipped += 1
            continue
        reporter = str(snap.get("node_id") or "").strip()[:64]
        target = str(snap.get("region") or "").strip()[:32]
        if not reporter or not target:
            skipped += 1
            continue
        reported_at = int(snap.get("reported_at") or now)
        if reported_at < now - TENANT_PLANETARY_VOTE_TTL_SEC:
            skipped += 1
            continue
        vote_id = hashlib.sha256(f"{reporter}|{target}|{reported_at}".encode()).hexdigest()[:24]
        with _conn() as conn:
            conn.execute(
                """
                INSERT INTO tenant_planetary_votes (
                    vote_id, reporter_node_id, reporter_region, target_region,
                    pairs_tracked, pairs_satisfied, pairs_under_quorum,
                    quorum_n, quorum_m, reported_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(vote_id) DO UPDATE SET
                    pairs_tracked = excluded.pairs_tracked,
                    pairs_satisfied = excluded.pairs_satisfied,
                    pairs_under_quorum = excluded.pairs_under_quorum,
                    quorum_n = excluded.quorum_n,
                    quorum_m = excluded.quorum_m,
                    reported_at = excluded.reported_at,
                    expires_at = excluded.expires_at
                """,
                (
                    vote_id,
                    reporter,
                    str(snap.get("reporter_region") or target)[:32],
                    target,
                    int(snap.get("pairs_tracked") or 0),
                    int(snap.get("pairs_satisfied") or 0),
                    int(snap.get("pairs_under_quorum") or 0),
                    int(snap.get("quorum_n") or 2),
                    int(snap.get("quorum_m") or 3),
                    reported_at,
                    expires,
                ),
            )
        recorded += 1

    return {"ok": True, "votes_recorded": recorded, "votes_skipped": skipped}


def update_tenant_planetary_quorum() -> Dict[str, Any]:
    if not TENANT_PLANETARY_ENABLE:
        return {"ok": True, "skipped": True, "reason": "TENANT_PLANETARY_ENABLE off"}

    init_tenant_planetary_db()
    local = _region()
    regions = _discover_regions()
    now = _now()
    region_rows: List[Dict[str, Any]] = []
    satisfied_count = 0

    for reg in regions:
        if reg == local:
            stats = _local_region_stats(reg)
        else:
            stats = _remote_region_stats(reg)
        ok = _region_satisfied(stats)
        if ok:
            satisfied_count += 1
        with _conn() as conn:
            conn.execute(
                """
                INSERT INTO tenant_planetary_regions (
                    region, source, pairs_tracked, pairs_satisfied,
                    pairs_under_quorum, quorum_ratio, peer_votes,
                    satisfied, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(region) DO UPDATE SET
                    source = excluded.source,
                    pairs_tracked = excluded.pairs_tracked,
                    pairs_satisfied = excluded.pairs_satisfied,
                    pairs_under_quorum = excluded.pairs_under_quorum,
                    quorum_ratio = excluded.quorum_ratio,
                    peer_votes = excluded.peer_votes,
                    satisfied = excluded.satisfied,
                    updated_at = excluded.updated_at
                """,
                (
                    reg,
                    stats["source"],
                    stats["pairs_tracked"],
                    stats["pairs_satisfied"],
                    stats["pairs_under_quorum"],
                    stats["quorum_ratio"],
                    stats["peer_votes"],
                    1 if ok else 0,
                    now,
                ),
            )
        region_rows.append({"region": reg, "satisfied": ok, **stats})

    under = len(regions) - satisfied_count
    planetary_ok = (
        len(regions) >= TENANT_PLANETARY_MIN_REGIONS
        and under == 0
        and satisfied_count >= TENANT_PLANETARY_MIN_REGIONS
    )
    result = {
        "ok": True,
        "format": TENANT_PLANETARY_FORMAT,
        "node_id": _node_id(),
        "local_region": local,
        "regions_total": len(regions),
        "regions_satisfied": satisfied_count,
        "regions_under_quorum": under,
        "planetary_satisfied": planetary_ok,
        "min_regions": TENANT_PLANETARY_MIN_REGIONS,
        "region_ratio_threshold": TENANT_PLANETARY_REGION_RATIO,
        "regions": region_rows[:20],
    }
    _LAST_ROLLUP.clear()
    _LAST_ROLLUP.update(result)
    return result


def list_regions(*, limit: int = 50) -> Dict[str, Any]:
    init_tenant_planetary_db()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT region, source, pairs_tracked, pairs_satisfied,
                   pairs_under_quorum, quorum_ratio, peer_votes,
                   satisfied, updated_at
            FROM tenant_planetary_regions
            ORDER BY satisfied ASC, quorum_ratio ASC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
    return {
        "ok": True,
        "format": TENANT_PLANETARY_FORMAT,
        "regions": [dict(r) for r in rows],
        "count": len(rows),
    }


def build_planetary_gossip_snapshots(*, limit: int = 5) -> List[Dict[str, Any]]:
    if not TENANT_PLANETARY_ENABLE:
        return []
    snap = build_quorum_snapshot()
    return [snap] if snap else []


def ingest_planetary_snapshots(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    ingest = ingest_quorum_snapshots(snapshots)
    rollup = update_tenant_planetary_quorum()
    return {
        "ok": True,
        "votes_recorded": ingest.get("votes_recorded", 0),
        "votes_skipped": ingest.get("votes_skipped", 0),
        "rollup": rollup,
    }


def status_payload() -> Dict[str, Any]:
    rollup = update_tenant_planetary_quorum()
    regions = list_regions(limit=TENANT_PLANETARY_MAX_REGIONS)
    public = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    return {
        "ok": True,
        "format": TENANT_PLANETARY_FORMAT,
        "enabled": TENANT_PLANETARY_ENABLE,
        "node_id": _node_id(),
        "local_region": _region(),
        "rollup": rollup,
        "regions": regions.get("regions") or [],
        "last_rollup": dict(_LAST_ROLLUP),
        "apis": {
            "status": f"{public}/api/convergence/tenant/planetary/status",
            "snapshots": f"{public}/api/convergence/tenant/planetary/snapshots",
        },
    }