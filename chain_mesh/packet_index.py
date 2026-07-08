"""Index BSM3 on-chain packet channel anchors."""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from chain_mesh import db as mesh_db
from chain_mesh import packet_protocol as pp
from chain_mesh.anchor_index import rpc

INDEX_DB = os.environ.get(
    "CHAIN_MESH_PACKET_INDEX_DB",
    "/var/lib/bloodstone-chain-mesh/packet_index.db",
)
_LOCK = threading.Lock()


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    os.makedirs(os.path.dirname(INDEX_DB) or ".", exist_ok=True)
    conn = sqlite3.connect(INDEX_DB, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_packet_index_db() -> None:
    with _LOCK:
        with _conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS packet_anchor_index (
                    txid TEXT PRIMARY KEY,
                    block_height INTEGER NOT NULL,
                    block_hash TEXT NOT NULL,
                    block_time INTEGER,
                    vout INTEGER NOT NULL,
                    channel_id_prefix TEXT NOT NULL,
                    recipient_prefix TEXT NOT NULL,
                    seq INTEGER NOT NULL DEFAULT 0,
                    payload_hex TEXT NOT NULL,
                    channel_id TEXT,
                    recipient TEXT,
                    indexed_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_packet_anchor_height
                    ON packet_anchor_index(block_height DESC);
                CREATE INDEX IF NOT EXISTS idx_packet_anchor_channel
                    ON packet_anchor_index(channel_id_prefix);
                """
            )


def extract_bsm3_from_script(script_pub_key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if (script_pub_key or {}).get("type") != "nulldata":
        return None
    raw_hex = script_pub_key.get("burn") or ""
    if not raw_hex:
        asm = script_pub_key.get("asm") or ""
        parts = asm.split()
        if len(parts) >= 2 and parts[0] == "OP_RETURN":
            raw_hex = parts[1]
    if not raw_hex:
        spk_hex = script_pub_key.get("hex") or ""
        if spk_hex.startswith("6a"):
            raw_hex = spk_hex[4:] if len(spk_hex) > 4 else ""
    try:
        data = bytes.fromhex(raw_hex)
    except ValueError:
        return None
    if len(data) < 40 or data[:4] != pp.PACKET_MAGIC:
        return None
    parsed = {
        "magic": "BSM3",
        "channel_id_prefix": data[4:20].hex(),
        "recipient_prefix": data[20:36].hex(),
        "seq": int.from_bytes(data[36:40], "big") if len(data) >= 40 else 0,
        "payload_hex": raw_hex,
    }
    return parsed


def _enrich_channel(channel_id_prefix: str) -> Dict[str, Optional[str]]:
    with mesh_db._conn() as conn:
        row = conn.execute(
            """
            SELECT channel_id, sender, recipient, label
            FROM chain_mesh_packet_channels
            WHERE channel_id LIKE ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (f"{channel_id_prefix}%",),
        ).fetchone()
    if not row:
        return {"channel_id": None, "recipient": None, "sender": None}
    data = dict(row)
    return {
        "channel_id": data.get("channel_id"),
        "recipient": data.get("recipient"),
        "sender": data.get("sender"),
    }


def index_tx_vouts(
    *,
    txid: str,
    block_height: int,
    block_hash: str,
    block_time: Optional[int],
    vouts: List[Dict[str, Any]],
) -> int:
    init_packet_index_db()
    found = 0
    now = int(time.time())
    with _conn() as conn:
        for vout in vouts:
            anchor = extract_bsm3_from_script(vout.get("scriptPubKey") or {})
            if not anchor:
                continue
            enrich = _enrich_channel(anchor["channel_id_prefix"])
            cur = conn.execute(
                """
                INSERT INTO packet_anchor_index (
                    txid, block_height, block_hash, block_time, vout,
                    channel_id_prefix, recipient_prefix, seq, payload_hex,
                    channel_id, recipient, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(txid) DO UPDATE SET
                    block_height = excluded.block_height,
                    channel_id = COALESCE(excluded.channel_id, packet_anchor_index.channel_id),
                    recipient = COALESCE(excluded.recipient, packet_anchor_index.recipient),
                    indexed_at = excluded.indexed_at
                """,
                (
                    txid,
                    int(block_height),
                    block_hash,
                    int(block_time) if block_time else None,
                    int(vout.get("n") or 0),
                    anchor["channel_id_prefix"],
                    anchor["recipient_prefix"],
                    int(anchor["seq"]),
                    anchor["payload_hex"],
                    enrich.get("channel_id"),
                    enrich.get("recipient"),
                    now,
                ),
            )
            if cur.rowcount > 0:
                found += 1
    return found


def refresh_index(*, lookback: int = 500) -> Dict[str, Any]:
    """Scan recent blocks for BSM3 anchors (reuses anchor_index block fetch)."""
    init_packet_index_db()
    mesh_db.init_db()
    tip = int(rpc("getblockcount"))
    start = max(0, tip - max(1, lookback))
    indexed = 0
    for height in range(start, tip + 1):
        block_hash = rpc("getblockhash", [height])
        block = rpc("getblock", [block_hash, 2])
        for tx in block.get("tx") or []:
            indexed += index_tx_vouts(
                txid=tx.get("txid") or "",
                block_height=height,
                block_hash=block_hash,
                block_time=block.get("time"),
                vouts=tx.get("vout") or [],
            )
    return {"ok": True, "tip": tip, "from_height": start, "bsm3_indexed": indexed}


def list_anchors(
    *,
    channel_id_prefix: str = "",
    limit: int = 50,
) -> Dict[str, Any]:
    init_packet_index_db()
    clauses = []
    params: List[Any] = []
    if channel_id_prefix:
        clauses.append("channel_id_prefix LIKE ?")
        params.append(f"{channel_id_prefix.strip().lower()}%")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(200, int(limit))))
    sql = (
        f"SELECT txid, block_height, block_hash, block_time, channel_id_prefix, "
        f"recipient_prefix, seq, channel_id, recipient, indexed_at "
        f"FROM packet_anchor_index {where} ORDER BY block_height DESC LIMIT ?"
    )
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"ok": True, "anchors": [dict(r) for r in rows], "count": len(rows)}