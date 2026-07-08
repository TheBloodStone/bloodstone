"""Time Capsule — archive full chain to mesh, then optionally prune local storage.

History lives in the federated mesh so new nodes sync a pruned tip (~550 MiB) instead of
downloading the full chain. Coordinator archives block files before any prune is applied.
"""

import json
import os
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from chain_mesh.config import (
    CLI,
    CONF,
    DATADIR,
    TIME_CAPSULE_ENABLE_PRUNE,
    TIME_CAPSULE_MIN_PEER_UNIQUE_CHUNKS,
    TIME_CAPSULE_PRUNE_MIB,
)
from chain_mesh import db as mesh_db
from chain_mesh.manifest import current_manifest, publish_manifest
from chain_mesh.restore import local_coverage
from chain_mesh.store import chunk_exists, stored_chunk_count


def _now() -> int:
    return int(time.time())


def _rpc(method: str, *params: Any) -> Any:
    args = [CLI, f"-conf={CONF}", method]
    for p in params:
        args.append(json.dumps(p))
    raw = subprocess.check_output(args, stderr=subprocess.DEVNULL, timeout=120)
    return json.loads(raw.decode("utf-8"))


def _blockchain_info() -> Dict[str, Any]:
    try:
        return _rpc("getblockchaininfo")
    except (subprocess.SubprocessError, json.JSONDecodeError, FileNotFoundError):
        return {}


def _blocks_dir_bytes() -> int:
    blocks_dir = os.path.join(DATADIR, "blocks")
    if not os.path.isdir(blocks_dir):
        return 0
    total = 0
    for name in os.listdir(blocks_dir):
        if name.startswith(("blk", "rev")) and name.endswith(".dat"):
            path = os.path.join(blocks_dir, name)
            if os.path.isfile(path):
                total += os.path.getsize(path)
    return total


