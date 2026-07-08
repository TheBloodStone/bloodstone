"""Household internet gateway — one mesh peer shares egress with all LAN miners."""

from __future__ import annotations

import os
import time
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db
from chain_mesh import ip_gateway as gw

GATEWAY_TTL_SEC = int(os.environ.get("BSM4_INTERNET_GATEWAY_TTL", "180"))
PEER_GATEWAY_ENABLED = os.environ.get("BSM4_PEER_GATEWAY_ENABLED", "1") == "1"
COORDINATOR_FALLBACK = gw.GATEWAY_RECIPIENT


def _init_tables() -> None:
    with mesh_db._conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chain_mesh_internet_gateways (
                device_id TEXT PRIMARY KEY,
                public_ip TEXT NOT NULL DEFAULT '',
                lan_ip TEXT NOT NULL DEFAULT '',
                label TEXT NOT NULL DEFAULT '',
                peer_kind TEXT NOT NULL DEFAULT 'android',
                share_internet INTEGER NOT NULL DEFAULT 0,
                latency_ms INTEGER NOT NULL DEFAULT 0,
                egress_count INTEGER NOT NULL DEFAULT 0,
                last_seen INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_mesh_inet_gw_public
                ON chain_mesh_internet_gateways(public_ip, share_internet, last_seen DESC);
            """
        )


_init_tables()


def _purge_stale() -> None:
    cutoff = int(time.time()) - GATEWAY_TTL_SEC
    with mesh_db._conn() as conn:
        conn.execute(
            "DELETE FROM chain_mesh_internet_gateways WHERE last_seen < ?",
            (cutoff,),
        )


def register_gateway_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Register or heartbeat a peer that can share internet with the mesh."""
    device_id = str(payload.get("device_id") or "").strip().lower()
    if not device_id:
        raise ValueError("device_id required")
    share = bool(payload.get("share_internet", True))
    now = int(time.time())
    public_ip = str(payload.get("public_ip") or "").strip()[:64]
    lan_ip = str(payload.get("lan_ip") or "").strip()[:64]
    label = str(payload.get("label") or device_id)[:120]
    peer_kind = str(payload.get("peer_kind") or "android").strip()[:24]
    latency_ms = max(0, int(payload.get("latency_ms") or 0))

    with mesh_db._conn() as conn:
        conn.execute(
            """
            INSERT INTO chain_mesh_internet_gateways (
                device_id, public_ip, lan_ip, label, peer_kind,
                share_internet, latency_ms, egress_count, last_seen, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                public_ip = excluded.public_ip,
                lan_ip = excluded.lan_ip,
                label = excluded.label,
                peer_kind = excluded.peer_kind,
                share_internet = excluded.share_internet,
                latency_ms = CASE WHEN excluded.latency_ms > 0 THEN excluded.latency_ms ELSE latency_ms END,
                last_seen = excluded.last_seen
            """,
            (
                device_id,
                public_ip,
                lan_ip,
                label,
                peer_kind,
                1 if share else 0,
                latency_ms,
                now,
                now,
            ),
        )
    return {
        "ok": True,
        "device_id": device_id,
        "share_internet": share,
        "recipient": device_id if share else COORDINATOR_FALLBACK,
        "ttl_sec": GATEWAY_TTL_SEC,
    }


def unregister_gateway_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    device_id = str(payload.get("device_id") or "").strip().lower()
    if not device_id:
        raise ValueError("device_id required")
    with mesh_db._conn() as conn:
        conn.execute(
            """
            UPDATE chain_mesh_internet_gateways
            SET share_internet = 0, last_seen = ?
            WHERE device_id = ?
            """,
            (int(time.time()), device_id),
        )
    return {"ok": True, "device_id": device_id, "share_internet": False}


def list_gateway_candidates(*, public_ip: str = "", limit: int = 16) -> Dict[str, Any]:
    _purge_stale()
    cutoff = int(time.time()) - GATEWAY_TTL_SEC
    clauses = ["share_internet = 1", "last_seen >= ?"]
    params: List[Any] = [cutoff]
    if public_ip:
        clauses.append("public_ip = ?")
        params.append(public_ip.strip())
    params.append(max(1, min(32, int(limit))))
    sql = (
        "SELECT * FROM chain_mesh_internet_gateways WHERE "
        + " AND ".join(clauses)
        + " ORDER BY last_seen DESC LIMIT ?"
    )
    with mesh_db._conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {
        "ok": True,
        "candidates": [dict(r) for r in rows],
        "count": len(rows),
        "coordinator_fallback": COORDINATOR_FALLBACK,
    }


def _rank_candidate(row: Dict[str, Any]) -> tuple:
    kind = str(row.get("peer_kind") or "").lower()
    kind_rank = {"pc": 0, "linux": 0, "raspberry": 1, "android": 2, "phone": 2}.get(
        kind, 3
    )
    latency = int(row.get("latency_ms") or 9999)
    return (kind_rank, latency, -int(row.get("last_seen") or 0))


def elect_gateway_payload(
    *,
    public_ip: str = "",
    requester_device_id: str = "",
) -> Dict[str, Any]:
    """Pick the best household internet gateway for mesh egress."""
    _purge_stale()
    cutoff = int(time.time()) - GATEWAY_TTL_SEC
    requester = (requester_device_id or "").strip().lower()

    with mesh_db._conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM chain_mesh_internet_gateways
            WHERE share_internet = 1 AND last_seen >= ?
            ORDER BY last_seen DESC
            """,
            (cutoff,),
        ).fetchall()

    candidates = [dict(r) for r in rows]
    if public_ip:
        household = [c for c in candidates if c.get("public_ip") == public_ip.strip()]
        if household:
            candidates = household

    if requester:
        candidates = [c for c in candidates if c.get("device_id") != requester] or candidates

    if candidates and PEER_GATEWAY_ENABLED:
        best = sorted(candidates, key=_rank_candidate)[0]
        return {
            "ok": True,
            "source": "peer",
            "recipient": str(best["device_id"]),
            "device_id": str(best["device_id"]),
            "public_ip": best.get("public_ip") or "",
            "lan_ip": best.get("lan_ip") or "",
            "label": best.get("label") or "",
            "peer_kind": best.get("peer_kind") or "",
            "latency_ms": int(best.get("latency_ms") or 0),
            "coordinator_fallback": COORDINATOR_FALLBACK,
        }

    return {
        "ok": True,
        "source": "coordinator",
        "recipient": COORDINATOR_FALLBACK,
        "device_id": COORDINATOR_FALLBACK,
        "public_ip": "",
        "lan_ip": "",
        "label": "Coordinator VPS",
        "peer_kind": "coordinator",
        "latency_ms": 0,
        "coordinator_fallback": COORDINATOR_FALLBACK,
    }


def _pending_peer_packets(*, recipient: str, limit: int = 16) -> List[Dict[str, Any]]:
    with mesh_db._conn() as conn:
        rows = conn.execute(
            """
            SELECT p.* FROM chain_mesh_packets p
            WHERE p.recipient = ?
              AND p.payload_type IN ('ipv4', 'ip')
              AND NOT EXISTS (
                SELECT 1 FROM chain_mesh_ip_gateway_processed g
                WHERE g.packet_id = p.packet_id
              )
            ORDER BY p.created_at ASC
            LIMIT ?
            """,
            (recipient.strip(), max(1, min(64, int(limit)))),
        ).fetchall()
    return [dict(r) for r in rows]


def run_peer_egress_batch(*, device_id: str, limit: int = 12) -> Dict[str, Any]:
    """Process IPv4 packets addressed to this device as household internet gateway."""
    if not PEER_GATEWAY_ENABLED:
        return {"ok": False, "error": "peer gateway disabled"}
    if not gw.GATEWAY_ENABLED:
        return {"ok": False, "error": "gateway egress disabled"}

    device_id = (device_id or "").strip().lower()
    if not device_id:
        raise ValueError("device_id required")

    rows = _pending_peer_packets(recipient=device_id, limit=limit)
    token = gw.gateway_sender_context(device_id)
    results: List[Dict[str, Any]] = []
    ok_count = 0
    poll_results: List[Dict[str, Any]] = []
    try:
        for row in rows:
            result = gw.process_ipv4_egress(row)
            results.append(result)
            if result.get("ok"):
                ok_count += 1
        from chain_mesh import ip_gateway_tcp as gw_tcp

        poll_results = gw_tcp.poll_active_tls_sessions(
            inject_reply=gw._inject_reply,
            limit=max(2, limit // 2),
            gateway_sender=device_id,
        )
    finally:
        gw.reset_gateway_sender(token)

    now = int(time.time())
    with mesh_db._conn() as conn:
        conn.execute(
            """
            UPDATE chain_mesh_internet_gateways
            SET egress_count = egress_count + ?, last_seen = ?
            WHERE device_id = ?
            """,
            (ok_count, now, device_id),
        )

    return {
        "ok": True,
        "device_id": device_id,
        "processed": len(results),
        "success": ok_count,
        "results": results,
        "tls_poll": poll_results,
    }


def pending_peer_packets_payload(*, device_id: str, limit: int = 12) -> Dict[str, Any]:
    """Return pending IPv4 packets for a peer gateway (APK/PC processes locally)."""
    device_id = (device_id or "").strip().lower()
    if not device_id:
        raise ValueError("device_id required")
    rows = _pending_peer_packets(recipient=device_id, limit=limit)
    packets = []
    for row in rows:
        packets.append(
            {
                "packet_id": row.get("packet_id"),
                "channel_id": row.get("channel_id"),
                "sender": row.get("sender"),
                "seq": row.get("seq"),
                "payload_b64": row.get("payload_b64"),
                "created_at": row.get("created_at"),
            }
        )
    return {"ok": True, "device_id": device_id, "packets": packets, "count": len(packets)}


def submit_peer_reply_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Inject egress reply from a peer gateway (e.g. APK fetch() result)."""
    packet_id = str(payload.get("packet_id") or "").strip()
    channel_id = str(payload.get("channel_id") or "").strip()
    mesh_sender = str(payload.get("mesh_sender") or payload.get("sender") or "").strip()
    gateway_device_id = str(payload.get("device_id") or "").strip().lower()
    reply_b64 = str(payload.get("reply_ip_b64") or payload.get("ip_packet_b64") or "").strip()
    action = str(payload.get("action") or "peer_http_reply").strip()
    if not packet_id or not reply_b64 or not mesh_sender:
        raise ValueError("packet_id, mesh_sender, reply_ip_b64 required")

    import base64

    reply_ip = base64.b64decode(reply_b64)
    token = gw.gateway_sender_context(gateway_device_id or gw.GATEWAY_RECIPIENT)
    try:
        inject = gw._inject_reply(
            channel_id=channel_id,
            sender=gateway_device_id or gw.current_gateway_sender(),
            recipient=mesh_sender,
            ip_packet=reply_ip,
        )
        gw._mark_processed(packet_id, channel_id=channel_id, action=action)
    finally:
        gw.reset_gateway_sender(token)

    return {
        "ok": True,
        "packet_id": packet_id,
        "action": action,
        "reply_packet_id": (inject.get("packet") or {}).get("packet_id"),
    }


def gateway_status_extended() -> Dict[str, Any]:
    _purge_stale()
    base = gw.gateway_status_payload()
    elected = elect_gateway_payload()
    candidates = list_gateway_candidates(limit=8)
    return {
        **base,
        "peer_gateway_enabled": PEER_GATEWAY_ENABLED,
        "elected": elected,
        "candidates": candidates.get("candidates") or [],
        "free_internet": {
            "description": (
                "One APK or PC on the LAN with internet registers as gateway; "
                "all mesh miners route BSM4 packets through them."
            ),
            "register_api": "/api/chain-mesh/internet-gateway/register",
            "elect_api": "/api/chain-mesh/internet-gateway/elected",
        },
    }