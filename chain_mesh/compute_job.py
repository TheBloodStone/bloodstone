"""Wave F — DePIN compute job manifests on mesh (bloodstone_compute_job/v1)."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional

import requests

from chain_mesh import ai_provider as aip
from chain_mesh import blurt_registry_v2 as blurt_reg
from chain_mesh import depin_credits as depin

COMPUTE_JOB_ID = "bloodstone_compute_job/v1"
JOB_ID_RE = re.compile(r"^[a-zA-Z0-9\-_]{1,64}$")
VALID_JOB_TYPES = frozenset(
    {"inference", "render", "transcode", "train", "batch", "custom"}
)
VALID_STATUSES = frozenset(
    {"pending", "running", "completed", "failed", "cancelled"}
)

BLURT_RPC_NODES = blurt_reg.BLURT_RPC_NODES
REGISTRY_ACCOUNTS = blurt_reg.REGISTRY_ACCOUNTS


def _now() -> int:
    return int(time.time())


def _conn():
    from chain_mesh import db as mesh_db

    mesh_db.init_db()
    return mesh_db._conn()


def init_compute_job_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bloodstone_compute_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                stone_address TEXT NOT NULL,
                blurt_author TEXT NOT NULL DEFAULT '',
                agent_id TEXT NOT NULL DEFAULT '',
                job_type TEXT NOT NULL DEFAULT 'batch',
                status TEXT NOT NULL DEFAULT 'pending',
                flops_budget INTEGER NOT NULL DEFAULT 0,
                input_asset_keys TEXT NOT NULL DEFAULT '[]',
                output_asset_key TEXT NOT NULL DEFAULT '',
                region TEXT NOT NULL DEFAULT 'global',
                provider_id TEXT NOT NULL DEFAULT '',
                job_json TEXT NOT NULL DEFAULT '{}',
                trx_id TEXT NOT NULL DEFAULT '',
                block_num INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                is_current INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_compute_job_id
                ON bloodstone_compute_jobs(job_id, is_current DESC);
            CREATE INDEX IF NOT EXISTS idx_compute_job_stone
                ON bloodstone_compute_jobs(stone_address, status, created_at DESC);
            """
        )


def _normalize_job_id(value: str, *, stone_address: str = "") -> str:
    jid = (value or "").strip()
    if not jid:
        stone = (stone_address or "").strip()[:8]
        jid = f"job-{stone or 'mesh'}-{uuid.uuid4().hex[:10]}"
    jid = re.sub(r"[^a-zA-Z0-9\-_]", "-", jid).strip("-_")[:64]
    if not JOB_ID_RE.match(jid):
        raise ValueError("job_id must be 1–64 chars: letters, digits, - _")
    return jid


