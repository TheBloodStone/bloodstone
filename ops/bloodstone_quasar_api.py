"""Shared Flask handlers for QUASAR API routes (Phases 1–3)."""

from __future__ import annotations

from typing import Any, Callable, Dict

import bloodstone_braid_index as bbi
import bloodstone_lan_echo as ble
import bloodstone_quasar as bq
import bloodstone_quasar_enforcement as bqe
import bloodstone_quasar_tripwire as bqt
import bloodstone_witness as bw


def status_payload(rpc: Callable) -> Dict[str, Any]:
    return bq.build_status(rpc)


def witness_submit(payload: Dict[str, Any]) -> Dict[str, Any]:
    return bw.ingest_capsule(payload)


def witness_list(*, tip_hash: str = "", limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    return bw.list_capsules(tip_hash=tip_hash, limit=limit, offset=offset)


def lan_echo_submit(
    payload: Dict[str, Any],
    *,
    public_ip: str,
    rpc: Callable,
) -> Dict[str, Any]:
    info = rpc("getblockchaininfo")
    return ble.record_echo(
        payload,
        public_ip=public_ip,
        pool_tip_hash=str(info.get("bestblockhash") or ""),
        pool_tip_height=int(info.get("blocks") or 0),
    )


def lan_echo_status_payload(
    *,
    public_ip: str = "",
    rpc: Callable,
) -> Dict[str, Any]:
    info = rpc("getblockchaininfo")
    return ble.lan_echo_status(
        public_ip=public_ip,
        pool_tip_hash=str(info.get("bestblockhash") or ""),
        pool_tip_height=int(info.get("blocks") or 0),
    )


def alerts_payload(rpc: Callable) -> Dict[str, Any]:
    result = bqt.evaluate_tripwires(rpc)
    asset_key = bqt.publish_alerts_mesh(result)
    if asset_key:
        result["mesh_asset_key"] = asset_key
    return result


def braid_index_payload(*, sync: bool = False, rpc: Callable = None) -> Dict[str, Any]:
    if sync and rpc is not None:
        bbi.sync_index(rpc)
        export = bbi.rpc_export()
        import json
        import os

        path = os.path.join(bbi.INDEX_ROOT, "rpc-export.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(export, fh, indent=2)
            fh.write("\n")
    return bbi.index_payload()


def enforcement_check(amount_stone: float, rpc: Callable) -> Dict[str, Any]:
    status = bq.build_status(rpc, use_cache=True)
    decision = bqe.evaluate_spend(
        amount_stone,
        braid_status=str(status.get("braid_status") or "unknown"),
        witness_status=str((status.get("witness") or {}).get("status") or ""),
        lan_echo_status=str((status.get("lan_echo") or {}).get("status") or ""),
        tripwire_active=bool((status.get("tripwire") or {}).get("active")),
        enforcement_mode=str(status.get("enforcement_mode") or "policy"),
    )
    decision["quasar_status"] = {
        "braid_status": status.get("braid_status"),
        "witness_status": (status.get("witness") or {}).get("status"),
        "lan_echo_status": (status.get("lan_echo") or {}).get("status"),
    }
    return decision


def activation_payload() -> Dict[str, Any]:
    return bqe.activation_params()


def emit_coordinator_witness(rpc: Callable) -> Dict[str, Any]:
    import os

    device_id = os.environ.get("QUASAR_COORDINATOR_DEVICE_ID", "vps-coordinator")
    try:
        mining = rpc("getnetworkinfo")
        peer_count = int(mining.get("connections") or 0)
    except Exception:
        peer_count = 0
    capsule = bw.build_capsule_from_rpc(
        rpc,
        device_id=device_id,
        node_mode="coordinator",
        peer_count=peer_count,
    )
    return bw.ingest_capsule(capsule)