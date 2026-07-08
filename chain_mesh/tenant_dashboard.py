"""Wave S — unified multi-tenant dashboard (compute + bandwidth + storage)."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

DASHBOARD_FORMAT = "bloodstone_tenant_dashboard/v1"


def _default_tenant() -> str:
    return (os.environ.get("DTN_DEFAULT_TENANT") or "bloodstone").strip()[:64] or "bloodstone"


def _normalize_author(value: str = "") -> str:
    return (value or "").lstrip("@").lower().strip()[:64]


def dashboard_payload(
    *,
    tenant_id: str = "",
    blurt_author: str = "",
    stone_address: str = "",
) -> Dict[str, Any]:
    from chain_mesh import bandwidth_tenant_quota as bw
    from chain_mesh import compute_tenant_quota as compute
    from chain_mesh import storage_tenant_quota as storage

    tid = (tenant_id or _default_tenant()).strip()[:64] or _default_tenant()
    author = _normalize_author(blurt_author)
    addr = (stone_address or "").strip()
    compute_q = compute.tenant_quota(
        tenant_id=tid, blurt_author=author, stone_address=addr
    )
    bandwidth_q = bw.tenant_quota(
        tenant_id=tid, blurt_author=author, stone_address=addr
    )
    storage_q = storage.tenant_quota(
        tenant_id=tid, blurt_author=author, stone_address=addr
    )
    return {
        "ok": True,
        "format": DASHBOARD_FORMAT,
        "tenant_id": tid,
        "blurt_author": author,
        "stone_address": addr,
        "rails": {
            "compute": compute_q,
            "bandwidth": bandwidth_q,
            "storage": storage_q,
        },
        "enforce": {
            "compute": bool(compute_q.get("enforce")),
            "bandwidth": bool(bandwidth_q.get("enforce")),
            "storage": bool(storage_q.get("enforce")),
        },
    }


def bind_all_rails(
    *,
    tenant_id: str = "",
    blurt_author: str = "",
    stone_address: str = "",
    flops_cap: int = 0,
    bandwidth_bytes_cap: int = 0,
    storage_bytes_cap: int = 0,
) -> Dict[str, Any]:
    from chain_mesh import bandwidth_tenant_quota as bw
    from chain_mesh import compute_tenant_quota as compute
    from chain_mesh import storage_tenant_quota as storage

    tid = (tenant_id or _default_tenant()).strip()[:64] or _default_tenant()
    author = _normalize_author(blurt_author)
    if not author:
        raise ValueError("blurt_author required")
    addr = (stone_address or "").strip()
    return {
        "ok": True,
        "tenant_id": tid,
        "blurt_author": author,
        "stone_address": addr,
        "compute": compute.bind_tenant_author(
            tenant_id=tid,
            blurt_author=author,
            stone_address=addr,
            flops_cap=int(flops_cap or 0),
        ),
        "bandwidth": bw.bind_tenant_author(
            tenant_id=tid,
            blurt_author=author,
            stone_address=addr,
            bytes_cap=int(bandwidth_bytes_cap or 0),
        ),
        "storage": storage.bind_tenant_author(
            tenant_id=tid,
            blurt_author=author,
            stone_address=addr,
            bytes_cap=int(storage_bytes_cap or 0),
        ),
    }


def resolve_tenant_context(
    *,
    blurt_author: str = "",
    tenant_id: str = "",
    stone_address: str = "",
) -> Dict[str, str]:
    from chain_mesh import tenant_fleet_sync as fleet

    return fleet.resolve_tenant_context(
        blurt_author=blurt_author,
        tenant_id=tenant_id,
        stone_address=stone_address,
    )


def status_payload() -> Dict[str, Any]:
    from chain_mesh import bandwidth_tenant_quota as bw
    from chain_mesh import compute_tenant_quota as compute
    from chain_mesh import storage_tenant_quota as storage

    public = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    compute_s = compute.status_payload()
    bandwidth_s = bw.status_payload()
    storage_s = storage.status_payload()
    return {
        "ok": True,
        "format": DASHBOARD_FORMAT,
        "default_tenant": _default_tenant(),
        "rails": {
            "compute": compute_s,
            "bandwidth": bandwidth_s,
            "storage": storage_s,
        },
        "bindings_total": (
            int(compute_s.get("bindings_count") or 0)
            + int(bandwidth_s.get("bindings_count") or 0)
            + int(storage_s.get("bindings_count") or 0)
        ),
        "apis": {
            "dashboard": f"{public}/api/convergence/tenant/dashboard",
            "bind": f"{public}/api/convergence/tenant/bind",
            "status": f"{public}/api/convergence/tenant/status",
        },
    }