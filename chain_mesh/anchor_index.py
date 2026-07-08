"""Index BSM1 on-chain anchors from block transactions."""

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

import requests

from chain_mesh.anchor import ANCHOR_MAGIC, parse_anchor_payload
from chain_mesh import db as mesh_db

INDEX_DB = os.environ.get(
    "CHAIN_MESH_ANCHOR_INDEX_DB",
    "/var/lib/bloodstone-chain-mesh/anchor_index.db",
)
CONF_PATH = os.environ.get("BLOODSTONE_CONF", "/root/.bloodstone/bloodstone.conf")
SCAN_BATCH = int(os.environ.get("CHAIN_MESH_ANCHOR_SCAN_BATCH", "200"))
LOOKBACK = int(os.environ.get("CHAIN_MESH_ANCHOR_INDEX_LOOKBACK", "500"))
_LOCK = threading.Lock()


def _load_rpc_url() -> str:
    values: Dict[str, str] = {}
    if os.path.isfile(CONF_PATH):
        with open(CONF_PATH, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                values[key.strip()] = val.strip()
    user = values.get("rpcuser", os.environ.get("RPC_USER", "bloodstone"))
    password = values.get("rpcpassword", os.environ.get("RPC_PASSWORD", ""))
    port = values.get("rpcport", os.environ.get("RPC_PORT", "18332"))
    host = os.environ.get("RPC_HOST", "127.0.0.1")
    return f"http://{user}:{password}@{host}:{port}/"


def rpc(method: str, params: Optional[List[Any]] = None) -> Any:
    payload = {"jsonrpc": "1.0", "id": "mesh-anchor-index", "method": method, "params": params or []}
    resp = requests.post(
        _load_rpc_url(),
        json=payload,
        headers={"content-type": "text/plain;"},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        err = data["error"]
        raise RuntimeError(err.get("message", str(err)))
    return data["result"]


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


def init_index_db() -> None:
    with _LOCK:
        with _conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS anchor_index_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chain_anchor_index (
                    txid TEXT PRIMARY KEY,
                    block_height INTEGER NOT NULL,
                    block_hash TEXT NOT NULL,
                    block_time INTEGER,
                    vout INTEGER NOT NULL,
                    asset_id_prefix TEXT NOT NULL,
                    merkle_root TEXT NOT NULL,
                    payload_hex TEXT NOT NULL,
                    asset_key TEXT,
                    display_name TEXT,
                    indexed_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chain_anchor_height
                    ON chain_anchor_index(block_height DESC);
                CREATE INDEX IF NOT EXISTS idx_chain_anchor_merkle
                    ON chain_anchor_index(merkle_root);
                """
            )


def _meta_get(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute(
        "SELECT value FROM anchor_index_meta WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else default


def _meta_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO anchor_index_meta (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def extract_bsm1_from_script(script_pub_key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
    parsed = parse_anchor_payload(data)
    if not parsed:
        return None
    return {**parsed, "payload_hex": raw_hex}


def _enrich_asset(merkle_root: str, asset_id_prefix: str) -> Dict[str, Optional[str]]:
    asset = mesh_db.get_asset_by_merkle_root(merkle_root)
    if asset:
        return {
            "asset_key": asset.get("asset_key"),
            "display_name": asset.get("display_name"),
            "asset_id": asset.get("asset_id"),
        }
    for row in mesh_db.list_assets(limit=200):
        aid = row.get("asset_id") or ""
        if aid.startswith(asset_id_prefix):
            full = mesh_db.get_asset(asset_id=aid)
            if full and full.get("merkle_root") == merkle_root:
                return {
                    "asset_key": full.get("asset_key"),
                    "display_name": full.get("display_name"),
                    "asset_id": full.get("asset_id"),
                }
    return {"asset_key": None, "display_name": None, "asset_id": None}


def _insert_anchor(
    conn: sqlite3.Connection,
    *,
    txid: str,
    block_height: int,
    block_hash: str,
    block_time: Optional[int],
    vout: int,
    anchor: Dict[str, Any],
) -> bool:
    enrich = _enrich_asset(anchor["merkle_root"], anchor["asset_id_prefix"])
    now = int(time.time())
    cur = conn.execute(
        """
        INSERT INTO chain_anchor_index (
            txid, block_height, block_hash, block_time, vout,
            asset_id_prefix, merkle_root, payload_hex,
            asset_key, display_name, indexed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(txid) DO UPDATE SET
            block_height = excluded.block_height,
            block_hash = excluded.block_hash,
            block_time = excluded.block_time,
            asset_key = COALESCE(excluded.asset_key, chain_anchor_index.asset_key),
            display_name = COALESCE(excluded.display_name, chain_anchor_index.display_name),
            indexed_at = excluded.indexed_at
        """,
        (
            txid,
            int(block_height),
            block_hash,
            int(block_time) if block_time else None,
            int(vout),
            anchor["asset_id_prefix"],
            anchor["merkle_root"],
            anchor["payload_hex"],
            enrich.get("asset_key"),
            enrich.get("display_name"),
            now,
        ),
    )
    return cur.rowcount > 0


def scan_block(height: int, *, block: Optional[Dict[str, Any]] = None) -> int:
    init_index_db()
    mesh_db.init_db()
    if block is None:
        block_hash = rpc("getblockhash", [height])
        block = rpc("getblock", [block_hash, 2])
    found = 0
    with _conn() as conn:
        for tx in block.get("tx") or []:
            txid = tx.get("txid") or ""
            for vout in tx.get("vout") or []:
                anchor = extract_bsm1_from_script(vout.get("scriptPubKey") or {})
                if not anchor:
                    continue
                if _insert_anchor(
                    conn,
                    txid=txid,
                    block_height=height,
                    block_hash=block.get("hash") or "",
                    block_time=block.get("time"),
                    vout=int(vout.get("n") or 0),
                    anchor=anchor,
                ):
                    found += 1
    return found


def index_txid(txid: str) -> bool:
    """Index one transaction if it contains BSM1 (mempool or confirmed)."""
    init_index_db()
    mesh_db.init_db()
    tx = rpc("getrawtransaction", [txid, True])
    block_height = 0
    block_hash = ""
    block_time = None
    if tx.get("blockhash"):
        block_hash = tx["blockhash"]
        header = rpc("getblockheader", [block_hash])
        block_height = int(header.get("height") or 0)
        block_time = int(header.get("time") or 0)
    found = False
    with _conn() as conn:
        for vout in tx.get("vout") or []:
            anchor = extract_bsm1_from_script(vout.get("scriptPubKey") or {})
            if not anchor:
                continue
            if _insert_anchor(
                conn,
                txid=txid,
                block_height=block_height,
                block_hash=block_hash,
                block_time=block_time,
                vout=int(vout.get("n") or 0),
                anchor=anchor,
            ):
                found = True
    return found


def _index_mesh_registry_anchors() -> int:
    """Pull anchor txids registered in mesh asset catalog."""
    count = 0
    for row in mesh_db.list_assets(limit=200):
        txid = (row.get("anchor_txid") or "").strip()
        if not txid:
            continue
        try:
            if index_txid(txid):
                count += 1
        except RuntimeError:
            pass
    return count


def refresh_index(*, full: bool = False) -> Dict[str, Any]:
    init_index_db()
    mesh_db.init_db()
    tip = int(rpc("getblockcount"))
    registry_hits = _index_mesh_registry_anchors()
    start = 0
    if full:
        start = int(os.environ.get("CHAIN_MESH_ANCHOR_INDEX_START", "0"))
    else:
        with _conn() as conn:
            last = _meta_get(conn, "last_scanned_height", "")
            if last.isdigit():
                start = max(0, int(last) + 1)
            else:
                start = max(0, tip - LOOKBACK)

    scanned = 0
    anchors_found = registry_hits
    h = start
    while h <= tip:
        batch_end = min(tip, h + SCAN_BATCH - 1)
        for height in range(h, batch_end + 1):
            anchors_found += scan_block(height)
            scanned += 1
        with _conn() as conn:
            _meta_set(conn, "last_scanned_height", str(batch_end))
            _meta_set(conn, "last_refresh_at", str(int(time.time())))
            _meta_set(conn, "tip_at_refresh", str(tip))
        h = batch_end + 1

    _sync_mesh_db_anchors()
    return {
        "ok": True,
        "tip": tip,
        "scanned_blocks": scanned,
        "anchors_found": anchors_found,
        "registry_indexed": registry_hits,
        "start_height": start,
        "end_height": tip,
    }


def _sync_mesh_db_anchors() -> int:
    """Backfill mesh asset registry from on-chain index when block confirmed."""
    updated = 0
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT txid, block_height, merkle_root
            FROM chain_anchor_index
            WHERE block_height > 0
            ORDER BY block_height DESC
            LIMIT 500
            """
        ).fetchall()
    for row in rows:
        asset = mesh_db.get_asset_by_merkle_root(row["merkle_root"])
        if not asset:
            continue
        if asset.get("anchor_txid") == row["txid"]:
            continue
        try:
            tx = rpc("getrawtransaction", [row["txid"], True])
            conf = int(tx.get("confirmations") or 0)
        except RuntimeError:
            conf = 0
        mesh_db.update_asset_anchor(
            asset["asset_id"],
            anchor_txid=row["txid"],
            anchor_height=int(row["block_height"]),
            anchor_confirmations=conf,
        )
        updated += 1
    return updated


def list_anchors(*, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    init_index_db()
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT txid, block_height, block_hash, block_time, vout,
                   asset_id_prefix, merkle_root, payload_hex,
                   asset_key, display_name, indexed_at
            FROM chain_anchor_index
            ORDER BY block_height DESC, txid DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) AS n FROM chain_anchor_index").fetchone()["n"]
        meta = {
            "last_scanned_height": _meta_get(conn, "last_scanned_height", "0"),
            "last_refresh_at": int(_meta_get(conn, "last_refresh_at", "0") or 0),
            "tip_at_refresh": int(_meta_get(conn, "tip_at_refresh", "0") or 0),
        }
    anchors = []
    for row in rows:
        entry = dict(row)
        entry["confirmations"] = None
        if entry.get("block_height"):
            try:
                tip = int(rpc("getblockcount"))
                entry["confirmations"] = max(0, tip - int(entry["block_height"]) + 1)
            except RuntimeError:
                pass
        anchors.append(entry)
    return {"ok": True, "total": int(total), "anchors": anchors, "meta": meta}


def get_anchor(txid: str) -> Optional[Dict[str, Any]]:
    init_index_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM chain_anchor_index WHERE txid = ?",
            ((txid or "").strip().lower(),),
        ).fetchone()
    if not row:
        return None
    entry = dict(row)
    asset = mesh_db.get_asset_by_merkle_root(entry["merkle_root"])
    if asset:
        entry["asset"] = {
            "asset_key": asset.get("asset_key"),
            "display_name": asset.get("display_name"),
            "file_size": asset.get("file_size"),
            "file_sha256": asset.get("file_sha256"),
            "chunk_count": asset.get("chunk_count"),
        }
    return entry


def decode_tx_anchors(tx: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for vout in tx.get("vout") or []:
        anchor = extract_bsm1_from_script(vout.get("scriptPubKey") or {})
        if not anchor:
            continue
        enrich = _enrich_asset(anchor["merkle_root"], anchor["asset_id_prefix"])
        out.append(
            {
                "vout": int(vout.get("n") or 0),
                **anchor,
                **enrich,
            }
        )
    return out


def ensure_fresh(*, max_age_sec: int = 300) -> Dict[str, Any]:
    init_index_db()
    with _conn() as conn:
        last = int(_meta_get(conn, "last_refresh_at", "0") or 0)
        last_h = int(_meta_get(conn, "last_scanned_height", "-1") or -1)
    try:
        tip = int(rpc("getblockcount"))
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}
    stale = (int(time.time()) - last) > max_age_sec or last_h < tip
    if stale:
        return refresh_index(full=False)
    return {"ok": True, "skipped": True, "tip": tip, "last_scanned_height": last_h}