def _conf_has_txindex() -> bool:
    if not os.path.isfile(CONF):
        return False
    with open(CONF, "r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.lower().startswith("txindex="):
                val = stripped.split("=", 1)[1].strip().lower()
                return val not in ("0", "false", "no")
    return False


def _conf_prune_mib() -> Optional[int]:
    if not os.path.isfile(CONF):
        return None
    with open(CONF, "r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.lower().startswith("prune="):
                try:
                    return int(stripped.split("=", 1)[1].strip())
                except ValueError:
                    return None
    return None


def _set_conf_lines(
    *,
    enable_prune_mib: Optional[int] = None,
    disable_txindex: bool = False,
) -> Tuple[bool, str]:
    """Atomically update bloodstone.conf for prune mode."""
    if not os.path.isfile(CONF):
        return False, f"config not found: {CONF}"
    with open(CONF, "r", encoding="utf-8") as fh:
        lines = fh.readlines()

    changed = False
    out: List[str] = []
    saw_prune = False
    saw_txindex = False

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        if lower.startswith("prune="):
            saw_prune = True
            if enable_prune_mib is not None:
                new = f"prune={enable_prune_mib}\n"
                if line != new:
                    changed = True
                out.append(new)
            else:
                out.append(line)
            continue
        if lower.startswith("txindex="):
            saw_txindex = True
            if disable_txindex:
                new = "# txindex=1  # disabled for Time Capsule prune (history on mesh)\n"
                if line != new:
                    changed = True
                out.append(new)
            else:
                out.append(line)
            continue
        out.append(line)

    if enable_prune_mib is not None and not saw_prune:
        out.append(f"\n# Time Capsule — keep recent blocks locally; history on mesh\n")
        out.append(f"prune={enable_prune_mib}\n")
        changed = True
    if disable_txindex and not saw_txindex:
        out.append("# txindex disabled for prune compatibility\n")
        changed = True

    if not changed:
        return False, "config unchanged"

    tmp = CONF + ".time-capsule.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.writelines(out)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, CONF)
    return True, "config updated"


def _restart_node() -> None:
    subprocess.run(["systemctl", "restart", "bloodstoned"], check=False, timeout=60)
    for _ in range(30):
        time.sleep(2)
        info = _blockchain_info()
        if info.get("blocks") is not None:
            return
    raise RuntimeError("bloodstoned did not come back after restart")


def capsule_coverage() -> Dict[str, Any]:
    """Coordinator chunk coverage for the current manifest."""
    cov = local_coverage()
    manifest = current_manifest()
    pct = 100.0
    if manifest and cov.get("need"):
        pct = round(100.0 * int(cov.get("have") or 0) / int(cov["need"]), 2)
    return {
        **cov,
        "coverage_pct": pct,
        "coordinator_chunks": stored_chunk_count(),
    }


def is_capsule_complete() -> bool:
    cov = capsule_coverage()
    return bool(cov.get("complete"))


def peer_redundancy_ok() -> Tuple[bool, Dict[str, Any]]:
    stats = mesh_db.public_stats()
    unique = int(stats.get("peer_unique_chunks") or 0)
    need = int((stats.get("manifest") or {}).get("chunk_count") or 0)
    min_required = TIME_CAPSULE_MIN_PEER_UNIQUE_CHUNKS
    if min_required <= 0:
        return True, {"required": 0, "have": unique, "manifest_chunks": need}
    ok = unique >= min_required
    return ok, {
        "required": min_required,
        "have": unique,
        "manifest_chunks": need,
    }


def archive_capsule(*, force_publish: bool = False) -> Dict[str, Any]:
    """Publish block files to mesh and verify coordinator holds every chunk."""
    mesh_db.init_db()
    info = _blockchain_info()
    height = int(info.get("blocks") or 0)
    best_hash = str(info.get("bestblockhash") or "")
    blocks_bytes = _blocks_dir_bytes()

    if force_publish or not is_capsule_complete():
        pub = publish_manifest(store_chunks=True)
    else:
        manifest = current_manifest()
        pub = {
            "skipped": True,
            "manifest_id": manifest["id"] if manifest else 0,
            "best_block_hash": best_hash,
            "block_height": height,
            "chunk_count": manifest["chunk_count"] if manifest else 0,
        }

    cov = capsule_coverage()
    complete = bool(cov.get("complete"))
    mesh_db.record_time_capsule_event(
        action="archive",
        block_height=height,
        best_block_hash=best_hash,
        chunk_count=int(cov.get("need") or pub.get("chunk_count") or 0),
        coordinator_coverage_pct=float(cov.get("coverage_pct") or 0),
        blocks_bytes=blocks_bytes,
        pruned=bool(info.get("pruned")),
        message="archive complete" if complete else "archive incomplete",
    )
    return {
        "ok": complete,
        "complete": complete,
        "publish": pub,
        "coverage": cov,
        "blocks_bytes": blocks_bytes,
        "block_height": height,
        "best_block_hash": best_hash,
    }


def prune_readiness() -> Dict[str, Any]:
    """Whether local prune is safe and what would change."""
    info = _blockchain_info()
    cov = capsule_coverage()
    peer_ok, peer_stats = peer_redundancy_ok()
    txindex = _conf_has_txindex()
    conf_prune = _conf_prune_mib()
    already_pruned = bool(info.get("pruned")) or conf_prune is not None

    blockers: List[str] = []
    if not cov.get("complete"):
        blockers.append("capsule archive incomplete on coordinator")
    if not TIME_CAPSULE_ENABLE_PRUNE:
        blockers.append("BLOODSTONE_TIME_CAPSULE_ENABLE_PRUNE not set")
    if not peer_ok:
        blockers.append(
            f"peer redundancy below minimum ({peer_stats['have']}/{peer_stats['required']} unique chunks)"
        )
    if already_pruned:
        blockers.append("node already pruned")

    return {
        "ready": len(blockers) == 0,
        "blockers": blockers,
        "enable_prune_flag": TIME_CAPSULE_ENABLE_PRUNE,
        "target_prune_mib": TIME_CAPSULE_PRUNE_MIB,
        "txindex_enabled": txindex,
        "txindex_will_disable": txindex,
        "conf_prune_mib": conf_prune,
        "already_pruned": already_pruned,
        "peer_redundancy": peer_stats,
        "coverage": cov,
    }


def apply_prune(*, confirm: bool = False) -> Dict[str, Any]:
    """Enable prune mode after capsule is complete. Requires confirm=True."""
    if not confirm:
        raise ValueError("confirm=true required to apply prune")

    readiness = prune_readiness()
    if not readiness["ready"]:
        return {
            "ok": False,
            "error": "prune not ready",
            "readiness": readiness,
        }

    info = _blockchain_info()
    height = int(info.get("blocks") or 0)
    best_hash = str(info.get("bestblockhash") or "")
    blocks_before = _blocks_dir_bytes()
    disable_tx = bool(readiness["txindex_enabled"])

    changed, msg = _set_conf_lines(
        enable_prune_mib=TIME_CAPSULE_PRUNE_MIB,
        disable_txindex=disable_tx,
    )
    if not changed:
        return {"ok": False, "error": msg, "readiness": readiness}

    _restart_node()
    info_after = _blockchain_info()
    prune_height = None
    try:
        prune_height = int(_rpc("pruneblockchain", TIME_CAPSULE_PRUNE_MIB * 1024 * 1024))
    except (subprocess.SubprocessError, json.JSONDecodeError, TypeError, ValueError):
        pass

    blocks_after = _blocks_dir_bytes()
    mesh_db.record_time_capsule_event(
        action="prune",
        block_height=height,
        best_block_hash=best_hash,
        chunk_count=int(readiness["coverage"].get("need") or 0),
        coordinator_coverage_pct=float(readiness["coverage"].get("coverage_pct") or 0),
        blocks_bytes=blocks_after,
        pruned=True,
        prune_mib=TIME_CAPSULE_PRUNE_MIB,
        txindex_disabled=disable_tx,
        message=f"prune enabled ({TIME_CAPSULE_PRUNE_MIB} MiB); pruneheight={prune_height}",
    )
    return {
        "ok": True,
        "prune_mib": TIME_CAPSULE_PRUNE_MIB,
        "pruneheight": prune_height,
        "txindex_disabled": disable_tx,
        "blocks_bytes_before": blocks_before,
        "blocks_bytes_after": blocks_after,
        "node": info_after,
    }


def maybe_prune() -> Dict[str, Any]:
    """Upkeep hook: prune only when flag set and capsule complete."""
    readiness = prune_readiness()
    if not readiness["ready"]:
        return {"ok": True, "skipped": True, "reason": readiness["blockers"], "readiness": readiness}
    return apply_prune(confirm=True)


def capability_matrix(*, pruned: bool, txindex: bool) -> Dict[str, Any]:
    """What the node can do locally vs via Time Capsule mesh."""
    return {
        "validate_chain": True,
        "mine": True,
        "wallet_recent": True,
        "relay_blocks": True,
        "serve_recent_blocks_rpc": True,
        "serve_old_blocks_rpc": not pruned or "mesh_restore",
        "getrawtransaction_by_txid": txindex or (not pruned),
        "getrawtransaction_via_mesh": pruned and not txindex,
        "initial_sync_download": "pruned_tip" if pruned else "full_chain",
        "history_source": "time_capsule_mesh" if pruned else "local_disk",
    }


def status_payload() -> Dict[str, Any]:
    """Public Time Capsule status for API and UI."""
    mesh_db.init_db()
    info = _blockchain_info()
    cov = capsule_coverage()
    readiness = prune_readiness()
    manifest = current_manifest()
    stats = mesh_db.public_stats()
    pruned = bool(info.get("pruned"))
    txindex = _conf_has_txindex()
    blocks_bytes = _blocks_dir_bytes()
    prune_target_bytes = TIME_CAPSULE_PRUNE_MIB * 1024 * 1024
    potential_savings = max(0, blocks_bytes - prune_target_bytes) if not pruned else 0

    return {
        "ok": True,
        "name": "Time Capsule",
        "tagline": "Full chain history on the mesh — pruned tip on disk",
        "block_height": int(info.get("blocks") or 0),
        "best_block_hash": str(info.get("bestblockhash") or ""),
        "size_on_disk": int(info.get("size_on_disk") or 0),
        "blocks_bytes": blocks_bytes,
        "pruned": pruned,
        "pruneheight": int(info.get("pruneheight") or 0),
        "prune_target_mib": TIME_CAPSULE_PRUNE_MIB,
        "potential_savings_bytes": potential_savings,
        "txindex_enabled": txindex,
        "capsule_complete": bool(cov.get("complete")),
        "coverage": cov,
        "manifest": {
            "chunk_count": manifest["chunk_count"] if manifest else 0,
            "total_bytes": manifest["total_bytes"] if manifest else 0,
            "updated_at": manifest["created_at"] if manifest else 0,
        },
        "mesh_peers": {
            "active_peers": int(stats.get("active_peers") or 0),
            "peer_unique_chunks": int(stats.get("peer_unique_chunks") or 0),
            "coordinator_chunks": int(stats.get("coordinator_chunks") or 0),
        },
        "prune_readiness": readiness,
        "capabilities": capability_matrix(pruned=pruned, txindex=txindex),
        "recent_events": mesh_db.list_time_capsule_events(limit=5),
    }