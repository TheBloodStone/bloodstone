"""SQLite registry for manifests, chunks, and storage peers."""

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

from chain_mesh.config import DB_PATH, MESH_ROOT

_LOCK = threading.Lock()


def _now() -> int:
    return int(time.time())


def ensure_dirs() -> None:
    os.makedirs(MESH_ROOT, exist_ok=True)
    os.makedirs(os.path.dirname(DB_PATH) or MESH_ROOT, exist_ok=True)


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _LOCK:
        with _conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS chain_manifest (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    best_block_hash TEXT NOT NULL,
                    block_height INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    total_bytes INTEGER NOT NULL,
                    is_current INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_chain_manifest_current
                    ON chain_manifest(is_current, created_at DESC);

                CREATE TABLE IF NOT EXISTS chain_chunks (
                    chunk_hash TEXT PRIMARY KEY,
                    source_file TEXT NOT NULL,
                    file_offset INTEGER NOT NULL,
                    size INTEGER NOT NULL,
                    manifest_id INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY (manifest_id) REFERENCES chain_manifest(id)
                );
                CREATE INDEX IF NOT EXISTS idx_chain_chunks_manifest
                    ON chain_chunks(manifest_id);
                CREATE INDEX IF NOT EXISTS idx_chain_chunks_source
                    ON chain_chunks(source_file, file_offset);

                CREATE TABLE IF NOT EXISTS chain_storage_peers (
                    device_id TEXT PRIMARY KEY,
                    peer_kind TEXT NOT NULL DEFAULT 'browser',
                    model TEXT NOT NULL DEFAULT '',
                    capacity_bytes INTEGER NOT NULL DEFAULT 0,
                    chunks_held INTEGER NOT NULL DEFAULT 0,
                    first_seen INTEGER NOT NULL,
                    last_seen INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chain_peers_last_seen
                    ON chain_storage_peers(last_seen);

                CREATE TABLE IF NOT EXISTS chain_peer_chunks (
                    device_id TEXT NOT NULL,
                    chunk_hash TEXT NOT NULL,
                    announced_at INTEGER NOT NULL,
                    PRIMARY KEY (device_id, chunk_hash)
                );
                CREATE INDEX IF NOT EXISTS idx_chain_peer_chunks_hash
                    ON chain_peer_chunks(chunk_hash);

                CREATE TABLE IF NOT EXISTS chain_assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_id TEXT NOT NULL UNIQUE,
                    asset_key TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL DEFAULT '',
                    mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                    version TEXT NOT NULL DEFAULT '',
                    file_size INTEGER NOT NULL,
                    file_sha256 TEXT NOT NULL,
                    merkle_root TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    anchor_txid TEXT,
                    anchor_height INTEGER,
                    anchor_confirmations INTEGER,
                    created_at INTEGER NOT NULL,
                    is_current INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_chain_assets_key
                    ON chain_assets(asset_key);
                CREATE INDEX IF NOT EXISTS idx_chain_assets_current
                    ON chain_assets(is_current, created_at DESC);

                CREATE TABLE IF NOT EXISTS chain_asset_chunks (
                    asset_id TEXT NOT NULL,
                    chunk_hash TEXT NOT NULL,
                    file_offset INTEGER NOT NULL,
                    size INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    PRIMARY KEY (asset_id, chunk_index)
                );
                CREATE INDEX IF NOT EXISTS idx_chain_asset_chunks_hash
                    ON chain_asset_chunks(chunk_hash);

                CREATE TABLE IF NOT EXISTS chain_mesh_pending_submissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    asset_key TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                    version TEXT NOT NULL DEFAULT '',
                    file_size INTEGER NOT NULL,
                    file_sha256 TEXT NOT NULL,
                    merkle_root TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL,
                    chunks_json TEXT NOT NULL,
                    anchor_requested INTEGER NOT NULL DEFAULT 1,
                    submitter_address TEXT NOT NULL DEFAULT '',
                    submitter_device_id TEXT NOT NULL DEFAULT '',
                    submitter_note TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    reviewed_at INTEGER,
                    reviewed_by TEXT NOT NULL DEFAULT '',
                    rejection_reason TEXT NOT NULL DEFAULT '',
                    published_asset_id TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_mesh_pending_status
                    ON chain_mesh_pending_submissions(status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_mesh_pending_key
                    ON chain_mesh_pending_submissions(asset_key, status);

                CREATE TABLE IF NOT EXISTS chain_time_capsule_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    block_height INTEGER NOT NULL,
                    best_block_hash TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    coordinator_coverage_pct REAL NOT NULL DEFAULT 0,
                    blocks_bytes INTEGER NOT NULL DEFAULT 0,
                    pruned INTEGER NOT NULL DEFAULT 0,
                    prune_mib INTEGER,
                    txindex_disabled INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_time_capsule_events_created
                    ON chain_time_capsule_events(created_at DESC);

                CREATE TABLE IF NOT EXISTS chain_blurt_traffic_daily (
                    day_utc TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    bytes INTEGER NOT NULL DEFAULT 0,
                    requests INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (day_utc, direction)
                );
                CREATE INDEX IF NOT EXISTS idx_blurt_traffic_day
                    ON chain_blurt_traffic_daily(day_utc);
                """
            )
            migrate_blurt_author_columns(conn)


def migrate_blurt_author_columns(conn: sqlite3.Connection) -> Dict[str, Any]:
    """
    Rename DB column blurt_author → blurt_account (Open Item 7 / audit rename).

    SQLite 3.25+ RENAME COLUMN. Idempotent: no-op when already migrated.
    Callers should use blurt_account in SQL; dual API keys remain at HTTP edge.
    """
    renamed = []
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    for row in tables:
        table = str(row[0] if not isinstance(row, sqlite3.Row) else row["name"])
        try:
            cols = {
                str(c[1] if not isinstance(c, sqlite3.Row) else c["name"])
                for c in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
        except sqlite3.Error:
            continue
        if "blurt_author" in cols and "blurt_account" not in cols:
            try:
                conn.execute(
                    f'ALTER TABLE "{table}" RENAME COLUMN blurt_author TO blurt_account'
                )
                renamed.append(table)
            except sqlite3.Error:
                # Older SQLite or complex PK: leave column; code uses blurt_account
                # only after migration succeeds.
                pass
    return {"ok": True, "renamed_tables": renamed}


def record_blurt_traffic_daily(
    *,
    direction: str,
    byte_count: int,
    requests: int = 1,
) -> None:
    """Accumulate Blurt partner mesh traffic for the current UTC day."""
    if byte_count <= 0 and requests <= 0:
        return
    init_db()
    day = time.strftime("%Y-%m-%d", time.gmtime())
    direc = "out" if str(direction).lower() in ("out", "outbound", "egress") else "in"
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO chain_blurt_traffic_daily (day_utc, direction, bytes, requests)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(day_utc, direction) DO UPDATE SET
                bytes = bytes + excluded.bytes,
                requests = requests + excluded.requests
            """,
            (day, direc, max(0, int(byte_count)), max(0, int(requests))),
        )


def list_blurt_traffic_daily() -> List[Dict[str, Any]]:
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT day_utc, direction, bytes, requests
            FROM chain_blurt_traffic_daily
            ORDER BY day_utc ASC
            """
        ).fetchall()
    return [
        {
            "day_utc": str(r["day_utc"]),
            "direction": str(r["direction"]),
            "bytes": int(r["bytes"] or 0),
            "requests": int(r["requests"] or 0),
        }
        for r in rows
    ]


def set_current_manifest(
    *,
    best_block_hash: str,
    block_height: int,
    chunks: List[Dict[str, Any]],
) -> int:
    init_db()
    now = _now()
    total_bytes = sum(int(c["size"]) for c in chunks)
    with _conn() as conn:
        conn.execute("UPDATE chain_manifest SET is_current = 0 WHERE is_current = 1")
        cur = conn.execute(
            """
            INSERT INTO chain_manifest (
                best_block_hash, block_height, created_at,
                chunk_count, total_bytes, is_current
            ) VALUES (?, ?, ?, ?, ?, 1)
            """,
            (
                best_block_hash,
                int(block_height),
                now,
                len(chunks),
                total_bytes,
            ),
        )
        manifest_id = int(cur.lastrowid)
        for chunk in chunks:
            conn.execute(
                """
                INSERT INTO chain_chunks (
                    chunk_hash, source_file, file_offset, size,
                    manifest_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_hash) DO UPDATE SET
                    source_file = excluded.source_file,
                    file_offset = excluded.file_offset,
                    size = excluded.size,
                    manifest_id = excluded.manifest_id,
                    created_at = excluded.created_at
                """,
                (
                    chunk["chunk_hash"],
                    chunk["source_file"],
                    int(chunk["file_offset"]),
                    int(chunk["size"]),
                    manifest_id,
                    now,
                ),
            )
        return manifest_id


def get_current_manifest() -> Optional[Dict[str, Any]]:
    init_db()
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM chain_manifest
            WHERE is_current = 1
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
        if not row:
            return None
        chunks = conn.execute(
            """
            SELECT chunk_hash, source_file, file_offset, size
            FROM chain_chunks
            WHERE manifest_id = ?
            ORDER BY source_file, file_offset
            """,
            (int(row["id"]),),
        ).fetchall()
        return {
            "id": int(row["id"]),
            "best_block_hash": row["best_block_hash"],
            "block_height": int(row["block_height"]),
            "created_at": int(row["created_at"]),
            "chunk_count": int(row["chunk_count"]),
            "total_bytes": int(row["total_bytes"]),
            "chunks": [dict(c) for c in chunks],
        }


def upsert_peer(
    *,
    device_id: str,
    peer_kind: str = "browser",
    model: str = "",
    capacity_bytes: int = 0,
    chunk_hashes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    init_db()
    did = (device_id or "").strip().lower()
    if not did:
        raise ValueError("device_id required")
    now = _now()
    hashes = [h.strip().lower() for h in (chunk_hashes or []) if h and h.strip()]
    hashes = hashes[: int(os.environ.get("CHAIN_MESH_MAX_CHUNKS_PER_DEVICE", "32"))]

    with _conn() as conn:
        row = conn.execute(
            "SELECT first_seen FROM chain_storage_peers WHERE device_id = ?",
            (did,),
        ).fetchone()
        first_seen = int(row["first_seen"]) if row else now
        conn.execute(
            """
            INSERT INTO chain_storage_peers (
                device_id, peer_kind, model, capacity_bytes,
                chunks_held, first_seen, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                peer_kind = excluded.peer_kind,
                model = excluded.model,
                capacity_bytes = excluded.capacity_bytes,
                chunks_held = excluded.chunks_held,
                last_seen = excluded.last_seen
            """,
            (
                did,
                (peer_kind or "browser").strip().lower()[:24],
                (model or "")[:120],
                max(0, int(capacity_bytes)),
                len(hashes),
                first_seen,
                now,
            ),
        )
        if hashes:
            conn.execute(
                "DELETE FROM chain_peer_chunks WHERE device_id = ?",
                (did,),
            )
            conn.executemany(
                """
                INSERT INTO chain_peer_chunks (device_id, chunk_hash, announced_at)
                VALUES (?, ?, ?)
                """,
                [(did, h, now) for h in hashes],
            )

    return {
        "device_id": did,
        "chunks_held": len(hashes),
        "last_seen": now,
    }


def peers_for_chunk(chunk_hash: str, *, active_sec: int = 3600) -> List[str]:
    init_db()
    cutoff = _now() - active_sec
    h = (chunk_hash or "").strip().lower()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT p.device_id
            FROM chain_peer_chunks c
            JOIN chain_storage_peers p ON p.device_id = c.device_id
            WHERE c.chunk_hash = ? AND p.last_seen >= ?
            ORDER BY p.last_seen DESC
            """,
            (h, cutoff),
        ).fetchall()
        return [r["device_id"] for r in rows]


def peers_for_chunk_with_endpoints(
    chunk_hash: str,
    *,
    requester_public_ip: str = "",
    active_sec: int = 3600,
) -> List[Dict[str, Any]]:
    from chain_mesh import lan_registry as lan

    init_db()
    lan.init_lan_db()
    cutoff = _now() - active_sec
    h = (chunk_hash or "").strip().lower()
    pub_ip = (requester_public_ip or "").strip()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT p.device_id, p.peer_kind, p.model, p.last_seen,
                   l.lan_ip, l.chunk_port, l.public_ip
            FROM chain_peer_chunks c
            JOIN chain_storage_peers p ON p.device_id = c.device_id
            LEFT JOIN chain_lan_nodes l ON l.device_id = p.device_id
            WHERE c.chunk_hash = ? AND p.last_seen >= ?
            ORDER BY p.last_seen DESC
            """,
            (h, cutoff),
        ).fetchall()
    endpoints: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        lan_ip = (row["lan_ip"] or "").strip()
        if not lan_ip:
            continue
        if pub_ip and row["public_ip"] and row["public_ip"] != pub_ip:
            continue
        port = int(row["chunk_port"] or 18341)
        key = f"{lan_ip}:{port}"
        if key in seen:
            continue
        seen.add(key)
        endpoints.append(
            {
                "device_id": row["device_id"],
                "lan_ip": lan_ip,
                "chunk_port": port,
                "peer_kind": row["peer_kind"] or "",
                "model": row["model"] or "",
                "last_seen": int(row["last_seen"] or 0),
            }
        )
    return endpoints


def public_stats(*, active_sec: int = 3600) -> Dict[str, Any]:
    init_db()
    cutoff = _now() - active_sec
    manifest = get_current_manifest()
    with _conn() as conn:
        peer_count = conn.execute(
            "SELECT COUNT(*) AS n FROM chain_storage_peers WHERE last_seen >= ?",
            (cutoff,),
        ).fetchone()["n"]
        chunk_replicas = conn.execute(
            """
            SELECT COUNT(DISTINCT chunk_hash) AS unique_chunks,
                   COUNT(*) AS replica_announcements
            FROM chain_peer_chunks c
            JOIN chain_storage_peers p ON p.device_id = c.device_id
            WHERE p.last_seen >= ?
            """,
            (cutoff,),
        ).fetchone()
    from chain_mesh.store import chunk_exists, stored_chunk_count

    coordinator_chunks = stored_chunk_count()
    return {
        "manifest": {
            "block_height": manifest["block_height"] if manifest else 0,
            "best_block_hash": manifest["best_block_hash"] if manifest else "",
            "chunk_count": manifest["chunk_count"] if manifest else 0,
            "total_bytes": manifest["total_bytes"] if manifest else 0,
            "updated_at": manifest["created_at"] if manifest else 0,
        },
        "coordinator_chunks": coordinator_chunks,
        "active_peers": int(peer_count),
        "peer_unique_chunks": int(chunk_replicas["unique_chunks"] or 0),
        "peer_replica_announcements": int(chunk_replicas["replica_announcements"] or 0),
        "chunk_size": int(os.environ.get("CHAIN_MESH_CHUNK_SIZE", str(256 * 1024))),
    }


def register_asset(
    *,
    asset_id: str,
    asset_key: str,
    display_name: str,
    mime_type: str,
    version: str,
    file_size: int,
    file_sha256: str,
    merkle_root: str,
    chunks: List[Dict[str, Any]],
    anchor_txid: Optional[str] = None,
    anchor_height: Optional[int] = None,
) -> Dict[str, Any]:
    init_db()
    now = _now()
    aid = (asset_id or "").strip().lower()
    key = (asset_key or "").strip()
    if not aid or not key:
        raise ValueError("asset_id and asset_key required")
    with _conn() as conn:
        existing = conn.execute(
            "SELECT id FROM chain_assets WHERE asset_key = ?",
            (key,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE chain_assets SET
                    display_name = ?,
                    mime_type = ?,
                    version = ?,
                    file_size = ?,
                    file_sha256 = ?,
                    merkle_root = ?,
                    chunk_count = ?,
                    anchor_txid = COALESCE(?, anchor_txid),
                    anchor_height = COALESCE(?, anchor_height),
                    anchor_confirmations = CASE WHEN ? IS NOT NULL THEN 0 ELSE anchor_confirmations END,
                    created_at = ?,
                    is_current = 1
                WHERE asset_key = ?
                """,
                (
                    (display_name or "")[:200],
                    (mime_type or "application/octet-stream")[:120],
                    (version or "")[:64],
                    int(file_size),
                    (file_sha256 or "").strip().lower(),
                    (merkle_root or "").strip().lower(),
                    len(chunks),
                    anchor_txid,
                    int(anchor_height) if anchor_height is not None else None,
                    anchor_txid,
                    now,
                    key,
                ),
            )
            row_id = int(existing["id"])
        else:
            cur = conn.execute(
                """
                INSERT INTO chain_assets (
                    asset_id, asset_key, display_name, mime_type, version,
                    file_size, file_sha256, merkle_root, chunk_count,
                    anchor_txid, anchor_height, anchor_confirmations,
                    created_at, is_current
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    aid,
                    key,
                    (display_name or "")[:200],
                    (mime_type or "application/octet-stream")[:120],
                    (version or "")[:64],
                    int(file_size),
                    (file_sha256 or "").strip().lower(),
                    (merkle_root or "").strip().lower(),
                    len(chunks),
                    anchor_txid,
                    int(anchor_height) if anchor_height is not None else None,
                    0 if anchor_txid else None,
                    now,
                ),
            )
            row_id = int(cur.lastrowid)
        conn.execute("DELETE FROM chain_asset_chunks WHERE asset_id = ?", (aid,))
        for idx, chunk in enumerate(chunks):
            conn.execute(
                """
                INSERT INTO chain_asset_chunks (
                    asset_id, chunk_hash, file_offset, size, chunk_index
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    aid,
                    str(chunk["chunk_hash"]).strip().lower(),
                    int(chunk["file_offset"]),
                    int(chunk["size"]),
                    idx,
                ),
            )
    return {"id": row_id, "asset_id": aid, "asset_key": key, "created_at": now}


def update_asset_anchor(
    asset_id: str,
    *,
    anchor_txid: str,
    anchor_height: int,
    anchor_confirmations: int = 0,
) -> None:
    init_db()
    with _conn() as conn:
        conn.execute(
            """
            UPDATE chain_assets SET
                anchor_txid = ?,
                anchor_height = ?,
                anchor_confirmations = ?
            WHERE asset_id = ?
            """,
            (
                anchor_txid,
                int(anchor_height),
                int(anchor_confirmations),
                (asset_id or "").strip().lower(),
            ),
        )


def get_asset(*, asset_key: Optional[str] = None, asset_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    init_db()
    with _conn() as conn:
        if asset_key:
            row = conn.execute(
                """
                SELECT * FROM chain_assets
                WHERE asset_key = ? AND is_current = 1
                ORDER BY created_at DESC LIMIT 1
                """,
                (asset_key.strip(),),
            ).fetchone()
        elif asset_id:
            row = conn.execute(
                """
                SELECT * FROM chain_assets
                WHERE asset_id = ? AND is_current = 1
                ORDER BY created_at DESC LIMIT 1
                """,
                (asset_id.strip().lower(),),
            ).fetchone()
        else:
            return None
        if not row:
            return None
        chunks = conn.execute(
            """
            SELECT chunk_hash, file_offset, size, chunk_index
            FROM chain_asset_chunks
            WHERE asset_id = ?
            ORDER BY chunk_index
            """,
            (row["asset_id"],),
        ).fetchall()
        return {
            "id": int(row["id"]),
            "asset_id": row["asset_id"],
            "asset_key": row["asset_key"],
            "display_name": row["display_name"],
            "mime_type": row["mime_type"],
            "version": row["version"],
            "file_size": int(row["file_size"]),
            "file_sha256": row["file_sha256"],
            "merkle_root": row["merkle_root"],
            "chunk_count": int(row["chunk_count"]),
            "anchor_txid": row["anchor_txid"],
            "anchor_height": int(row["anchor_height"] or 0),
            "anchor_confirmations": int(row["anchor_confirmations"] or 0),
            "created_at": int(row["created_at"]),
            "chunks": [dict(c) for c in chunks],
        }


def get_asset_by_merkle_root(merkle_root: str) -> Optional[Dict[str, Any]]:
    init_db()
    root = (merkle_root or "").strip().lower()
    if len(root) != 64:
        return None
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM chain_assets
            WHERE merkle_root = ? AND is_current = 1
            ORDER BY created_at DESC LIMIT 1
            """,
            (root,),
        ).fetchone()
    if not row:
        return None
    return get_asset(asset_id=row["asset_id"])


def update_asset_metadata(
    asset_key: str,
    *,
    display_name: Optional[str] = None,
    version: Optional[str] = None,
) -> Dict[str, Any]:
    """Update catalog labels for the current revision (content chunks unchanged)."""
    init_db()
    key = (asset_key or "").strip()
    if not key:
        raise ValueError("asset_key required")
    fields: List[str] = []
    values: List[Any] = []
    if display_name is not None:
        fields.append("display_name = ?")
        values.append(str(display_name)[:200])
    if version is not None:
        fields.append("version = ?")
        values.append(str(version)[:64])
    if not fields:
        raise ValueError("nothing to update")
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT asset_id FROM chain_assets
            WHERE asset_key = ? AND is_current = 1
            ORDER BY created_at DESC LIMIT 1
            """,
            (key,),
        ).fetchone()
        if not row:
            raise KeyError(key)
        conn.execute(
            f"UPDATE chain_assets SET {', '.join(fields)} WHERE asset_id = ?",
            (*values, row["asset_id"]),
        )
    asset = get_asset(asset_key=key)
    if not asset:
        raise KeyError(key)
    return asset


def list_asset_versions(asset_key: str, *, limit: int = 20) -> List[Dict[str, Any]]:
    init_db()
    key = (asset_key or "").strip()
    if not key:
        return []
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT asset_id, asset_key, display_name, version, file_size, file_sha256,
                   merkle_root, chunk_count, anchor_txid, anchor_height, created_at,
                   is_current
            FROM chain_assets
            WHERE asset_key = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (key, max(1, min(int(limit), 50))),
        ).fetchall()
    return [dict(r) for r in rows]