def build_compute_job_manifest(
    *,
    stone_address: str,
    job_id: str = "",
    blurt_author: str = "",
    agent_id: str = "",
    job_type: str = "batch",
    status: str = "pending",
    flops_budget: int = 0,
    input_asset_keys: Optional[List[str]] = None,
    output_asset_key: str = "",
    region: str = "global",
    provider_id: str = "",
    notes: str = "",
    ai_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Layer 3 DePIN — portable compute job manifest for mesh dispatch."""
    addr = (stone_address or "").strip()
    if len(addr) < 25:
        raise ValueError("stone_address required")
    jid = _normalize_job_id(job_id, stone_address=addr)
    jtype = (job_type or "batch").strip().lower()
    if jtype not in VALID_JOB_TYPES:
        raise ValueError(f"job_type must be one of: {sorted(VALID_JOB_TYPES)}")
    st = (status or "pending").strip().lower()
    if st not in VALID_STATUSES:
        raise ValueError(f"status must be one of: {sorted(VALID_STATUSES)}")

    inputs = [str(k).strip() for k in (input_asset_keys or []) if str(k).strip()]
    normalized_ai = aip.validate_ai_spec(ai_spec, job_type=jtype)
    if normalized_ai:
        prompt_key = normalized_ai.get("prompt_asset_key") or ""
        if prompt_key and prompt_key not in inputs:
            inputs.insert(0, prompt_key)
        elif prompt_key and inputs and inputs[0] != prompt_key:
            raise ValueError("input_asset_keys must include ai_spec.prompt_asset_key")
    body: Dict[str, Any] = {
        "v": "1",
        "job_id": jid,
        "stone_address": addr,
        "blurt_author": (blurt_author or "").lstrip("@").lower(),
        "agent_id": (agent_id or "").strip().lower(),
        "job_type": jtype,
        "status": st,
        "flops_budget": max(0, int(flops_budget)),
        "input_asset_keys": inputs,
        "output_asset_key": (output_asset_key or "").strip(),
        "region": (region or "global").strip()[:32],
        "provider_id": (provider_id or "").strip(),
        "provider_role": "compute",
        "memo_format": f"compute:{addr}:{jid}",
        "notes": (notes or "").strip()[:512],
        "created_at": _now(),
    }
    if normalized_ai:
        body["ai_spec"] = normalized_ai
    auth = body["blurt_author"]
    posting = [auth] if auth else []
    return {
        "id": COMPUTE_JOB_ID,
        "required_posting_auths": posting,
        "json": json.dumps(body, separators=(",", ":")),
        "body": body,
    }


def index_compute_job(
    *,
    body: Dict[str, Any],
    author: str = "",
    trx_id: str = "",
    block_num: int = 0,
) -> Dict[str, Any]:
    init_compute_job_db()
    jid = str(body.get("job_id") or "").strip()
    addr = str(body.get("stone_address") or "").strip()
    if not jid or not addr:
        raise ValueError("job_id and stone_address required in body")
    now = _now()
    with _conn() as conn:
        conn.execute(
            "UPDATE bloodstone_compute_jobs SET is_current = 0 WHERE job_id = ?",
            (jid,),
        )
        conn.execute(
            """
            INSERT INTO bloodstone_compute_jobs (
                job_id, stone_address, blurt_author, agent_id, job_type, status,
                flops_budget, input_asset_keys, output_asset_key, region, provider_id,
                job_json, trx_id, block_num, created_at, updated_at, is_current
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                jid,
                addr,
                str(body.get("blurt_author") or author or "").lstrip("@").lower(),
                str(body.get("agent_id") or ""),
                str(body.get("job_type") or "batch"),
                str(body.get("status") or "pending"),
                int(body.get("flops_budget") or 0),
                json.dumps(body.get("input_asset_keys") or []),
                str(body.get("output_asset_key") or ""),
                str(body.get("region") or "global")[:32],
                str(body.get("provider_id") or ""),
                json.dumps(body),
                trx_id,
                int(block_num or 0),
                int(body.get("created_at") or now),
                now,
            ),
        )
    return {"ok": True, "job_id": jid, "stone_address": addr, "status": body.get("status")}


