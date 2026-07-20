"""Wave P — multi-tenant compute quota (per-author caps on shared Pi / STONE pools)."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db
from chain_mesh import depin_credits as depin

TENANT_FORMAT = "bloodstone_compute_tenant/v1"


def _tenant_enable() -> bool:
    return os.environ.get("COMPUTE_TENANT_ENFORCE", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def _default_tenant() -> str:
    return (os.environ.get("DTN_DEFAULT_TENANT") or "bloodstone").strip()[:64] or "bloodstone"


def _default_author_cap() -> int:
    return max(0, int(os.environ.get("COMPUTE_TENANT_AUTHOR_CAP", "0")))


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def init_tenant_quota_db() -> None:
    depin.init_depin_db()
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS compute_tenant_bindings (
                tenant_id TEXT NOT NULL,
                blurt_account TEXT NOT NULL,
                stone_address TEXT NOT NULL DEFAULT '',
                flops_cap INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (tenant_id, blurt_account)
            );
            CREATE INDEX IF NOT EXISTS idx_compute_tenant_author
                ON compute_tenant_bindings(blurt_account);

            CREATE TABLE IF NOT EXISTS compute_tenant_usage (
                tenant_id TEXT NOT NULL,
                blurt_account TEXT NOT NULL,
                stone_address TEXT NOT NULL DEFAULT '',
                flops_used INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (tenant_id, blurt_account, stone_address)
            );
            """
        )


def normalize_tenant_id(value: str = "") -> str:
    tid = (value or _default_tenant()).strip()[:64]
    return tid or _default_tenant()


def normalize_author(value: str = "") -> str:
    return (value or "").lstrip("@").lower().strip()[:64]