def list_assets(*, limit: int = 50) -> List[Dict[str, Any]]:
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT asset_id, asset_key, display_name, mime_type, version,
                   file_size, file_sha256, merkle_root, chunk_count,
                   anchor_txid, anchor_height, created_at
            FROM chain_assets
            WHERE is_current = 1
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 200)),),
        ).fetchall()
    return [dict(r) for r in rows]


def search_assets(
    *,
    tokens: Optional[List[str]] = None,
    glob_like: Optional[str] = None,
    prefix: Optional[str] = None,
    mime_contains: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Filter current mesh assets by glob, token substring match, or both."""
    init_db()
    toks = [t.strip().lower() for t in (tokens or []) if t and str(t).strip()]
    clauses = ["is_current = 1"]
    params: List[Any] = []

    if prefix:
        clauses.append("asset_key LIKE ?")
        params.append(f"{prefix.rstrip('/')}/%")

    if mime_contains:
        mc = mime_contains.strip().lower()
        use_sub = os.environ.get("CHAIN_MESH_SEARCH_SUBSTRING", "0").strip().lower() in (
            "1", "true", "yes",
        )
        if use_sub:
            clauses.append("LOWER(mime_type) LIKE ?")
            params.append(f"%{mc}%")
        else:
            # prefix match on mime (e.g. application/%)
            clauses.append("LOWER(mime_type) LIKE ?")
            params.append(f"{mc}%")

    if glob_like:
        glob_clause = """(
            LOWER(asset_key) LIKE ? ESCAPE '\\'
            OR LOWER(COALESCE(display_name, '')) LIKE ? ESCAPE '\\'
        )"""
        clauses.append(glob_clause)
        params.extend([glob_like, glob_like])

    # E-03 / F-10: default prefix match for tokens ≥3 chars; substring only when
    # CHAIN_MESH_SEARCH_SUBSTRING=1 (or token length < 3). file_sha256 is exact only.
    use_substring = os.environ.get("CHAIN_MESH_SEARCH_SUBSTRING", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    for tok in toks:
        # F-10: 64-hex → exact file_sha256 match (never leading-wildcard scan).
        if len(tok) == 64 and all(c in "0123456789abcdef" for c in tok):
            clauses.append("LOWER(COALESCE(file_sha256, '')) = ?")
            params.append(tok)
            continue
        if use_substring or len(tok) < 3:
            like = f"%{tok}%"
            if use_substring:
                clauses.append(
                    """(
                        LOWER(asset_key) LIKE ? OR LOWER(display_name) LIKE ?
                        OR LOWER(version) LIKE ? OR LOWER(mime_type) LIKE ?
                    )"""
                )
                params.extend([like, like, like, like])
            else:
                # Short tokens: substring on name fields only (no file_sha256 scan)
                clauses.append(
                    """(
                        LOWER(asset_key) LIKE ? OR LOWER(display_name) LIKE ?
                        OR LOWER(version) LIKE ?
                    )"""
                )
                params.extend([like, like, like])
            continue
        # Default: prefix-oriented match (B-tree friendly on asset_key / display_name)
        like_prefix = f"{tok}%"
        clauses.append(
            """(
                LOWER(asset_key) LIKE ? OR LOWER(display_name) LIKE ?
                OR LOWER(asset_key) LIKE ? OR LOWER(version) LIKE ?
            )"""
        )
        params.extend([like_prefix, like_prefix, f"%/{tok}%", f"{tok}%"])

    where = " AND ".join(clauses)
    sql = f"""
        SELECT asset_id, asset_key, display_name, mime_type, version,
               file_size, file_sha256, merkle_root, chunk_count,
               anchor_txid, anchor_height, created_at
        FROM chain_assets
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([max(1, min(int(limit), 500)), max(0, int(offset))])

    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def _pending_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    data = dict(row)
    try:
        data["chunks"] = json.loads(data.pop("chunks_json") or "[]")
    except (TypeError, json.JSONDecodeError):
        data["chunks"] = []
        data.pop("chunks_json", None)
    data["anchor_requested"] = bool(data.get("anchor_requested"))
    return data


def pending_submission_for_key(asset_key: str, *, status: str = "pending") -> Optional[Dict[str, Any]]:
    init_db()
    key = (asset_key or "").strip()
    if not key:
        return None
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM chain_mesh_pending_submissions
            WHERE asset_key = ? AND status = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (key, str(status)),
        ).fetchone()
    return _pending_row_to_dict(row) if row else None


