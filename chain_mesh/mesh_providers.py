"""Chain Mesh v2.0-Lite provider registry (DHT bootstrap + storage nodes)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db

DEFAULT_PROVIDER_ID = os.environ.get(
    "CHAIN_MESH_PROVIDER_PEER_ID", "bloodstone-coordinator-v1"
)
DEFAULT_MULTIADDR = os.environ.get(
    "CHAIN_MESH_PROVIDER_MULTIADDR",
    "/dns4/bloodstonewallet.mytunnel.org/tcp/443/https",
)


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def init_providers_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS mesh_provider_nodes (
                peer_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL DEFAULT '',
                multiaddrs TEXT NOT NULL DEFAULT '[]',
                roles TEXT NOT NULL DEFAULT '[]',
                tenant TEXT NOT NULL DEFAULT '',
                read_only INTEGER NOT NULL DEFAULT 0,
                storage_enabled INTEGER NOT NULL DEFAULT 1,
                last_seen INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_mesh_provider_tenant
                ON mesh_provider_nodes(tenant, last_seen DESC);

            CREATE TABLE IF NOT EXISTS mesh_chunk_providers (
                chunk_hash TEXT NOT NULL,
                peer_id TEXT NOT NULL,
                announced_at INTEGER NOT NULL,
                PRIMARY KEY (chunk_hash, peer_id)
            );
            CREATE INDEX IF NOT EXISTS idx_mesh_chunk_providers_hash
                ON mesh_chunk_providers(chunk_hash);
            """
        )


def register_provider(
    *,
    peer_id: str,
    multiaddrs: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
    display_name: str = "",
    tenant: str = "",
    read_only: bool = False,
    storage_enabled: bool = True,
) -> Dict[str, Any]:
    init_providers_db()
    pid = (peer_id or "").strip()
    if not pid:
        raise ValueError("peer_id required")
    addrs = [str(a).strip() for a in (multiaddrs or []) if str(a).strip()]
    role_list = [str(r).strip().lower() for r in (roles or ["storage"]) if str(r).strip()]
    now = _now()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO mesh_provider_nodes (
                peer_id, display_name, multiaddrs, roles, tenant,
                read_only, storage_enabled, last_seen, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(peer_id) DO UPDATE SET
                display_name = excluded.display_name,
                multiaddrs = excluded.multiaddrs,
                roles = excluded.roles,
                tenant = excluded.tenant,
                read_only = excluded.read_only,
                storage_enabled = excluded.storage_enabled,
                last_seen = excluded.last_seen
            """,
            (
                pid,
                (display_name or pid)[:120],
                json.dumps(addrs),
                json.dumps(role_list),
                (tenant or "")[:64],
                1 if read_only else 0,
                1 if storage_enabled else 0,
                now,
                now,
            ),
        )
    return {"ok": True, "peer_id": pid, "multiaddrs": addrs, "roles": role_list}


def ensure_default_provider() -> Dict[str, Any]:
    return register_provider(
        peer_id=DEFAULT_PROVIDER_ID,
        multiaddrs=[DEFAULT_MULTIADDR],
        roles=["storage", "compute", "bandwidth", "coordinator"],
        display_name="Bloodstone coordinator (v1 catalog + v2 provider)",
        tenant="bloodstone",
        read_only=False,
        storage_enabled=True,
    )


def list_providers(*, tenant: str = "", role: str = "") -> List[Dict[str, Any]]:
    init_providers_db()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM mesh_provider_nodes
            ORDER BY last_seen DESC
            """
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["multiaddrs"] = json.loads(item.get("multiaddrs") or "[]")
        item["roles"] = json.loads(item.get("roles") or "[]")
        item["read_only"] = bool(item.get("read_only"))
        item["storage_enabled"] = bool(item.get("storage_enabled"))
        if tenant and item.get("tenant") != tenant:
            continue
        if role and role.lower() not in item["roles"]:
            continue
        out.append(item)
    return out


def announce_chunks(peer_id: str, chunk_hashes: List[str]) -> Dict[str, Any]:
    init_providers_db()
    pid = (peer_id or "").strip()
    if not pid:
        raise ValueError("peer_id required")
    now = _now()
    announced = 0
    with _conn() as conn:
        for raw in chunk_hashes:
            h = (raw or "").strip().lower()
            if len(h) != 64:
                continue
            conn.execute(
                """
                INSERT INTO mesh_chunk_providers (chunk_hash, peer_id, announced_at)
                VALUES (?, ?, ?)
                ON CONFLICT(chunk_hash, peer_id) DO UPDATE SET announced_at = excluded.announced_at
                """,
                (h, pid, now),
            )
            announced += 1
        conn.execute(
            "UPDATE mesh_provider_nodes SET last_seen = ? WHERE peer_id = ?",
            (now, pid),
        )
    return {"ok": True, "peer_id": pid, "announced": announced}


def providers_for_chunk(chunk_hash: str) -> List[str]:
    init_providers_db()
    h = (chunk_hash or "").strip().lower()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT peer_id FROM mesh_chunk_providers
            WHERE chunk_hash = ?
            ORDER BY announced_at DESC
            """,
            (h,),
        ).fetchall()
    return [str(r["peer_id"]) for r in rows]


def peer_id_for_device(device_id: str) -> str:
    did = (device_id or "bloodstone").strip().lower()
    digest = hashlib.sha256(did.encode("utf-8")).hexdigest()[:32]
    return f"12D3KooW{digest}"