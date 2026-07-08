"""
BSM2 — Bloodstone Mesh Transfer Protocol v1

Send files over the Bloodstone mesh with an on-chain commitment (BSM2 OP_RETURN)
and miner hash-power attestation for chunk relay.

Layers
------
1. **Commitment (on-chain)** — BSM2 anchor: transfer_id + merkle_root + recipient
2. **Payload (off-chain mesh)** — 256 KiB chunks stored by miners/nodes (assignment)
3. **Attestation (mining)** — miners bind recent share work to chunks they relay

Flow
----
  SENDER                          MINERS / MESH                    RECIPIENT
    | chunk file + manifest           |                               |
    |------------------------------->| store assigned chunks         |
    | BSM2 anchor tx (OP_RETURN)      |                               |
    |---------------- chain --------->| index anchor                  |
    |                                 | attest share + chunk_hash     |
    |                                 |------------------------------>|
    |                                 |         fetch manifest+chunks |
    |                                 |         verify merkle + ACK   |

Mining hash-power role
----------------------
Miners do not embed transfer data in stratum shares (that would break pools).
Instead, after a valid share is accepted, the miner client may POST an
attestation:

  work_digest = SHA256("BSM2" || transfer_id || chunk_hash || job_id || nonce_hex)

The coordinator records attested bytes and boosts replication priority for
active transfers. Chunk assignment for transfers uses:

  bucket = SHA256(transfer_id || node_id || chunk_hash) mod 100 < backup_pct

This ties mesh relay work to the same devices that are already mining.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from typing import Any, Dict, List, Optional

TRANSFER_PROTOCOL = "bsm2-transfer-v1"
TRANSFER_MAGIC = b"BSM2"
TRANSFER_ANCHOR_BYTES = 68

TRANSFER_STATUS_DRAFT = "draft"
TRANSFER_STATUS_ANCHORING = "anchoring"
TRANSFER_STATUS_REPLICATING = "replicating"
TRANSFER_STATUS_READY = "ready"
TRANSFER_STATUS_CLAIMED = "claimed"
TRANSFER_STATUS_EXPIRED = "expired"
TRANSFER_STATUS_FAILED = "failed"

ACTIVE_STATUSES = (
    TRANSFER_STATUS_ANCHORING,
    TRANSFER_STATUS_REPLICATING,
    TRANSFER_STATUS_READY,
)


def transfer_id_for(
    *,
    sender: str,
    recipient: str,
    file_sha256: str,
    nonce: Optional[str] = None,
) -> str:
    """Deterministic 32-byte hex transfer id (unless nonce overrides)."""
    if nonce:
        raw = f"{sender}|{recipient}|{file_sha256}|{nonce}"
    else:
        raw = f"{sender}|{recipient}|{file_sha256}|{secrets.token_hex(8)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def transfer_asset_key(transfer_id: str, filename: str = "payload") -> str:
    tid = (transfer_id or "").strip().lower()
    if len(tid) != 64:
        raise ValueError("transfer_id must be 64 hex chars")
    name = (filename or "payload").strip().replace("..", "").lstrip("/")
    if not name:
        name = "payload"
    return f"transfers/{tid[:16]}/{name}"


def recipient_prefix(recipient_address: str) -> bytes:
    digest = hashlib.sha256((recipient_address or "").encode("utf-8")).digest()
    return digest[:16]


def build_transfer_anchor_payload(
    *,
    transfer_id: str,
    merkle_root: str,
    recipient_address: str,
) -> bytes:
    """68-byte BSM2 OP_RETURN payload."""
    tid = (transfer_id or "").strip().lower()
    root = (merkle_root or "").strip().lower()
    if len(tid) != 64:
        raise ValueError("transfer_id must be 64 hex chars")
    if len(root) != 64:
        raise ValueError("merkle_root must be 64 hex chars")
    return (
        TRANSFER_MAGIC
        + bytes.fromhex(tid[:32])
        + bytes.fromhex(root)
        + recipient_prefix(recipient_address)
    )


def parse_transfer_anchor_payload(data: bytes) -> Optional[Dict[str, Any]]:
    if len(data) < TRANSFER_ANCHOR_BYTES or data[:4] != TRANSFER_MAGIC:
        return None
    return {
        "magic": "BSM2",
        "transfer_id_prefix": data[4:20].hex(),
        "transfer_id_prefix_full": data[4:36].hex() if len(data) >= 36 else data[4:20].hex(),
        "merkle_root": data[20:52].hex(),
        "recipient_prefix": data[52:68].hex(),
    }


def work_digest(
    *,
    transfer_id: str,
    chunk_hash: str,
    job_id: str,
    nonce_hex: str,
) -> str:
    """Hash-power attestation digest bound to a mining share."""
    parts = [
        TRANSFER_MAGIC.decode("ascii"),
        (transfer_id or "").strip().lower(),
        (chunk_hash or "").strip().lower(),
        str(job_id or ""),
        str(nonce_hex or "").strip().lower(),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def transfer_assignment_bucket(
    transfer_id: str,
    node_id: str,
    chunk_hash: str,
) -> int:
    """0–99 bucket for transfer-priority chunk assignment."""
    raw = f"{(transfer_id or '').lower()}:{(node_id or '').lower()}:{(chunk_hash or '').lower()}"
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8], 16) % 100


def node_should_relay_transfer_chunk(
    transfer_id: str,
    node_id: str,
    chunk_hash: str,
    *,
    backup_pct: int = 10,
) -> bool:
    pct = max(1, min(100, int(backup_pct)))
    return transfer_assignment_bucket(transfer_id, node_id, chunk_hash) < pct


def build_transfer_manifest(
    *,
    transfer_id: str,
    sender: str,
    recipient: str,
    display_name: str,
    mime_type: str,
    file_size: int,
    file_sha256: str,
    merkle_root: str,
    chunks: List[Dict[str, Any]],
    asset_key: Optional[str] = None,
    anchor_txid: Optional[str] = None,
    status: str = TRANSFER_STATUS_DRAFT,
    created_at: Optional[int] = None,
) -> Dict[str, Any]:
    key = (asset_key or "").strip() or transfer_asset_key(transfer_id, display_name)
    return {
        "protocol": TRANSFER_PROTOCOL,
        "transfer_id": transfer_id,
        "sender": sender,
        "recipient": recipient,
        "display_name": display_name,
        "mime_type": mime_type,
        "file_size": int(file_size),
        "file_sha256": file_sha256,
        "merkle_root": merkle_root,
        "chunk_count": len(chunks),
        "chunks": chunks,
        "asset_key": key,
        "anchor_txid": anchor_txid,
        "status": status,
        "created_at": created_at or int(time.time()),
    }


def replication_ready(
    *,
    chunk_count: int,
    peers_holding: int,
    min_peers: int = 2,
) -> bool:
    """Transfer is deliverable when enough independent peers hold all chunks."""
    if chunk_count <= 0:
        return False
    return peers_holding >= max(1, min_peers)