"""Blurt Chain Mesh v2.0-Lite registry — custom_json anchors on Blurt Layer 1."""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional

import requests

from chain_mesh import db as mesh_db
from chain_mesh.merkle import merkle_root

RFC_VERSION = "2.0-lite"
CUSTOM_JSON_ID = "chain_mesh_anchor"
BLURT_RPC_NODES = [
    n.strip()
    for n in os.environ.get(
        "BLURT_REGISTRY_RPC_NODES", "https://rpc.blurt.blog,https://blurt-rpc.saboin.com"
    ).split(",")
    if n.strip()
]
REGISTRY_ACCOUNTS = [
    a.strip().lstrip("@").lower()
    for a in os.environ.get(
        "BLURT_MESH_REGISTRY_ACCOUNTS", "megadrive,bloodstone"
    ).split(",")
    if a.strip()
]


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def init_blurt_registry_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS blurt_mesh_anchors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_key TEXT NOT NULL,
                block_num INTEGER NOT NULL DEFAULT 0,
                trx_id TEXT NOT NULL DEFAULT '',
                author TEXT NOT NULL DEFAULT '',
                manifest_merkle_root TEXT NOT NULL,
                file_sha256 TEXT NOT NULL,
                file_size INTEGER NOT NULL DEFAULT 0,
                mime_type TEXT NOT NULL DEFAULT '',
                provider_ids TEXT NOT NULL DEFAULT '[]',
                replication_factor INTEGER NOT NULL DEFAULT 1,
                chunk_hashes TEXT NOT NULL DEFAULT '[]',
                uploader_signature TEXT NOT NULL DEFAULT '',
                anchor_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                is_current INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_blurt_mesh_anchors_key
                ON blurt_mesh_anchors(asset_key, is_current DESC, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_blurt_mesh_anchors_trx
                ON blurt_mesh_anchors(trx_id);
            """
        )


def build_custom_json_anchor(
    *,
    asset_key: str,
    manifest_merkle_root: str,
    file_sha256: str,
    file_size: int,
    mime_type: str,
    provider_ids: List[str],
    chunk_hashes: List[str],
    replication_factor: int = 3,
    uploader_signature: str = "",
    timestamp: Optional[int] = None,
) -> Dict[str, Any]:
    """RFC §3.1 — payload Blurt backend broadcasts via custom_json."""
    root = (manifest_merkle_root or "").strip().lower()
    fhash = (file_sha256 or "").strip().lower()
    if len(root) != 64 or len(fhash) != 64:
        raise ValueError("merkle_root and file_sha256 must be 64 hex chars")
    providers = [str(p).strip() for p in provider_ids if str(p).strip()]
    hashes = [(h or "").strip().lower() for h in chunk_hashes if (h or "").strip()]
    if not hashes:
        raise ValueError("chunk_hashes required")
    computed = merkle_root(hashes)
    if computed != root:
        raise ValueError("merkle_root does not match chunk_hashes")
    body = {
        "v": RFC_VERSION,
        "asset_key": (asset_key or "").strip(),
        "manifest_merkle_root": root,
        "file_sha256": fhash,
        "file_size": int(file_size),
        "mime_type": (mime_type or "application/octet-stream")[:120],
        "provider_ids": providers,
        "replication_factor": max(1, int(replication_factor)),
        "chunk_hashes": hashes,
        "uploader_signature": (uploader_signature or "").strip(),
        "timestamp": int(timestamp or _now()),
    }
    return {
        "id": CUSTOM_JSON_ID,
        "required_posting_auths": [],
        "required_auths": [],
        "json": json.dumps(body, separators=(",", ":"), sort_keys=True),
        "body": body,
    }


def parse_custom_json_body(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(str(raw))
        except (TypeError, json.JSONDecodeError):
            return None
    if str(data.get("v") or "") not in (RFC_VERSION, "2.0", "2.0-lite"):
        return None
    asset_key = str(data.get("asset_key") or "").strip()
    root = str(data.get("manifest_merkle_root") or "").strip().lower()
    fhash = str(data.get("file_sha256") or "").strip().lower()
    if not asset_key or len(root) != 64 or len(fhash) != 64:
        return None
    return data


def index_anchor(
    *,
    asset_key: str,
    body: Dict[str, Any],
    author: str = "",
    trx_id: str = "",
    block_num: int = 0,
) -> Dict[str, Any]:
    init_blurt_registry_db()
    key = (asset_key or "").strip()
    now = _now()
    with _conn() as conn:
        conn.execute(
            "UPDATE blurt_mesh_anchors SET is_current = 0 WHERE asset_key = ?",
            (key,),
        )
        cur = conn.execute(
            """
            INSERT INTO blurt_mesh_anchors (
                asset_key, block_num, trx_id, author,
                manifest_merkle_root, file_sha256, file_size, mime_type,
                provider_ids, replication_factor, chunk_hashes,
                uploader_signature, anchor_json, created_at, is_current
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                key,
                int(block_num),
                str(trx_id or ""),
                str(author or "").lstrip("@").lower(),
                str(body.get("manifest_merkle_root") or "").lower(),
                str(body.get("file_sha256") or "").lower(),
                int(body.get("file_size") or 0),
                str(body.get("mime_type") or ""),
                json.dumps(body.get("provider_ids") or []),
                int(body.get("replication_factor") or 1),
                json.dumps(body.get("chunk_hashes") or []),
                str(body.get("uploader_signature") or ""),
                json.dumps(body),
                now,
            ),
        )
        return {"ok": True, "id": int(cur.lastrowid), "asset_key": key}


