"""Wave Z — capstone tenant sovereign mesh status + fleet reconcile."""

from __future__ import annotations

import os
import time
from typing import Any, Dict

SOVEREIGN_FORMAT = "bloodstone_tenant_sovereign/v1"
_LAST_RECONCILE: Dict[str, Any] = {}


def _now() -> int:
    return int(time.time())


def _subsystem_status() -> Dict[str, Any]:
    from chain_mesh import tenant_fleet_quorum as tquorum
    from chain_mesh import tenant_manifest_gossip as tmgossip
    from chain_mesh import tenant_planetary_quorum as tplanetary
    from chain_mesh import tenant_route_ledger as tledger
    from chain_mesh import tenant_submit_gate as tgate
    from chain_mesh import tenant_upkeep as tup

    return {
        "fleet_quorum": tquorum.status_payload(),
        "route_ledger": tledger.status_payload(),
        "manifest_gossip": tmgossip.status_payload(),
        "submit_gate": tgate.status_payload(),
        "upkeep": tup.status_payload(),
        "planetary": tplanetary.status_payload(),
    }


def sovereign_summary() -> Dict[str, Any]:
    from chain_mesh import tenant_fleet_quorum as tquorum
    from chain_mesh import tenant_planetary_quorum as tplanetary
    from chain_mesh import tenant_route_ledger as tledger
    from chain_mesh import tenant_upkeep as tup

    quorum = tquorum.status_payload()
    ledger = tledger.status_payload()
    planetary = tplanetary.update_tenant_planetary_quorum()
    upkeep = tup.last_upkeep()
    return {
        "pairs_tracked": int(quorum.get("pairs_tracked") or 0),
        "pairs_satisfied": int(quorum.get("pairs_satisfied") or 0),
        "assignments_total": int(ledger.get("assignments_total") or 0),
        "regions_total": int(planetary.get("regions_total") or 0),
        "regions_satisfied": int(planetary.get("regions_satisfied") or 0),
        "planetary_satisfied": bool(planetary.get("planetary_satisfied")),
        "last_upkeep_at": int(upkeep.get("at") or 0),
    }


def reconcile_fleet(*, force_quorum_apply: bool = False) -> Dict[str, Any]:
    from chain_mesh import tenant_planetary_quorum as tplanetary
    from chain_mesh import tenant_upkeep as tup

    upkeep = tup.upkeep_tenant(force_quorum_apply=force_quorum_apply)
    planetary = tplanetary.update_tenant_planetary_quorum()
    summary = sovereign_summary()
    result = {
        "ok": True,
        "format": SOVEREIGN_FORMAT,
        "upkeep": upkeep,
        "planetary": planetary,
        "summary": summary,
        "at": _now(),
    }
    _LAST_RECONCILE.clear()
    _LAST_RECONCILE.update(result)
    return result


def reconcile_sovereign_mesh(*, force_quorum_apply: bool = False) -> Dict[str, Any]:
    return reconcile_fleet(force_quorum_apply=force_quorum_apply)


def last_reconcile() -> Dict[str, Any]:
    return dict(_LAST_RECONCILE)


def status_payload() -> Dict[str, Any]:
    public = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    return {
        "ok": True,
        "format": SOVEREIGN_FORMAT,
        "summary": sovereign_summary(),
        "subsystems": _subsystem_status(),
        "last_reconcile": last_reconcile(),
        "apis": {
            "status": f"{public}/api/convergence/tenant/sovereign/status",
            "reconcile": f"{public}/api/convergence/tenant/sovereign/reconcile",
        },
    }