def bind_tenant_author(
    *,
    tenant_id: str = "",
    blurt_account: str = "",
    stone_address: str = "",
    flops_cap: int = 0,
) -> Dict[str, Any]:
    init_tenant_quota_db()
    tid = normalize_tenant_id(tenant_id)
    author = normalize_author(blurt_account)
    if not author:
        raise ValueError("blurt_account required")
    addr = (stone_address or "").strip()
    cap = max(0, int(flops_cap or _default_author_cap()))
    now = _now()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO compute_tenant_bindings (
                tenant_id, blurt_account, stone_address, flops_cap, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, blurt_account) DO UPDATE SET
                stone_address = CASE WHEN excluded.stone_address != ''
                    THEN excluded.stone_address ELSE stone_address END,
                flops_cap = CASE WHEN excluded.flops_cap > 0
                    THEN excluded.flops_cap ELSE flops_cap END,
                updated_at = excluded.updated_at
            """,
            (tid, author, addr, cap, now, now),
        )
    return {
        "ok": True,
        "tenant_id": tid,
        "blurt_account": author,
        "stone_address": addr,
        "flops_cap": cap,
    }


def tenant_quota(
    *,
    tenant_id: str = "",
    blurt_account: str = "",
    stone_address: str = "",
) -> Dict[str, Any]:
    init_tenant_quota_db()
    tid = normalize_tenant_id(tenant_id)
    author = normalize_author(blurt_account)
    addr = (stone_address or "").strip()
    binding = None
    with _conn() as conn:
        if author:
            row = conn.execute(
                """
                SELECT * FROM compute_tenant_bindings
                WHERE tenant_id = ? AND blurt_account = ?
                """,
                (tid, author),
            ).fetchone()
            binding = dict(row) if row else None
            usage_row = conn.execute(
                """
                SELECT flops_used FROM compute_tenant_usage
                WHERE tenant_id = ? AND blurt_account = ? AND stone_address = ?
                """,
                (tid, author, addr or str((binding or {}).get("stone_address") or "")),
            ).fetchone()
        else:
            rows = conn.execute(
                """
                SELECT b.*, COALESCE(u.flops_used, 0) AS flops_used
                FROM compute_tenant_bindings b
                LEFT JOIN compute_tenant_usage u
                  ON u.tenant_id = b.tenant_id
                 AND u.blurt_account = b.blurt_account
                 AND u.stone_address = b.stone_address
                WHERE b.tenant_id = ?
                ORDER BY b.updated_at DESC
                LIMIT 50
                """,
                (tid,),
            ).fetchall()
            return {
                "ok": True,
                "format": TENANT_FORMAT,
                "tenant_id": tid,
                "enforce": _tenant_enable(),
                "authors": [dict(r) for r in rows],
                "count": len(rows),
            }
    used = int(usage_row["flops_used"]) if usage_row else 0
    cap = int((binding or {}).get("flops_cap") or 0)
    bound_stone = str((binding or {}).get("stone_address") or addr)
    stone_q = depin.compute_quota(bound_stone) if bound_stone else {}
    remaining = max(0, cap - used) if cap > 0 else int(stone_q.get("flops_remaining") or 0)
    return {
        "ok": True,
        "format": TENANT_FORMAT,
        "tenant_id": tid,
        "blurt_account": author,
        "stone_address": bound_stone,
        "flops_cap": cap,
        "flops_used": used,
        "flops_remaining": remaining,
        "enforce": _tenant_enable(),
        "stone_quota": stone_q,
    }


def check_tenant_compute_allowed(
    *,
    stone_address: str,
    flops_budget: int = 0,
    job_id: str = "",
    blurt_account: str = "",
    tenant_id: str = "",
) -> Dict[str, Any]:
    stone_q = depin.check_compute_allowed(
        stone_address,
        flops_budget=int(flops_budget),
        job_id=str(job_id or ""),
    )
    if not stone_q.get("allowed"):
        stone_q["tenant"] = {"skipped": True, "reason": "stone quota denied"}
        return stone_q

    if not _tenant_enable() or not normalize_author(blurt_account):
        stone_q["tenant"] = {"skipped": True, "reason": "tenant enforcement off or no author"}
        return stone_q

    init_tenant_quota_db()
    tid = normalize_tenant_id(tenant_id)
    author = normalize_author(blurt_account)
    tq = tenant_quota(tenant_id=tid, blurt_account=author, stone_address=stone_address)
    cap = int(tq.get("flops_cap") or 0)
    need = max(0, int(flops_budget))
    remaining = int(tq.get("flops_remaining") or 0)
    if cap <= 0:
        stone_q["tenant"] = tq
        return stone_q
    if need > 0 and remaining >= need:
        stone_q["tenant"] = tq
        return stone_q
    if need <= 0 and remaining > 0:
        stone_q["tenant"] = tq
        return stone_q
    return {
        "ok": True,
        "allowed": False,
        "quota": stone_q.get("quota"),
        "tenant": tq,
        "reason": f"tenant author cap exceeded: need {need} FLOPS, have {remaining} for @{author}",
    }


def record_tenant_compute_usage(
    *,
    blurt_account: str,
    stone_address: str,
    delta_flops: int,
    tenant_id: str = "",
) -> Dict[str, Any]:
    init_tenant_quota_db()
    author = normalize_author(blurt_account)
    if not author:
        return {"ok": True, "skipped": True, "reason": "no blurt_account"}
    tid = normalize_tenant_id(tenant_id)
    addr = (stone_address or "").strip()
    delta = max(0, int(delta_flops))
    now = _now()
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT flops_used FROM compute_tenant_usage
            WHERE tenant_id = ? AND blurt_account = ? AND stone_address = ?
            """,
            (tid, author, addr),
        ).fetchone()
        used = max(0, int(row["flops_used"]) + delta) if row else delta
        conn.execute(
            """
            INSERT INTO compute_tenant_usage (
                tenant_id, blurt_account, stone_address, flops_used, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, blurt_account, stone_address) DO UPDATE SET
                flops_used = excluded.flops_used,
                updated_at = excluded.updated_at
            """,
            (tid, author, addr, used, now),
        )
    return {
        "ok": True,
        "tenant_id": tid,
        "blurt_account": author,
        "stone_address": addr,
        "flops_used": used,
    }


def sync_bindings_from_jobs(*, limit: int = 100) -> Dict[str, Any]:
    from chain_mesh import compute_job as cjobs

    init_tenant_quota_db()
    cjobs.init_compute_job_db()
    bound = 0
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT blurt_account, stone_address
            FROM bloodstone_compute_jobs
            WHERE is_current = 1 AND blurt_account != '' AND stone_address != ''
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
    for row in rows:
        author = normalize_author(str(row["blurt_account"]))
        addr = str(row["stone_address"])
        if not author or not addr:
            continue
        bind_tenant_author(
            tenant_id=_default_tenant(),
            blurt_account=author,
            stone_address=addr,
            flops_cap=_default_author_cap(),
        )
        bound += 1
    return {"ok": True, "bound": bound, "tenant_id": _default_tenant()}


def status_payload() -> Dict[str, Any]:
    init_tenant_quota_db()
    with _conn() as conn:
        authors = conn.execute(
            "SELECT COUNT(*) AS c FROM compute_tenant_bindings"
        ).fetchone()["c"]
        usage_rows = conn.execute(
            "SELECT COUNT(*) AS c FROM compute_tenant_usage"
        ).fetchone()["c"]
    public = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    return {
        "ok": True,
        "format": TENANT_FORMAT,
        "enabled": _tenant_enable(),
        "default_tenant": _default_tenant(),
        "default_author_cap": _default_author_cap(),
        "bindings_count": int(authors),
        "usage_rows": int(usage_rows),
        "apis": {
            "quota": f"{public}/api/convergence/compute/tenant/quota",
            "bind": f"{public}/api/convergence/compute/tenant/bind",
        },
    }