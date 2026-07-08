"""Wave K — planetary DTN quorum: multi-region rollup + cross-region heal via gossip."""

from __future__ import annotations

import hashlib
import os
import random
import time
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db

PLANETARY_FORMAT = "bloodstone_dtn_planetary/v1"
PLANETARY_ENABLE = os.environ.get("DTN_PLANETARY_ENABLE", "1").strip() not in (
    "0",
    "false",
    "no",
)
PLANETARY_MIN_REGIONS = max(1, int(os.environ.get("DTN_PLANETARY_MIN_REGIONS", "1")))
PLANETARY_REGION_RATIO = min(
    1.0,
    max(0.1, float(os.environ.get("DTN_PLANETARY_REGION_RATIO", "0.8"))),
)
PLANETARY_VOTE_TTL_SEC = max(300, int(os.environ.get("DTN_PLANETARY_VOTE_TTL_SEC", "7200")))
PLANETARY_MAX_REGIONS = max(5, int(os.environ.get("DTN_PLANETARY_MAX_REGIONS", "32")))
PLANETARY_HEAL_LIMIT = max(1, int(os.environ.get("DTN_PLANETARY_HEAL_LIMIT", "3")))
PLANETARY_EXCHANGE_PEERS = max(1, int(os.environ.get("DTN_PLANETARY_EXCHANGE_PEERS", "5")))
PLANETARY_TIMEOUT_SEC = max(5, int(os.environ.get("DTN_PLANETARY_TIMEOUT_SEC", "25")))

_LAST_ROLLUP: Dict[str, Any] = {}
_LAST_HEAL: Dict[str, Any] = {}


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def _node_id() -> str:
    return (os.environ.get("DTN_NODE_ID") or "pi-edge").strip()[:64]


def _region() -> str:
    return (os.environ.get("DTN_DEFAULT_REGION", "global") or "global").strip()[:32]


