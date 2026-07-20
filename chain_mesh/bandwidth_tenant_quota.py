"""Wave Q — multi-tenant bandwidth quota (per-author byte caps on shared Pi / STONE pools)."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db
from chain_mesh import depin_credits as depin

TENANT_FORMAT = "bloodstone_bandwidth_tenant/v1"


def _tenant_enable() -> bool:
    return os.environ.get("BANDWIDTH_TENANT_ENFORCE", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def _default_tenant() -> str:
    return (os.environ.get("DTN_DEFAULT_TENANT") or "bloodstone").strip()[:64] or "bloodstone"


def _default_author_cap() -> int:
    return max(0, int(os.environ.get("BANDWIDTH_TENANT_AUTHOR_CAP", "0")))


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
            CREATE TABLE IF NOT EXISTS bandwidth_tenant_bindings (
                tenant_id TEXT NOT NULL,
                blurt_account TEXT NOT NULL,
                stone_address TEXT NOT NULL DEFAULT '',
                bytes_cap INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (tenant_id, blurt_account)
            );
            CREATE INDEX IF NOT EXISTS idx_bandwidth_tenant_author
                ON bandwidth_tenant_bindings(blurt_account);

            CREATE TABLE IF NOT EXISTS bandwidth_tenant_usage (
                tenant_id TEXT NOT NULL,
                blurt_account TEXT NOT NULL,
                stone_address TEXT NOT NULL DEFAULT '',
                bytes_used INTEGER NOT NULL DEFAULT 0,
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
    bytes_cap: int = 0,
) -> Dict[str, Any]:
    init_tenant_quota_db()
    tid = normalize_tenant_id(tenant_id)
    author = normalize_author(blurt_account)
    if not author:
        raise ValueError("blurt_account required")
    addr = (stone_address or "").strip()
    cap = max(0, int(bytes_cap or _default_author_cap()))
    now = _now()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO bandwidth_tenant_bindings (
                tenant_id, blurt_account, stone_address, bytes_cap, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, blurt_account) DO UPDATE SET
                stone_address = CASE WHEN excluded.stone_address != ''
                    THEN excluded.stone_address ELSE stone_address END,
                bytes_cap = CASE WHEN excluded.bytes_cap > 0
                    THEN excluded.bytes_cap ELSE bytes_cap END,
                updated_at = excluded.updated_at
            """,
            (tid, author, addr, cap, now, now),
        )
    return {
        "ok": True,
        "tenant_id": tid,
        "blurt_account": author,
        "stone_address": addr,
        "bytes_cap": cap,
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
                SELECT * FROM bandwidth_tenant_bindings
                WHERE tenant_id = ? AND blurt_account = ?
                """,
                (tid, author),
            ).fetchone()
            binding = dict(row) if row else None
            usage_row = conn.execute(
                """
                SELECT bytes_used FROM bandwidth_tenant_usage
                WHERE tenant_id = ? AND blurt_account = ? AND stone_address = ?
                """,
                (tid, author, addr or str((binding or {}).get("stone_address") or "")),
            ).fetchone()
        else:
            rows = conn.execute(
                """
                SELECT b.*, COALESCE(u.bytes_used, 0) AS bytes_used
                FROM bandwidth_tenant_bindings b
                LEFT JOIN bandwidth_tenant_usage u
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
    used = int(usage_row["bytes_used"]) if usage_row else 0
    cap = int((binding or {}).get("bytes_cap") or 0)
    bound_stone = str((binding or {}).get("stone_address") or addr)
    stone_q = depin.bandwidth_quota(bound_stone) if bound_stone else {}
    remaining = max(0, cap - used) if cap > 0 else int(stone_q.get("bytes_remaining") or 0)
    return {
        "ok": True,
        "format": TENANT_FORMAT,
        "tenant_id": tid,
        "blurt_account": author,
        "stone_address": bound_stone,
        "bytes_cap": cap,
        "bytes_used": used,
        "bytes_remaining": remaining,
        "enforce": _tenant_enable(),
        "stone_quota": stone_q,
    }


def check_tenant_bandwidth_allowed(
    *,
    stone_address: str,
    byte_size: int = 0,
    blurt_account: str = "",
    tenant_id: str = "",
) -> Dict[str, Any]:
    stone_q = depin.bandwidth_quota(stone_address)
    if depin.ENFORCE_BANDWIDTH and stone_address and int(stone_q.get("bytes_remaining") or 0) < max(
        0, int(byte_size)
    ):
        return {
            "ok": True,
            "allowed": False,
            "quota": stone_q,
            "tenant": {"skipped": True, "reason": "stone bandwidth quota denied"},
            "reason": f"insufficient bandwidth credits: need {max(0, int(byte_size))}, have {stone_q.get('bytes_remaining')}",
        }

    if not _tenant_enable() or not normalize_author(blurt_account):
        return {
            "ok": True,
            "allowed": True,
            "quota": stone_q,
            "tenant": {"skipped": True, "reason": "tenant enforcement off or no author"},
        }

    init_tenant_quota_db()
    tid = normalize_tenant_id(tenant_id)
    author = normalize_author(blurt_account)
    tq = tenant_quota(tenant_id=tid, blurt_account=author, stone_address=stone_address)
    cap = int(tq.get("bytes_cap") or 0)
    need = max(0, int(byte_size))
    remaining = int(tq.get("bytes_remaining") or 0)
    if cap <= 0:
        return {"ok": True, "allowed": True, "quota": stone_q, "tenant": tq}
    if need > 0 and remaining >= need:
        return {"ok": True, "allowed": True, "quota": stone_q, "tenant": tq}
    if need <= 0 and remaining > 0:
        return {"ok": True, "allowed": True, "quota": stone_q, "tenant": tq}
    return {
        "ok": True,
        "allowed": False,
        "quota": stone_q,
        "tenant": tq,
        "reason": f"tenant author bandwidth cap exceeded: need {need} bytes, have {remaining} for @{author}",
    }


def record_tenant_bandwidth_usage(
    *,
    blurt_account: str,
    stone_address: str,
    delta_bytes: int,
    tenant_id: str = "",
) -> Dict[str, Any]:
    init_tenant_quota_db()
    author = normalize_author(blurt_account)
    if not author:
        return {"ok": True, "skipped": True, "reason": "no blurt_account"}
    tid = normalize_tenant_id(tenant_id)
    addr = (stone_address or "").strip()
    delta = max(0, int(delta_bytes))
    now = _now()
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT bytes_used FROM bandwidth_tenant_usage
            WHERE tenant_id = ? AND blurt_account = ? AND stone_address = ?
            """,
            (tid, author, addr),
        ).fetchone()
        used = max(0, int(row["bytes_used"]) + delta) if row else delta
        conn.execute(
            """
            INSERT INTO bandwidth_tenant_usage (
                tenant_id, blurt_account, stone_address, bytes_used, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, blurt_account, stone_address) DO UPDATE SET
                bytes_used = excluded.bytes_used,
                updated_at = excluded.updated_at
            """,
            (tid, author, addr, used, now),
        )
    return {
        "ok": True,
        "tenant_id": tid,
        "blurt_account": author,
        "stone_address": addr,
        "bytes_used": used,
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
            bytes_cap=_default_author_cap(),
        )
        bound += 1
    return {"ok": True, "bound": bound, "tenant_id": _default_tenant()}


def status_payload() -> Dict[str, Any]:
    init_tenant_quota_db()
    with _conn() as conn:
        authors = conn.execute(
            "SELECT COUNT(*) AS c FROM bandwidth_tenant_bindings"
        ).fetchone()["c"]
        usage_rows = conn.execute(
            "SELECT COUNT(*) AS c FROM bandwidth_tenant_usage"
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
            "quota": f"{public}/api/convergence/bandwidth/tenant/quota",
            "bind": f"{public}/api/convergence/bandwidth/tenant/bind",
            "status": f"{public}/api/convergence/bandwidth/tenant/status",
        },
    }