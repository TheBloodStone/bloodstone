"""Sovereign Mesh Wave A — digital provenance anchor + verify (Trust Anchor L1)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional

import requests

from chain_mesh import blurt_registry_v2 as blurt_reg
from chain_mesh import db as mesh_db
from chain_mesh import mesh_v2_lite as v2

PROVENANCE_ID = "bloodstone_provenance/v1"
SHA256_RE = re.compile(r"^[a-f0-9]{64}$", re.I)

BLURT_RPC_NODES = blurt_reg.BLURT_RPC_NODES
REGISTRY_ACCOUNTS = blurt_reg.REGISTRY_ACCOUNTS


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def init_provenance_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bloodstone_provenance_anchors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provenance_id TEXT NOT NULL,
                asset_key TEXT NOT NULL,
                author TEXT NOT NULL DEFAULT '',
                content_sha256 TEXT NOT NULL,
                mesh_merkle_root TEXT NOT NULL DEFAULT '',
                device_id TEXT NOT NULL DEFAULT '',
                witness_capsule_id TEXT NOT NULL DEFAULT '',
                anchor_json TEXT NOT NULL DEFAULT '{}',
                trx_id TEXT NOT NULL DEFAULT '',
                block_num INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                is_current INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_provenance_asset
                ON bloodstone_provenance_anchors(asset_key, is_current DESC);
            CREATE INDEX IF NOT EXISTS idx_provenance_id
                ON bloodstone_provenance_anchors(provenance_id);
            """
        )


def _normalize_sha256(value: str) -> str:
    h = (value or "").strip().lower()
    if not SHA256_RE.match(h):
        raise ValueError("content_sha256 must be 64 hex chars")
    return h


def provenance_asset_key(*, provenance_id: str, filename: str = "original") -> str:
    pid = re.sub(r"[^a-zA-Z0-9\-_]", "-", (provenance_id or "").strip())[:64]
    fname = (filename or "original").strip().lstrip("/")
    if ".." in fname:
        raise ValueError("invalid filename")
    return f"assets/blurt/provenance/{pid}/{fname}"


def build_provenance_anchor(
    *,
    author: str,
    asset_key: str,
    content_sha256: str,
    title: str = "",
    device_id: str = "",
    captured_at: Optional[int] = None,
    witness_capsule_id: str = "",
    provenance_id: str = "",
) -> Dict[str, Any]:
    """Layer 1 Trust Anchor — Blurt custom_json + mesh pointer."""
    key = (asset_key or "").strip().lstrip("/")
    if not key.startswith("assets/"):
        raise ValueError("asset_key must be under assets/")
    content_hash = _normalize_sha256(content_sha256)
    auth = (author or "").lstrip("@").lower()
    if not auth:
        raise ValueError("author required")

    mesh_merkle = ""
    mesh_file_sha = ""
    resolved = v2.resolve_manifest(key)
    if resolved.get("ok"):
        manifest = resolved.get("manifest") or {}
        mesh_merkle = str(manifest.get("manifest_merkle_root") or "").lower()
        mesh_file_sha = str(manifest.get("file_sha256") or "").lower()
        if mesh_file_sha and mesh_file_sha != content_hash:
            raise ValueError(
                f"content_sha256 mismatch vs mesh file_sha256 ({mesh_file_sha[:12]}…)"
            )

    pid = (provenance_id or "").strip() or content_hash[:16]
    body = {
        "v": "1",
        "provenance_id": pid,
        "author": auth,
        "asset_key": key,
        "content_sha256": content_hash,
        "mesh_merkle_root": mesh_merkle,
        "mesh_spec": blurt_reg.RFC_VERSION,
        "title": (title or "")[:200],
        "device_id": (device_id or "")[:128],
        "captured_at": int(captured_at or _now()),
        "anchored_at": _now(),
    }
    if witness_capsule_id:
        body["witness_capsule_id"] = witness_capsule_id.strip()
    return {
        "id": PROVENANCE_ID,
        "required_posting_auths": [auth],
        "required_auths": [],
        "json": json.dumps(body, separators=(",", ":"), sort_keys=True),
        "body": body,
    }


