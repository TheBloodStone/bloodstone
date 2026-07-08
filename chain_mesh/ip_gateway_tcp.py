"""BSM4 TCP/TLS passthrough — relay raw bytes to upstream without terminating TLS."""

from __future__ import annotations

import socket
import time
from typing import Any, Dict, List, Optional, Tuple

import os

from chain_mesh import db as mesh_db
from chain_mesh import ip_tunnel_protocol as ip4
from chain_mesh import ip_tunnel_tls as tls
def _gateway_recipient() -> str:
    from chain_mesh import ip_gateway as gw

    return gw.current_gateway_sender()

TLS_RELAY_TIMEOUT = float(os.environ.get("BSM4_GATEWAY_TLS_RELAY_TIMEOUT", "8"))
TLS_RELAY_MAX_BYTES = int(os.environ.get("BSM4_GATEWAY_TLS_RELAY_MAX_BYTES", "16384"))
TLS_SESSION_TTL_SEC = int(os.environ.get("BSM4_GATEWAY_TLS_SESSION_TTL", "180"))

_SOCKETS: Dict[str, socket.socket] = {}


def _migrate_tcp_session_columns(conn) -> None:
    """Add multi-round relay columns to pre-existing session tables."""
    existing = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(chain_mesh_ip_gateway_tcp_sessions)"
        )
    }
    if "client_next_ack" not in existing:
        conn.execute(
            "ALTER TABLE chain_mesh_ip_gateway_tcp_sessions "
            "ADD COLUMN client_next_ack INTEGER NOT NULL DEFAULT 0"
        )
    if "relay_rounds" not in existing:
        conn.execute(
            "ALTER TABLE chain_mesh_ip_gateway_tcp_sessions "
            "ADD COLUMN relay_rounds INTEGER NOT NULL DEFAULT 0"
        )
    if "handshake_complete" not in existing:
        conn.execute(
            "ALTER TABLE chain_mesh_ip_gateway_tcp_sessions "
            "ADD COLUMN handshake_complete INTEGER NOT NULL DEFAULT 0"
        )