def create_pending_submission(
    *,
    asset_key: str,
    display_name: str,
    mime_type: str,
    version: str,
    file_size: int,
    file_sha256: str,
    merkle_root: str,
    chunks: List[Dict[str, Any]],
    anchor_requested: bool = True,
    submitter_address: str = "",
    submitter_device_id: str = "",
    submitter_note: str = "",
) -> Dict[str, Any]:
    init_db()
    key = (asset_key or "").strip()
    if not key:
        raise ValueError("asset_key required")
    if pending_submission_for_key(key, status="pending"):
        raise ValueError(f"asset_key already pending review: {key}")
    now = _now()
    chunks_json = json.dumps(chunks, separators=(",", ":"))
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO chain_mesh_pending_submissions (
                status, asset_key, display_name, mime_type, version,
                file_size, file_sha256, merkle_root, chunk_count, chunks_json,
                anchor_requested, submitter_address, submitter_device_id,
                submitter_note, created_at
            ) VALUES ('pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                (display_name or "")[:200],
                (mime_type or "application/octet-stream")[:120],
                (version or "")[:64],
                int(file_size),
                (file_sha256 or "").strip().lower(),
                (merkle_root or "").strip().lower(),
                len(chunks),
                chunks_json,
                1 if anchor_requested else 0,
                (submitter_address or "")[:120],
                (submitter_device_id or "")[:120],
                (submitter_note or "")[:500],
                now,
            ),
        )
        row_id = int(cur.lastrowid)
    row = get_pending_submission(row_id)
    if not row:
        raise RuntimeError("failed to load pending submission")
    return row


