"""Wave Y — unified tenant upkeep (quorum, gossip, broadcast, route ledger)."""

from __future__ import annotations

import os
import time
from typing import Any, Dict

UPKEEP_FORMAT = "bloodstone_tenant_upkeep/v1"
_LAST_UPKEEP: Dict[str, Any] = {}


def _now() -> int:
    return int(time.time())


def upkeep_tenant(*, force_quorum_apply: bool = False) -> Dict[str, Any]:
    from chain_mesh import tenant_broadcast as tb
    from chain_mesh import tenant_fleet_quorum as tquorum
    from chain_mesh import tenant_manifest_gossip as tmgossip
    from chain_mesh import tenant_route_ledger as tledger

    quorum = tquorum.update_quorum_state()
    applied = tquorum.apply_satisfied_bindings()
    broadcast_queue = tb.prepare_tenant_broadcast_queue()
    registry_sync = tb.sync_registry_tenants()
    manifest_snaps = tmgossip.build_manifest_snapshots()
    route_snaps = tledger.build_route_gossip_snapshots()
    result = {
        "ok": True,
        "format": UPKEEP_FORMAT,
        "quorum": quorum,
        "quorum_applied": applied,
        "broadcast_queue": broadcast_queue.get("count", 0),
        "registry_synced": registry_sync.get("indexed", 0),
        "manifest_gossip": len(manifest_snaps),
        "route_gossip": len(route_snaps),
        "assignments_total": tledger.status_payload().get("assignments_total", 0),
        "at": _now(),
    }
    if force_quorum_apply:
        result["force_quorum_apply"] = True
    _LAST_UPKEEP.clear()
    _LAST_UPKEEP.update(result)
    return result


def last_upkeep() -> Dict[str, Any]:
    return dict(_LAST_UPKEEP)


def status_payload() -> Dict[str, Any]:
    public = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    return {
        "ok": True,
        "format": UPKEEP_FORMAT,
        "last_upkeep": last_upkeep(),
        "apis": {
            "status": f"{public}/api/convergence/tenant/upkeep/status",
            "run": f"{public}/api/convergence/tenant/upkeep/run",
        },
    }