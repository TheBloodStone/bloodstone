"""QUASAR — epoch braid finality, witness/LAN policy, Phase 3 braid index + enforcement."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import pool_algos as palgos

QUASAR_VERSION = "5.0"
QUASAR_PHASE = 5

EPOCH_BLOCKS = int(os.environ.get("QUASAR_EPOCH_BLOCKS", "10"))
SKEW_SHA256D_FRACTION = float(os.environ.get("QUASAR_SKEW_SHA256D_FRACTION", "0.85"))
SKEW_CPU_MIN_FRACTION = float(os.environ.get("QUASAR_SKEW_CPU_MIN_FRACTION", "0.10"))
WARN_SHA256D_FRACTION = float(os.environ.get("QUASAR_WARN_SHA256D_FRACTION", "0.70"))
BASE_CONFIRMATIONS = int(os.environ.get("QUASAR_BASE_CONFIRMATIONS", "6"))
MAX_CONFIRMATIONS = int(os.environ.get("QUASAR_MAX_CONFIRMATIONS", "20"))

BRAID_ALGOS: Tuple[str, ...] = ("sha256d", "neoscrypt", "yespower")
CPU_ALGOS = frozenset({"neoscrypt", "neoscrypt-xaya", "yespower"})

_CACHE: Dict[str, Any] = {"ts": 0.0, "payload": None}
_CACHE_TTL = float(os.environ.get("QUASAR_STATUS_CACHE_SEC", "45"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def braid_algo_bucket(algo: Optional[str]) -> str:
    """Map block pow algo to braid vector bucket."""
    key = palgos.normalize_algo(algo or "")
    if key in (palgos.SHA256D, "sha256"):
        return "sha256d"
    if key in (palgos.NEOSCRYPT_XAYA, palgos.LEGACY_NEOSCRYPT):
        return "neoscrypt"
    if key == palgos.YESPOWER:
        return "yespower"
    return "unknown"


def empty_braid_vector() -> Dict[str, int]:
    return {algo: 0 for algo in BRAID_ALGOS}


def summarize_epoch(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    vector = empty_braid_vector()
    unknown = 0
    algo_heights: Dict[str, List[int]] = {a: [] for a in BRAID_ALGOS}

    for block in blocks:
        powdata = block.get("powdata") or {}
        bucket = braid_algo_bucket(powdata.get("algo"))
        height = int(block.get("height", 0))
        if bucket in vector:
            vector[bucket] += 1
            algo_heights[bucket].append(height)
        else:
            unknown += 1

    total = sum(vector.values())
    sha_frac = (vector["sha256d"] / total) if total else 0.0
    cpu_frac = (
        (vector["neoscrypt"] + vector["yespower"]) / total if total else 0.0
    )
    distinct = sum(1 for v in vector.values() if v > 0)

    if (
        total
        and sha_frac >= SKEW_SHA256D_FRACTION
        and cpu_frac < SKEW_CPU_MIN_FRACTION
    ):
        status = "deferred"
    elif total and (
        sha_frac >= WARN_SHA256D_FRACTION or cpu_frac < SKEW_CPU_MIN_FRACTION
    ):
        status = "skewed"
    else:
        status = "healthy"

    return {
        "blocks_sampled": total,
        "unknown_algo_blocks": unknown,
        "braid_vector": vector,
        "sha256d_fraction": round(sha_frac, 4),
        "cpu_fraction": round(cpu_frac, 4),
        "distinct_algorithms": distinct,
        "status": status,
        "algo_heights": algo_heights,
        "tip_hash": blocks[-1]["hash"] if blocks else None,
        "start_height": blocks[0]["height"] if blocks else None,
        "end_height": blocks[-1]["height"] if blocks else None,
    }


def epoch_continuity_ok(
    previous: Dict[str, Any], current: Dict[str, Any], rpc: Callable
) -> bool:
    """True when ≥2 algo streams in the current epoch share ancestry with prior epoch tip."""
    prev_tip = previous.get("tip_hash")
    if not prev_tip or not current.get("blocks_sampled"):
        return True

    streams_with_continuity = 0
    for algo, heights in (current.get("algo_heights") or {}).items():
        if not heights:
            continue
        sample_height = max(heights)
        try:
            block_hash = rpc("getblockhash", [sample_height])
            block = rpc("getblock", [block_hash, 1])
            chain = {block.get("hash"), block.get("previousblockhash")}
            if prev_tip in chain:
                streams_with_continuity += 1
                continue
            ancestor = block.get("previousblockhash")
            steps = 0
            while ancestor and steps < EPOCH_BLOCKS * 3:
                if ancestor == prev_tip:
                    streams_with_continuity += 1
                    break
                parent = rpc("getblock", [ancestor, 1])
                ancestor = parent.get("previousblockhash")
                steps += 1
        except Exception:
            continue

    return streams_with_continuity >= 2


def confirmation_policy(
    braid_status: str,
    sha256d_fraction: float,
    witness_status: str = "not_live",
    witness_quorum: int = 0,
    *,
    tripwire_active: bool = False,
    lan_echo_status: str = "",
) -> Dict[str, Any]:
    base = BASE_CONFIRMATIONS
    multiplier = 1.0
    policy = "standard"
    reason = "Epoch braid balanced across CPU and SHA256d lanes."

    if witness_status == "split":
        return {
            "base": base,
            "witness_bonus": 0,
            "recommended_deposit": MAX_CONFIRMATIONS,
            "recommended_withdrawal": base,
            "multiplier": round(MAX_CONFIRMATIONS / base, 2),
            "policy": "halt_deposits",
            "reason": (
                "Witness capsules disagree on chain tip or tip height — halt deposits "
                "pending AI-reviewed operator confirmation "
                "(/api/quasar/witness/tip-review)."
            ),
        }

    if braid_status == "deferred":
        recommended = MAX_CONFIRMATIONS
        multiplier = recommended / base
        policy = "deferred_finality"
        reason = (
            f"SHA256d contributed {sha256d_fraction:.0%} of the current epoch "
            f"(threshold {SKEW_SHA256D_FRACTION:.0%}) with low CPU braid presence."
        )
    elif braid_status == "skewed":
        bump = int((sha256d_fraction - WARN_SHA256D_FRACTION) * 40)
        recommended = min(MAX_CONFIRMATIONS, max(12, base + max(0, bump)))
        multiplier = recommended / base
        policy = "skew_bump"
        reason = (
            "Epoch braid skew detected — increase deposit confirmations until "
            "neoscrypt and yespower blocks restitch the epoch."
        )
    else:
        recommended = base

    if tripwire_active:
        recommended = min(MAX_CONFIRMATIONS, max(recommended, 12))
        multiplier = recommended / base
        policy = "tripwire_bump"
        reason = "QUASAR anomaly tripwire active — auto-bumped deposit confirmations."

    if lan_echo_status in ("split_brain", "disagree"):
        recommended = min(MAX_CONFIRMATIONS, max(recommended, 15))
        multiplier = recommended / base
        policy = "lan_echo_warn"
        reason = "LAN echo quorum disagrees with pool tip — delay large deposits."

    witness_bonus = 0
    if witness_status == "live" and witness_quorum >= 3:
        witness_bonus = 0
    elif witness_status == "live" and witness_quorum < 3:
        witness_bonus = max(0, 3 - witness_quorum)
        recommended = min(MAX_CONFIRMATIONS, recommended + witness_bonus)
        multiplier = recommended / base
        policy = "witness_pending"
        reason = "Awaiting mesh witness quorum before large deposits."

    return {
        "base": base,
        "witness_bonus": witness_bonus,
        "recommended_deposit": int(recommended),
        "recommended_withdrawal": base,
        "multiplier": round(multiplier, 2),
        "policy": policy,
        "reason": reason,
    }


def witness_snapshot(tip_hash: str = "", tip_height: int = 0) -> Dict[str, Any]:
    try:
        import bloodstone_witness as bw

        return bw.witness_status_payload(tip_hash, tip_height)
    except Exception as exc:
        return {
            "phase": 2,
            "status": "awaiting",
            "quorum_depth": 0,
            "required_quorum": 3,
            "error": str(exc),
            "capsule_schema": "bloodstone/witness-capsule/v1",
        }


def fetch_epoch_blocks(
    rpc: Callable, tip: int, epoch_index: int
) -> List[Dict[str, Any]]:
    start = max(0, epoch_index * EPOCH_BLOCKS)
    end = min(tip, start + EPOCH_BLOCKS - 1)
    blocks: List[Dict[str, Any]] = []
    for height in range(start, end + 1):
        block_hash = rpc("getblockhash", [height])
        block = rpc("getblock", [block_hash, 1])
        blocks.append(
            {
                "height": block["height"],
                "hash": block["hash"],
                "time": block.get("time"),
                "powdata": block.get("powdata") or {},
            }
        )
    return blocks


def build_status(rpc: Callable, *, use_cache: bool = True) -> Dict[str, Any]:
    now = time.time()
    if use_cache and _CACHE.get("payload") and now - _CACHE["ts"] < _CACHE_TTL:
        return dict(_CACHE["payload"])

    tip = int(rpc("getblockcount"))
    info = rpc("getblockchaininfo")
    current_epoch_index = tip // EPOCH_BLOCKS if EPOCH_BLOCKS else 0
    previous_epoch_index = max(0, current_epoch_index - 1)

    current_blocks = fetch_epoch_blocks(rpc, tip, current_epoch_index)
    previous_blocks = (
        fetch_epoch_blocks(rpc, tip, previous_epoch_index)
        if previous_epoch_index < current_epoch_index
        else []
    )

    current = summarize_epoch(current_blocks)
    current["epoch_index"] = current_epoch_index
    previous = summarize_epoch(previous_blocks) if previous_blocks else None
    if previous:
        previous["epoch_index"] = previous_epoch_index

    continuity_ok = True
    if previous and previous.get("tip_hash"):
        try:
            continuity_ok = epoch_continuity_ok(previous, current, rpc)
        except Exception:
            continuity_ok = True

    current["continuity_ok"] = continuity_ok
    braid_status = current["status"]
    if not continuity_ok and braid_status == "healthy":
        braid_status = "skewed"
    if not continuity_ok and current["status"] == "deferred":
        braid_status = "deferred"

    tip_hash = str(info.get("bestblockhash") or "")
    witness = witness_snapshot(tip_hash, tip)

    tripwire = {"ok": True, "active": False, "alerts": [], "alert_count": 0}
    try:
        import bloodstone_quasar_tripwire as bqt

        tripwire = bqt.evaluate_tripwires(rpc)
    except Exception:
        try:
            import bloodstone_quasar_tripwire as bqt

            tripwire = bqt.load_alerts()
        except Exception:
            pass

    lan_echo = {"ok": True, "status": "no_echoes"}
    try:
        import bloodstone_lan_echo as ble

        lan_echo = ble.lan_echo_status(
            pool_tip_hash=tip_hash,
            pool_tip_height=tip,
        )
    except Exception:
        pass

    confirmations = confirmation_policy(
        braid_status,
        float(current.get("sha256d_fraction") or 0),
        witness_status=witness.get("status", "awaiting"),
        witness_quorum=int(witness.get("quorum_depth") or 0),
        tripwire_active=bool(tripwire.get("active")),
        lan_echo_status=str(lan_echo.get("status") or ""),
    )

    braid_index = {"ok": False}
    activation = {}
    signaling = {"ok": False}
    fork_rehearsal = {"ok": False}
    try:
        import bloodstone_braid_index as bbi
        import bloodstone_quasar_enforcement as bqe
        import bloodstone_quasar_signaling as bqs

        braid_index = bbi.index_payload(epochs=3)
        activation = bqe.activation_params()
        signaling = bqs.signaling_payload(rpc)
        if activation.get("state") == "defined" and signaling.get("state"):
            activation["state"] = signaling.get("state")
    except Exception:
        pass
    try:
        import bloodstone_quasar_fork as bqf

        fork_rehearsal = {
            "ok": True,
            "readiness": bqf.readiness_checks(
                rpc,
                signaling=signaling,
                braid_index=braid_index,
                activation=activation,
            ),
        }
    except Exception:
        pass

    payload = {
        "ok": True,
        "quasar_version": QUASAR_VERSION,
        "phase": QUASAR_PHASE,
        "layer": "E-BF(hard) + MWC + LEQ + EWP + AT",
        "enforcement_mode": activation.get("enforcement_mode", "policy"),
        "braid_index": braid_index,
        "activation": activation,
        "signaling": signaling,
        "fork_rehearsal": fork_rehearsal,
        "tip_height": tip,
        "tip_hash": tip_hash,
        "epoch_blocks": EPOCH_BLOCKS,
        "epoch_duration_minutes_approx": round((EPOCH_BLOCKS * 90) / 60, 1),
        "current_epoch": current,
        "previous_epoch": previous,
        "braid_status": braid_status,
        "braid_labels": {
            "healthy": "Braid balanced — standard confirmations apply.",
            "skewed": "Braid skewed — increase deposit confirmations.",
            "deferred": "Deferred finality — SHA256d-heavy epoch; treat as high reorg risk.",
        },
        "witness": witness,
        "lan_echo": lan_echo,
        "tripwire": {
            "active": bool(tripwire.get("active")),
            "alert_count": int(tripwire.get("alert_count") or 0),
            "alerts": tripwire.get("alerts") or [],
            "evaluated_at": tripwire.get("evaluated_at"),
        },
        "confirmations": confirmations,
        "thresholds": {
            "skew_sha256d_fraction": SKEW_SHA256D_FRACTION,
            "skew_cpu_min_fraction": SKEW_CPU_MIN_FRACTION,
            "warn_sha256d_fraction": WARN_SHA256D_FRACTION,
        },
        "updated_utc": _utc_now(),
    }

    _CACHE["ts"] = now
    _CACHE["payload"] = payload
    return dict(payload)


def exchange_quasar_fields(status: Dict[str, Any], public_root: str) -> Dict[str, Any]:
    """Compact QUASAR block for /api/exchange listing pack."""
    conf = status.get("confirmations") or {}
    current = status.get("current_epoch") or {}
    return {
        "version": status.get("quasar_version"),
        "phase": status.get("phase"),
        "braid_status": status.get("braid_status"),
        "braid_finality_epoch_blocks": status.get("epoch_blocks"),
        "confirmation_multiplier": conf.get("multiplier"),
        "confirmations_deposit_recommended": conf.get("recommended_deposit"),
        "confirmations_withdrawal_recommended": conf.get("recommended_withdrawal"),
        "confirmations_policy": conf.get("policy"),
        "confirmations_reason": conf.get("reason"),
        "current_epoch_braid_vector": current.get("braid_vector"),
        "sha256d_epoch_fraction": current.get("sha256d_fraction"),
        "witness_status": (status.get("witness") or {}).get("status"),
        "witness_quorum_depth": (status.get("witness") or {}).get("quorum_depth"),
        "lan_echo_status": (status.get("lan_echo") or {}).get("status"),
        "lan_echo_quorum": (status.get("lan_echo") or {}).get("quorum_label"),
        "tripwire_active": bool((status.get("tripwire") or {}).get("active")),
        "tripwire_alerts": (status.get("tripwire") or {}).get("alerts") or [],
        "enforcement_mode": status.get("enforcement_mode"),
        "braid_index_synced_height": (status.get("braid_index") or {}).get("synced_height"),
        "braid_index_status": (status.get("braid_index") or {}).get("braid_status"),
        "fork_state": (status.get("activation") or {}).get("state"),
        "signaling_blocks": (status.get("signaling") or {}).get("signaling_blocks"),
        "signaling_threshold": (status.get("signaling") or {}).get("threshold_blocks"),
        "fork_rehearsal_ready": bool((status.get("fork_rehearsal") or {}).get("readiness", {}).get("ready")),
        "signaling_url": f"{public_root.rstrip('/')}/api/quasar/signaling",
        "fork_rehearsal_url": f"{public_root.rstrip('/')}/api/quasar/fork-rehearsal",
        "miner_guide_url": f"{public_root.rstrip('/')}/downloads/Bloodstone-QUASAR-Phase4-Miner-Operator-Guide.md",
        "status_url": f"{public_root.rstrip('/')}/api/quasar/status",
        "braid_index_url": f"{public_root.rstrip('/')}/api/quasar/braid-index",
        "enforcement_url": f"{public_root.rstrip('/')}/api/quasar/enforcement/check",
        "activation_url": f"{public_root.rstrip('/')}/api/quasar/activation",
        "guide_url": f"{public_root.rstrip('/')}/downloads/Bloodstone-QUASAR-Witness-Aware-Confirmation-Guide.md",
        "phase3_proposal_url": f"{public_root.rstrip('/')}/downloads/Bloodstone-QUASAR-Phase3-Braid-Finality-Proposal.md",
    }