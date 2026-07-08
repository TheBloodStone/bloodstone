"""Sovereign Mesh Wave B — machine agent identity (bloodstone_agent/v1)."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional

import requests

from chain_mesh import blurt_registry_v2 as blurt_reg

AGENT_ID = "bloodstone_agent/v1"
VALID_CAPABILITIES = frozenset(
    {
        "publish",
        "compute",
        "storage",
        "bandwidth",
        "sensor",
        "provenance",
        "relay",
    }
)
AGENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]{2,63}$", re.I)

BLURT_RPC_NODES = blurt_reg.BLURT_RPC_NODES
REGISTRY_ACCOUNTS = blurt_reg.REGISTRY_ACCOUNTS


def _now() -> int:
    return int(time.time())


def _conn():
    from chain_mesh import db as mesh_db

    mesh_db.init_db()
    return mesh_db._conn()


def init_agent_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bloodstone_agent_identities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                blurt_author TEXT NOT NULL,
                stone_address TEXT NOT NULL DEFAULT '',
                capabilities TEXT NOT NULL DEFAULT '[]',
                display_name TEXT NOT NULL DEFAULT '',
                pubkey_hint TEXT NOT NULL DEFAULT '',
                agent_json TEXT NOT NULL DEFAULT '{}',
                trx_id TEXT NOT NULL DEFAULT '',
                block_num INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                is_current INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_agent_blurt
                ON bloodstone_agent_identities(blurt_author, is_current DESC);
            CREATE INDEX IF NOT EXISTS idx_agent_id
                ON bloodstone_agent_identities(agent_id, is_current DESC);
            """
        )


def _normalize_capabilities(raw: Any) -> List[str]:
    caps: List[str] = []
    for item in raw or []:
        tag = str(item or "").strip().lower()
        if tag in VALID_CAPABILITIES and tag not in caps:
            caps.append(tag)
    return caps


def _normalize_agent_id(value: str, *, author: str = "") -> str:
    aid = (value or "").strip().lower()
    if not aid:
        auth = (author or "").lstrip("@").lower()
        aid = f"{auth}-agent" if auth else uuid.uuid4().hex[:12]
    aid = re.sub(r"[^a-z0-9\-_]", "-", aid).strip("-_")[:64]
    if not AGENT_ID_RE.match(aid):
        raise ValueError("agent_id must be 3–64 chars: letters, digits, - _")
    return aid


def build_agent_manifest(
    *,
    blurt_author: str,
    stone_address: str,
    agent_id: str = "",
    capabilities: Optional[List[str]] = None,
    display_name: str = "",
    pubkey_hint: str = "",
) -> Dict[str, Any]:
    """Layer 0 — Blurt custom_json machine identity manifest."""
    auth = (blurt_author or "").lstrip("@").lower()
    if not auth:
        raise ValueError("blurt_author required")
    stone = (stone_address or "").strip()
    if len(stone) < 25:
        raise ValueError("stone_address required")
    aid = _normalize_agent_id(agent_id, author=auth)
    caps = _normalize_capabilities(capabilities or ["publish"])
    if not caps:
        caps = ["publish"]
    now = _now()
    body = {
        "v": "1",
        "agent_id": aid,
        "blurt_author": auth,
        "stone_address": stone,
        "capabilities": caps,
        "display_name": (display_name or aid)[:120],
        "pubkey_hint": (pubkey_hint or "")[:128],
        "registered_at": now,
        "updated_at": now,
    }
    return {
        "id": AGENT_ID,
        "required_posting_auths": [auth],
        "required_auths": [],
        "json": json.dumps(body, separators=(",", ":"), sort_keys=True),
        "body": body,
    }


