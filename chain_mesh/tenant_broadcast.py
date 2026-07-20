"""Wave V — Blurt on-chain tenant manifest broadcast + registry sync."""

from __future__ import annotations

from chain_mesh.security import public_error
import json
import os
import time
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db

TENANT_MANIFEST_ID = "bloodstone_tenant_manifest/v1"


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def _default_tenant() -> str:
    return (os.environ.get("DTN_DEFAULT_TENANT") or "bloodstone").strip()[:64] or "bloodstone"


def _normalize_author(value: str = "") -> str:
    return (value or "").lstrip("@").lower().strip()[:64]


def init_tenant_manifest_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tenant_manifest_index (
                manifest_key TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                blurt_account TEXT NOT NULL,
                stone_address TEXT NOT NULL DEFAULT '',
                manifest_json TEXT NOT NULL DEFAULT '{}',
                source TEXT NOT NULL DEFAULT 'local',
                trx_id TEXT NOT NULL DEFAULT '',
                block_num INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tenant_manifest_author
                ON tenant_manifest_index(blurt_account, updated_at DESC);
            """
        )


def _parse_manifest_body(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(data, dict):
        return None
    if str(data.get("v") or "") != "1":
        return None
    author = _normalize_author(str(data.get("blurt_account") or data.get("blurt_author") or data.get("author") or ""))
    tid = str(data.get("tenant_id") or _default_tenant()).strip()[:64]
    if not author:
        return None
    rails = data.get("rails") if isinstance(data.get("rails"), dict) else {}
    npu_models = data.get("npu_models") if isinstance(data.get("npu_models"), list) else []
    return {
        "v": "1",
        "format": TENANT_MANIFEST_ID,
        "tenant_id": tid,
        "blurt_account": author,
        "stone_address": str(data.get("stone_address") or "").strip(),
        "rails": rails,
        "npu_models": npu_models,
        "node_id": str(data.get("node_id") or "").strip()[:64],
        "updated_at": int(data.get("updated_at") or _now()),
    }


def build_tenant_manifest_body(
    *,
    tenant_id: str = "",
    blurt_account: str = "",
    stone_address: str = "",
    flops_cap: int = 0,
    bandwidth_bytes_cap: int = 0,
    storage_bytes_cap: int = 0,
    node_id: str = "",
) -> Dict[str, Any]:
    from chain_mesh import tenant_dashboard as tdash

    tid = (tenant_id or _default_tenant()).strip()[:64] or _default_tenant()
    author = _normalize_author(blurt_account)
    if not author:
        raise ValueError("blurt_account required")
    dash = tdash.dashboard_payload(
        tenant_id=tid,
        blurt_account=author,
        stone_address=stone_address,
    )
    rails = dash.get("rails") if isinstance(dash.get("rails"), dict) else {}
    if int(flops_cap or 0) > 0:
        rails.setdefault("compute", {})["flops_cap"] = int(flops_cap)
    if int(bandwidth_bytes_cap or 0) > 0:
        rails.setdefault("bandwidth", {})["bytes_cap"] = int(bandwidth_bytes_cap)
    if int(storage_bytes_cap or 0) > 0:
        rails.setdefault("storage", {})["bytes_cap"] = int(storage_bytes_cap)
    from chain_mesh import tenant_npu_models as tnpu

    npu_models = tnpu.npu_models_for_manifest(tenant_id=tid, blurt_account=author)
    return {
        "v": "1",
        "format": TENANT_MANIFEST_ID,
        "tenant_id": tid,
        "blurt_account": author,
        "stone_address": (stone_address or "").strip(),
        "rails": rails,
        "npu_models": npu_models,
        "node_id": (node_id or os.environ.get("DTN_NODE_ID") or "pi-edge").strip()[:64],
        "updated_at": _now(),
    }


def build_tenant_broadcast_manifest(
    *,
    tenant_id: str = "",
    blurt_account: str = "",
    stone_address: str = "",
    body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    parsed = _parse_manifest_body(body or {})
    if not parsed:
        parsed = build_tenant_manifest_body(
            tenant_id=tenant_id,
            blurt_account=blurt_account,
            stone_address=stone_address,
        )
    parsed["updated_at"] = _now()
    auth = parsed.get("blurt_account") or ""
    return {
        "id": TENANT_MANIFEST_ID,
        "required_posting_auths": [auth] if auth else [],
        "json": json.dumps(parsed, separators=(",", ":")),
        "body": parsed,
    }


def index_manifest(
    *,
    body: Dict[str, Any],
    source: str = "local",
    trx_id: str = "",
    block_num: int = 0,
) -> Dict[str, Any]:
    parsed = _parse_manifest_body(body)
    if not parsed:
        raise ValueError("invalid tenant manifest body")
    init_tenant_manifest_db()
    key = f"{parsed['tenant_id']}:{parsed['blurt_account']}"
    now = _now()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO tenant_manifest_index (
                manifest_key, tenant_id, blurt_account, stone_address,
                manifest_json, source, trx_id, block_num, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(manifest_key) DO UPDATE SET
                stone_address = CASE WHEN excluded.stone_address != '' THEN excluded.stone_address ELSE stone_address END,
                manifest_json = excluded.manifest_json,
                source = excluded.source,
                trx_id = CASE WHEN excluded.trx_id != '' THEN excluded.trx_id ELSE trx_id END,
                block_num = CASE WHEN excluded.block_num > 0 THEN excluded.block_num ELSE block_num END,
                updated_at = MAX(updated_at, excluded.updated_at)
            """,
            (
                key,
                parsed["tenant_id"],
                parsed["blurt_account"],
                parsed.get("stone_address") or "",
                json.dumps(parsed, separators=(",", ":")),
                source,
                trx_id,
                int(block_num or 0),
                now,
            ),
        )
    apply_manifest_bindings(parsed)
    return {"ok": True, "manifest_key": key, "blurt_account": parsed["blurt_account"]}


