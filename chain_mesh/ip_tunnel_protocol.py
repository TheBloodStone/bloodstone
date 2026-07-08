"""
BSM4 — Bloodstone Mesh IP Tunnel Protocol v1

Raw IPv4 datagram encapsulation over BSM3 mesh packet channels.

BSM3 carries framed payloads; BSM4 defines payload_type=ipv4 as a complete
IPv4 packet (header + payload) suitable for userspace tunnel endpoints.

Browsers cannot open raw sockets; BSM4 endpoints run in JavaScript or on Android
nodes, reassembling virtual LAN traffic from mesh-delivered IP frames.
"""

from __future__ import annotations

import hashlib
import struct
from typing import Any, Dict, Optional, Tuple

TUNNEL_PROTOCOL = "bsm4-ip-tunnel-v1"
TUNNEL_MAGIC = b"BSM4"
TUNNEL_ANCHOR_BYTES = 44

MAX_IPV4_DATAGRAM = 1400
MIN_IPV4_HEADER = 20
IPV4_VERSION = 4

PROTO_ICMP = 1
PROTO_TCP = 6
PROTO_UDP = 17


def ipv4_checksum(header: bytes) -> int:
    """RFC 791 header checksum."""
    if len(header) < 20:
        return 0
    total = 0
    i = 0
    while i < len(header):
        if i == 10:
            i += 2
            continue
        word = (header[i] << 8) + header[i + 1]
        total += word
        i += 2
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def validate_ipv4_datagram(data: bytes, *, verify_checksum: bool = True) -> Dict[str, Any]:
    """Parse and validate a raw IPv4 packet."""
    if not data or len(data) < MIN_IPV4_HEADER:
        raise ValueError("IPv4 datagram too short")
    if len(data) > MAX_IPV4_DATAGRAM:
        raise ValueError(f"IPv4 datagram exceeds {MAX_IPV4_DATAGRAM} bytes")

    version_ihl = data[0]
    version = version_ihl >> 4
    ihl = (version_ihl & 0x0F) * 4
    if version != IPV4_VERSION:
        raise ValueError(f"not IPv4 (version={version})")
    if ihl < MIN_IPV4_HEADER or ihl > len(data):
        raise ValueError("invalid IPv4 IHL")

    total_length = struct.unpack("!H", data[2:4])[0]
    if total_length < ihl or total_length > len(data):
        raise ValueError("invalid IPv4 total length")

    packet = data[:total_length]
    proto = packet[9]
    src = ".".join(str(b) for b in packet[12:16])
    dst = ".".join(str(b) for b in packet[16:20])

    if verify_checksum:
        expected = ipv4_checksum(packet[:ihl])
        actual = struct.unpack("!H", packet[10:12])[0]
        if expected != actual:
            raise ValueError("IPv4 header checksum mismatch")

    result: Dict[str, Any] = {
        "version": version,
        "ihl": ihl,
        "total_length": total_length,
        "protocol": proto,
        "protocol_name": {PROTO_ICMP: "icmp", PROTO_TCP: "tcp", PROTO_UDP: "udp"}.get(
            proto, f"ipproto-{proto}"
        ),
        "src": src,
        "dst": dst,
        "ttl": packet[8],
        "identification": struct.unpack("!H", packet[4:6])[0],
    }

    transport = packet[ihl:total_length]
    if proto == PROTO_TCP and len(transport) >= 20:
        result["src_port"] = struct.unpack("!H", transport[0:2])[0]
        result["dst_port"] = struct.unpack("!H", transport[2:4])[0]
        result["tcp_flags"] = transport[13]
    elif proto == PROTO_UDP and len(transport) >= 8:
        result["src_port"] = struct.unpack("!H", transport[0:2])[0]
        result["dst_port"] = struct.unpack("!H", transport[2:4])[0]
    elif proto == PROTO_ICMP and len(transport) >= 8:
        result["icmp_type"] = transport[0]
        result["icmp_code"] = transport[1]

    return result


