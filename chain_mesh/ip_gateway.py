"""BSM4 mesh internet gateway — egress IPv4 frames to the real internet."""

from __future__ import annotations

import base64
import os
import socket
from contextvars import ContextVar
import ssl
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Set, Tuple

from chain_mesh import db as mesh_db
from chain_mesh import ip_tunnel_protocol as ip4
from chain_mesh import ip_tunnel_tls as tls
from chain_mesh import packets as mesh_packets

GATEWAY_RECIPIENT = os.environ.get("BSM4_GATEWAY_RECIPIENT", "mesh-gateway").strip()
_gateway_sender_var: ContextVar[str] = ContextVar("bsm4_gateway_sender", default=GATEWAY_RECIPIENT)


def current_gateway_sender() -> str:
    return _gateway_sender_var.get() or GATEWAY_RECIPIENT


def gateway_sender_context(sender: str):
    """Context manager / token for peer household gateway egress."""
    return _gateway_sender_var.set(sender or GATEWAY_RECIPIENT)


def reset_gateway_sender(token) -> None:
    _gateway_sender_var.reset(token)
GATEWAY_VIRTUAL_IP = os.environ.get("BSM4_GATEWAY_VIRTUAL_IP", "10.73.0.1").strip()
GATEWAY_DNS_UPSTREAM = os.environ.get("BSM4_GATEWAY_DNS", "8.8.8.8").strip()
GATEWAY_ENABLED = os.environ.get("BSM4_GATEWAY_ENABLED", "1") == "1"
EGRESS_BATCH = int(os.environ.get("BSM4_GATEWAY_BATCH", "16"))
EGRESS_INTERVAL_SEC = float(os.environ.get("BSM4_GATEWAY_INTERVAL_SEC", "4"))
GATEWAY_HTTP_PORTS = tuple(
    int(p.strip())
    for p in os.environ.get("BSM4_GATEWAY_HTTP_PORTS", "80,8080").split(",")
    if p.strip().isdigit()
) or (80,)
GATEWAY_HTTPS_PORTS = tuple(
    int(p.strip())
    for p in os.environ.get("BSM4_GATEWAY_HTTPS_PORTS", "443,8443,18443").split(",")
    if p.strip().isdigit()
) or (443,)
GATEWAY_WEB_PORTS: Set[int] = set(GATEWAY_HTTP_PORTS) | set(GATEWAY_HTTPS_PORTS)
MAX_HTTP_RESPONSE_BYTES = int(os.environ.get("BSM4_GATEWAY_HTTP_MAX_BYTES", "1200"))
HTTP_FETCH_TIMEOUT = float(os.environ.get("BSM4_GATEWAY_HTTP_TIMEOUT", "8"))
TLS_VERIFY = os.environ.get("BSM4_GATEWAY_TLS_VERIFY", "1") == "1"


