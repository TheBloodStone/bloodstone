"""QUASAR Phase 2 — mesh witness capsules (bloodstone/witness-capsule/v1)."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from chain_mesh import db as mesh_db

CAPSULE_TYPE = "bloodstone/witness-capsule/v1"
WITNESS_DIR = os.environ.get(
    "QUASAR_WITNESS_MESH_PREFIX", "assets/witness"
)
REQUIRED_QUORUM = int(os.environ.get("QUASAR_WITNESS_QUORUM", "3"))
QUORUM_WINDOW_SEC = int(os.environ.get("QUASAR_WITNESS_WINDOW_SEC", "7200"))
PUBLISH_MESH = os.environ.get("QUASAR_WITNESS_PUBLISH_MESH", "1") == "1"


def _now() -> int:
    return int(time.time())


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def init_witness_db() -> None:
    mesh_db.init_db()
    with mesh_db._conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS quasar_witness_capsules (
                capsule_id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                tip_hash TEXT NOT NULL,
                height INTEGER NOT NULL,
                node_mode TEXT NOT NULL DEFAULT 'full',
                peer_count INTEGER NOT NULL DEFAULT 0,
                issued_at TEXT NOT NULL,
                mesh_key TEXT NOT NULL DEFAULT '',
                asset_key TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_quasar_witness_tip
                ON quasar_witness_capsules(tip_hash, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_quasar_witness_device
                ON quasar_witness_capsules(device_id, created_at DESC);
            """
        )


def _canonical_capsule_body(capsule: Dict[str, Any]) -> Dict[str, Any]:
    body = dict(capsule)
    body.pop("capsule_id", None)
    body.pop("signature", None)
    return body


def capsule_id_for(capsule: Dict[str, Any]) -> str:
    raw = json.dumps(_canonical_capsule_body(capsule), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_capsule(capsule: Dict[str, Any]) -> Dict[str, Any]:
    if str(capsule.get("type") or "") != CAPSULE_TYPE:
        raise ValueError(f"type must be {CAPSULE_TYPE}")
    height = int(capsule.get("height") or 0)
    tip_hash = str(capsule.get("tip_hash") or "").strip().lower()
    device_id = str(capsule.get("device_id") or "").strip().lower()
    if height <= 0 or len(tip_hash) != 64 or not device_id:
        raise ValueError("height, tip_hash, and device_id required")
    algo_work = capsule.get("algo_work")
    if not isinstance(algo_work, dict):
        raise ValueError("algo_work object required")
    out = {
        "type": CAPSULE_TYPE,
        "height": height,
        "tip_hash": tip_hash,
        "algo_work": {str(k): str(v) for k, v in algo_work.items()},
        "peer_count": max(0, int(capsule.get("peer_count") or 0)),
        "node_mode": str(capsule.get("node_mode") or "full")[:24],
        "device_id": device_id,
        "mesh_key": str(capsule.get("mesh_key") or device_id)[:128],
        "issued_at": str(capsule.get("issued_at") or _utc_now()),
    }
    out["capsule_id"] = capsule_id_for(out)
    return out


def build_capsule_from_rpc(
    rpc: Callable,
    *,
    device_id: str,
    node_mode: str = "coordinator",
    peer_count: int = 0,
    mesh_key: str = "",
) -> Dict[str, Any]:
    info = rpc("getblockchaininfo")
    mining = rpc("getmininginfo")
    height = int(info.get("blocks") or 0)
    tip_hash = str(info.get("bestblockhash") or "").strip().lower()
    diff = mining.get("difficulty") or {}
    if isinstance(diff, dict):
        algo_work = {str(k): str(v) for k, v in diff.items()}
    else:
        algo_work = {"chain": str(diff)}
    return validate_capsule(
        {
            "type": CAPSULE_TYPE,
            "height": height,
            "tip_hash": tip_hash,
            "algo_work": algo_work,
            "peer_count": peer_count,
            "node_mode": node_mode,
            "device_id": device_id,
            "mesh_key": mesh_key or device_id,
            "issued_at": _utc_now(),
        }
    )


def _mesh_asset_key(device_id: str, height: int) -> str:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in device_id)[:48]
    return f"{WITNESS_DIR}/{month}/{safe}-{height}.json"