def get_pending_submission(submission_id: int) -> Optional[Dict[str, Any]]:
    init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM chain_mesh_pending_submissions WHERE id = ?",
            (int(submission_id),),
        ).fetchone()
    return _pending_row_to_dict(row) if row else None


def list_pending_submissions(
    *,
    status: str = "pending",
    limit: int = 50,
) -> List[Dict[str, Any]]:
    init_db()
    st = (status or "pending").strip().lower()
    with _conn() as conn:
        if st == "all":
            rows = conn.execute(
                """
                SELECT * FROM chain_mesh_pending_submissions
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM chain_mesh_pending_submissions
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (st, max(1, min(int(limit), 200))),
            ).fetchall()
    return [_pending_row_to_dict(r) for r in rows]


def update_pending_submission_status(
    submission_id: int,
    *,
    status: str,
    reviewed_by: str = "",
    rejection_reason: str = "",
    published_asset_id: str = "",
) -> Optional[Dict[str, Any]]:
    init_db()
    now = _now()
    with _conn() as conn:
        conn.execute(
            """
            UPDATE chain_mesh_pending_submissions SET
                status = ?,
                reviewed_at = ?,
                reviewed_by = ?,
                rejection_reason = ?,
                published_asset_id = COALESCE(NULLIF(?, ''), published_asset_id)
            WHERE id = ? AND status = 'pending'
            """,
            (
                str(status),
                now,
                (reviewed_by or "")[:120],
                (rejection_reason or "")[:500],
                (published_asset_id or "").strip().lower(),
                int(submission_id),
            ),
        )
    return get_pending_submission(submission_id)


def record_time_capsule_event(
    *,
    action: str,
    block_height: int,
    best_block_hash: str,
    chunk_count: int = 0,
    coordinator_coverage_pct: float = 0.0,
    blocks_bytes: int = 0,
    pruned: bool = False,
    prune_mib: Optional[int] = None,
    txindex_disabled: bool = False,
    message: str = "",
) -> int:
    init_db()
    now = _now()
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO chain_time_capsule_events (
                action, block_height, best_block_hash, chunk_count,
                coordinator_coverage_pct, blocks_bytes, pruned, prune_mib,
                txindex_disabled, message, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (action or "")[:32],
                int(block_height),
                (best_block_hash or "")[:64],
                int(chunk_count),
                float(coordinator_coverage_pct),
                int(blocks_bytes),
                1 if pruned else 0,
                int(prune_mib) if prune_mib is not None else None,
                1 if txindex_disabled else 0,
                (message or "")[:500],
                now,
            ),
        )
        return int(cur.lastrowid)


def list_time_capsule_events(*, limit: int = 10) -> List[Dict[str, Any]]:
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT action, block_height, best_block_hash, chunk_count,
                   coordinator_coverage_pct, blocks_bytes, pruned, prune_mib,
                   txindex_disabled, message, created_at
            FROM chain_time_capsule_events
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 50)),),
        ).fetchall()
    return [dict(r) for r in rows]