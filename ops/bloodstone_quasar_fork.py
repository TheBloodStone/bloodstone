"""QUASAR Phase 4 — testnet fork rehearsal coordinator."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict

import bloodstone_braid_index as bbi
import bloodstone_quasar_enforcement as bqe
import bloodstone_quasar_signaling as bqs

REHEARSAL_ROOT = os.environ.get(
    "QUASAR_FORK_REHEARSAL_DIR",
    os.path.join(bbi.INDEX_ROOT, "fork-rehearsal"),
)
STATUS_FILE = os.path.join(REHEARSAL_ROOT, "status.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_dir() -> None:
    os.makedirs(REHEARSAL_ROOT, exist_ok=True)


def readiness_checks(
    rpc: Callable,
    *,
    signaling: Dict[str, Any],
    braid_index: Dict[str, Any],
    activation: Dict[str, Any],
) -> Dict[str, Any]:
    checks = []

    index_ok = bool(braid_index.get("enforcement_ready"))
    checks.append(
        {
            "id": "braid_index",
            "ok": index_ok,
            "detail": f"synced_height={braid_index.get('synced_height', 0)}",
        }
    )

    signaling_blocks = int(signaling.get("signaling_blocks") or 0)
    checks.append(
        {
            "id": "miner_signaling",
            "ok": signaling_blocks > 0 or signaling.get("state") in ("started", "locked_in"),
            "detail": f"{signaling_blocks}/{signaling.get('threshold_blocks')} blocks in window",
        }
    )

    braid_status = str(braid_index.get("braid_status") or "unknown")
    checks.append(
        {
            "id": "braid_health",
            "ok": braid_status in ("healthy", "skewed"),
            "detail": f"braid_status={braid_status}",
        }
    )

    start_height = int(activation.get("start_height") or 0)
    tip = int(signaling.get("tip_height") or 0)
    checks.append(
        {
            "id": "fork_schedule",
            "ok": start_height == 0 or tip >= start_height,
            "detail": f"start_height={start_height} tip={tip}",
        }
    )

    passed = sum(1 for c in checks if c["ok"])
    return {
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "ready": passed == len(checks),
    }


def rehearsal_payload(rpc: Callable) -> Dict[str, Any]:
    signaling = bqs.signaling_payload(rpc)
    braid_index = bbi.index_payload(epochs=3)
    activation = bqe.activation_params()
    readiness = readiness_checks(
        rpc,
        signaling=signaling,
        braid_index=braid_index,
        activation=activation,
    )

    return {
        "ok": True,
        "phase": 4,
        "mode": os.environ.get("QUASAR_FORK_REHEARSAL_MODE", "testnet"),
        "signaling": signaling,
        "braid_index": {
            "synced_height": braid_index.get("synced_height"),
            "braid_status": braid_index.get("braid_status"),
            "enforcement_ready": braid_index.get("enforcement_ready"),
        },
        "activation": activation,
        "readiness": readiness,
        "next_steps": _next_steps(readiness, signaling),
        "updated_utc": _utc_now(),
    }


def _next_steps(readiness: Dict[str, Any], signaling: Dict[str, Any]) -> list:
    steps = []
    if not readiness.get("ready"):
        for check in readiness.get("checks") or []:
            if not check.get("ok"):
                steps.append(f"Resolve check `{check['id']}`: {check.get('detail')}")
    if signaling.get("state") == "defined":
        steps.append("Set QUASAR_FORK_START_HEIGHT and rebuild miners with quasar_braid_finality bit.")
    if signaling.get("blocks_until_lock_in", 0) > 0:
        steps.append(
            f"Need {signaling['blocks_until_lock_in']} more signaling blocks "
            f"(bit {signaling.get('version_bit')}) in the window."
        )
    if not steps:
        steps.append("Rehearsal criteria met — proceed to locked-in monitoring and testnet activation drill.")
    return steps


def persist_rehearsal_status(rpc: Callable) -> Dict[str, Any]:
    payload = rehearsal_payload(rpc)
    _ensure_dir()
    with open(STATUS_FILE, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    payload["status_file"] = STATUS_FILE
    return payload