def index_provenance_anchor(
    *,
    body: Dict[str, Any],
    author: str = "",
    trx_id: str = "",
    block_num: int = 0,
) -> Dict[str, Any]:
    init_provenance_db()
    key = str(body.get("asset_key") or "").strip()
    pid = str(body.get("provenance_id") or uuid.uuid4().hex[:16])
    now = _now()
    with _conn() as conn:
        conn.execute(
            "UPDATE bloodstone_provenance_anchors SET is_current = 0 WHERE asset_key = ?",
            (key,),
        )
        cur = conn.execute(
            """
            INSERT INTO bloodstone_provenance_anchors (
                provenance_id, asset_key, author, content_sha256,
                mesh_merkle_root, device_id, witness_capsule_id,
                anchor_json, trx_id, block_num, created_at, is_current
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                pid,
                key,
                str(author or body.get("author") or "").lstrip("@").lower(),
                str(body.get("content_sha256") or "").lower(),
                str(body.get("mesh_merkle_root") or "").lower(),
                str(body.get("device_id") or ""),
                str(body.get("witness_capsule_id") or ""),
                json.dumps(body),
                str(trx_id or ""),
                int(block_num),
                now,
            ),
        )
        return {"ok": True, "id": int(cur.lastrowid), "provenance_id": pid, "asset_key": key}


def get_provenance_anchor(*, asset_key: str = "", provenance_id: str = "") -> Optional[Dict[str, Any]]:
    init_provenance_db()
    with _conn() as conn:
        if provenance_id:
            row = conn.execute(
                """
                SELECT * FROM bloodstone_provenance_anchors
                WHERE provenance_id = ? AND is_current = 1
                ORDER BY created_at DESC LIMIT 1
                """,
                (provenance_id.strip(),),
            ).fetchone()
        elif asset_key:
            row = conn.execute(
                """
                SELECT * FROM bloodstone_provenance_anchors
                WHERE asset_key = ? AND is_current = 1
                ORDER BY created_at DESC LIMIT 1
                """,
                (asset_key.strip().lstrip("/"),),
            ).fetchone()
        else:
            return None
    if not row:
        return None
    item = dict(row)
    item["body"] = json.loads(item.get("anchor_json") or "{}")
    return item


def verify_badge_html(*, verified: bool, detail: str = "") -> str:
    title = detail or ("Cryptographic provenance verified" if verified else "Provenance check failed")
    if verified:
        return (
            f'<span class="bs-provenance bs-provenance-ok" title="{title}" '
            f'style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;'
            f'border-radius:6px;background:#1a3d2e;color:#3fb950;font-size:0.85rem;">'
            f'<span aria-hidden="true">✓</span> Verified origin</span>'
        )
    return (
        f'<span class="bs-provenance bs-provenance-fail" title="{title}" '
        f'style="display:inline-flex;align-items:center;gap:4px;padding:2px 8px;'
        f'border-radius:6px;background:#3d1a1a;color:#f85149;font-size:0.85rem;">'
        f'<span aria-hidden="true">✗</span> Unverified</span>'
    )


def verify_provenance(
    *,
    asset_key: str = "",
    provenance_id: str = "",
    content_sha256: str = "",
) -> Dict[str, Any]:
    """Post-Truth Engine — mesh + anchor + optional witness checks."""
    key = (asset_key or "").strip().lstrip("/")
    anchor = get_provenance_anchor(asset_key=key, provenance_id=provenance_id)
    if anchor and not key:
        key = str(anchor.get("asset_key") or "")
    if not key:
        return {"ok": False, "verified": False, "error": "asset_key or provenance_id required"}

    checks: Dict[str, Any] = {}
    declared_hash = (content_sha256 or (anchor or {}).get("content_sha256") or "").strip().lower()
    if declared_hash and not SHA256_RE.match(declared_hash):
        return {"ok": False, "verified": False, "error": "invalid content_sha256"}

    resolved = v2.resolve_manifest(key)
    checks["mesh_resolved"] = bool(resolved.get("ok"))
    checks["mesh_source"] = resolved.get("source")

    mesh_hash = ""
    mesh_merkle = ""
    if resolved.get("ok"):
        manifest = resolved.get("manifest") or {}
        mesh_hash = str(manifest.get("file_sha256") or "").lower()
        mesh_merkle = str(manifest.get("manifest_merkle_root") or "").lower()
        checks["mesh_file_sha256"] = mesh_hash
        checks["mesh_merkle_root"] = mesh_merkle

    checks["anchor_indexed"] = anchor is not None
    if anchor:
        checks["anchor_author"] = anchor.get("author")
        checks["anchor_trx_id"] = anchor.get("trx_id")
        declared_hash = declared_hash or str(anchor.get("content_sha256") or "").lower()

    hash_match = False
    if declared_hash and mesh_hash:
        hash_match = declared_hash == mesh_hash
        checks["content_hash_match"] = hash_match
    elif declared_hash and not mesh_hash:
        checks["content_hash_match"] = None
    else:
        checks["content_hash_match"] = None

    merkle_match = True
    if anchor and mesh_merkle:
        anchor_merkle = str((anchor.get("body") or {}).get("mesh_merkle_root") or anchor.get("mesh_merkle_root") or "").lower()
        if anchor_merkle:
            merkle_match = anchor_merkle == mesh_merkle
            checks["merkle_match"] = merkle_match

    witness_ok = None
    witness_id = str((anchor or {}).get("witness_capsule_id") or (anchor or {}).get("body", {}).get("witness_capsule_id") or "")
    if witness_id:
        try:
            import bloodstone_witness as witness

            caps = witness.list_capsules(limit=200)
            witness_ok = any(
                str(c.get("capsule_id") or "") == witness_id for c in (caps.get("capsules") or [])
            )
            checks["witness_capsule_found"] = witness_ok
        except Exception as exc:
            checks["witness_capsule_found"] = False
            checks["witness_error"] = str(exc)

    verified = (
        checks.get("mesh_resolved")
        and (hash_match if declared_hash and mesh_hash else checks.get("mesh_resolved"))
        and merkle_match
        and (witness_ok is not False)
    )

    reason = "Cryptographic provenance verified against mesh manifest."
    if not checks.get("mesh_resolved"):
        reason = "Mesh manifest not found — cannot verify content hash."
        verified = False
    elif declared_hash and mesh_hash and not hash_match:
        reason = "Declared content hash does not match mesh file_sha256."
        verified = False
    elif not merkle_match:
        reason = "Anchor merkle root does not match live mesh manifest."
        verified = False
    elif witness_ok is False:
        reason = "Referenced witness capsule not found in quorum index."
        verified = False
    elif not anchor:
        reason = "Mesh verified; Blurt provenance anchor not yet indexed (broadcast custom_json)."

    public = os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org").rstrip("/")
    return {
        "ok": True,
        "verified": bool(verified),
        "layer": 1,
        "use_case": "post_truth_reality_engine",
        "asset_key": key,
        "provenance_id": (anchor or {}).get("provenance_id") or (anchor or {}).get("body", {}).get("provenance_id"),
        "content_sha256": declared_hash or mesh_hash,
        "checks": checks,
        "reason": reason,
        "verify_url": f"{public}/api/convergence/provenance/verify?asset_key={key}",
        "badge_html": verify_badge_html(verified=bool(verified), detail=reason),
        "anchor": anchor,
    }


def anchor_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    asset_key = str(payload.get("asset_key") or "").strip()
    if not asset_key and payload.get("provenance_id") and payload.get("filename"):
        asset_key = provenance_asset_key(
            provenance_id=str(payload.get("provenance_id")),
            filename=str(payload.get("filename")),
        )
    custom = build_provenance_anchor(
        author=str(payload.get("author") or ""),
        asset_key=asset_key,
        content_sha256=str(payload.get("content_sha256") or ""),
        title=str(payload.get("title") or ""),
        device_id=str(payload.get("device_id") or ""),
        captured_at=payload.get("captured_at"),
        witness_capsule_id=str(payload.get("witness_capsule_id") or ""),
        provenance_id=str(payload.get("provenance_id") or ""),
    )
    body = custom["body"]
    index_provenance_anchor(body=body, author=body.get("author", ""))
    verify = verify_provenance(asset_key=body["asset_key"], content_sha256=body["content_sha256"])
    public = os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org").rstrip("/")
    return {
        "ok": True,
        "layer": 1,
        "blurt_custom_json": {
            "id": custom["id"],
            "required_posting_auths": custom.get("required_posting_auths") or [],
            "json": custom["json"],
        },
        "body": body,
        "verification": verify,
        "badge_html": verify.get("badge_html"),
        "verify_url": f"{public}/api/convergence/provenance/verify?asset_key={body['asset_key']}",
        "next_steps": [
            "Publish asset to mesh (partner publish or existing asset_key)",
            f"Broadcast {PROVENANCE_ID} custom_json on Blurt",
            "Embed badge_html alongside Condenser post body or provenance verify URL",
        ],
    }


def _parse_provenance_op(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if str(data.get("v") or "") != "1":
        return None
    asset_key = str(data.get("asset_key") or "").strip()
    content = str(data.get("content_sha256") or "").strip().lower()
    if not asset_key or not SHA256_RE.match(content):
        return None
    return data


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


def sync_account_provenance(account: str, *, limit: int = 200) -> Dict[str, Any]:
    """Scan Blurt history for bloodstone_provenance/v1 ops."""
    init_provenance_db()
    acct = (account or "").lstrip("@").lower()
    history = _blurt_rpc(
        "database_api.get_account_history",
        [acct, -1, limit, 1000000000],
    )
    indexed = 0
    for item in history or []:
        op = (item.get("op") or [])[1] if isinstance(item.get("op"), list) else {}
        if not isinstance(op, dict) or op.get("id") != PROVENANCE_ID:
            continue
        try:
            data = json.loads(op.get("json") or "{}")
        except json.JSONDecodeError:
            continue
        body = _parse_provenance_op(data)
        if not body:
            continue
        index_provenance_anchor(
            body=body,
            author=acct,
            trx_id=str(item.get("trx_id") or ""),
            block_num=int(item.get("block") or 0),
        )
        indexed += 1
    return {"ok": True, "account": acct, "indexed": indexed}


def sync_registry_provenance() -> Dict[str, Any]:
    results = []
    for acct in REGISTRY_ACCOUNTS:
        try:
            results.append(sync_account_provenance(acct))
        except Exception as exc:
            results.append({"ok": False, "account": acct, "error": str(exc)})
    return {"ok": True, "accounts": results}