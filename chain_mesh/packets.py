"""BSM3 mesh packet service — virtual LAN datagrams with mining attestation."""

from __future__ import annotations

import base64
import time
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db
from chain_mesh import packet_protocol as pp
from chain_mesh import packet_stream as pkt_stream
from chain_mesh.transfer import _anchor_bsm2_payload


def _init_packet_tables() -> None:
    with mesh_db._conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chain_mesh_packet_channels (
                channel_id TEXT PRIMARY KEY,
                sender TEXT NOT NULL DEFAULT '',
                recipient TEXT NOT NULL DEFAULT '',
                label TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                anchor_txid TEXT,
                packet_count INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                expires_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_mesh_packet_channels_recipient
                ON chain_mesh_packet_channels(recipient, status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS chain_mesh_packets (
                packet_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                sender TEXT NOT NULL DEFAULT '',
                recipient TEXT NOT NULL DEFAULT '',
                payload_type TEXT NOT NULL DEFAULT 'text',
                payload_b64 TEXT NOT NULL,
                payload_size INTEGER NOT NULL,
                payload_sha256 TEXT NOT NULL,
                relay_count INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                UNIQUE(channel_id, seq)
            );
            CREATE INDEX IF NOT EXISTS idx_mesh_packets_channel
                ON chain_mesh_packets(channel_id, seq);
            CREATE INDEX IF NOT EXISTS idx_mesh_packets_recipient
                ON chain_mesh_packets(recipient, created_at DESC);

            CREATE TABLE IF NOT EXISTS chain_mesh_packet_attestations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL,
                packet_id TEXT NOT NULL,
                device_id TEXT NOT NULL DEFAULT '',
                worker TEXT NOT NULL DEFAULT '',
                job_id TEXT NOT NULL DEFAULT '',
                nonce_hex TEXT NOT NULL DEFAULT '',
                work_digest TEXT NOT NULL,
                bytes_attested INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                UNIQUE(packet_id, device_id, work_digest)
            );
            CREATE INDEX IF NOT EXISTS idx_packet_attest_pid
                ON chain_mesh_packet_attestations(packet_id, created_at DESC);
            """
        )


_init_packet_tables()


def protocol_payload() -> Dict[str, Any]:
    with mesh_db._conn() as conn:
        ch = conn.execute("SELECT COUNT(*) AS n FROM chain_mesh_packet_channels").fetchone()
        pk = conn.execute("SELECT COUNT(*) AS n FROM chain_mesh_packets").fetchone()
        att = conn.execute(
            """
            SELECT COUNT(*) AS n, COALESCE(SUM(bytes_attested), 0) AS bytes
            FROM chain_mesh_packet_attestations
            """
        ).fetchone()
    return {
        "ok": True,
        "protocol": pp.PACKET_PROTOCOL,
        "magic": "BSM3",
        "max_packet_bytes": pp.MAX_PACKET_BYTES,
        "description": (
            "BSM3 virtual LAN packets: small datagrams over the mesh with miner "
            "hash-power attestation. Browsers send/receive via coordinator inbox."
        ),
        "channels": int(ch["n"] if ch else 0),
        "packets": int(pk["n"] if pk else 0),
        "attestations": {
            "count": int(att["n"] if att else 0),
            "bytes_attested": int(att["bytes"] if att else 0),
        },
        "work_digest": (
            'SHA256("BSM3" || channel_id || packet_id || job_id || nonce_hex)'
        ),
    }


def open_channel_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    sender = str(payload.get("sender") or payload.get("sender_address") or "").strip()
    recipient = str(payload.get("recipient") or payload.get("recipient_address") or "").strip()
    label = str(payload.get("label") or payload.get("name") or "").strip()[:120]
    anchor = bool(payload.get("anchor", False))
    ttl_hours = int(payload.get("ttl_hours") or 24)

    if not sender:
        raise ValueError("sender required")
    if not recipient:
        raise ValueError("recipient required (STONE address or device_id)")

    channel_id = str(payload.get("channel_id") or "").strip().lower()
    if not channel_id or len(channel_id) != 64:
        channel_id = pp.channel_id_for(sender=sender, recipient=recipient, label=label)

    now = int(time.time())
    expires_at = now + max(3600, ttl_hours * 3600)

    with mesh_db._conn() as conn:
        existing = conn.execute(
            "SELECT channel_id FROM chain_mesh_packet_channels WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE chain_mesh_packet_channels
                SET updated_at = ?, expires_at = ?, status = ?
                WHERE channel_id = ?
                """,
                (now, expires_at, pp.CHANNEL_STATUS_OPEN, channel_id),
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
                    channel_id,
                    sender,
                    recipient,
                    label,
                    pp.CHANNEL_STATUS_OPEN,
                    now,
                    now,
                    expires_at,
                ),
            )

    result: Dict[str, Any] = {
        "ok": True,
        "channel_id": channel_id,
        "sender": sender,
        "recipient": recipient,
        "label": label,
        "status": pp.CHANNEL_STATUS_OPEN,
        "expires_at": expires_at,
    }

    if anchor:
        try:
            anchor_bytes = pp.build_packet_anchor_payload(
                channel_id=channel_id,
                recipient_address=recipient,
                seq=0,
            )
            anchor_result = _anchor_bsm2_payload(payload_bytes=anchor_bytes)
            txid = anchor_result.get("txid")
            with mesh_db._conn() as conn:
                conn.execute(
                    "UPDATE chain_mesh_packet_channels SET anchor_txid = ? WHERE channel_id = ?",
                    (txid, channel_id),
                )
            result["anchor"] = {**anchor_result, "magic": "BSM3"}
        except Exception as exc:
            result["anchor"] = {"ok": False, "error": str(exc)}

    return result