def get_anchor(asset_key: str) -> Optional[Dict[str, Any]]:
    init_blurt_registry_db()
    key = (asset_key or "").strip()
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM blurt_mesh_anchors
            WHERE asset_key = ? AND is_current = 1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (key,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["provider_ids"] = json.loads(item.get("provider_ids") or "[]")
    item["chunk_hashes"] = json.loads(item.get("chunk_hashes") or "[]")
    item["anchor"] = json.loads(item.get("anchor_json") or "{}")
    return item


def manifest_from_coordinator_asset(asset: Dict[str, Any]) -> Dict[str, Any]:
    chunks = asset.get("chunks") or []
    hashes = [str(c.get("chunk_hash") or c.get("hash") or "") for c in chunks]
    return {
        "v": RFC_VERSION,
        "asset_key": asset.get("asset_key") or "",
        "manifest_merkle_root": asset.get("merkle_root") or "",
        "file_sha256": asset.get("file_sha256") or "",
        "file_size": int(asset.get("file_size") or 0),
        "mime_type": asset.get("mime_type") or "",
        "provider_ids": [],
        "replication_factor": 1,
        "chunk_hashes": [h for h in hashes if h],
        "source": "coordinator",
    }


def _blurt_rpc(method: str, params: List[Any]) -> Any:
    last_err = None
    for node in BLURT_RPC_NODES:
        try:
            resp = requests.post(
                node,
                json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
                timeout=20,
            )
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("error"):
                raise RuntimeError(payload["error"])
            return payload.get("result")
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"Blurt RPC failed: {last_err}")


def sync_account_anchors(account: str, *, limit: int = 200) -> Dict[str, Any]:
    """Scan recent account history for chain_mesh_anchor custom_json ops."""
    init_blurt_registry_db()
    acct = (account or "").lstrip("@").lower()
    history = _blurt_rpc(
        "database_api.get_account_history",
        [acct, -1, limit, 1000000000],
    )
    indexed = 0
    for entry in history or []:
        op = entry.get("op") or []
        if len(op) < 2 or op[0] != "custom_json":
            continue
        data = op[1] or {}
        if str(data.get("id") or "") != CUSTOM_JSON_ID:
            continue
        body = parse_custom_json_body(data.get("json"))
        if not body:
            continue
        index_anchor(
            asset_key=str(body.get("asset_key") or ""),
            body=body,
            author=acct,
            trx_id=str(entry.get("trx_id") or ""),
            block_num=int(entry.get("block") or 0),
        )
        indexed += 1
    return {"ok": True, "account": acct, "indexed": indexed}


def sync_registry_accounts() -> Dict[str, Any]:
    results = []
    for acct in REGISTRY_ACCOUNTS:
        try:
            results.append(sync_account_anchors(acct))
        except Exception as exc:
            results.append({"ok": False, "account": acct, "error": str(exc)})
    return {"ok": True, "accounts": results}