def _init_gateway_tables() -> None:
    with mesh_db._conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chain_mesh_ip_gateway_processed (
                packet_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_mesh_ip_gw_processed_at
                ON chain_mesh_ip_gateway_processed(created_at DESC);
            """
        )


_init_gateway_tables()


def gateway_status_payload() -> Dict[str, Any]:
    with mesh_db._conn() as conn:
        processed = conn.execute(
            "SELECT COUNT(*) AS n FROM chain_mesh_ip_gateway_processed"
        ).fetchone()
        pending = conn.execute(
            """
            SELECT COUNT(*) AS n FROM chain_mesh_packets p
            WHERE p.recipient = ?
              AND p.payload_type IN ('ipv4', 'ip')
              AND NOT EXISTS (
                SELECT 1 FROM chain_mesh_ip_gateway_processed g
                WHERE g.packet_id = p.packet_id
              )
            """,
            (GATEWAY_RECIPIENT,),
        ).fetchone()
    return {
        "ok": True,
        "enabled": GATEWAY_ENABLED,
        "recipient": GATEWAY_RECIPIENT,
        "virtual_ip": GATEWAY_VIRTUAL_IP,
        "dns_upstream": GATEWAY_DNS_UPSTREAM,
        "supported_egress": [
            "icmp_echo",
            "udp_dns",
            "tcp_http",
            "tcp_https",
            "tcp_tls_passthrough",
            "tcp_tls_continue",
        ],
        "http_ports": list(GATEWAY_HTTP_PORTS),
        "https_ports": list(GATEWAY_HTTPS_PORTS),
        "tls_verify": TLS_VERIFY,
        "processed_count": int(processed["n"] if processed else 0),
        "pending_count": int(pending["n"] if pending else 0),
        "interval_sec": EGRESS_INTERVAL_SEC,
    }


def _mark_processed(packet_id: str, *, channel_id: str, action: str) -> None:
    now = int(time.time())
    with mesh_db._conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO chain_mesh_ip_gateway_processed
                (packet_id, channel_id, action, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (packet_id, channel_id, action, now),
        )


def _pending_egress_packets(*, limit: int = EGRESS_BATCH) -> List[Dict[str, Any]]:
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
            (GATEWAY_RECIPIENT, max(1, min(64, int(limit)))),
        ).fetchall()
    return [dict(r) for r in rows]


def _icmp_ping(dst: str, *, timeout_sec: float = 2.5) -> Tuple[bool, str]:
    """Best-effort real ICMP via system ping (IP-literal only — M-01)."""
    try:
        from chain_mesh.security import validate_ip_literal

        safe_dst = validate_ip_literal(dst, private_only=False)
    except ValueError as exc:
        return False, str(exc)
    try:
        proc = subprocess.run(
            ["ping", "-c", "1", "-W", str(max(1, int(timeout_sec))), safe_dst],
            capture_output=True,
            text=True,
            timeout=timeout_sec + 1,
        )
        if proc.returncode == 0:
            return True, "ping ok"
        return False, (proc.stderr or proc.stdout or "ping failed").strip()[:200]
    except Exception as exc:
        return False, str(exc)


def _dns_relay(query: bytes, *, server: str = GATEWAY_DNS_UPSTREAM) -> Optional[bytes]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(3.0)
        sock.sendto(query, (server, 53))
        data, _ = sock.recvfrom(4096)
        return data
    except Exception:
        return None
    finally:
        sock.close()


def _parse_http_request(payload: bytes) -> Optional[Dict[str, str]]:
    if not payload:
        return None
    try:
        head = payload.split(b"\r\n\r\n", 1)[0].decode("latin-1", errors="replace")
    except Exception:
        return None
    lines = head.split("\r\n")
    if not lines:
        return None
    parts = lines[0].split(" ")
    if len(parts) < 2:
        return None
    method = parts[0].upper()
    if method not in ("GET", "HEAD", "POST"):
        return None
    path = parts[1]
    host = ""
    for line in lines[1:]:
        if line.lower().startswith("host:"):
            host = line.split(":", 1)[1].strip()
            break
    return {"method": method, "path": path or "/", "host": host}


def _build_http_response(
    body: bytes,
    *,
    status: str = "200 OK",
    content_type: str = "text/plain; charset=utf-8",
) -> bytes:
    header = (
        f"HTTP/1.1 {status}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    )
    return header.encode("ascii", errors="replace") + body


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if not TLS_VERIFY:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _web_authority(*, host: str, dst_ip: str, dst_port: int, use_tls: bool) -> str:
    authority = host or dst_ip
    default_port = 443 if use_tls else 80
    if dst_port != default_port:
        authority = f"{authority}:{dst_port}"
    return authority


def _web_fetch(
    *,
    method: str,
    host: str,
    path: str,
    dst_ip: str,
    dst_port: int,
    use_tls: bool,
) -> Tuple[bytes, str]:
    """Fetch HTTP or HTTPS upstream; return (body, content_type)."""
    # H-02: SSRF guard — block metadata/loopback; restrict ports; validate Host.
    try:
        from chain_mesh.security import validate_ip_literal, validate_url_ssrf

        safe_ip = validate_ip_literal(dst_ip, private_only=False)
        allowed = set(GATEWAY_HTTP_PORTS) | set(GATEWAY_HTTPS_PORTS) | {80, 443, 8080, 8443}
        if int(dst_port) not in allowed:
            raise ValueError(f"port {dst_port} not allowed for gateway fetch")
        # Build URL on IP, validate (blocks 169.254.169.254 etc.)
        scheme = "https" if use_tls else "http"
        probe = f"{scheme}://{safe_ip}:{int(dst_port)}{(path or '/')}"
        validate_url_ssrf(probe, mode="block_internal", allowed_ports=allowed)
        # Host header: hostname only, no credentials/path
        safe_host = (host or safe_ip).split("/")[0].split("@")[-1][:253]
    except ValueError as exc:
        raise urllib.error.URLError(str(exc)) from exc
    scheme = "https" if use_tls else "http"
    authority = _web_authority(host=safe_host, dst_ip=safe_ip, dst_port=dst_port, use_tls=use_tls)
    url = f"{scheme}://{authority}{path}"
    req = urllib.request.Request(
        url,
        method=method if method in ("GET", "HEAD") else "GET",
        headers={
            "User-Agent": "Bloodstone-BSM4-Gateway/1.0",
            "Host": safe_host or safe_ip,
            "Accept": "*/*",
        },
    )
    kwargs: Dict[str, Any] = {"timeout": HTTP_FETCH_TIMEOUT}
    if use_tls:
        kwargs["context"] = _ssl_context()
    try:
        with urllib.request.urlopen(req, **kwargs) as resp:
            content_type = resp.headers.get("Content-Type", "text/plain")
            if method == "HEAD":
                return b"", content_type
            body = resp.read(MAX_HTTP_RESPONSE_BYTES + 1)
            if len(body) > MAX_HTTP_RESPONSE_BYTES:
                body = body[:MAX_HTTP_RESPONSE_BYTES]
            return body, content_type
    except urllib.error.HTTPError as exc:
        snippet = exc.read(MAX_HTTP_RESPONSE_BYTES) if exc.fp else b""
        return snippet or str(exc).encode("utf-8", errors="replace"), "text/plain"
    except Exception as exc:
        return str(exc).encode("utf-8", errors="replace")[:MAX_HTTP_RESPONSE_BYTES], "text/plain"


def _handle_tcp_web_egress(
    *,
    raw: bytes,
    channel_id: str,
    mesh_sender: str,
    packet_id: str,
    dst: str,
    dst_port: int,
    use_tls: bool,
) -> Dict[str, Any]:
    """SYN-ACK, HTTP GET proxy, and mesh reply for cleartext or TLS upstream."""
    action = "tcp_https" if use_tls else "tcp_http"
    tcp_info = ip4.extract_tcp_from_ipv4(raw)
    flags = int(tcp_info.get("flags") or 0)
    tcp_payload = tcp_info.get("tcp_payload") or b""

    if (flags & ip4.TCP_FLAG_SYN) and not (flags & ip4.TCP_FLAG_ACK):
        reply_ip = ip4.build_tcp_reply_datagram(
            raw,
            flags=ip4.TCP_FLAG_SYN | ip4.TCP_FLAG_ACK,
            seq=int(time.time()) & 0xFFFFFFFF,
        )
        inject = _inject_reply(
            channel_id=channel_id,
            sender=current_gateway_sender(),
            recipient=mesh_sender,
            ip_packet=reply_ip,
        )
        _mark_processed(packet_id, channel_id=channel_id, action="tcp_syn_ack")
        return {
            "ok": True,
            "packet_id": packet_id,
            "action": "tcp_syn_ack",
            "dst": dst,
            "dst_port": dst_port,
            "tls": use_tls,
            "reply_packet_id": (inject.get("packet") or {}).get("packet_id"),
        }

    http_req = _parse_http_request(tcp_payload)
    if not http_req:
        _mark_processed(packet_id, channel_id=channel_id, action="tcp_no_http")
        return {
            "ok": False,
            "packet_id": packet_id,
            "action": action,
            "error": "TCP port open but payload is not HTTP GET/HEAD",
        }

    body, content_type = _web_fetch(
        method=http_req["method"],
        host=http_req["host"],
        path=http_req["path"],
        dst_ip=dst,
        dst_port=dst_port,
        use_tls=use_tls,
    )
    http_resp = _build_http_response(
        body,
        content_type=content_type.split(";")[0].strip(),
    )
    reply_ip = _fit_tcp_reply(raw, ip4.TCP_FLAG_PSH | ip4.TCP_FLAG_ACK, http_resp)
    inject = _inject_reply(
        channel_id=channel_id,
        sender=current_gateway_sender(),
        recipient=mesh_sender,
        ip_packet=reply_ip,
    )
    _mark_processed(packet_id, channel_id=channel_id, action=action)
    return {
        "ok": True,
        "packet_id": packet_id,
        "action": action,
        "dst": dst,
        "dst_port": dst_port,
        "tls": use_tls,
        "host": http_req.get("host") or dst,
        "path": http_req.get("path"),
        "bytes": len(body),
        "reply_packet_id": (inject.get("packet") or {}).get("packet_id"),
    }


def _fit_tcp_reply(request_ip: bytes, flags: int, payload: bytes) -> bytes:
    """Ensure reply IPv4 datagram fits BSM4 MTU."""
    max_payload = ip4.MAX_IPV4_DATAGRAM - ip4.MIN_IPV4_HEADER - 20
    if len(payload) > max_payload:
        payload = payload[:max_payload]
    return ip4.build_tcp_reply_datagram(request_ip, flags=flags, payload=payload)


def _inject_reply(
    *,
    channel_id: str,
    sender: str,
    recipient: str,
    ip_packet: bytes,
) -> Dict[str, Any]:
    return mesh_packets.send_packet_payload(
        {
            "channel_id": channel_id,
            "sender": sender,
            "recipient": recipient,
            "payload_type": "ipv4",
            "payload_b64": base64.b64encode(ip_packet).decode("ascii"),
        }
    )


def process_ipv4_egress(
    row: Dict[str, Any],
) -> Dict[str, Any]:
    """Handle one mesh IPv4 frame destined for the internet gateway."""
    packet_id = str(row.get("packet_id") or "")
    channel_id = str(row.get("channel_id") or "")
    mesh_sender = str(row.get("sender") or "")
    b64 = str(row.get("payload_b64") or "")

    try:
        raw = base64.b64decode(b64)
        parsed = ip4.validate_ipv4_datagram(raw, verify_checksum=False)
    except Exception as exc:
        _mark_processed(packet_id, channel_id=channel_id, action=f"skip:{exc}")
        return {"ok": False, "packet_id": packet_id, "error": str(exc)}

    proto = parsed.get("protocol")
    dst = parsed.get("dst") or ""
    action = "unknown"

    try:
        if proto == ip4.PROTO_ICMP and parsed.get("icmp_type") == 8:
            action = "icmp_echo"
            ihl = int(parsed.get("ihl") or 20)
            icmp_req = raw[ihl : int(parsed["total_length"])]
            ok, detail = _icmp_ping(dst)
            if not ok:
                _mark_processed(packet_id, channel_id=channel_id, action=f"icmp_fail")
                return {
                    "ok": False,
                    "packet_id": packet_id,
                    "action": action,
                    "error": detail,
                }
            icmp_reply = ip4.build_icmp_echo_reply(icmp_req)
            reply_ip = ip4.build_icmp_reply_datagram(raw, icmp_body=icmp_reply)
            inject = _inject_reply(
                channel_id=channel_id,
                sender=current_gateway_sender(),
                recipient=mesh_sender,
                ip_packet=reply_ip,
            )
            _mark_processed(packet_id, channel_id=channel_id, action=action)
            return {
                "ok": True,
                "packet_id": packet_id,
                "action": action,
                "dst": dst,
                "reply_packet_id": (inject.get("packet") or {}).get("packet_id"),
                "detail": detail,
            }

        if proto == ip4.PROTO_UDP and parsed.get("dst_port") == 53:
            action = "udp_dns"
            ihl = int(parsed.get("ihl") or 20)
            transport = raw[ihl : int(parsed["total_length"])]
            if len(transport) < 8:
                raise ValueError("UDP header too short")
            query = transport[8:]
            answer = _dns_relay(query)
            if not answer:
                _mark_processed(packet_id, channel_id=channel_id, action="dns_fail")
                return {
                    "ok": False,
                    "packet_id": packet_id,
                    "action": action,
                    "error": "DNS upstream timeout",
                }
            src_port = int(parsed.get("src_port") or 0)
            reply_ip = ip4.build_udp_datagram(
                src_ip=dst,
                dst_ip=parsed["src"],
                src_port=53,
                dst_port=src_port,
                payload=answer,
            )
            inject = _inject_reply(
                channel_id=channel_id,
                sender=current_gateway_sender(),
                recipient=mesh_sender,
                ip_packet=reply_ip,
            )
            _mark_processed(packet_id, channel_id=channel_id, action=action)
            return {
                "ok": True,
                "packet_id": packet_id,
                "action": action,
                "dst": dst,
                "reply_packet_id": (inject.get("packet") or {}).get("packet_id"),
            }

        if proto == ip4.PROTO_TCP:
            tcp_info = ip4.extract_tcp_from_ipv4(raw)
            dst_port = int(tcp_info.get("dst_port") or 0)
            tcp_payload = tcp_info.get("tcp_payload") or b""
            flags = int(tcp_info.get("flags") or 0)
            if dst_port in GATEWAY_WEB_PORTS:
                use_tls = dst_port in GATEWAY_HTTPS_PORTS
                if use_tls and (
                    tls.is_tls_record(tcp_payload)
                    or (
                        (flags & ip4.TCP_FLAG_SYN)
                        and not (flags & ip4.TCP_FLAG_ACK)
                        and not tcp_payload
                    )
                    or (flags & ip4.TCP_FLAG_FIN)
                ):
                    from chain_mesh import ip_gateway_tcp as gw_tcp

                    return gw_tcp.handle_tcp_tls_passthrough(
                        raw=raw,
                        channel_id=channel_id,
                        mesh_sender=mesh_sender,
                        packet_id=packet_id,
                        dst=dst,
                        dst_port=dst_port,
                        mark_processed=_mark_processed,
                        inject_reply=_inject_reply,
                        fit_tcp_reply=_fit_tcp_reply,
                    )
                return _handle_tcp_web_egress(
                    raw=raw,
                    channel_id=channel_id,
                    mesh_sender=mesh_sender,
                    packet_id=packet_id,
                    dst=dst,
                    dst_port=dst_port,
                    use_tls=use_tls,
                )

        _mark_processed(packet_id, channel_id=channel_id, action="unsupported")
        return {
            "ok": False,
            "packet_id": packet_id,
            "action": "unsupported",
            "protocol": parsed.get("protocol_name"),
            "error": "egress protocol not supported yet",
        }
    except Exception as exc:
        _mark_processed(packet_id, channel_id=channel_id, action=f"error")
        return {"ok": False, "packet_id": packet_id, "action": action, "error": str(exc)}


def run_egress_batch(*, limit: int = EGRESS_BATCH) -> Dict[str, Any]:
    """Process pending gateway egress packets (admin trigger or background loop)."""
    if not GATEWAY_ENABLED:
        return {"ok": False, "error": "gateway disabled", **gateway_status_payload()}

    rows = _pending_egress_packets(limit=limit)
    results: List[Dict[str, Any]] = []
    ok_count = 0
    for row in rows:
        result = process_ipv4_egress(row)
        results.append(result)
        if result.get("ok"):
            ok_count += 1

    from chain_mesh import ip_gateway_tcp as gw_tcp

    poll_results = gw_tcp.poll_active_tls_sessions(
        inject_reply=_inject_reply,
        limit=max(2, limit // 2),
    )

    return {
        "ok": True,
        "processed": len(results),
        "success": ok_count,
        "results": results,
        "tls_poll": poll_results,
        "status": gateway_status_payload(),
    }