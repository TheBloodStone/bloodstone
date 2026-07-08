"""QUASAR Phase 3 — braid-aware spend enforcement (pre-consensus policy gate)."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

DEFER_THRESHOLD_STONE = float(os.environ.get("QUASAR_DEFER_THRESHOLD_STONE", "100"))
HALT_THRESHOLD_STONE = float(os.environ.get("QUASAR_HALT_THRESHOLD_STONE", "10000"))
ENFORCEMENT_MODE = os.environ.get("QUASAR_ENFORCEMENT_MODE", "policy")


def evaluate_spend(
    amount_stone: float,
    *,
    braid_status: str = "healthy",
    witness_status: str = "live",
    lan_echo_status: str = "quorum",
    tripwire_active: bool = False,
    enforcement_mode: Optional[str] = None,
) -> Dict[str, Any]:
    mode = (enforcement_mode or ENFORCEMENT_MODE).strip().lower()
    amount = max(0.0, float(amount_stone or 0))

    if mode == "off":
        return {
            "allowed": True,
            "action": "allow",
            "reason": "QUASAR enforcement disabled.",
            "mode": mode,
        }

    if witness_status == "split":
        return {
            "allowed": False,
            "action": "halt",
            "reason": "Witness capsule split — spends halted pending manual review.",
            "mode": mode,
        }

    if lan_echo_status == "split_brain":
        return {
            "allowed": False,
            "action": "halt",
            "reason": "LAN echo split-brain detected — spends halted.",
            "mode": mode,
        }

    if tripwire_active and amount >= DEFER_THRESHOLD_STONE:
        return {
            "allowed": False,
            "action": "defer",
            "reason": "Anomaly tripwire active — defer spend until cleared.",
            "mode": mode,
            "retry_after_sec": 1800,
        }

    if braid_status == "deferred":
        if amount >= HALT_THRESHOLD_STONE:
            return {
                "allowed": False,
                "action": "halt",
                "reason": "Deferred finality epoch — large spends blocked until braid restitches.",
                "mode": mode,
            }
        if amount >= DEFER_THRESHOLD_STONE:
            return {
                "allowed": False,
                "action": "defer",
                "reason": "Deferred finality epoch — medium spends delayed.",
                "mode": mode,
                "retry_after_sec": 900,
            }

    if braid_status == "skewed" and amount >= DEFER_THRESHOLD_STONE:
        return {
            "allowed": False,
            "action": "defer",
            "reason": "Skewed epoch braid — increase confirmations before spending.",
            "mode": mode,
            "retry_after_sec": 600,
        }

    if witness_status in ("pending", "awaiting") and amount >= HALT_THRESHOLD_STONE:
        return {
            "allowed": False,
            "action": "defer",
            "reason": "Insufficient witness quorum for large spend.",
            "mode": mode,
            "retry_after_sec": 1200,
        }

    return {
        "allowed": True,
        "action": "allow",
        "reason": "Spend permitted under current QUASAR policy.",
        "mode": mode,
    }


def activation_params() -> Dict[str, Any]:
    """BIP9-style deployment descriptor for optional future soft-fork."""
    return {
        "deployment": "quasar_braid_finality",
        "version": 1,
        "start_height": int(os.environ.get("QUASAR_FORK_START_HEIGHT", "0")),
        "timeout_height": int(os.environ.get("QUASAR_FORK_TIMEOUT_HEIGHT", "0")),
        "threshold": int(os.environ.get("QUASAR_FORK_THRESHOLD", "750")),
        "window_blocks": int(os.environ.get("QUASAR_FORK_WINDOW", "1008")),
        "state": os.environ.get("QUASAR_FORK_STATE", "defined"),
        "enforcement_mode": ENFORCEMENT_MODE,
        "note": (
            "Phase 3 policy enforcement is live. Consensus soft-fork activation "
            "requires miner signaling when start_height is configured."
        ),
    }