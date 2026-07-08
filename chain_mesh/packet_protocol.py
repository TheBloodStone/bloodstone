"""
BSM3 — Bloodstone Mesh Packet Protocol v1

Send small datagrams over the Bloodstone mesh with miner hash-power attestation,
like a lightweight virtual LAN link rendered in the browser.

Layers
------
1. **Channel (off-chain)** — sender + recipient (STONE address or device_id)
2. **Packets (off-chain)** — small framed payloads (≤ 1400 B), sequenced per channel
3. **Attestation (mining)** — miners bind accepted share work to packets they relay

Mining does not embed packet bytes in stratum shares. After a pool accepts a share:

  work_digest = SHA256("BSM3" || channel_id || packet_id || job_id || nonce_hex)

Browsers poll the coordinator inbox and decode payloads as text, JSON, or hex.
LAN chunk peers (:18341) can mirror hot packets for household recovery.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from typing import Any, Dict, List, Optional

PACKET_PROTOCOL = "bsm3-packet-v1"
PACKET_MAGIC = b"BSM3"
PACKET_ANCHOR_BYTES = 40

MAX_PACKET_BYTES = 1400
MAX_CHANNEL_PACKETS = 10_000
DEFAULT_TTL_SEC = 3600

CHANNEL_STATUS_OPEN = "open"
CHANNEL_STATUS_CLOSED = "closed"

# Network chat — shared lobby + canonical DM channels (BSM3 labels).
NETWORK_CHAT_LOBBY_ID = "bloodstone-network-chat"
NETWORK_CHAT_ROOM_LABEL = "network-chat-room"
NETWORK_CHAT_DM_LABEL = "network-chat-dm"


def is_room_channel_label(label: str) -> bool:
    return (label or "").strip() == NETWORK_CHAT_ROOM_LABEL


def lobby_channel_id() -> str:
    return channel_id_for(
        sender=NETWORK_CHAT_LOBBY_ID,
        recipient=NETWORK_CHAT_LOBBY_ID,
        label=NETWORK_CHAT_ROOM_LABEL,
        nonce="lobby",
    )


def dm_channel_id(user_a: str, user_b: str) -> str:
    a, b = sorted([(user_a or "").strip(), (user_b or "").strip()])
    if not a or not b:
        raise ValueError("both participants required for DM channel")
    return channel_id_for(sender=a, recipient=b, label=NETWORK_CHAT_DM_LABEL, nonce="dm")


def channel_id_for(
    *,
    sender: str,
    recipient: str,
    label: str = "",
    nonce: Optional[str] = None,
) -> str:
    raw = "|".join(
        [
            (sender or "").strip(),
            (recipient or "").strip(),
            (label or "").strip(),
            nonce or secrets.token_hex(8),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def packet_id_for(*, channel_id: str, seq: int, payload_sha256: str) -> str:
    raw = f"{(channel_id or '').lower()}|{int(seq)}|{(payload_sha256 or '').lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def payload_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def build_packet_anchor_payload(
    *,
    channel_id: str,
    recipient_address: str,
    seq: int = 0,
) -> bytes:
    """52-byte BSM3 OP_RETURN: magic + channel prefix + recipient prefix + seq."""
    cid = (channel_id or "").strip().lower()
    if len(cid) != 64:
        raise ValueError("channel_id must be 64 hex chars")
    recip = hashlib.sha256((recipient_address or "").encode("utf-8")).digest()[:16]
    seq_bytes = int(seq).to_bytes(4, "big")
    return PACKET_MAGIC + bytes.fromhex(cid[:32]) + recip + seq_bytes


def work_digest(
    *,
    channel_id: str,
    packet_id: str,
    job_id: str,
    nonce_hex: str,
) -> str:
    parts = [
        PACKET_MAGIC.decode("ascii"),
        (channel_id or "").strip().lower(),
        (packet_id or "").strip().lower(),
        str(job_id or ""),
        str(nonce_hex or "").strip().lower(),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def packet_assignment_bucket(channel_id: str, node_id: str, packet_id: str) -> int:
    raw = f"{(channel_id or '').lower()}:{(node_id or '').lower()}:{(packet_id or '').lower()}"
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8], 16) % 100


def node_should_relay_packet(
    channel_id: str,
    node_id: str,
    packet_id: str,
    *,
    backup_pct: int = 10,
) -> bool:
    pct = max(1, min(100, int(backup_pct)))
    return packet_assignment_bucket(channel_id, node_id, packet_id) < pct


def build_packet_frame(
    *,
    channel_id: str,
    packet_id: str,
    seq: int,
    sender: str,
    recipient: str,
    payload_type: str,
    payload_size: int,
    payload_sha256_hex: str,
    created_at: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "protocol": PACKET_PROTOCOL,
        "channel_id": channel_id,
        "packet_id": packet_id,
        "seq": int(seq),
        "sender": sender,
        "recipient": recipient,
        "payload_type": payload_type,
        "payload_size": int(payload_size),
        "payload_sha256": payload_sha256_hex,
        "created_at": created_at or int(time.time()),
    }