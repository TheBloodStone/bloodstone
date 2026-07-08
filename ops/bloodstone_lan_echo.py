"""QUASAR Phase 2 — LAN Echo Quorum (LEQ) across household fleet nodes."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db
from chain_mesh import lan_registry as lan

import os

ECHO_TYPE = "bloodstone/lan-echo/v1"
ECHO_TTL_SEC = int(os.environ.get("QUASAR_LAN_ECHO_TTL_SEC", "300"))
ECHO_DELTA_BLOCKS = int(os.environ.get("QUASAR_LAN_ECHO_DELTA_BLOCKS", "3"))


def _now() -> int:
    return int(time.time())


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def init_lan_echo_db() -> None:
    lan.init_lan_db()
    with mesh_db._conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS quasar_lan_echoes (
                echo_id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                public_ip TEXT NOT NULL DEFAULT '',
                tip_hash TEXT NOT NULL,
                block_height INTEGER NOT NULL,
                pool_tip_hash TEXT NOT NULL DEFAULT '',
                pool_tip_height INTEGER NOT NULL DEFAULT 0,
                agrees INTEGER NOT NULL DEFAULT 1,
                payload_json TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_quasar_lan_echo_ip_time
                ON quasar_lan_echoes(public_ip, created_at DESC);
            """
        )
        cols = {row[1] for row in conn.execute("PRAGMA table_info(chain_lan_nodes)").fetchall()}
        if "tip_hash" not in cols:
            conn.execute("ALTER TABLE chain_lan_nodes ADD COLUMN tip_hash TEXT NOT NULL DEFAULT ''")
        if "best_block_hash" not in cols:
            conn.execute(
                "ALTER TABLE chain_lan_nodes ADD COLUMN best_block_hash TEXT NOT NULL DEFAULT ''"
            )


def _echo_id(device_id: str, tip_hash: str, issued_at: str) -> str:
    raw = f"{device_id}|{tip_hash}|{issued_at}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_echo_packet(packet: Dict[str, Any]) -> Dict[str, Any]:
    if str(packet.get("type") or "") != ECHO_TYPE:
        raise ValueError(f"type must be {ECHO_TYPE}")
    device_id = str(packet.get("device_id") or "").strip().lower()
    tip_hash = str(packet.get("tip_hash") or "").strip().lower()
    height = int(packet.get("block_height") or packet.get("height") or 0)
    if not device_id or len(tip_hash) != 64 or height <= 0:
        raise ValueError("device_id, tip_hash, block_height required")
    issued_at = str(packet.get("issued_at") or _utc_now())
    return {
        "type": ECHO_TYPE,
        "device_id": device_id,
        "tip_hash": tip_hash,
        "block_height": height,
        "lan_ip": str(packet.get("lan_ip") or "")[:64],
        "node_mode": str(packet.get("node_mode") or "gateway")[:24],
        "issued_at": issued_at,
        "echo_id": _echo_id(device_id, tip_hash, issued_at),
    }


def record_echo(
    packet: Dict[str, Any],
    *,
    public_ip: str,
    pool_tip_hash: str = "",
    pool_tip_height: int = 0,
) -> Dict[str, Any]:
    init_lan_echo_db()
    normalized = validate_echo_packet(packet)
    pool_hash = (pool_tip_hash or "").strip().lower()
    pool_height = max(0, int(pool_tip_height or 0))
    agrees = 1
    if pool_hash and normalized["tip_hash"] != pool_hash:
        delta = abs(int(normalized["block_height"]) - pool_height)
        agrees = 1 if delta <= ECHO_DELTA_BLOCKS else 0
    now = _now()
    with mesh_db._conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO quasar_lan_echoes (
                echo_id, device_id, public_ip, tip_hash, block_height,
                pool_tip_hash, pool_tip_height, agrees, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["echo_id"],
                normalized["device_id"],
                (public_ip or "").strip()[:64],
                normalized["tip_hash"],
                normalized["block_height"],
                pool_hash,
                pool_height,
                agrees,
                json.dumps(normalized, sort_keys=True),
                now,
            ),
        )
        conn.execute(
            """
            UPDATE chain_lan_nodes
            SET tip_hash = ?, best_block_hash = ?, block_height = ?, last_seen = ?
            WHERE device_id = ?
            """,
            (
                normalized["tip_hash"],
                normalized["tip_hash"],
                normalized["block_height"],
                now,
                normalized["device_id"],
            ),
        )
    return {
        "ok": True,
        "echo": normalized,
        "agrees_with_pool": bool(agrees),
        "pool_tip_hash": pool_hash,
        "pool_tip_height": pool_height,
    }