def get_compute_job(*, job_id: str = "") -> Optional[Dict[str, Any]]:
    init_compute_job_db()
    jid = (job_id or "").strip()
    if not jid:
        return None
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT job_id, stone_address, blurt_author, agent_id, job_type, status,
                   flops_budget, input_asset_keys, output_asset_key, region, provider_id,
                   job_json, trx_id, block_num, created_at, updated_at
            FROM bloodstone_compute_jobs
            WHERE job_id = ? AND is_current = 1
            ORDER BY updated_at DESC LIMIT 1
            """,
            (jid,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["input_asset_keys"] = json.loads(item.get("input_asset_keys") or "[]")
    item["body"] = json.loads(item.get("job_json") or "{}")
    return item


def list_compute_jobs(
    *,
    stone_address: str = "",
    status: str = "",
    limit: int = 30,
) -> Dict[str, Any]:
    init_compute_job_db()
    addr = (stone_address or "").strip()
    st = (status or "").strip().lower()
    clauses = ["is_current = 1"]
    params: List[Any] = []
    if addr:
        clauses.append("stone_address = ?")
        params.append(addr)
    if st:
        clauses.append("status = ?")
        params.append(st)
    sql = f"""
        SELECT job_id, stone_address, job_type, status, flops_budget,
               region, provider_id, created_at, updated_at
        FROM bloodstone_compute_jobs
        WHERE {' AND '.join(clauses)}
        ORDER BY updated_at DESC
        LIMIT ?
    """
    params.append(max(1, int(limit)))
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"ok": True, "jobs": [dict(r) for r in rows], "count": len(rows)}


def submit_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    custom = build_compute_job_manifest(
        stone_address=str(payload.get("stone_address") or ""),
        job_id=str(payload.get("job_id") or ""),
        blurt_author=str(payload.get("blurt_author") or payload.get("author") or ""),
        agent_id=str(payload.get("agent_id") or ""),
        job_type=str(payload.get("job_type") or "batch"),
        status=str(payload.get("status") or "pending"),
        flops_budget=int(payload.get("flops_budget") or 0),
        input_asset_keys=payload.get("input_asset_keys"),
        output_asset_key=str(payload.get("output_asset_key") or ""),
        region=str(payload.get("region") or ""),
        provider_id=str(payload.get("provider_id") or ""),
        notes=str(payload.get("notes") or ""),
        ai_spec=payload.get("ai_spec"),
    )
    body = custom["body"]
    from chain_mesh import tenant_dashboard as tdash

    tctx = tdash.resolve_tenant_context(
        blurt_author=str(body.get("blurt_author") or ""),
        tenant_id=str(payload.get("tenant_id") or ""),
        stone_address=body["stone_address"],
    )
    quota_check = depin.check_compute_allowed(
        body["stone_address"],
        flops_budget=int(body.get("flops_budget") or 0),
        job_id=str(body.get("job_id") or ""),
        blurt_author=tctx["blurt_author"],
        tenant_id=tctx["tenant_id"],
    )
    if not quota_check.get("allowed"):
        raise PermissionError(quota_check.get("reason") or "compute quota exceeded")
    index_compute_job(body=body, author=body.get("blurt_author", ""))
    quota = depin.compute_quota(body["stone_address"])
    public = os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org").rstrip("/")
    return {
        "ok": True,
        "layer": 3,
        "use_case": "autonomous_ai_creator_economy",
        "compute_job_id": COMPUTE_JOB_ID,
        "blurt_custom_json": {
            "id": custom["id"],
            "required_posting_auths": custom.get("required_posting_auths") or [],
            "json": custom["json"],
        },
        "body": body,
        "quota": {
            "flops_remaining": quota.get("flops_remaining"),
            "enforce_quota": quota.get("enforce_quota"),
        },
        "verify_url": f"{public}/api/convergence/compute/job/verify?job_id={body['job_id']}",
        "memo": f"compute:{body['stone_address']}:{body['job_id']}",
        "next_steps": [
            f"Broadcast {COMPUTE_JOB_ID} custom_json on Blurt",
            f"Pay BLURT memo: compute:{body['stone_address']}:{body['job_id']}",
            "Assign provider via /api/chain-mesh/v2/providers?role=compute",
            "DTN sync propagates job manifest to offline Pi nodes",
        ],
    }


def verify_payload(*, job_id: str = "", stone_address: str = "") -> Dict[str, Any]:
    jid = (job_id or "").strip()
    addr = (stone_address or "").strip()
    job = get_compute_job(job_id=jid) if jid else None
    if not job and addr:
        jobs = list_compute_jobs(stone_address=addr, limit=1)
        if jobs.get("jobs"):
            job = get_compute_job(job_id=str(jobs["jobs"][0]["job_id"]))
    if not job:
        return {
            "ok": True,
            "verified": False,
            "error": "compute job not indexed",
            "reason": f"Broadcast {COMPUTE_JOB_ID} on Blurt or POST /api/convergence/compute/job/submit",
        }
    quota = depin.compute_quota(str(job.get("stone_address") or ""))
    jid = str(job.get("job_id") or "")
    addr = str(job.get("stone_address") or "")
    memo_ok = any(str(r.get("job_id") or "") == jid for r in (quota.get("recent_jobs") or []))
    verified = bool(job) and (not depin.ENFORCE_COMPUTE or memo_ok or quota.get("flops_remaining", 0) > 0)
    public = os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org").rstrip("/")
    return {
        "ok": True,
        "verified": verified,
        "layer": 3,
        "job_id": jid,
        "stone_address": addr,
        "status": job.get("status"),
        "job_type": job.get("job_type"),
        "flops_budget": job.get("flops_budget"),
        "memo_credited": memo_ok,
        "flops_remaining": quota.get("flops_remaining"),
        "enforce_quota": depin.ENFORCE_COMPUTE,
        "reason": "Compute job indexed on mesh."
        if verified
        else "Job indexed but quota/memo not satisfied (ENFORCE_COMPUTE off allows dispatch).",
        "verify_url": f"{public}/api/convergence/compute/job/verify?job_id={jid}",
        "job": job,
    }


def _tenant_status() -> Dict[str, Any]:
    try:
        from chain_mesh import compute_tenant_quota as tenant

        return tenant.status_payload()
    except Exception:
        return {"ok": False}


def status_payload() -> Dict[str, Any]:
    init_compute_job_db()
    with _conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM bloodstone_compute_jobs WHERE is_current = 1"
        ).fetchone()["c"]
        pending = conn.execute(
            "SELECT COUNT(*) AS c FROM bloodstone_compute_jobs WHERE is_current = 1 AND status = 'pending'"
        ).fetchone()["c"]
        running = conn.execute(
            "SELECT COUNT(*) AS c FROM bloodstone_compute_jobs WHERE is_current = 1 AND status = 'running'"
        ).fetchone()["c"]
    public = os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org").rstrip("/")
    return {
        "ok": True,
        "compute_job_id": COMPUTE_JOB_ID,
        "job_types": sorted(VALID_JOB_TYPES),
        "statuses": sorted(VALID_STATUSES),
        "jobs_indexed": int(total),
        "pending": int(pending),
        "running": int(running),
        "memo_format": "compute:<STONE_ADDRESS>:<job_id>",
        "enforce_quota": depin.ENFORCE_COMPUTE,
        "tenant_quota": _tenant_status(),
        "apis": {
            "submit": f"{public}/api/convergence/compute/job/submit",
            "verify": f"{public}/api/convergence/compute/job/verify",
            "list": f"{public}/api/convergence/compute/jobs",
            "quota": f"{public}/api/convergence/compute/quota",
            "tenant_quota": f"{public}/api/convergence/compute/tenant/quota",
            "tenant_bind": f"{public}/api/convergence/compute/tenant/bind",
            "ai_provider_sync": f"{public}/api/convergence/ai/provider/sync",
        },
    }


def _parse_job_op(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if str(data.get("v") or "") != "1":
        return None
    jid = str(data.get("job_id") or "").strip()
    addr = str(data.get("stone_address") or "").strip()
    if not jid or len(addr) < 25:
        return None
    jtype = str(data.get("job_type") or "batch").lower()
    if jtype not in VALID_JOB_TYPES:
        jtype = "batch"
    st = str(data.get("status") or "pending").lower()
    if st not in VALID_STATUSES:
        st = "pending"
    data["job_type"] = jtype
    data["status"] = st
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


def sync_account_jobs(account: str, *, limit: int = 200) -> Dict[str, Any]:
    init_compute_job_db()
    acct = (account or "").lstrip("@").lower()
    history = _blurt_rpc(
        "database_api.get_account_history",
        [acct, -1, limit, 1000000000],
    )
    indexed = 0
    for item in history or []:
        op = (item.get("op") or [])[1] if isinstance(item.get("op"), list) else {}
        if not isinstance(op, dict) or op.get("id") != COMPUTE_JOB_ID:
            continue
        try:
            data = json.loads(op.get("json") or "{}")
        except json.JSONDecodeError:
            continue
        body = _parse_job_op(data)
        if not body:
            continue
        index_compute_job(
            body=body,
            author=acct,
            trx_id=str(item.get("trx_id") or ""),
            block_num=int(item.get("block") or 0),
        )
        indexed += 1
    return {"ok": True, "account": acct, "indexed": indexed}


def sync_registry_jobs() -> Dict[str, Any]:
    results = []
    for acct in REGISTRY_ACCOUNTS:
        try:
            results.append(sync_account_jobs(acct))
        except Exception as exc:
            results.append({"ok": False, "account": acct, "error": str(exc)})
    return {"ok": True, "accounts": results}


def import_job_rows(rows: List[Dict[str, Any]]) -> int:
    imported = 0
    for row in rows or []:
        body = row.get("body") if isinstance(row.get("body"), dict) else row
        if not isinstance(body, dict):
            continue
        parsed = _parse_job_op(body) or (
            body if body.get("job_id") and body.get("stone_address") else None
        )
        if not parsed:
            continue
        try:
            index_compute_job(body=parsed, author=str(parsed.get("blurt_author") or ""))
            imported += 1
        except ValueError:
            continue
    return imported