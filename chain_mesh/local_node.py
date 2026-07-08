"""Local VPS node registry — job cache and offline share queue from mobile/web miners."""

import json
import os
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

from chain_mesh.config import MESH_ROOT
from chain_mesh import db as mesh_db

_LOCAL_ROOT = os.path.join(MESH_ROOT, "local-nodes")
_JOB_CACHE_DIR = os.path.join(_LOCAL_ROOT, "job-cache")
_PENDING_SHARES_DIR = os.path.join(_LOCAL_ROOT, "pending-shares")
_MAX_PENDING_PER_DEVICE = int(os.environ.get("CHAIN_MESH_MAX_PENDING_SHARES", "200"))
_JOB_CACHE_TTL_SEC = int(os.environ.get("CHAIN_MESH_JOB_CACHE_TTL", str(6 * 3600)))


def _now() -> int:
    return int(time.time())


def ensure_dirs() -> None:
    mesh_db.ensure_dirs()
    os.makedirs(_JOB_CACHE_DIR, exist_ok=True)
    os.makedirs(_PENDING_SHARES_DIR, exist_ok=True)


def _device_path(base: str, device_id: str) -> str:
    did = (device_id or "").strip().lower()
    if not did:
        raise ValueError("device_id required")
    safe = "".join(c for c in did if c.isalnum() or c in "-_")[:64]
    return os.path.join(base, f"{safe}.json")