def lan_echo_status(
    *,
    public_ip: str = "",
    pool_tip_hash: str = "",
    pool_tip_height: int = 0,
) -> Dict[str, Any]:
    init_lan_echo_db()
    cutoff = _now() - ECHO_TTL_SEC
    pool_hash = (pool_tip_hash or "").strip().lower()
    pool_height = max(0, int(pool_tip_height or 0))
    clauses = ["created_at >= ?"]
    params: List[Any] = [cutoff]
    if public_ip:
        clauses.append("public_ip = ?")
        params.append(public_ip.strip()[:64])
    where = " AND ".join(clauses)
    with mesh_db._conn() as conn:
        rows = conn.execute(
            f"""
            SELECT device_id, tip_hash, block_height, agrees, created_at, public_ip
            FROM quasar_lan_echoes
            WHERE {where}
            ORDER BY created_at DESC
            """,
            params,
        ).fetchall()
    echoes = [dict(r) for r in rows]
    devices = {str(e["device_id"]) for e in echoes}
    agreeing = [e for e in echoes if int(e.get("agrees") or 0)]
    agree_devices = {str(e["device_id"]) for e in agreeing}
    tip_votes: Dict[str, int] = {}
    for e in echoes:
        th = str(e.get("tip_hash") or "")
        tip_votes[th] = tip_votes.get(th, 0) + 1

    split_brain = False
    if pool_hash and echoes:
        pool_agree = sum(
            1
            for e in echoes
            if str(e.get("tip_hash") or "") == pool_hash
            or abs(int(e.get("block_height") or 0) - pool_height) <= ECHO_DELTA_BLOCKS
        )
    else:
        pool_agree = len(agree_devices)

    if len(tip_votes) >= 2:
        sorted_votes = sorted(tip_votes.values(), reverse=True)
        if len(sorted_votes) >= 2 and sorted_votes[1] >= 2:
            split_brain = True

    total_active = len(devices)
    agree_count = len(agree_devices) if pool_hash else len(agree_devices)
    quorum_label = f"{agree_count}/{max(total_active, agree_count)} agree"
    if split_brain:
        status = "split_brain"
    elif total_active == 0:
        status = "no_echoes"
    elif pool_hash and agree_count < max(1, total_active // 2):
        status = "disagree"
    else:
        status = "quorum"

    lag = lan.all_lan_nodes_lag(lookback_sec=ECHO_TTL_SEC * 4, include_inactive=False)
    return {
        "ok": True,
        "status": status,
        "agree_count": agree_count,
        "total_echoes": len(echoes),
        "total_devices": total_active,
        "quorum_label": quorum_label,
        "split_brain": split_brain,
        "pool_tip_hash": pool_hash,
        "pool_tip_height": pool_height,
        "tip_votes": tip_votes,
        "echoes": echoes[:32],
        "lan_registry": {
            "active_count": int(lag.get("active_count") or 0),
            "network_tip": int(lag.get("network_tip") or 0),
            "max_blocks_behind": int(lag.get("max_blocks_behind") or 0),
        },
        "ttl_sec": ECHO_TTL_SEC,
        "delta_blocks": ECHO_DELTA_BLOCKS,
    }