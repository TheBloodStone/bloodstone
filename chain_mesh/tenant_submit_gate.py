"""Wave W — quorum-gated compute/AI submit (fleet agreement before job acceptance)."""

from __future__ import annotations

import os
from typing import Any, Dict

GATE_FORMAT = "bloodstone_tenant_submit_gate/v1"


def _submit_quorum_require() -> bool:
    return os.environ.get("TENANT_SUBMIT_QUORUM_REQUIRE", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _default_tenant() -> str:
    return (os.environ.get("DTN_DEFAULT_TENANT") or "bloodstone").strip()[:64] or "bloodstone"


def _normalize_author(value: str = "") -> str:
    return (value or "").lstrip("@").lower().strip()[:64]


def quorum_for_author(
    *,
    tenant_id: str = "",
    blurt_account: str = "",
) -> Dict[str, Any]:
    from chain_mesh import tenant_fleet_quorum as tquorum

    tid = (tenant_id or _default_tenant()).strip()[:64] or _default_tenant()
    author = _normalize_author(blurt_account)
    if not author:
        return {"ok": False, "reason": "blurt_account required"}
    tquorum.init_tenant_quorum_db()
    with tquorum._conn() as conn:
        row = conn.execute(
            """
            SELECT tenant_id, blurt_account, votes_found, quorum_n, quorum_m,
                   satisfied, rails_hash, updated_at
            FROM tenant_fleet_quorum
            WHERE tenant_id = ? AND blurt_account = ?
            """,
            (tid, author),
        ).fetchone()
    if not row:
        return {
            "ok": True,
            "tenant_id": tid,
            "blurt_account": author,
            "satisfied": False,
            "votes_found": 0,
            "quorum": f"{tquorum.QUORUM_N}-of-{tquorum.QUORUM_M}",
            "reason": "no quorum votes yet",
        }
    return {
        "ok": True,
        "tenant_id": tid,
        "blurt_account": author,
        "satisfied": bool(int(row["satisfied"] or 0)),
        "votes_found": int(row["votes_found"] or 0),
        "quorum_n": int(row["quorum_n"] or tquorum.QUORUM_N),
        "quorum_m": int(row["quorum_m"] or tquorum.QUORUM_M),
        "quorum": f"{int(row['quorum_n'] or tquorum.QUORUM_N)}-of-{int(row['quorum_m'] or tquorum.QUORUM_M)}",
        "rails_hash": str(row["rails_hash"] or ""),
        "updated_at": int(row["updated_at"] or 0),
    }


def check_submit_allowed(
    *,
    tenant_id: str = "",
    blurt_account: str = "",
    stone_address: str = "",
) -> Dict[str, Any]:
    tid = (tenant_id or _default_tenant()).strip()[:64] or _default_tenant()
    author = _normalize_author(blurt_account)
    if not _submit_quorum_require():
        return {
            "ok": True,
            "allowed": True,
            "format": GATE_FORMAT,
            "require_quorum": False,
            "tenant_id": tid,
            "blurt_account": author,
            "stone_address": (stone_address or "").strip(),
            "reason": "submit quorum not required",
        }
    if not author:
        return {
            "ok": True,
            "allowed": False,
            "require_quorum": True,
            "reason": "blurt_account required when TENANT_SUBMIT_QUORUM_REQUIRE=1",
        }
    q = quorum_for_author(tenant_id=tid, blurt_account=author)
    allowed = bool(q.get("satisfied"))
    return {
        "ok": True,
        "allowed": allowed,
        "format": GATE_FORMAT,
        "require_quorum": True,
        "tenant_id": tid,
        "blurt_account": author,
        "stone_address": (stone_address or "").strip(),
        "quorum": q,
        "reason": "ok" if allowed else "tenant fleet quorum not satisfied",
    }


def status_payload() -> Dict[str, Any]:
    public = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    return {
        "ok": True,
        "format": GATE_FORMAT,
        "require_quorum": _submit_quorum_require(),
        "enforcement_mode": "strict" if _submit_quorum_require() else "beta_permissive",
        "apis": {
            "status": f"{public}/api/convergence/tenant/submit/status",
            "check": f"{public}/api/convergence/tenant/submit/check",
            "quorum_for_author": f"{public}/api/convergence/tenant/quorum/author",
        },
    }