def index_agent_identity(
    *,
    body: Dict[str, Any],
    author: str = "",
    trx_id: str = "",
    block_num: int = 0,
) -> Dict[str, Any]:
    init_agent_db()
    aid = str(body.get("agent_id") or "").strip().lower()
    auth = str(author or body.get("blurt_author") or "").lstrip("@").lower()
    now = _now()
    with _conn() as conn:
        conn.execute(
            "UPDATE bloodstone_agent_identities SET is_current = 0 WHERE agent_id = ?",
            (aid,),
        )
        cur = conn.execute(
            """
            INSERT INTO bloodstone_agent_identities (
                agent_id, blurt_author, stone_address, capabilities,
                display_name, pubkey_hint, agent_json,
                trx_id, block_num, created_at, is_current
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                aid,
                auth,
                str(body.get("stone_address") or ""),
                json.dumps(body.get("capabilities") or []),
                str(body.get("display_name") or ""),
                str(body.get("pubkey_hint") or ""),
                json.dumps(body),
                str(trx_id or ""),
                int(block_num),
                now,
            ),
        )
        return {"ok": True, "id": int(cur.lastrowid), "agent_id": aid, "blurt_author": auth}


def get_agent_identity(
    *,
    agent_id: str = "",
    blurt_author: str = "",
) -> Optional[Dict[str, Any]]:
    init_agent_db()
    with _conn() as conn:
        if agent_id:
            row = conn.execute(
                """
                SELECT * FROM bloodstone_agent_identities
                WHERE agent_id = ? AND is_current = 1
                ORDER BY created_at DESC LIMIT 1
                """,
                (agent_id.strip().lower(),),
            ).fetchone()
        elif blurt_author:
            row = conn.execute(
                """
                SELECT * FROM bloodstone_agent_identities
                WHERE blurt_author = ? AND is_current = 1
                ORDER BY created_at DESC LIMIT 1
                """,
                (blurt_author.lstrip("@").lower(),),
            ).fetchone()
        else:
            return None
    if not row:
        return None
    item = dict(row)
    item["capabilities"] = json.loads(item.get("capabilities") or "[]")
    item["body"] = json.loads(item.get("agent_json") or "{}")
    return item


def verify_agent(
    *,
    agent_id: str = "",
    blurt_author: str = "",
) -> Dict[str, Any]:
    """Check indexed agent identity + capability tags."""
    aid = (agent_id or "").strip().lower()
    auth = (blurt_author or "").lstrip("@").lower()
    agent = get_agent_identity(agent_id=aid, blurt_author=auth if not aid else "")
    if agent and not aid:
        aid = str(agent.get("agent_id") or "")
    if not aid and not auth:
        return {"ok": False, "verified": False, "error": "agent_id or blurt_author required"}

    checks: Dict[str, Any] = {"anchor_indexed": agent is not None}
    verified = agent is not None
    reason = "Agent identity indexed — Blurt bloodstone_agent/v1 manifest found."
    if not agent:
        reason = "Agent not indexed — broadcast bloodstone_agent/v1 custom_json on Blurt."
        verified = False

    public = os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org").rstrip("/")
    query = f"agent_id={aid}" if aid else f"blurt_author={auth}"
    return {
        "ok": True,
        "verified": bool(verified),
        "layer": 0,
        "use_case": "autonomous_ai_creator_economy",
        "agent_id": aid or (agent or {}).get("agent_id"),
        "blurt_author": auth or (agent or {}).get("blurt_author"),
        "stone_address": (agent or {}).get("stone_address"),
        "capabilities": (agent or {}).get("capabilities") or [],
        "checks": checks,
        "reason": reason,
        "verify_url": f"{public}/api/convergence/agent/verify?{query}",
        "agent": agent,
    }


def register_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    custom = build_agent_manifest(
        blurt_author=str(payload.get("blurt_author") or payload.get("author") or ""),
        stone_address=str(payload.get("stone_address") or ""),
        agent_id=str(payload.get("agent_id") or ""),
        capabilities=payload.get("capabilities"),
        display_name=str(payload.get("display_name") or ""),
        pubkey_hint=str(payload.get("pubkey_hint") or ""),
    )
    body = custom["body"]
    index_agent_identity(body=body, author=body.get("blurt_author", ""))
    verify = verify_agent(agent_id=body["agent_id"])
    public = os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org").rstrip("/")
    return {
        "ok": True,
        "layer": 0,
        "blurt_custom_json": {
            "id": custom["id"],
            "required_posting_auths": custom.get("required_posting_auths") or [],
            "json": custom["json"],
        },
        "body": body,
        "verification": verify,
        "verify_url": f"{public}/api/convergence/agent/verify?agent_id={body['agent_id']}",
        "next_steps": [
            f"Broadcast {AGENT_ID} custom_json on Blurt",
            "Fund STONE address for mesh storage/compute/bandwidth memo rails",
            "Use POST /api/convergence/agent/publish-flow for autonomous post scaffold",
        ],
    }


def publish_flow_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Scaffold: agent identity + blog manifest + optional provenance pointer."""
    from chain_mesh import blog_manifest as blog

    auth = str(payload.get("blurt_author") or payload.get("author") or "")
    post_id = str(payload.get("post_id") or payload.get("permlink") or "")
    if not post_id:
        raise ValueError("post_id required")
    agent = register_payload(
        {
            "blurt_author": auth,
            "stone_address": str(payload.get("stone_address") or ""),
            "agent_id": str(payload.get("agent_id") or ""),
            "capabilities": payload.get("capabilities") or ["publish", "provenance"],
            "display_name": str(payload.get("display_name") or ""),
        }
    )
    asset_keys = payload.get("asset_keys") or []
    if not asset_keys:
        asset_keys = [
            blog.media_asset_key(
                post_id=post_id,
                filename=str(payload.get("filename") or "media.mp4"),
            )
        ]
    manifest = blog.build_post_manifest(
        post_id=post_id,
        author=auth,
        asset_keys=list(asset_keys),
        title=str(payload.get("title") or ""),
        permlink=str(payload.get("permlink") or post_id),
    )
    return {
        "ok": True,
        "layer": 0,
        "agent": agent,
        "blog_manifest": {
            "id": manifest["id"],
            "json": manifest["json"],
            "body": manifest["body"],
        },
        "credit_rails": {
            "storage_memo": f"storage:{agent['body']['stone_address']}:<bytes>",
            "compute_memo": f"compute:{agent['body']['stone_address']}:<job_id>",
            "bandwidth_memo": f"bandwidth:{agent['body']['stone_address']}:<bytes>",
        },
        "next_steps": [
            "Broadcast agent + blog custom_json ops on Blurt",
            "Publish media to mesh via partner publish",
            "Pay memo rails on Blurt to credit STONE address",
        ],
    }


def _parse_agent_op(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if str(data.get("v") or "") != "1":
        return None
    aid = str(data.get("agent_id") or "").strip().lower()
    auth = str(data.get("blurt_author") or "").lstrip("@").lower()
    stone = str(data.get("stone_address") or "").strip()
    if not aid or not auth or len(stone) < 25:
        return None
    data["capabilities"] = _normalize_capabilities(data.get("capabilities"))
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


def sync_account_agents(account: str, *, limit: int = 200) -> Dict[str, Any]:
    init_agent_db()
    acct = (account or "").lstrip("@").lower()
    history = _blurt_rpc(
        "database_api.get_account_history",
        [acct, -1, limit, 1000000000],
    )
    indexed = 0
    for item in history or []:
        op = (item.get("op") or [])[1] if isinstance(item.get("op"), list) else {}
        if not isinstance(op, dict) or op.get("id") != AGENT_ID:
            continue
        try:
            data = json.loads(op.get("json") or "{}")
        except json.JSONDecodeError:
            continue
        body = _parse_agent_op(data)
        if not body:
            continue
        index_agent_identity(
            body=body,
            author=acct,
            trx_id=str(item.get("trx_id") or ""),
            block_num=int(item.get("block") or 0),
        )
        indexed += 1
    return {"ok": True, "account": acct, "indexed": indexed}


def sync_registry_agents() -> Dict[str, Any]:
    results = []
    for acct in REGISTRY_ACCOUNTS:
        try:
            results.append(sync_account_agents(acct))
        except Exception as exc:
            results.append({"ok": False, "account": acct, "error": str(exc)})
    return {"ok": True, "accounts": results}