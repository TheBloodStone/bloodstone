"""Network chat — lobby room, DM channels, and node presence for old-school IM."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db
from chain_mesh import lan_registry as lan
from chain_mesh import packet_protocol as pp
from chain_mesh import packets as mesh_packets

_PRESENCE_TTL_SEC = int(os.environ.get("NETWORK_CHAT_PRESENCE_TTL_SEC", "180"))


def _now() -> int:
    return int(time.time())


def _init_chat_tables() -> None:
    mesh_db.init_db()
    with mesh_db._conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chain_chat_presence (
                device_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL DEFAULT '',
                status_message TEXT NOT NULL DEFAULT '',
                peer_kind TEXT NOT NULL DEFAULT 'browser',
                model TEXT NOT NULL DEFAULT '',
                public_ip TEXT NOT NULL DEFAULT '',
                last_seen INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chain_chat_presence_seen
                ON chain_chat_presence(last_seen DESC);
            """
        )


def ensure_lobby_channel() -> Dict[str, Any]:
    """Create or refresh the shared network lobby room channel."""
    cid = pp.lobby_channel_id()
    now = _now()
    expires_at = now + 86400 * 365
    with mesh_db._conn() as conn:
        row = conn.execute(
            "SELECT channel_id FROM chain_mesh_packet_channels WHERE channel_id = ?",
            (cid,),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE chain_mesh_packet_channels
                SET updated_at = ?, expires_at = ?, status = ?
                WHERE channel_id = ?
                """,
                (now, expires_at, pp.CHANNEL_STATUS_OPEN, cid),
            )
        else:
            conn.execute(
                """
                INSERT INTO chain_mesh_packet_channels (
                    channel_id, sender, recipient, label, status,
                    created_at, updated_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cid,
                    pp.NETWORK_CHAT_LOBBY_ID,
                    pp.NETWORK_CHAT_LOBBY_ID,
                    pp.NETWORK_CHAT_ROOM_LABEL,
                    pp.CHANNEL_STATUS_OPEN,
                    now,
                    now,
                    expires_at,
                ),
            )
    return {
        "ok": True,
        "channel_id": cid,
        "room_id": pp.NETWORK_CHAT_LOBBY_ID,
        "label": pp.NETWORK_CHAT_ROOM_LABEL,
    }


def lobby_info_payload() -> Dict[str, Any]:
    lobby = ensure_lobby_channel()
    cid = lobby["channel_id"]
    with mesh_db._conn() as conn:
        row = conn.execute(
            "SELECT packet_count, updated_at FROM chain_mesh_packet_channels WHERE channel_id = ?",
            (cid,),
        ).fetchone()
    return {
        **lobby,
        "packet_count": int(row["packet_count"] if row else 0),
        "updated_at": int(row["updated_at"] if row else 0),
    }


def lobby_inbox_payload(
    *,
    since_seq: int = 0,
    limit: int = 80,
) -> Dict[str, Any]:
    ensure_lobby_channel()
    cid = pp.lobby_channel_id()
    clauses = ["channel_id = ?"]
    params: List[Any] = [cid]
    if since_seq > 0:
        clauses.append("seq > ?")
        params.append(int(since_seq))
    params.append(max(1, min(200, int(limit))))
    sql = (
        "SELECT * FROM chain_mesh_packets WHERE "
        + " AND ".join(clauses)
        + " ORDER BY created_at ASC LIMIT ?"
    )
    with mesh_db._conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    packets = [mesh_packets._decode_packet_row(dict(r)) for r in rows]
    return {
        "ok": True,
        "room_id": pp.NETWORK_CHAT_LOBBY_ID,
        "channel_id": cid,
        "packets": packets,
        "count": len(packets),
    }