def send_packet_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    channel_id = str(payload.get("channel_id") or "").strip().lower()
    sender = str(payload.get("sender") or "").strip()
    recipient = str(payload.get("recipient") or "").strip()
    payload_type = str(payload.get("payload_type") or payload.get("type") or "text").strip()[:32]
    payload_b64 = str(payload.get("payload_b64") or "").strip()
    seq_override = payload.get("seq")

    if len(channel_id) != 64:
        raise ValueError("channel_id required (64 hex chars)")
    if not payload_b64:
        raise ValueError("payload_b64 required")

    try:
        raw = base64.b64decode(payload_b64, validate=True)
    except Exception as exc:
        raise ValueError(f"invalid payload_b64: {exc}") from exc

    if len(raw) <= 0 or len(raw) > pp.MAX_PACKET_BYTES:
        raise ValueError(f"payload must be 1..{pp.MAX_PACKET_BYTES} bytes")

    phash = pp.payload_sha256(raw)
    now = int(time.time())
    ttl_sec = int(payload.get("ttl_sec") or pp.DEFAULT_TTL_SEC)
    expires_at = now + max(60, min(86400, ttl_sec))

    with mesh_db._conn() as conn:
        ch = conn.execute(
            "SELECT * FROM chain_mesh_packet_channels WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
        if not ch:
            raise ValueError("channel not found — open channel first")
        data = dict(ch)
        if data["status"] != pp.CHANNEL_STATUS_OPEN:
            raise ValueError(f"channel status is {data['status']}")
        ch_sender = str(data["sender"] or "")
        ch_recipient = str(data["recipient"] or "")
        ch_label = str(data.get("label") or "")
        is_room = pp.is_room_channel_label(ch_label)
        parties = {p for p in (ch_sender, ch_recipient) if p}
        if is_room:
            if not sender:
                raise ValueError("sender required for room messages")
            recipient = ch_recipient or pp.NETWORK_CHAT_LOBBY_ID
        else:
            if sender and parties and sender not in parties:
                raise ValueError("sender must be a channel party")
            if recipient and parties and recipient not in parties:
                raise ValueError("recipient must be a channel party")
            sender = sender or ch_sender
            recipient = recipient or ch_recipient

        if seq_override is not None:
            seq = int(seq_override)
        else:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS m FROM chain_mesh_packets WHERE channel_id = ?",
                (channel_id,),
            ).fetchone()
            seq = int(row["m"] if row else 0) + 1

        packet_id = pp.packet_id_for(channel_id=channel_id, seq=seq, payload_sha256=phash)

        conn.execute(
            """
            INSERT INTO chain_mesh_packets (
                packet_id, channel_id, seq, sender, recipient,
                payload_type, payload_b64, payload_size, payload_sha256,
                created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                packet_id,
                channel_id,
                seq,
                sender,
                recipient,
                payload_type,
                payload_b64,
                len(raw),
                phash,
                now,
                expires_at,
            ),
        )
        conn.execute(
            """
            UPDATE chain_mesh_packet_channels
            SET packet_count = packet_count + 1, updated_at = ?
            WHERE channel_id = ?
            """,
            (now, channel_id),
        )

    frame = pp.build_packet_frame(
        channel_id=channel_id,
        packet_id=packet_id,
        seq=seq,
        sender=sender,
        recipient=recipient,
        payload_type=payload_type,
        payload_size=len(raw),
        payload_sha256_hex=phash,
        created_at=now,
    )
    frame["payload_b64"] = payload_b64
    pkt_stream.publish(
        recipient,
        {"type": "packet", "packet": {k: v for k, v in frame.items() if k != "payload_b64"}},
    )
    if sender and sender != recipient:
        pkt_stream.publish(sender, {"type": "packet_sent", "packet_id": packet_id, "seq": seq})
    return {"ok": True, "packet": frame}


def _decode_packet_row(row: Dict[str, Any], *, include_payload: bool = True) -> Dict[str, Any]:
    data = dict(row)
    frame = pp.build_packet_frame(
        channel_id=data["channel_id"],
        packet_id=data["packet_id"],
        seq=int(data["seq"]),
        sender=data["sender"],
        recipient=data["recipient"],
        payload_type=data["payload_type"],
        payload_size=int(data["payload_size"]),
        payload_sha256_hex=data["payload_sha256"],
        created_at=int(data["created_at"]),
    )
    if include_payload:
        frame["payload_b64"] = data["payload_b64"]
        try:
            raw = base64.b64decode(data["payload_b64"])
            if data["payload_type"] in ("text", "json", "utf8"):
                frame["payload_text"] = raw.decode("utf-8", errors="replace")
            frame["payload_hex"] = raw.hex()
        except Exception:
            pass
    frame["relay_count"] = int(data.get("relay_count") or 0)
    frame["expires_at"] = int(data.get("expires_at") or 0)
    return frame


def inbox_payload(
    recipient: str,
    *,
    channel_id: str = "",
    since_seq: int = 0,
    limit: int = 50,
) -> Dict[str, Any]:
    addr = (recipient or "").strip()
    if not addr:
        raise ValueError("recipient required")

    clauses = ["recipient = ?"]
    params: List[Any] = [addr]
    if channel_id:
        clauses.append("channel_id = ?")
        params.append(channel_id.strip().lower())
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

    packets = [_decode_packet_row(dict(r)) for r in rows]
    return {
        "ok": True,
        "recipient": addr,
        "channel_id": channel_id or None,
        "packets": packets,
        "count": len(packets),
    }


def channel_payload(channel_id: str) -> Dict[str, Any]:
    cid = (channel_id or "").strip().lower()
    with mesh_db._conn() as conn:
        row = conn.execute(
            "SELECT * FROM chain_mesh_packet_channels WHERE channel_id = ?",
            (cid,),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "channel not found"}
        data = dict(row)
        att = conn.execute(
            """
            SELECT COUNT(*) AS n, COALESCE(SUM(bytes_attested), 0) AS bytes
            FROM chain_mesh_packet_attestations
            WHERE channel_id = ?
            """,
            (cid,),
        ).fetchone()
    return {
        "ok": True,
        "channel": data,
        "attestations": {
            "count": int(att["n"] if att else 0),
            "bytes_attested": int(att["bytes"] if att else 0),
        },
    }


def relay_queue_payload(
    device_id: str,
    *,
    limit: int = 8,
    backup_pct: int = 10,
) -> Dict[str, Any]:
    """Packets this miner should attest after share acceptance."""
    node = (device_id or "").strip()
    if not node:
        raise ValueError("device_id required")

    now = int(time.time())
    with mesh_db._conn() as conn:
        rows = conn.execute(
            """
            SELECT p.* FROM chain_mesh_packets p
            JOIN chain_mesh_packet_channels c ON c.channel_id = p.channel_id
            WHERE c.status = 'open' AND p.expires_at > ?
            ORDER BY p.created_at DESC
            LIMIT 200
            """,
            (now,),
        ).fetchall()

    candidates = []
    for row in rows:
        data = dict(row)
        pid = data["packet_id"]
        cid = data["channel_id"]
        if not pp.node_should_relay_packet(cid, node, pid, backup_pct=backup_pct):
            continue
        candidates.append(
            {
                "channel_id": cid,
                "packet_id": pid,
                "seq": int(data["seq"]),
                "payload_size": int(data["payload_size"]),
                "recipient": data["recipient"],
            }
        )
        if len(candidates) >= max(1, min(32, int(limit))):
            break

    return {"ok": True, "device_id": node, "queue": candidates, "count": len(candidates)}


def attest_packet_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    channel_id = str(payload.get("channel_id") or "").strip().lower()
    packet_id = str(payload.get("packet_id") or "").strip().lower()
    device_id = str(payload.get("device_id") or "").strip()
    worker = str(payload.get("worker") or "").strip()
    job_id = str(payload.get("job_id") or "").strip()
    nonce_hex = str(payload.get("nonce_hex") or payload.get("nonce") or "").strip().lower()

    if len(channel_id) != 64:
        raise ValueError("channel_id required")
    if len(packet_id) != 64:
        raise ValueError("packet_id required")
    if not device_id:
        raise ValueError("device_id required")
    if not job_id or not nonce_hex:
        raise ValueError("job_id and nonce_hex required")

    digest = pp.work_digest(
        channel_id=channel_id,
        packet_id=packet_id,
        job_id=job_id,
        nonce_hex=nonce_hex,
    )

    with mesh_db._conn() as conn:
        row = conn.execute(
            "SELECT * FROM chain_mesh_packets WHERE packet_id = ? AND channel_id = ?",
            (packet_id, channel_id),
        ).fetchone()
        if not row:
            raise ValueError("packet not found")
        data = dict(row)
        size = int(data["payload_size"])
        now = int(time.time())
        try:
            conn.execute(
                """
                INSERT INTO chain_mesh_packet_attestations (
                    channel_id, packet_id, device_id, worker, job_id,
                    nonce_hex, work_digest, bytes_attested, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    channel_id,
                    packet_id,
                    device_id,
                    worker,
                    job_id,
                    nonce_hex,
                    digest,
                    size,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE chain_mesh_packets
                SET relay_count = relay_count + 1
                WHERE packet_id = ?
                """,
                (packet_id,),
            )
        except Exception:
            return {
                "ok": True,
                "duplicate": True,
                "work_digest": digest,
                "bytes_attested": size,
            }

        mesh_db.upsert_peer(
            device_id=device_id,
            peer_kind=str(payload.get("peer_kind") or "android-miner"),
            model=str(payload.get("model") or ""),
            capacity_bytes=size,
            chunk_hashes=[],
        )

    return {
        "ok": True,
        "channel_id": channel_id,
        "packet_id": packet_id,
        "work_digest": digest,
        "bytes_attested": size,
    }