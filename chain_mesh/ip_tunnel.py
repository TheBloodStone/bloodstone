"""BSM4 IP tunnel service — raw IPv4 over BSM3 mesh packets."""

from __future__ import annotations

import base64
import time
from typing import Any, Dict, List, Optional

from chain_mesh import ip_tunnel_protocol as ip4
from chain_mesh import packets as mesh_packets


def protocol_payload() -> Dict[str, Any]:
    from chain_mesh import ip_gateway as gw

    bsm3 = mesh_packets.protocol_payload()
    gw_status = gw.gateway_status_payload()
    return {
        "ok": True,
        "protocol": ip4.TUNNEL_PROTOCOL,
        "magic": "BSM4",
        "max_ipv4_datagram": ip4.MAX_IPV4_DATAGRAM,
        "payload_type": "ipv4",
        "description": (
            "BSM4 encapsulates raw IPv4 datagrams inside BSM3 packets "
            "(payload_type=ipv4). Mining attestation uses the parent BSM3 packet_id."
        ),
        "bsm3": {
            "channels": bsm3.get("channels"),
            "packets": bsm3.get("packets"),
            "attestations": bsm3.get("attestations"),
        },
        "supported_protocols": ["icmp", "tcp", "udp"],
        "virtual_subnet_default": "10.73.0.0/16",
        "gateway": {
            "recipient": gw_status.get("recipient"),
            "virtual_ip": gw_status.get("virtual_ip"),
            "enabled": gw_status.get("enabled"),
            "supported_egress": gw_status.get("supported_egress"),
            "pending_count": gw_status.get("pending_count"),
        },
    }


def send_ip_datagram_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Encapsulate raw IPv4 bytes in a BSM3 packet."""
    channel_id = str(payload.get("channel_id") or "").strip().lower()
    sender = str(payload.get("sender") or "").strip()
    recipient = str(payload.get("recipient") or "").strip()
    ip_b64 = str(payload.get("ip_packet_b64") or payload.get("ipv4_b64") or "").strip()
    verify = bool(payload.get("verify_checksum", True))

    if len(channel_id) != 64:
        raise ValueError("channel_id required (64 hex chars)")
    if not ip_b64:
        raise ValueError("ip_packet_b64 required")

    try:
        raw = base64.b64decode(ip_b64, validate=True)
    except Exception as exc:
        raise ValueError(f"invalid ip_packet_b64: {exc}") from exc

    parsed = ip4.validate_ipv4_datagram(raw, verify_checksum=verify)

    result = mesh_packets.send_packet_payload(
        {
            "channel_id": channel_id,
            "sender": sender,
            "recipient": recipient,
            "payload_type": "ipv4",
            "payload_b64": base64.b64encode(raw).decode("ascii"),
        }
    )

    pkt = result.get("packet") or {}
    return {
        "ok": True,
        "protocol": ip4.TUNNEL_PROTOCOL,
        "packet": pkt,
        "ipv4": parsed,
        "tunnel": {
            "channel_id": channel_id,
            "packet_id": pkt.get("packet_id"),
            "seq": pkt.get("seq"),
        },
    }


def decode_inbox_ip_packets(inbox: Dict[str, Any]) -> Dict[str, Any]:
    """Annotate BSM3 inbox packets that carry IPv4 frames."""
    decoded: List[Dict[str, Any]] = []
    for pkt in inbox.get("packets") or []:
        row = dict(pkt)
        if row.get("payload_type") != "ipv4" and row.get("payload_type") != "ip":
            decoded.append(row)
            continue
        b64 = row.get("payload_b64") or ""
        try:
            raw = base64.b64decode(b64)
            row["ipv4"] = ip4.validate_ipv4_datagram(raw, verify_checksum=False)
            row["ip_packet_hex"] = raw.hex()
        except Exception as exc:
            row["ipv4_error"] = str(exc)
        decoded.append(row)
    return {
        **inbox,
        "packets": decoded,
        "ipv4_count": sum(1 for p in decoded if p.get("ipv4")),
    }


def open_tunnel_channel_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Open BSM3 channel with BSM4 tunnel metadata."""
    virtual_subnet = str(payload.get("virtual_subnet") or "10.73.0.0/16").strip()
    label = str(payload.get("label") or "bsm4-tunnel").strip()
    body = {**payload, "label": label, "anchor": bool(payload.get("anchor", False))}
    ch = mesh_packets.open_channel_payload(body)
    tunnel_id = ip4.tunnel_id_for(
        channel_id=ch["channel_id"],
        virtual_ip=str(payload.get("virtual_ip") or virtual_subnet),
    )
    ch["tunnel_id"] = tunnel_id
    ch["protocol"] = ip4.TUNNEL_PROTOCOL
    ch["virtual_subnet"] = virtual_subnet
    return ch