def lobby_send_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    sender = str(payload.get("sender") or payload.get("device_id") or "").strip()
    if not sender:
        raise ValueError("sender required")
    ensure_lobby_channel()
    text = str(payload.get("message") or payload.get("text") or "").strip()
    if not text:
        raise ValueError("message required")
    import base64

    raw = text.encode("utf-8")
    if len(raw) > pp.MAX_PACKET_BYTES:
        raise ValueError(f"message too long (max {pp.MAX_PACKET_BYTES} bytes)")
    return mesh_packets.send_packet_payload(
        {
            "channel_id": pp.lobby_channel_id(),
            "sender": sender,
            "recipient": pp.NETWORK_CHAT_LOBBY_ID,
            "payload_type": "text",
            "payload_b64": base64.b64encode(raw).decode("ascii"),
        }
    )


def open_dm_channel_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Open (or reuse) a canonical 1:1 DM channel between two identities."""
    user_a = str(payload.get("sender") or payload.get("self") or "").strip()
    user_b = str(payload.get("recipient") or payload.get("peer") or "").strip()
    if not user_a or not user_b:
        raise ValueError("sender and recipient required")
    if user_a == user_b:
        raise ValueError("cannot DM yourself")
    cid = pp.dm_channel_id(user_a, user_b)
    a, b = sorted([user_a, user_b])
    return mesh_packets.open_channel_payload(
        {
            "channel_id": cid,
            "sender": a,
            "recipient": b,
            "label": pp.NETWORK_CHAT_DM_LABEL,
            "ttl_hours": int(payload.get("ttl_hours") or 168),
        }
    )


def channels_for_participant(participant: str, *, limit: int = 40) -> Dict[str, Any]:
    who = (participant or "").strip()
    if not who:
        raise ValueError("participant required")
    with mesh_db._conn() as conn:
        rows = conn.execute(
            """
            SELECT channel_id, sender, recipient, label, status,
                   packet_count, created_at, updated_at
            FROM chain_mesh_packet_channels
            WHERE label = ? AND (sender = ? OR recipient = ?)
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (pp.NETWORK_CHAT_DM_LABEL, who, who, max(1, min(100, int(limit)))),
        ).fetchall()
    channels = []
    for row in rows:
        data = dict(row)
        peer = data["recipient"] if data["sender"] == who else data["sender"]
        channels.append(
            {
                "channel_id": data["channel_id"],
                "peer": peer,
                "sender": data["sender"],
                "recipient": data["recipient"],
                "packet_count": int(data.get("packet_count") or 0),
                "updated_at": int(data.get("updated_at") or 0),
            }
        )
    return {"ok": True, "participant": who, "channels": channels, "count": len(channels)}


def heartbeat_payload(payload: Dict[str, Any], *, public_ip: str = "") -> Dict[str, Any]:
    """Register web/APK chat presence (buddy list)."""
    _init_chat_tables()
    device_id = str(payload.get("device_id") or payload.get("sender") or "").strip().lower()
    if not device_id:
        raise ValueError("device_id required")
    display_name = str(payload.get("display_name") or payload.get("nick") or device_id)[:64]
    status_message = str(payload.get("status_message") or payload.get("status") or "")[:120]
    peer_kind = str(payload.get("peer_kind") or "browser")[:24]
    model = str(payload.get("model") or "")[:120]
    now = _now()
    with mesh_db._conn() as conn:
        conn.execute(
            """
            INSERT INTO chain_chat_presence (
                device_id, display_name, status_message, peer_kind,
                model, public_ip, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                display_name = excluded.display_name,
                status_message = excluded.status_message,
                peer_kind = excluded.peer_kind,
                model = excluded.model,
                public_ip = excluded.public_ip,
                last_seen = excluded.last_seen
            """,
            (
                device_id,
                display_name,
                status_message,
                peer_kind,
                model,
                (public_ip or "")[:64],
                now,
            ),
        )
    return {
        "ok": True,
        "device_id": device_id,
        "display_name": display_name,
        "last_seen": now,
    }


def _presence_status(*, age_sec: int, active_sec: int) -> str:
    if age_sec <= active_sec:
        return "online"
    if age_sec <= active_sec * 3:
        return "away"
    return "offline"