def _init_tcp_session_tables() -> None:
    with mesh_db._conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chain_mesh_ip_gateway_tcp_sessions (
                session_key TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                mesh_sender TEXT NOT NULL,
                dst_ip TEXT NOT NULL,
                dst_port INTEGER NOT NULL,
                sni_host TEXT NOT NULL DEFAULT '',
                gateway_seq INTEGER NOT NULL DEFAULT 1,
                client_next_ack INTEGER NOT NULL DEFAULT 0,
                relay_rounds INTEGER NOT NULL DEFAULT 0,
                handshake_complete INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_mesh_gw_tcp_sess_updated
                ON chain_mesh_ip_gateway_tcp_sessions(updated_at DESC);
            """
        )
        _migrate_tcp_session_columns(conn)


_init_tcp_session_tables()


def _session_key(
    *,
    channel_id: str,
    src_ip: str,
    src_port: int,
    dst_ip: str,
    dst_port: int,
) -> str:
    return f"{channel_id}|{src_ip}|{src_port}|{dst_ip}|{dst_port}"


def _load_session(key: str) -> Optional[Dict[str, Any]]:
    with mesh_db._conn() as conn:
        row = conn.execute(
            "SELECT * FROM chain_mesh_ip_gateway_tcp_sessions WHERE session_key = ?",
            (key,),
        ).fetchone()
    return dict(row) if row else None


def _upsert_session(
    key: str,
    *,
    channel_id: str,
    mesh_sender: str,
    dst_ip: str,
    dst_port: int,
    sni_host: str,
    gateway_seq: int,
    client_next_ack: int = 0,
    relay_rounds: int = 0,
    handshake_complete: int = 0,
) -> None:
    now = int(time.time())
    with mesh_db._conn() as conn:
        conn.execute(
            """
            INSERT INTO chain_mesh_ip_gateway_tcp_sessions (
                session_key, channel_id, mesh_sender, dst_ip, dst_port,
                sni_host, gateway_seq, client_next_ack, relay_rounds,
                handshake_complete, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_key) DO UPDATE SET
                sni_host = CASE WHEN excluded.sni_host != '' THEN excluded.sni_host ELSE sni_host END,
                gateway_seq = excluded.gateway_seq,
                client_next_ack = CASE WHEN excluded.client_next_ack > 0 THEN excluded.client_next_ack ELSE client_next_ack END,
                relay_rounds = excluded.relay_rounds,
                handshake_complete = CASE WHEN excluded.handshake_complete > 0 THEN excluded.handshake_complete ELSE handshake_complete END,
                updated_at = excluded.updated_at
            """,
            (
                key,
                channel_id,
                mesh_sender,
                dst_ip,
                dst_port,
                sni_host,
                gateway_seq,
                client_next_ack,
                relay_rounds,
                handshake_complete,
                now,
            ),
        )


def _delete_session(key: str) -> None:
    sock = _SOCKETS.pop(key, None)
    if sock:
        try:
            sock.close()
        except Exception:
            pass
    with mesh_db._conn() as conn:
        conn.execute(
            "DELETE FROM chain_mesh_ip_gateway_tcp_sessions WHERE session_key = ?",
            (key,),
        )


def _purge_stale_sessions() -> None:
    cutoff = int(time.time()) - TLS_SESSION_TTL_SEC
    with mesh_db._conn() as conn:
        rows = conn.execute(
            "SELECT session_key FROM chain_mesh_ip_gateway_tcp_sessions WHERE updated_at < ?",
            (cutoff,),
        ).fetchall()
    for row in rows:
        _delete_session(str(row["session_key"]))


def _is_ipv4(addr: str) -> bool:
    parts = (addr or "").split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


def _connect_target(dst_ip: str, sni_host: str) -> str:
    """TCP connect uses the IPv4 destination from the mesh frame (SNI stays in TLS)."""
    return dst_ip


def _get_upstream_socket(
    key: str,
    *,
    channel_id: str,
    mesh_sender: str,
    dst_ip: str,
    dst_port: int,
    sni_host: str,
) -> socket.socket:
    existing = _SOCKETS.get(key)
    if existing:
        return existing
    target = _connect_target(dst_ip, sni_host)
    sock = socket.create_connection((target, dst_port), timeout=TLS_RELAY_TIMEOUT)
    sock.settimeout(TLS_RELAY_TIMEOUT)
    _SOCKETS[key] = sock
    sess = _load_session(key)
    gateway_seq = int(sess["gateway_seq"]) if sess else int(time.time()) & 0x7FFFFFFF
    _upsert_session(
        key,
        channel_id=channel_id,
        mesh_sender=mesh_sender,
        dst_ip=dst_ip,
        dst_port=dst_port,
        sni_host=sni_host,
        gateway_seq=gateway_seq,
    )
    return sock


def _recv_upstream(sock: socket.socket) -> bytes:
    """Read a full server flight (handshake may span multiple TLS records)."""
    chunks: List[bytes] = []
    total = 0
    idle = 0
    sock.settimeout(0.35)
    while total < TLS_RELAY_MAX_BYTES and idle < 6:
        try:
            block = sock.recv(min(8192, TLS_RELAY_MAX_BYTES - total))
        except socket.timeout:
            idle += 1
            continue
        if not block:
            break
        chunks.append(block)
        total += len(block)
        idle = 0
    return b"".join(chunks)


def handle_tcp_tls_passthrough(
    *,
    raw: bytes,
    channel_id: str,
    mesh_sender: str,
    packet_id: str,
    dst: str,
    dst_port: int,
    mark_processed,
    inject_reply,
    fit_tcp_reply,
) -> Dict[str, Any]:
    """Relay TLS/TCP payload bytes to upstream; inject raw reply segment(s)."""
    _purge_stale_sessions()
    tcp_info = ip4.extract_tcp_from_ipv4(raw)
    flags = int(tcp_info.get("flags") or 0)
    tcp_payload = tcp_info.get("tcp_payload") or b""
    src_ip = str(tcp_info.get("src") or "")
    src_port = int(tcp_info.get("src_port") or 0)
    key = _session_key(
        channel_id=channel_id,
        src_ip=src_ip,
        src_port=src_port,
        dst_ip=dst,
        dst_port=dst_port,
    )

    if (flags & ip4.TCP_FLAG_SYN) and not (flags & ip4.TCP_FLAG_ACK):
        gateway_seq = int(time.time()) & 0x7FFFFFFF
        _upsert_session(
            key,
            channel_id=channel_id,
            mesh_sender=mesh_sender,
            dst_ip=dst,
            dst_port=dst_port,
            sni_host="",
            gateway_seq=gateway_seq,
        )
        reply_ip = ip4.build_tcp_reply_datagram(
            raw,
            flags=ip4.TCP_FLAG_SYN | ip4.TCP_FLAG_ACK,
            seq=gateway_seq,
        )
        inject = inject_reply(
            channel_id=channel_id,
            sender=_gateway_recipient(),
            recipient=mesh_sender,
            ip_packet=reply_ip,
        )
        mark_processed(packet_id, channel_id=channel_id, action="tcp_tls_syn_ack")
        return {
            "ok": True,
            "packet_id": packet_id,
            "action": "tcp_tls_syn_ack",
            "session_key": key,
            "reply_packet_id": (inject.get("packet") or {}).get("packet_id"),
        }

    if flags & ip4.TCP_FLAG_FIN:
        _delete_session(key)
        reply_ip = ip4.build_tcp_reply_datagram(raw, flags=ip4.TCP_FLAG_ACK | ip4.TCP_FLAG_FIN)
        inject = inject_reply(
            channel_id=channel_id,
            sender=_gateway_recipient(),
            recipient=mesh_sender,
            ip_packet=reply_ip,
        )
        mark_processed(packet_id, channel_id=channel_id, action="tcp_tls_fin")
        return {
            "ok": True,
            "packet_id": packet_id,
            "action": "tcp_tls_fin",
            "reply_packet_id": (inject.get("packet") or {}).get("packet_id"),
        }

    if not tcp_payload:
        mark_processed(packet_id, channel_id=channel_id, action="tcp_tls_empty")
        return {
            "ok": False,
            "packet_id": packet_id,
            "action": "tcp_tls_passthrough",
            "error": "TCP segment has no payload",
        }

    sess_existing = _load_session(key) or {}
    is_tls_payload = tls.is_tls_record(tcp_payload)
    if not is_tls_payload and not (flags & (ip4.TCP_FLAG_SYN | ip4.TCP_FLAG_FIN)):
        mark_processed(packet_id, channel_id=channel_id, action="tcp_tls_not_tls")
        return {
            "ok": False,
            "packet_id": packet_id,
            "action": "tcp_tls_passthrough",
            "error": "payload is not a TLS record",
        }

    sni = (
        tls.parse_tls_sni(tcp_payload)
        or str(sess_existing.get("sni_host") or "")
        or dst
    )
    try:
        sock = _get_upstream_socket(
            key,
            channel_id=channel_id,
            mesh_sender=mesh_sender,
            dst_ip=dst,
            dst_port=dst_port,
            sni_host=sni,
        )
        sock.sendall(tcp_payload)
        upstream = _recv_upstream(sock)
    except Exception as exc:
        _delete_session(key)
        mark_processed(packet_id, channel_id=channel_id, action="tcp_tls_error")
        return {
            "ok": False,
            "packet_id": packet_id,
            "action": "tcp_tls_passthrough",
            "error": str(exc),
            "sni": sni,
        }

    if not upstream:
        mark_processed(packet_id, channel_id=channel_id, action="tcp_tls_no_reply")
        return {
            "ok": False,
            "packet_id": packet_id,
            "action": "tcp_tls_passthrough",
            "error": "upstream returned no data",
            "sni": sni,
        }

    sess = _load_session(key) or {}
    gateway_seq = int(sess.get("gateway_seq") or 1)
    req_seq = int(tcp_info.get("seq") or 0)
    req_payload_len = len(tcp_payload)
    # TCP ack for replies: next byte expected from the mesh client.
    client_next_ack = req_seq + req_payload_len
    relay_rounds = int(sess.get("relay_rounds") or 0) + 1
    max_chunk = ip4.MAX_IPV4_DATAGRAM - ip4.MIN_IPV4_HEADER - 20
    reply_ids: List[str] = []
    offset = 0
    while offset < len(upstream):
        chunk = upstream[offset : offset + max_chunk]
        offset += len(chunk)
        reply_ip = ip4.build_tcp_reply_datagram(
            raw,
            flags=ip4.TCP_FLAG_PSH | ip4.TCP_FLAG_ACK,
            seq=gateway_seq,
            ack=req_seq + req_payload_len,
            payload=chunk,
        )
        gateway_seq += len(chunk)
        inject = inject_reply(
            channel_id=channel_id,
            sender=_gateway_recipient(),
            recipient=mesh_sender,
            ip_packet=reply_ip,
        )
        reply_ids.append((inject.get("packet") or {}).get("packet_id") or "")

    hs_up = tls.handshake_phase_summary(upstream)
    has_app = any(
        r[0] == tls.TLS_APPLICATION_DATA
        for r in tls.parse_tls_records(upstream)
    ) and relay_rounds > 1
    if relay_rounds > 1:
        action = "tcp_tls_app_data" if has_app else "tcp_tls_continue"
    else:
        action = "tcp_tls_passthrough"
    handshake_complete = 1 if relay_rounds >= 2 else 0
    _upsert_session(
        key,
        channel_id=channel_id,
        mesh_sender=mesh_sender,
        dst_ip=dst,
        dst_port=dst_port,
        sni_host=sni,
        gateway_seq=gateway_seq,
        client_next_ack=client_next_ack,
        relay_rounds=relay_rounds,
        handshake_complete=handshake_complete,
    )
    mark_processed(packet_id, channel_id=channel_id, action=action)
    return {
        "ok": True,
        "packet_id": packet_id,
        "action": action,
        "sni": sni,
        "relay_round": relay_rounds,
        "tls_summary": tls.summarize_tls_payload(tcp_payload),
        "upstream_summary": tls.summarize_tls_payload(upstream[:512]),
        "upstream_phases": hs_up.get("phases"),
        "has_server_hello": hs_up.get("has_server_hello"),
        "bytes_up": len(tcp_payload),
        "bytes_down": len(upstream),
        "reply_packets": len(reply_ids),
        "reply_packet_ids": reply_ids,
    }


def _parse_session_key(key: str) -> Dict[str, Any]:
    parts = (key or "").split("|")
    if len(parts) != 5:
        raise ValueError("invalid session key")
    return {
        "channel_id": parts[0],
        "src_ip": parts[1],
        "src_port": int(parts[2]),
        "dst_ip": parts[3],
        "dst_port": int(parts[4]),
    }


def _inject_upstream_chunks(
    *,
    key: str,
    sess: Dict[str, Any],
    upstream: bytes,
    inject_reply,
) -> List[str]:
    """Split upstream TLS bytes into MTU-sized TCP reply packets."""
    channel_id = str(sess["channel_id"])
    mesh_sender = str(sess["mesh_sender"])
    gateway_seq = int(sess.get("gateway_seq") or 1)
    client_ack = int(sess.get("client_next_ack") or 0) or 1
    flow = _parse_session_key(key)
    max_chunk = ip4.MAX_IPV4_DATAGRAM - ip4.MIN_IPV4_HEADER - 20
    reply_ids: List[str] = []
    offset = 0
    while offset < len(upstream):
        chunk = upstream[offset : offset + max_chunk]
        offset += len(chunk)
        reply_ip = ip4.build_tcp_segment(
            src_ip=str(sess["dst_ip"]),
            dst_ip=str(flow["src_ip"]),
            src_port=int(sess["dst_port"]),
            dst_port=int(flow["src_port"]),
            seq=gateway_seq,
            ack=client_ack,
            flags=ip4.TCP_FLAG_PSH | ip4.TCP_FLAG_ACK,
            payload=chunk,
        )
        gateway_seq += len(chunk)
        inject = inject_reply(
            channel_id=channel_id,
            sender=_gateway_recipient(),
            recipient=mesh_sender,
            ip_packet=reply_ip,
        )
        reply_ids.append((inject.get("packet") or {}).get("packet_id") or "")
    _upsert_session(
        key,
        channel_id=channel_id,
        mesh_sender=mesh_sender,
        dst_ip=str(sess["dst_ip"]),
        dst_port=int(sess["dst_port"]),
        sni_host=str(sess.get("sni_host") or ""),
        gateway_seq=gateway_seq,
        client_next_ack=int(sess.get("client_next_ack") or 0),
        relay_rounds=int(sess.get("relay_rounds") or 0),
        handshake_complete=int(sess.get("handshake_complete") or 1),
    )
    return reply_ids


def poll_active_tls_sessions(
    *,
    inject_reply,
    limit: int = 4,
    gateway_sender: str = "",
) -> List[Dict[str, Any]]:
    """Poll upstream sockets after handshake for more TLS application data."""
    from chain_mesh import ip_gateway as gw

    token = gw.gateway_sender_context(gateway_sender) if gateway_sender else None
    _purge_stale_sessions()
    cutoff = int(time.time()) - 30
    with mesh_db._conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM chain_mesh_ip_gateway_tcp_sessions
            WHERE handshake_complete = 1 AND updated_at >= ?
            ORDER BY updated_at ASC
            LIMIT ?
            """,
            (cutoff, max(1, min(int(limit), 16))),
        ).fetchall()
    results: List[Dict[str, Any]] = []
    try:
        for row in rows:
            key = str(row["session_key"])
            sock = _SOCKETS.get(key)
            if not sock:
                continue
            try:
                sock.settimeout(0.2)
                upstream = sock.recv(8192)
            except socket.timeout:
                continue
            except Exception as exc:
                _delete_session(key)
                results.append({"ok": False, "session_key": key, "error": str(exc)})
                continue
            if not upstream:
                continue
            sess = dict(row)
            reply_ids = _inject_upstream_chunks(
                key=key,
                sess=sess,
                upstream=upstream,
                inject_reply=inject_reply,
            )
            results.append(
                {
                    "ok": True,
                    "action": "tcp_tls_app_poll",
                    "session_key": key,
                    "bytes_down": len(upstream),
                    "reply_packets": len(reply_ids),
                }
            )
    finally:
        if token is not None:
            gw.reset_gateway_sender(token)
    return results