def build_tunnel_anchor_payload(
    *,
    channel_id: str,
    tunnel_id: str,
    virtual_subnet: str = "10.73.0.0",
) -> bytes:
    """44-byte BSM4 OP_RETURN: magic + channel prefix + tunnel_id prefix + subnet hint."""
    cid = (channel_id or "").strip().lower()
    tid = (tunnel_id or "").strip().lower()
    if len(cid) != 64 or len(tid) != 64:
        raise ValueError("channel_id and tunnel_id must be 64 hex chars")
    subnet_digest = hashlib.sha256(virtual_subnet.encode("utf-8")).digest()[:8]
    return (
        TUNNEL_MAGIC
        + bytes.fromhex(cid[:32])
        + bytes.fromhex(tid[:16])
        + subnet_digest
    )


def tunnel_id_for(*, channel_id: str, virtual_ip: str) -> str:
    raw = f"{channel_id.lower()}|{virtual_ip.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def work_digest(
    *,
    channel_id: str,
    packet_id: str,
    job_id: str,
    nonce_hex: str,
) -> str:
    """BSM4 reuses BSM3 attestation binding (IP frame rides in BSM3 packet)."""
    parts = [
        TUNNEL_MAGIC.decode("ascii"),
        (channel_id or "").strip().lower(),
        (packet_id or "").strip().lower(),
        str(job_id or ""),
        str(nonce_hex or "").strip().lower(),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _pack_ipv4(addr: str) -> bytes:
    return bytes(int(o) & 0xFF for o in str(addr).split("."))


def build_ipv4_header(
    *,
    src: str,
    dst: str,
    protocol: int,
    payload: bytes,
    identification: int = 0,
    ttl: int = 64,
    flags_frag: int = 0,
) -> bytes:
    """Build a 20-byte IPv4 header + payload with correct checksum."""
    total_len = MIN_IPV4_HEADER + len(payload)
    header = bytearray(MIN_IPV4_HEADER)
    header[0] = 0x45
    header[2:4] = struct.pack("!H", total_len)
    header[4:6] = struct.pack("!H", identification & 0xFFFF)
    header[6:8] = struct.pack("!H", flags_frag & 0xFFFF)
    header[8] = ttl & 0xFF
    header[9] = protocol & 0xFF
    header[12:16] = _pack_ipv4(src)
    header[16:20] = _pack_ipv4(dst)
    csum = ipv4_checksum(bytes(header))
    header[10:12] = struct.pack("!H", csum)
    return bytes(header) + payload


def _icmp_checksum(data: bytes) -> int:
    total = 0
    i = 0
    while i < len(data):
        if i + 1 < len(data):
            word = (data[i] << 8) + data[i + 1]
        else:
            word = data[i] << 8
        total += word
        i += 2
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def build_icmp_echo_reply(request_icmp: bytes, *, extra_data: bytes = b"") -> bytes:
    """ICMP type 0 echo reply preserving id/seq from type 8 request."""
    if len(request_icmp) < 8:
        raise ValueError("ICMP echo request too short")
    body = bytearray(request_icmp)
    body[0] = 0  # echo reply
    body[1] = 0  # code
    body[2] = 0
    body[3] = 0
    if extra_data:
        body = bytearray(body[:8]) + bytearray(extra_data)
    csum = _icmp_checksum(bytes(body))
    body[2] = (csum >> 8) & 0xFF
    body[3] = csum & 0xFF
    return bytes(body)


def build_udp_datagram(
    *,
    src_ip: str,
    dst_ip: str,
    src_port: int,
    dst_port: int,
    payload: bytes,
) -> bytes:
    udp_len = 8 + len(payload)
    udp = bytearray(udp_len)
    udp[0:2] = struct.pack("!H", src_port & 0xFFFF)
    udp[2:4] = struct.pack("!H", dst_port & 0xFFFF)
    udp[4:6] = struct.pack("!H", udp_len)
    udp[6:8] = b"\x00\x00"
    udp[8:] = payload
    return build_ipv4_header(src=src_ip, dst=dst_ip, protocol=PROTO_UDP, payload=bytes(udp))


def build_icmp_reply_datagram(request_ip: bytes, *, icmp_body: bytes) -> bytes:
    """Swap src/dst and embed ICMP reply payload."""
    parsed = validate_ipv4_datagram(request_ip, verify_checksum=False)
    return build_ipv4_header(
        src=parsed["dst"],
        dst=parsed["src"],
        protocol=PROTO_ICMP,
        payload=icmp_body,
        identification=parsed.get("identification") or 0,
    )


TCP_FLAG_FIN = 0x01
TCP_FLAG_SYN = 0x02
TCP_FLAG_RST = 0x04
TCP_FLAG_PSH = 0x08
TCP_FLAG_ACK = 0x10


def _tcp_checksum(src_ip: str, dst_ip: str, tcp_segment: bytes) -> int:
    pseudo = (
        _pack_ipv4(src_ip)
        + _pack_ipv4(dst_ip)
        + struct.pack("!BBH", 0, PROTO_TCP, len(tcp_segment))
    )
    data = pseudo + tcp_segment
    if len(data) % 2:
        data += b"\x00"
    total = 0
    for i in range(0, len(data), 2):
        total += (data[i] << 8) + data[i + 1]
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def build_tcp_segment(
    *,
    src_ip: str,
    dst_ip: str,
    src_port: int,
    dst_port: int,
    seq: int,
    ack: int,
    flags: int,
    payload: bytes = b"",
    window: int = 8192,
) -> bytes:
    """Build IPv4 datagram with 20-byte TCP header (no options)."""
    tcp_len = 20 + len(payload)
    tcp = bytearray(tcp_len)
    tcp[0:2] = struct.pack("!H", src_port & 0xFFFF)
    tcp[2:4] = struct.pack("!H", dst_port & 0xFFFF)
    tcp[4:8] = struct.pack("!I", seq & 0xFFFFFFFF)
    tcp[8:12] = struct.pack("!I", ack & 0xFFFFFFFF)
    tcp[12] = (5 << 4) & 0xFF
    tcp[13] = flags & 0xFF
    tcp[14:16] = struct.pack("!H", window & 0xFFFF)
    csum = _tcp_checksum(src_ip, dst_ip, bytes(tcp))
    tcp[16:18] = struct.pack("!H", csum)
    tcp[20:] = payload
    return build_ipv4_header(
        src=src_ip,
        dst=dst_ip,
        protocol=PROTO_TCP,
        payload=bytes(tcp),
    )


def extract_tcp_from_ipv4(raw_ip: bytes) -> Dict[str, Any]:
    """Parse IPv4 + minimal TCP header fields."""
    parsed = validate_ipv4_datagram(raw_ip, verify_checksum=False)
    if parsed.get("protocol") != PROTO_TCP:
        raise ValueError("not TCP")
    ihl = int(parsed.get("ihl") or 20)
    total = int(parsed["total_length"])
    transport = raw_ip[ihl:total]
    if len(transport) < 20:
        raise ValueError("TCP header too short")
    data_offset = (transport[12] >> 4) * 4
    if data_offset < 20 or data_offset > len(transport):
        raise ValueError("invalid TCP data offset")
    return {
        **parsed,
        "src_port": struct.unpack("!H", transport[0:2])[0],
        "dst_port": struct.unpack("!H", transport[2:4])[0],
        "seq": struct.unpack("!I", transport[4:8])[0],
        "ack": struct.unpack("!I", transport[8:12])[0],
        "flags": transport[13],
        "tcp_header_len": data_offset,
        "tcp_payload": transport[data_offset:],
    }


def build_tcp_reply_datagram(
    request_ip: bytes,
    *,
    flags: int,
    payload: bytes = b"",
    seq: Optional[int] = None,
    ack: Optional[int] = None,
) -> bytes:
    """Swap endpoints and build a TCP reply segment."""
    tcp = extract_tcp_from_ipv4(request_ip)
    req_seq = int(tcp["seq"])
    req_ack = int(tcp["ack"])
    req_flags = int(tcp["flags"])
    req_payload = tcp.get("tcp_payload") or b""
    reply_seq = seq if seq is not None else (req_ack if req_ack else 1)
    if ack is None:
        ack = req_seq + len(req_payload)
        if req_flags & TCP_FLAG_SYN:
            ack += 1
    return build_tcp_segment(
        src_ip=tcp["dst"],
        dst_ip=tcp["src"],
        src_port=int(tcp["dst_port"]),
        dst_port=int(tcp["src_port"]),
        seq=reply_seq,
        ack=ack,
        flags=flags,
        payload=payload,
    )