def presence_payload(
    *,
    public_ip: str = "",
    include_offline: bool = False,
    limit: int = 120,
) -> Dict[str, Any]:
    """Buddy list: LAN nodes + registered chat clients."""
    _init_chat_tables()
    lan.init_lan_db()
    now = _now()
    active_sec = _PRESENCE_TTL_SEC
    cutoff = now - max(active_sec * 6, 3600)
    buddies: Dict[str, Dict[str, Any]] = {}

    def upsert(
        device_id: str,
        *,
        display_name: str,
        peer_kind: str,
        model: str,
        last_seen: int,
        source: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        did = (device_id or "").strip().lower()
        if not did:
            return
        age_sec = max(0, now - int(last_seen or 0))
        status = _presence_status(age_sec=age_sec, active_sec=active_sec)
        if not include_offline and status == "offline":
            return
        row = {
            "device_id": did,
            "display_name": (display_name or did)[:64],
            "status": status,
            "status_message": "",
            "peer_kind": peer_kind or "unknown",
            "model": model or "",
            "last_seen": int(last_seen or 0),
            "age_sec": age_sec,
            "source": source,
        }
        if extra:
            row.update(extra)
        prev = buddies.get(did)
        if not prev or int(row["last_seen"]) >= int(prev.get("last_seen") or 0):
            buddies[did] = row

    with mesh_db._conn() as conn:
        chat_rows = conn.execute(
            """
            SELECT device_id, display_name, status_message, peer_kind,
                   model, public_ip, last_seen
            FROM chain_chat_presence
            WHERE last_seen >= ?
            ORDER BY last_seen DESC
            LIMIT ?
            """,
            (cutoff, max(1, min(500, int(limit)))),
        ).fetchall()
        for row in chat_rows:
            data = dict(row)
            upsert(
                data["device_id"],
                display_name=data.get("display_name") or data["device_id"],
                peer_kind=data.get("peer_kind") or "browser",
                model=data.get("model") or "",
                last_seen=int(data.get("last_seen") or 0),
                source="chat",
                extra={"status_message": data.get("status_message") or ""},
            )

    lag = lan.all_lan_nodes_lag(lookback_sec=86400, include_inactive=include_offline)
    for node in lag.get("nodes") or []:
        if not node.get("active") and not include_offline:
            continue
        status = "online" if node.get("active") else "offline"
        if node.get("status") in ("syncing", "behind", "caught_up"):
            status = "online" if node.get("active") else status
        upsert(
            node.get("device_id") or "",
            display_name=node.get("model") or node.get("device_id") or "",
            peer_kind=node.get("peer_kind") or "android",
            model=node.get("model") or "",
            last_seen=int(node.get("last_seen") or 0),
            source="lan",
            extra={
                "status": status,
                "mode": node.get("mode") or "",
                "lan_ip": node.get("lan_ip") or "",
                "block_height": int(node.get("block_height") or 0),
                "blocks_behind": int(node.get("blocks_behind") or 0),
            },
        )

    if public_ip:
        for node in lan.nearby_lan_nodes(public_ip):
            upsert(
                node.get("device_id") or "",
                display_name=node.get("model") or node.get("device_id") or "",
                peer_kind=node.get("peer_kind") or "android",
                model=node.get("model") or "",
                last_seen=int(node.get("last_seen") or now),
                source="nearby",
                extra={
                    "status": "online",
                    "lan_ip": node.get("lan_ip") or "",
                    "nearby": True,
                },
            )

    items = sorted(
        buddies.values(),
        key=lambda b: (
            0 if b.get("status") == "online" else 1 if b.get("status") == "away" else 2,
            -int(b.get("last_seen") or 0),
        ),
    )[: max(1, min(500, int(limit)))]
    counts = {"online": 0, "away": 0, "offline": 0}
    for item in items:
        counts[item.get("status") or "offline"] = counts.get(item.get("status") or "offline", 0) + 1

    return {
        "ok": True,
        "lobby": lobby_info_payload(),
        "buddies": items,
        "count": len(items),
        "counts": counts,
        "active_sec": active_sec,
        "updated_at": now,
    }