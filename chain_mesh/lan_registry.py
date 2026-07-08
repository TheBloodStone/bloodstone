"""LAN local-node registry — phones advertise RPC/stratum endpoints for same-network peers."""

import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db

_LAN_TTL_SEC = int(os.environ.get("CHAIN_MESH_LAN_TTL_SEC", "300"))


def _now() -> int:
    return int(time.time())


def init_lan_db() -> None:
    mesh_db.init_db()
    with mesh_db._conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chain_lan_nodes (
                device_id TEXT PRIMARY KEY,
                public_ip TEXT NOT NULL DEFAULT '',
                lan_ip TEXT NOT NULL DEFAULT '',
                rpc_port INTEGER NOT NULL DEFAULT 18340,
                stratum_port INTEGER NOT NULL DEFAULT 3437,
                stratum_port_yespower INTEGER NOT NULL DEFAULT 3438,
                chunk_port INTEGER NOT NULL DEFAULT 18341,
                rpc_user TEXT NOT NULL DEFAULT '',
                peer_kind TEXT NOT NULL DEFAULT 'android',
                model TEXT NOT NULL DEFAULT '',
                mode TEXT NOT NULL DEFAULT 'gateway',
                block_height INTEGER NOT NULL DEFAULT 0,
                pruned INTEGER NOT NULL DEFAULT 1,
                last_seen INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chain_lan_public_ip
                ON chain_lan_nodes(public_ip, last_seen DESC);
            """
        )
        cols = {row[1] for row in conn.execute("PRAGMA table_info(chain_lan_nodes)").fetchall()}
        if "stratum_port_yespower" not in cols:
            conn.execute(
                "ALTER TABLE chain_lan_nodes ADD COLUMN stratum_port_yespower INTEGER NOT NULL DEFAULT 3438"
            )
        if "chunk_port" not in cols:
            conn.execute(
                "ALTER TABLE chain_lan_nodes ADD COLUMN chunk_port INTEGER NOT NULL DEFAULT 18341"
            )
        if "sync_progress" not in cols:
            conn.execute(
                "ALTER TABLE chain_lan_nodes ADD COLUMN sync_progress REAL NOT NULL DEFAULT 0"
            )
        if "chain_bytes" not in cols:
            conn.execute(
                "ALTER TABLE chain_lan_nodes ADD COLUMN chain_bytes INTEGER NOT NULL DEFAULT 0"
            )
        if "consensus_only" not in cols:
            conn.execute(
                "ALTER TABLE chain_lan_nodes ADD COLUMN consensus_only INTEGER NOT NULL DEFAULT 0"
            )
        cols = {row[1] for row in conn.execute("PRAGMA table_info(chain_lan_nodes)").fetchall()}
        if "tip_hash" not in cols:
            conn.execute("ALTER TABLE chain_lan_nodes ADD COLUMN tip_hash TEXT NOT NULL DEFAULT ''")
        if "best_block_hash" not in cols:
            conn.execute(
                "ALTER TABLE chain_lan_nodes ADD COLUMN best_block_hash TEXT NOT NULL DEFAULT ''"
            )
        cols = {row[1] for row in conn.execute("PRAGMA table_info(chain_lan_nodes)").fetchall()}
        if "ai_runtimes" not in cols:
            conn.execute(
                "ALTER TABLE chain_lan_nodes ADD COLUMN ai_runtimes TEXT NOT NULL DEFAULT '[]'"
            )
        if "ai_inference_port" not in cols:
            conn.execute(
                "ALTER TABLE chain_lan_nodes ADD COLUMN ai_inference_port INTEGER NOT NULL DEFAULT 0"
            )


def _normalize_ai_runtimes(value: Any) -> str:
    if not value:
        return "[]"
    if isinstance(value, list):
        runtimes = [str(r).strip().lower() for r in value if str(r).strip()]
        return json.dumps(runtimes)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return "[]"
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    runtimes = [str(r).strip().lower() for r in parsed if str(r).strip()]
                    return json.dumps(runtimes)
            except Exception:
                pass
        runtimes = [r.strip().lower() for r in raw.split(",") if r.strip()]
        return json.dumps(runtimes)
    return "[]"


def register_lan_node(
    *,
    device_id: str,
    public_ip: str,
    lan_ip: str,
    rpc_port: int = 18340,
    stratum_port: int = 3437,
    stratum_port_yespower: int = 3438,
    chunk_port: int = 18341,
    rpc_user: str = "",
    peer_kind: str = "android",
    model: str = "",
    mode: str = "gateway",
    block_height: int = 0,
    pruned: bool = True,
    sync_progress: float = 0.0,
    chain_bytes: int = 0,
    consensus_only: bool = False,
    tip_hash: str = "",
    best_block_hash: str = "",
    ai_runtimes: Any = None,
    ai_inference_port: int = 0,
) -> Dict[str, Any]:
    init_lan_db()
    did = (device_id or "").strip().lower()
    if not did or not (lan_ip or "").strip():
        raise ValueError("device_id and lan_ip required")
    now = _now()
    with mesh_db._conn() as conn:
        conn.execute(
            """
            INSERT INTO chain_lan_nodes (
                device_id, public_ip, lan_ip, rpc_port, stratum_port,
                stratum_port_yespower, chunk_port,
                rpc_user, peer_kind, model, mode, block_height, pruned,
                sync_progress, chain_bytes, consensus_only, tip_hash,
                best_block_hash, ai_runtimes, ai_inference_port, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                public_ip = excluded.public_ip,
                lan_ip = excluded.lan_ip,
                rpc_port = excluded.rpc_port,
                stratum_port = excluded.stratum_port,
                stratum_port_yespower = excluded.stratum_port_yespower,
                chunk_port = excluded.chunk_port,
                rpc_user = excluded.rpc_user,
                peer_kind = excluded.peer_kind,
                model = excluded.model,
                mode = excluded.mode,
                block_height = excluded.block_height,
                pruned = excluded.pruned,
                sync_progress = excluded.sync_progress,
                chain_bytes = excluded.chain_bytes,
                consensus_only = excluded.consensus_only,
                tip_hash = excluded.tip_hash,
                best_block_hash = excluded.best_block_hash,
                ai_runtimes = excluded.ai_runtimes,
                ai_inference_port = excluded.ai_inference_port,
                last_seen = excluded.last_seen
            """,
            (
                did,
                (public_ip or "").strip()[:64],
                (lan_ip or "").strip()[:64],
                max(1, int(rpc_port)),
                max(0, int(stratum_port)),
                max(0, int(stratum_port_yespower)),
                max(0, int(chunk_port)),
                (rpc_user or "").strip()[:64],
                (peer_kind or "android").strip()[:24],
                (model or "")[:120],
                (mode or "gateway").strip()[:24],
                max(0, int(block_height)),
                1 if pruned else 0,
                max(0.0, min(1.0, float(sync_progress))),
                max(0, int(chain_bytes)),
                1 if consensus_only else 0,
                (tip_hash or best_block_hash or "").strip().lower()[:64],
                (best_block_hash or tip_hash or "").strip().lower()[:64],
                _normalize_ai_runtimes(ai_runtimes),
                max(0, int(ai_inference_port)),
                now,
            ),
        )
    try:
        purge_inactive_lan_nodes(older_than_sec=7 * 86400)
    except Exception:
        pass
    return {"device_id": did, "lan_ip": lan_ip, "last_seen": now}


def list_lan_ai_nodes(*, ttl_sec: int = _LAN_TTL_SEC) -> List[Dict[str, Any]]:
    """Return LAN nodes advertising on-device AI runtimes."""
    init_lan_db()
    cutoff = _now() - ttl_sec
    with mesh_db._conn() as conn:
        rows = conn.execute(
            """
            SELECT device_id, lan_ip, peer_kind, model, ai_runtimes,
                   ai_inference_port, last_seen
            FROM chain_lan_nodes
            WHERE last_seen >= ?
              AND ai_runtimes IS NOT NULL
              AND ai_runtimes != ''
              AND ai_runtimes != '[]'
            ORDER BY last_seen DESC
            """,
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


def active_lan_node_count(*, ttl_sec: int = _LAN_TTL_SEC) -> int:
    """Count LAN-registered local nodes seen recently (all public IPs)."""
    init_lan_db()
    cutoff = _now() - ttl_sec
    with mesh_db._conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM chain_lan_nodes WHERE last_seen >= ?",
            (cutoff,),
        ).fetchone()
    return int(row["n"] or 0) if row else 0


def nearby_lan_nodes(public_ip: str, *, ttl_sec: int = _LAN_TTL_SEC) -> List[Dict[str, Any]]:
    init_lan_db()
    cutoff = _now() - ttl_sec
    ip = (public_ip or "").strip()
    with mesh_db._conn() as conn:
        rows = conn.execute(
            """
            SELECT device_id, lan_ip, rpc_port, stratum_port, stratum_port_yespower,
                   chunk_port, rpc_user, peer_kind, model, mode, block_height, pruned,
                   sync_progress, chain_bytes, consensus_only, last_seen
            FROM chain_lan_nodes
            WHERE public_ip = ? AND last_seen >= ?
            ORDER BY last_seen DESC
            """,
            (ip, cutoff),
        ).fetchall()
    nodes = [dict(r) for r in rows]

    def _priority(node: Dict[str, Any]) -> tuple:
        mode = str(node.get("mode") or "").lower()
        pruned = bool(node.get("pruned", True))
        sync = float(node.get("sync_progress") or 0)
        if mode == "full" and not pruned:
            rank = 0
        elif mode == "mesh":
            rank = 1
        elif mode == "consensus":
            rank = 2
        elif mode == "pruned":
            rank = 3
        elif mode in ("consensus-witness", "consensus_witness"):
            rank = 4
        else:
            rank = 5
        synced = 1 if sync >= 0.999 else 0
        return (
            rank,
            -synced,
            -sync,
            -int(node.get("block_height") or 0),
            -int(node.get("last_seen") or 0),
        )

    nodes.sort(key=_priority)
    return nodes


def _network_tip_height() -> int:
    try:
        import bloodstone_broadcast as bb

        status = bb.sync_status()
        return max(0, int(status.get("local_height") or 0))
    except Exception:
        return 0


def _lag_status(
    *,
    behind: int,
    block_height: int,
    sync_progress: float,
    chain_bytes: int,
    age_sec: int,
    active_sec: int,
) -> str:
    if age_sec > active_sec:
        return "stale"
    if block_height <= 0:
        # Active heartbeat but no live RPC height — bootstrapping or daemon restart.
        if sync_progress > 0 or chain_bytes > 512 * 1024:
            return "syncing"
        return "syncing"
    if behind <= 3:
        return "caught_up"
    if behind <= 50:
        return "syncing"
    if sync_progress >= 0.999 and behind > 3:
        return "headers_ahead"
    return "behind"


def purge_inactive_lan_nodes(*, older_than_sec: int = 7 * 86400) -> int:
    """Drop LAN registry rows not seen recently (keeps IP lag lists readable)."""
    init_lan_db()
    cutoff = _now() - max(3600, int(older_than_sec))
    with mesh_db._conn() as conn:
        cur = conn.execute(
            "DELETE FROM chain_lan_nodes WHERE last_seen < ?",
            (cutoff,),
        )
        return int(cur.rowcount or 0)


def all_lan_nodes_lag(
    *,
    lookback_sec: int = 86400,
    active_sec: Optional[int] = None,
    include_inactive: bool = True,
) -> Dict[str, Any]:
    """All LAN-registered nodes with blocks-behind vs VPS tip (admin/dashboard)."""
    init_lan_db()
    ttl = int(active_sec if active_sec is not None else _LAN_TTL_SEC)
    now = _now()
    cutoff = now - max(60, int(lookback_sec))
    tip = _network_tip_height()
    with mesh_db._conn() as conn:
        rows = conn.execute(
            """
            SELECT device_id, public_ip, lan_ip, rpc_port, stratum_port,
                   stratum_port_yespower, chunk_port, peer_kind, model, mode,
                   block_height, pruned, sync_progress, chain_bytes,
                   consensus_only, last_seen
            FROM chain_lan_nodes
            WHERE last_seen >= ?
            ORDER BY last_seen DESC
            """,
            (cutoff,),
        ).fetchall()
    nodes: List[Dict[str, Any]] = []
    counts = {
        "active": 0,
        "caught_up": 0,
        "syncing": 0,
        "behind": 0,
        "stale": 0,
        "stuck": 0,
        "headers_ahead": 0,
    }
    max_behind = 0
    for row in rows:
        item = dict(row)
        height = int(item.get("block_height") or 0)
        sync_progress = float(item.get("sync_progress") or 0)
        last_seen = int(item.get("last_seen") or 0)
        age_sec = max(0, now - last_seen) if last_seen else lookback_sec
        behind = max(0, tip - height) if tip > 0 and height > 0 else (tip if height <= 0 else 0)
        status = _lag_status(
            behind=behind,
            block_height=height,
            sync_progress=sync_progress,
            chain_bytes=int(item.get("chain_bytes") or 0),
            age_sec=age_sec,
            active_sec=ttl,
        )
        if not include_inactive and status == "stale":
            continue
        counts[status] = counts.get(status, 0) + 1
        if age_sec <= ttl:
            counts["active"] += 1
        max_behind = max(max_behind, behind)
        nodes.append(
            {
                "device_id": item.get("device_id") or "",
                "public_ip": item.get("public_ip") or "",
                "lan_ip": item.get("lan_ip") or "",
                "mode": item.get("mode") or "",
                "model": item.get("model") or "",
                "peer_kind": item.get("peer_kind") or "",
                "block_height": height,
                "network_tip": tip,
                "blocks_behind": behind,
                "sync_progress": round(sync_progress, 4),
                "chain_bytes": int(item.get("chain_bytes") or 0),
                "pruned": bool(item.get("pruned")),
                "consensus_only": bool(item.get("consensus_only")),
                "rpc_port": int(item.get("rpc_port") or 0),
                "stratum_port": int(item.get("stratum_port") or 0),
                "stratum_port_yespower": int(item.get("stratum_port_yespower") or 0),
                "chunk_port": int(item.get("chunk_port") or 0),
                "last_seen": last_seen,
                "age_sec": age_sec,
                "active": age_sec <= ttl,
                "status": status,
            }
        )

    def sort_key(n: Dict[str, Any]) -> tuple:
        order = {
            "behind": 0,
            "headers_ahead": 1,
            "syncing": 2,
            "stuck": 3,
            "stale": 4,
            "caught_up": 5,
        }
        return (
            order.get(str(n.get("status")), 9),
            -int(n.get("blocks_behind") or 0),
            int(n.get("age_sec") or 0),
        )

    nodes.sort(key=sort_key)
    return {
        "ok": True,
        "network_tip": tip,
        "node_count": len(nodes),
        "active_count": counts["active"],
        "max_blocks_behind": max_behind,
        "counts": counts,
        "active_sec": ttl,
        "lookback_sec": lookback_sec,
        "include_inactive": include_inactive,
        "updated_at": now,
        "nodes": nodes,
    }