def _atomic_write_json(path: str, record: Dict[str, Any]) -> None:
    """Write JSON atomically; unique tmp avoids multi-worker replace races."""
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    tmp = os.path.join(parent, f".{os.path.basename(path)}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(record, fh, separators=(",", ":"))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def init_local_node_db() -> None:
    mesh_db.init_db()
    ensure_dirs()
    with mesh_db._conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chain_local_nodes (
                device_id TEXT PRIMARY KEY,
                peer_kind TEXT NOT NULL DEFAULT 'browser',
                model TEXT NOT NULL DEFAULT '',
                block_height INTEGER NOT NULL DEFAULT 0,
                best_block_hash TEXT NOT NULL DEFAULT '',
                chunks_held INTEGER NOT NULL DEFAULT 0,
                offline_capable INTEGER NOT NULL DEFAULT 0,
                job_cached INTEGER NOT NULL DEFAULT 0,
                pending_shares INTEGER NOT NULL DEFAULT 0,
                first_seen INTEGER NOT NULL,
                last_seen INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chain_local_nodes_seen
                ON chain_local_nodes(last_seen);
            """
        )


def upsert_local_node(
    *,
    device_id: str,
    peer_kind: str = "browser",
    model: str = "",
    block_height: int = 0,
    best_block_hash: str = "",
    chunks_held: int = 0,
    offline_capable: bool = False,
    job_cached: bool = False,
    pending_shares: int = 0,
) -> Dict[str, Any]:
    init_local_node_db()
    did = (device_id or "").strip().lower()
    if not did:
        raise ValueError("device_id required")
    now = _now()
    with mesh_db._conn() as conn:
        row = conn.execute(
            "SELECT first_seen FROM chain_local_nodes WHERE device_id = ?",
            (did,),
        ).fetchone()
        first_seen = int(row["first_seen"]) if row else now
        conn.execute(
            """
            INSERT INTO chain_local_nodes (
                device_id, peer_kind, model, block_height, best_block_hash,
                chunks_held, offline_capable, job_cached, pending_shares,
                first_seen, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                peer_kind = excluded.peer_kind,
                model = excluded.model,
                block_height = excluded.block_height,
                best_block_hash = excluded.best_block_hash,
                chunks_held = excluded.chunks_held,
                offline_capable = excluded.offline_capable,
                job_cached = excluded.job_cached,
                pending_shares = excluded.pending_shares,
                last_seen = excluded.last_seen
            """,
            (
                did,
                (peer_kind or "browser").strip().lower()[:24],
                (model or "")[:120],
                max(0, int(block_height)),
                (best_block_hash or "")[:64],
                max(0, int(chunks_held)),
                1 if offline_capable else 0,
                1 if job_cached else 0,
                max(0, int(pending_shares)),
                first_seen,
                now,
            ),
        )
    return {"device_id": did, "last_seen": now, "role": "local-vps-node"}


def store_job_cache(device_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    init_local_node_db()
    did = (device_id or "").strip().lower()
    if not did:
        raise ValueError("device_id required")
    ensure_dirs()
    path = _device_path(_JOB_CACHE_DIR, did)
    record = {
        "device_id": did,
        "saved_at": _now(),
        **payload,
    }
    _atomic_write_json(path, record)
    upsert_local_node(
        device_id=did,
        peer_kind=str(payload.get("peer_kind") or "browser"),
        model=str(payload.get("model") or ""),
        block_height=int(payload.get("block_height") or 0),
        best_block_hash=str(payload.get("best_block_hash") or ""),
        chunks_held=int(payload.get("chunks_held") or 0),
        offline_capable=True,
        job_cached=True,
    )
    return {"ok": True, "device_id": did, "saved_at": record["saved_at"]}


def get_job_cache(device_id: str) -> Optional[Dict[str, Any]]:
    init_local_node_db()
    did = (device_id or "").strip().lower()
    if not did:
        return None
    path = _device_path(_JOB_CACHE_DIR, did)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    saved_at = int(data.get("saved_at") or 0)
    if saved_at and _now() - saved_at > _JOB_CACHE_TTL_SEC:
        return None
    return data


def queue_pending_shares(device_id: str, shares: List[Dict[str, Any]]) -> Dict[str, Any]:
    init_local_node_db()
    did = (device_id or "").strip().lower()
    if not did:
        raise ValueError("device_id required")
    if not shares:
        return {"queued": 0, "total": 0}
    ensure_dirs()
    path = _device_path(_PENDING_SHARES_DIR, did)
    existing: List[Dict[str, Any]] = []
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                existing = json.load(fh).get("shares") or []
        except (OSError, json.JSONDecodeError):
            existing = []
    merged = existing + [s for s in shares if isinstance(s, dict)]
    merged = merged[-_MAX_PENDING_PER_DEVICE:]
    record = {"device_id": did, "updated_at": _now(), "shares": merged}
    _atomic_write_json(path, record)
    upsert_local_node(device_id=did, offline_capable=True, pending_shares=len(merged))
    return {"queued": len(shares), "total": len(merged)}


def drain_pending_shares(device_id: str) -> List[Dict[str, Any]]:
    init_local_node_db()
    did = (device_id or "").strip().lower()
    if not did:
        return []
    path = _device_path(_PENDING_SHARES_DIR, did)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    shares = data.get("shares") or []
    try:
        os.remove(path)
    except OSError:
        pass
    upsert_local_node(device_id=did, pending_shares=0)
    return shares


def local_node_stats(*, active_sec: int = 3600) -> Dict[str, Any]:
    init_local_node_db()
    cutoff = _now() - active_sec
    with mesh_db._conn() as conn:
        rows = conn.execute(
            """
            SELECT device_id, peer_kind, block_height, chunks_held,
                   offline_capable, job_cached, pending_shares
            FROM chain_local_nodes
            WHERE last_seen >= ?
            """,
            (cutoff,),
        ).fetchall()
    active = len(rows)
    offline_ready = sum(
        1 for r in rows if int(r["offline_capable"]) and int(r["job_cached"])
    )
    chunk_nodes = sum(1 for r in rows if int(r["chunks_held"]) > 0)
    pending_total = sum(int(r["pending_shares"] or 0) for r in rows)
    max_height = max((int(r["block_height"] or 0) for r in rows), default=0)
    return {
        "active_local_nodes": active,
        "offline_ready_nodes": offline_ready,
        "chunk_storage_nodes": chunk_nodes,
        "pending_shares_queued": pending_total,
        "max_peer_block_height": max_height,
        "window_sec": active_sec,
    }