def init_planetary_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS dtn_planetary_regions (
                region TEXT PRIMARY KEY,
                source TEXT NOT NULL DEFAULT 'local',
                chunks_tracked INTEGER NOT NULL DEFAULT 0,
                chunks_satisfied INTEGER NOT NULL DEFAULT 0,
                chunks_under_quorum INTEGER NOT NULL DEFAULT 0,
                quorum_ratio REAL NOT NULL DEFAULT 0,
                peer_votes INTEGER NOT NULL DEFAULT 0,
                satisfied INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dtn_planetary_votes (
                vote_id TEXT PRIMARY KEY,
                reporter_node_id TEXT NOT NULL DEFAULT '',
                reporter_region TEXT NOT NULL DEFAULT '',
                target_region TEXT NOT NULL DEFAULT '',
                chunks_tracked INTEGER NOT NULL DEFAULT 0,
                chunks_satisfied INTEGER NOT NULL DEFAULT 0,
                chunks_under_quorum INTEGER NOT NULL DEFAULT 0,
                quorum_n INTEGER NOT NULL DEFAULT 2,
                quorum_m INTEGER NOT NULL DEFAULT 3,
                reported_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_planetary_votes_region
                ON dtn_planetary_votes(target_region, reported_at DESC);
            """
        )


def _discover_regions() -> List[str]:
    from chain_mesh import dtn_sync as dtn

    dtn.init_dtn_db()
    init_planetary_db()
    regions = {_region()}
    with _conn() as conn:
        for row in conn.execute(
            "SELECT DISTINCT region FROM dtn_peers WHERE region != '' LIMIT ?",
            (PLANETARY_MAX_REGIONS,),
        ).fetchall():
            regions.add(str(row["region"]).strip()[:32])
        for row in conn.execute(
            "SELECT DISTINCT region FROM dtn_region_quorum LIMIT ?",
            (PLANETARY_MAX_REGIONS,),
        ).fetchall():
            regions.add(str(row["region"]).strip()[:32])
        for row in conn.execute(
            """
            SELECT DISTINCT target_region FROM dtn_planetary_votes
            WHERE expires_at >= ?
            LIMIT ?
            """,
            (_now(), PLANETARY_MAX_REGIONS),
        ).fetchall():
            regions.add(str(row["target_region"]).strip()[:32])
    return sorted(r for r in regions if r)[:PLANETARY_MAX_REGIONS]


def _local_region_stats(region: str) -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    dtn.init_dtn_db()
    with _conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM dtn_region_quorum WHERE region = ?",
            (region,),
        ).fetchone()["c"]
        unsatisfied = conn.execute(
            "SELECT COUNT(*) AS c FROM dtn_region_quorum WHERE region = ? AND satisfied = 0",
            (region,),
        ).fetchone()["c"]
    tracked = int(total)
    under = int(unsatisfied)
    satisfied = max(0, tracked - under)
    ratio = (satisfied / tracked) if tracked else 1.0
    return {
        "chunks_tracked": tracked,
        "chunks_satisfied": satisfied,
        "chunks_under_quorum": under,
        "quorum_ratio": round(ratio, 4),
        "peer_votes": 0,
        "source": "local",
    }


def _remote_region_stats(region: str) -> Dict[str, Any]:
    init_planetary_db()
    cutoff = _now() - PLANETARY_VOTE_TTL_SEC
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT reporter_node_id, chunks_tracked, chunks_satisfied,
                   chunks_under_quorum, quorum_n, quorum_m, reported_at
            FROM dtn_planetary_votes
            WHERE target_region = ? AND expires_at >= ? AND reported_at >= ?
            ORDER BY reported_at DESC
            """,
            (region, _now(), cutoff),
        ).fetchall()
    if not rows:
        return {
            "chunks_tracked": 0,
            "chunks_satisfied": 0,
            "chunks_under_quorum": 0,
            "quorum_ratio": 0.0,
            "peer_votes": 0,
            "source": "unknown",
        }

    by_reporter: Dict[str, Any] = {}
    for row in rows:
        rid = str(row["reporter_node_id"] or "")
        if rid and rid not in by_reporter:
            by_reporter[rid] = row

    votes = list(by_reporter.values())
    tracked = max(int(r["chunks_tracked"]) for r in votes)
    under = min(int(r["chunks_under_quorum"]) for r in votes)
    satisfied = max(0, tracked - under)
    ratio = (satisfied / tracked) if tracked else 0.0
    return {
        "chunks_tracked": tracked,
        "chunks_satisfied": satisfied,
        "chunks_under_quorum": under,
        "quorum_ratio": round(ratio, 4),
        "peer_votes": len(votes),
        "source": "gossip",
    }


def _region_satisfied(stats: Dict[str, Any]) -> bool:
    tracked = int(stats.get("chunks_tracked") or 0)
    under = int(stats.get("chunks_under_quorum") or 0)
    ratio = float(stats.get("quorum_ratio") or 0)
    if tracked == 0:
        return int(stats.get("peer_votes") or 0) > 0
    if under == 0:
        return True
    return ratio >= PLANETARY_REGION_RATIO


def build_quorum_snapshot() -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    if not PLANETARY_ENABLE:
        return {}
    dtn.init_dtn_db()
    init_planetary_db()
    reg = _region()
    dtn.update_region_quorum(region=reg)
    stats = _local_region_stats(reg)
    return {
        "format": PLANETARY_FORMAT,
        "node_id": _node_id(),
        "region": reg,
        "chunks_tracked": stats["chunks_tracked"],
        "chunks_satisfied": stats["chunks_satisfied"],
        "chunks_under_quorum": stats["chunks_under_quorum"],
        "quorum_n": dtn.DTN_QUORUM_N,
        "quorum_m": dtn.DTN_QUORUM_M,
        "reported_at": _now(),
    }


def ingest_quorum_snapshots(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not PLANETARY_ENABLE:
        return {"ok": True, "skipped": True, "votes_recorded": 0}
    init_planetary_db()
    now = _now()
    expires = now + PLANETARY_VOTE_TTL_SEC
    recorded = 0
    skipped = 0

    for snap in snapshots or []:
        if not isinstance(snap, dict):
            skipped += 1
            continue
        fmt = str(snap.get("format") or PLANETARY_FORMAT)
        if fmt != PLANETARY_FORMAT:
            skipped += 1
            continue
        reporter = str(snap.get("node_id") or "").strip()[:64]
        target = str(snap.get("region") or "").strip()[:32]
        if not reporter or not target:
            skipped += 1
            continue
        reported_at = int(snap.get("reported_at") or now)
        if reported_at < now - PLANETARY_VOTE_TTL_SEC:
            skipped += 1
            continue
        vote_id = hashlib.sha256(f"{reporter}|{target}|{reported_at}".encode()).hexdigest()[:24]
        with _conn() as conn:
            conn.execute(
                """
                INSERT INTO dtn_planetary_votes (
                    vote_id, reporter_node_id, reporter_region, target_region,
                    chunks_tracked, chunks_satisfied, chunks_under_quorum,
                    quorum_n, quorum_m, reported_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(vote_id) DO UPDATE SET
                    chunks_tracked = excluded.chunks_tracked,
                    chunks_satisfied = excluded.chunks_satisfied,
                    chunks_under_quorum = excluded.chunks_under_quorum,
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
                    int(snap.get("chunks_tracked") or 0),
                    int(snap.get("chunks_satisfied") or 0),
                    int(snap.get("chunks_under_quorum") or 0),
                    int(snap.get("quorum_n") or 2),
                    int(snap.get("quorum_m") or 3),
                    reported_at,
                    expires,
                ),
            )
        recorded += 1

    return {"ok": True, "votes_recorded": recorded, "votes_skipped": skipped}


def update_planetary_quorum() -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    if not PLANETARY_ENABLE:
        return {"ok": True, "skipped": True, "reason": "DTN_PLANETARY_ENABLE off"}

    dtn.init_dtn_db()
    init_planetary_db()
    local = _region()
    dtn.update_region_quorum(region=local)

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
                INSERT INTO dtn_planetary_regions (
                    region, source, chunks_tracked, chunks_satisfied,
                    chunks_under_quorum, quorum_ratio, peer_votes,
                    satisfied, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(region) DO UPDATE SET
                    source = excluded.source,
                    chunks_tracked = excluded.chunks_tracked,
                    chunks_satisfied = excluded.chunks_satisfied,
                    chunks_under_quorum = excluded.chunks_under_quorum,
                    quorum_ratio = excluded.quorum_ratio,
                    peer_votes = excluded.peer_votes,
                    satisfied = excluded.satisfied,
                    updated_at = excluded.updated_at
                """,
                (
                    reg,
                    stats["source"],
                    stats["chunks_tracked"],
                    stats["chunks_satisfied"],
                    stats["chunks_under_quorum"],
                    stats["quorum_ratio"],
                    stats["peer_votes"],
                    1 if ok else 0,
                    now,
                ),
            )
        region_rows.append({"region": reg, "satisfied": ok, **stats})

    under = len(regions) - satisfied_count
    planetary_ok = (
        len(regions) >= PLANETARY_MIN_REGIONS
        and under == 0
        and satisfied_count >= PLANETARY_MIN_REGIONS
    )
    result = {
        "ok": True,
        "format": PLANETARY_FORMAT,
        "node_id": _node_id(),
        "local_region": local,
        "regions_total": len(regions),
        "regions_satisfied": satisfied_count,
        "regions_under_quorum": under,
        "planetary_satisfied": planetary_ok,
        "min_regions": PLANETARY_MIN_REGIONS,
        "region_ratio_threshold": PLANETARY_REGION_RATIO,
        "regions": region_rows[:20],
    }
    _LAST_ROLLUP.clear()
    _LAST_ROLLUP.update(result)
    return result


def list_regions(*, limit: int = 50) -> Dict[str, Any]:
    init_planetary_db()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT region, source, chunks_tracked, chunks_satisfied,
                   chunks_under_quorum, quorum_ratio, peer_votes,
                   satisfied, updated_at
            FROM dtn_planetary_regions
            ORDER BY satisfied ASC, quorum_ratio ASC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
    return {
        "ok": True,
        "format": PLANETARY_FORMAT,
        "regions": [dict(r) for r in rows],
        "count": len(rows),
    }


def planetary_status() -> Dict[str, Any]:
    rollup = update_planetary_quorum()
    regions = list_regions(limit=PLANETARY_MAX_REGIONS)
    public = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    return {
        "ok": True,
        "format": PLANETARY_FORMAT,
        "enabled": PLANETARY_ENABLE,
        "node_id": _node_id(),
        "local_region": _region(),
        "rollup": rollup,
        "regions": regions.get("regions") or [],
        "last_heal": dict(_LAST_HEAL),
        "apis": {
            "status": f"{public}/api/convergence/dtn/planetary/status",
            "regions": f"{public}/api/convergence/dtn/planetary/regions",
            "heal": f"{public}/api/convergence/dtn/planetary/heal",
            "exchange": f"{public}/api/convergence/dtn/planetary/exchange",
        },
    }


def planetary_heal(*, limit: int = 0, regions: Optional[List[str]] = None) -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    if not PLANETARY_ENABLE:
        return {"ok": True, "skipped": True, "reason": "DTN_PLANETARY_ENABLE off"}

    per_region = max(1, int(limit or PLANETARY_HEAL_LIMIT))
    rollup = update_planetary_quorum()
    exchange = planetary_exchange_round()

    targets: List[str] = []
    if regions:
        targets = [str(r).strip()[:32] for r in regions if str(r).strip()]
    else:
        for row in rollup.get("regions") or []:
            if not row.get("satisfied"):
                targets.append(str(row.get("region") or ""))
        if not targets:
            targets = [_region()]

    heals: List[Dict[str, Any]] = []
    for reg in targets[:per_region]:
        if not reg:
            continue
        try:
            heal = dtn.replication_heal(region=reg, limit=per_region)
            heals.append({"region": reg, **heal})
        except Exception as exc:
            heals.append({"region": reg, "ok": False, "error": str(exc)})

    queued = sum(1 for h in heals if int(h.get("heal_queued") or 0) > 0)
    result = {
        "ok": True,
        "format": PLANETARY_FORMAT,
        "regions_healed": len(heals),
        "heal_bundles_queued": queued,
        "exchange": exchange,
        "heals": heals,
    }
    _LAST_HEAL.clear()
    _LAST_HEAL.update(result)
    return result


def planetary_exchange_round(*, limit: int = 0) -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn
    from chain_mesh import dtn_tls as tls

    if not PLANETARY_ENABLE:
        return {"ok": True, "skipped": True, "reason": "DTN_PLANETARY_ENABLE off"}

    dtn.init_dtn_db()
    init_planetary_db()
    n = max(1, int(limit or PLANETARY_EXCHANGE_PEERS))
    snapshot = build_quorum_snapshot()
    outbound = {
        "ok": True,
        "format": PLANETARY_FORMAT,
        "node_id": _node_id(),
        "region": _region(),
        "snapshot": snapshot,
        "quorum_snapshots": [snapshot] if snapshot else [],
    }

    peers = (dtn.list_dtn_peers(limit=50).get("peers") or [])
    self_node = _node_id()
    candidates = [
        str(p.get("base_url") or "").rstrip("/")
        for p in peers
        if str(p.get("base_url") or "").strip()
        and str(p.get("node_id") or "") != self_node
    ]
    if not candidates:
        return {"ok": True, "skipped": True, "reason": "no planetary peers", "exchanged": 0}

    random.shuffle(candidates)
    targets = candidates[:n]
    exchanged = 0
    votes_recorded = 0
    errors: List[Dict[str, Any]] = []

    for base in targets:
        url = f"{base.rstrip('/')}/api/convergence/dtn/planetary/exchange"
        try:
            resp = tls.post_json(url, outbound, timeout=PLANETARY_TIMEOUT_SEC)
            if resp.status_code >= 400:
                errors.append({"peer": base, "error": f"HTTP {resp.status_code}"})
                continue
            body = resp.json()
            ingest = ingest_exchange_payload(body)
            exchanged += 1
            votes_recorded += int(ingest.get("votes_recorded") or 0)
        except Exception as exc:
            errors.append({"peer": base, "error": str(exc)})

    return {
        "ok": True,
        "exchanged": exchanged,
        "targets": len(targets),
        "votes_recorded": votes_recorded,
        "errors": errors[:5],
    }


def ingest_exchange_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    fmt = str(payload.get("format") or "")
    if fmt and fmt != PLANETARY_FORMAT:
        raise ValueError(f"unsupported planetary format (expected {PLANETARY_FORMAT})")

    snapshots: List[Dict[str, Any]] = []
    snap = payload.get("snapshot")
    if isinstance(snap, dict):
        snapshots.append(snap)
    for row in payload.get("quorum_snapshots") or []:
        if isinstance(row, dict):
            snapshots.append(row)

    ingest = ingest_quorum_snapshots(snapshots)
    reply_snapshot = build_quorum_snapshot()
    return {
        "ok": True,
        "format": PLANETARY_FORMAT,
        "from_node": str(payload.get("node_id") or ""),
        "votes_recorded": ingest.get("votes_recorded", 0),
        "votes_skipped": ingest.get("votes_skipped", 0),
        "reply": {
            "ok": True,
            "format": PLANETARY_FORMAT,
            "node_id": _node_id(),
            "region": _region(),
            "snapshot": reply_snapshot,
            "quorum_snapshots": [reply_snapshot] if reply_snapshot else [],
        },
    }


def status_payload() -> Dict[str, Any]:
    return planetary_status()