def apply_manifest_bindings(body: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import bandwidth_tenant_quota as bw
    from chain_mesh import compute_tenant_quota as compute
    from chain_mesh import storage_tenant_quota as storage
    from chain_mesh import tenant_npu_models as tnpu

    parsed = _parse_manifest_body(body)
    if not parsed:
        return {"ok": False, "reason": "invalid manifest"}
    rails = parsed.get("rails") if isinstance(parsed.get("rails"), dict) else {}
    author = parsed["blurt_account"]
    tid = parsed["tenant_id"]
    addr = parsed.get("stone_address") or ""
    compute_r = rails.get("compute") if isinstance(rails.get("compute"), dict) else {}
    bw_r = rails.get("bandwidth") if isinstance(rails.get("bandwidth"), dict) else {}
    st_r = rails.get("storage") if isinstance(rails.get("storage"), dict) else {}
    if int(compute_r.get("flops_cap") or 0) > 0:
        compute.bind_tenant_author(
            tenant_id=tid,
            blurt_account=author,
            stone_address=addr,
            flops_cap=int(compute_r.get("flops_cap") or 0),
        )
    if int(bw_r.get("bytes_cap") or 0) > 0:
        bw.bind_tenant_author(
            tenant_id=tid,
            blurt_account=author,
            stone_address=addr,
            bytes_cap=int(bw_r.get("bytes_cap") or 0),
        )
    if int(st_r.get("bytes_cap") or 0) > 0:
        storage.bind_tenant_author(
            tenant_id=tid,
            blurt_account=author,
            stone_address=addr,
            bytes_cap=int(st_r.get("bytes_cap") or 0),
        )
    npu_models = parsed.get("npu_models") if isinstance(parsed.get("npu_models"), list) else []
    for entry in npu_models:
        if not isinstance(entry, dict):
            continue
        rt = str(entry.get("runtime") or "").strip().lower()
        if rt not in tnpu.VALID_RUNTIMES:
            continue
        try:
            tnpu.bind_npu_model(
                tenant_id=tid,
                blurt_account=author,
                runtime=rt,
                model_path=str(entry.get("model_path") or ""),
                hardware_kind=str(entry.get("hardware_kind") or "cpu"),
            )
        except Exception:
            pass
    return {"ok": True, "tenant_id": tid, "blurt_account": author}


def broadcast_tenant_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    manifest = build_tenant_broadcast_manifest(
        tenant_id=str(payload.get("tenant_id") or ""),
        blurt_account=str(payload.get("blurt_account") or payload.get("blurt_author") or payload.get("author") or ""),
        stone_address=str(payload.get("stone_address") or ""),
        body=payload if payload.get("rails") or payload.get("v") == "1" else None,
    )
    body = manifest["body"]
    index_manifest(body=body, source="local")
    public = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    return {
        "ok": True,
        "layer": "tenant",
        "use_case": "multi_tenant_depin_rails",
        "manifest_id": TENANT_MANIFEST_ID,
        "blurt_custom_json": {
            "id": manifest["id"],
            "required_posting_auths": manifest.get("required_posting_auths") or [],
            "json": manifest["json"],
        },
        "body": body,
        "verify_url": (
            f"{public}/api/convergence/tenant/dashboard"
            f"?blurt_account={body.get('blurt_account')}&tenant_id={body.get('tenant_id')}"
        ),
        "next_steps": [
            f"Broadcast {TENANT_MANIFEST_ID} custom_json on Blurt",
            "Peers sync via /api/convergence/tenant/sync or DTN gossip",
            f"Dashboard: {public}/convergence/tenant",
        ],
    }


def list_local_broadcast_candidates(*, limit: int = 10) -> Dict[str, Any]:
    from chain_mesh import compute_tenant_quota as compute

    compute.init_tenant_quota_db()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT tenant_id, blurt_account, stone_address, flops_cap, updated_at
            FROM compute_tenant_bindings
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
    manifests = []
    for row in rows:
        try:
            manifests.append(
                build_tenant_broadcast_manifest(
                    tenant_id=str(row["tenant_id"]),
                    blurt_account=str(row["blurt_account"]),
                    stone_address=str(row["stone_address"] or ""),
                )
            )
        except Exception:
            continue
    return {"ok": True, "count": len(manifests), "manifests": manifests[:limit]}


def prepare_tenant_broadcast_queue(*, limit: int = 10) -> Dict[str, Any]:
    if os.environ.get("TENANT_BROADCAST_PREPARE", "1").strip().lower() in (
        "0",
        "false",
        "no",
    ):
        return {"ok": True, "skipped": True, "reason": "TENANT_BROADCAST_PREPARE off"}
    result = list_local_broadcast_candidates(limit=limit)
    queue = []
    for manifest in result.get("manifests") or []:
        body = manifest.get("body") or {}
        queue.append(
            {
                "tenant_id": body.get("tenant_id"),
                "blurt_account": body.get("blurt_account"),
                "blurt_custom_json": {
                    "id": manifest.get("id"),
                    "required_posting_auths": manifest.get("required_posting_auths") or [],
                    "json": manifest.get("json"),
                },
            }
        )
    return {
        "ok": True,
        "count": len(queue),
        "queue": queue[:limit],
        "next_steps": [
            f"Broadcast {TENANT_MANIFEST_ID} custom_json on Blurt for each queue entry",
            "POST /api/convergence/tenant/sync to pull peer broadcasts",
        ],
    }


def _blurt_rpc(method: str, params: List[Any]) -> Any:
    from chain_mesh.ai_provider import _blurt_rpc as rpc

    return rpc(method, params)


def sync_account_tenants(account: str, *, limit: int = 200) -> Dict[str, Any]:
    init_tenant_manifest_db()
    acct = (account or "").lstrip("@").lower()
    history = _blurt_rpc(
        "database_api.get_account_history",
        [acct, -1, limit, 1000000000],
    )
    indexed = 0
    for item in history or []:
        op = (item.get("op") or [])[1] if isinstance(item.get("op"), list) else {}
        if not isinstance(op, dict) or op.get("id") != TENANT_MANIFEST_ID:
            continue
        try:
            data = json.loads(op.get("json") or "{}")
        except json.JSONDecodeError:
            continue
        body = _parse_manifest_body(data)
        if not body:
            continue
        index_manifest(
            body=body,
            source="blurt_registry",
            trx_id=str(item.get("trx_id") or ""),
            block_num=int(item.get("block") or 0),
        )
        indexed += 1
    return {"ok": True, "account": acct, "indexed": indexed}


def sync_registry_tenants() -> Dict[str, Any]:
    from chain_mesh import blurt_registry_v2 as blurt_reg

    results = []
    for acct in blurt_reg.REGISTRY_ACCOUNTS:
        try:
            results.append(sync_account_tenants(acct))
        except Exception as exc:
            results.append({"ok": False, "account": acct, "error": public_error(exc)})
    total = sum(int(r.get("indexed") or 0) for r in results if r.get("ok"))
    return {"ok": True, "accounts": results, "indexed": total}


def status_payload() -> Dict[str, Any]:
    init_tenant_manifest_db()
    with _conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM tenant_manifest_index").fetchone()["c"]
    public = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    return {
        "ok": True,
        "format": TENANT_MANIFEST_ID,
        "indexed_count": int(count),
        "apis": {
            "broadcast": f"{public}/api/convergence/tenant/broadcast",
            "queue": f"{public}/api/convergence/tenant/broadcast/queue",
            "sync": f"{public}/api/convergence/tenant/sync",
        },
    }