def _publish_capsule_asset(capsule: Dict[str, Any]) -> str:
    if not PUBLISH_MESH:
        return ""
    try:
        from chain_mesh import assets as mesh_assets
    except Exception:
        return ""
    asset_key = _mesh_asset_key(capsule["device_id"], capsule["height"])
    fd, path = tempfile.mkstemp(suffix=".json", prefix="witness-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(capsule, fh, indent=2, sort_keys=True)
            fh.write("\n")
        mesh_assets.publish_asset(
            path,
            asset_key=asset_key,
            display_name=f"witness-{capsule['device_id']}-{capsule['height']}",
            version=str(capsule["height"]),
            mime_type="application/json",
            anchor=False,
        )
        return asset_key
    except Exception:
        return ""
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def ingest_capsule(capsule: Dict[str, Any], *, publish: bool = True) -> Dict[str, Any]:
    init_witness_db()
    normalized = validate_capsule(capsule)
    asset_key = ""
    if publish:
        asset_key = _publish_capsule_asset(normalized)
    now = _now()
    with mesh_db._conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO quasar_witness_capsules (
                capsule_id, device_id, tip_hash, height, node_mode, peer_count,
                issued_at, mesh_key, asset_key, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["capsule_id"],
                normalized["device_id"],
                normalized["tip_hash"],
                normalized["height"],
                normalized["node_mode"],
                normalized["peer_count"],
                normalized["issued_at"],
                normalized["mesh_key"],
                asset_key,
                json.dumps(normalized, sort_keys=True),
                now,
            ),
        )
    return {"ok": True, "capsule": normalized, "asset_key": asset_key}


def list_capsules(
    *,
    tip_hash: str = "",
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    init_witness_db()
    limit = max(1, min(200, int(limit)))
    offset = max(0, int(offset))
    clauses = []
    params: List[Any] = []
    if tip_hash:
        clauses.append("tip_hash = ?")
        params.append(tip_hash.strip().lower())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with mesh_db._conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM quasar_witness_capsules {where}",
            params,
        ).fetchone()
        rows = conn.execute(
            f"""
            SELECT capsule_id, device_id, tip_hash, height, node_mode, peer_count,
                   issued_at, mesh_key, asset_key, created_at
            FROM quasar_witness_capsules {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
    return {
        "ok": True,
        "total": int(total["n"] if total else 0),
        "capsules": [dict(r) for r in rows],
        "limit": limit,
        "offset": offset,
    }


def quorum_for_tip(
    tip_hash: str,
    *,
    window_sec: int = QUORUM_WINDOW_SEC,
) -> Dict[str, Any]:
    init_witness_db()
    tip = (tip_hash or "").strip().lower()
    if len(tip) != 64:
        return {
            "ok": False,
            "quorum_depth": 0,
            "required_quorum": REQUIRED_QUORUM,
            "status": "unknown",
        }
    cutoff = _now() - max(300, int(window_sec))
    with mesh_db._conn() as conn:
        rows = conn.execute(
            """
            SELECT mesh_key, device_id, MAX(created_at) AS last_at
            FROM quasar_witness_capsules
            WHERE tip_hash = ? AND created_at >= ?
            GROUP BY mesh_key
            """,
            (tip, cutoff),
        ).fetchall()
        all_recent = conn.execute(
            """
            SELECT tip_hash, COUNT(DISTINCT mesh_key) AS signers
            FROM quasar_witness_capsules
            WHERE created_at >= ?
            GROUP BY tip_hash
            ORDER BY signers DESC
            LIMIT 5
            """,
            (cutoff,),
        ).fetchall()
    signers = [dict(r) for r in rows]
    depth = len(signers)
    dominant = [dict(r) for r in all_recent]
    split = False
    if len(dominant) >= 2:
        top = int(dominant[0].get("signers") or 0)
        second = int(dominant[1].get("signers") or 0)
        if second >= 2 and top <= second + 1:
            split = True
    if split:
        status = "split"
    elif depth >= REQUIRED_QUORUM:
        status = "live"
    elif depth > 0:
        status = "pending"
    else:
        status = "awaiting"
    return {
        "ok": True,
        "tip_hash": tip,
        "quorum_depth": depth,
        "required_quorum": REQUIRED_QUORUM,
        "signers": signers,
        "dominant_tips": dominant,
        "status": status,
        "window_sec": window_sec,
    }


def witness_status_payload(
    tip_hash: str,
    tip_height: int,
) -> Dict[str, Any]:
    quorum = quorum_for_tip(tip_hash)
    capsules = list_capsules(tip_hash=tip_hash, limit=10)
    anchors = 0
    try:
        from chain_mesh.anchor_index import ensure_fresh, list_anchors

        ensure_fresh()
        anchors = int(list_anchors(limit=1).get("total") or 0)
    except Exception:
        anchors = 0
    return {
        "phase": 2,
        "status": quorum.get("status", "awaiting"),
        "quorum_depth": int(quorum.get("quorum_depth") or 0),
        "required_quorum": REQUIRED_QUORUM,
        "tip_hash": tip_hash,
        "tip_height": tip_height,
        "recent_capsules": capsules.get("capsules") or [],
        "dominant_tips": quorum.get("dominant_tips") or [],
        "mesh_anchors_indexed": anchors,
        "capsule_schema": CAPSULE_TYPE,
        "submit_url": "/api/quasar/witness/submit",
    }