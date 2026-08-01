#!/usr/bin/env python3
"""Fork Lab launch-fee decay curve (§3c) — portal layer only, not consensus.

requirement(stone_height, stone_diff) with:
  - STONE post-genesis height clock (not child-coin eras)
  - height-stepped decay START → FLOOR
  - difficulty gate so thin networks do not cheapen launches early
  - freeze-at-draft is the caller's job (this module only computes current)

Node facts locked 2026-08-01 (bloodstone-cli mainnet):
  STONE_GENESIS_HEIGHT = 0
  GENESIS_DIFF_SHA256D = 0.00390625   # first sha256d block height 1
  GENESIS_DIFF_NEOSCRYPT = 0.000244140625  # genesis powdata (height 0)
  STEP_BLOCKS = 350_640               # ~1 design-year at ~90s average
  design block time ~90s; empirical tip often ~240–280s (difficulty gate covers)

Enable with FORK_LAB_FEE_DECAY=1 (default off until operator flips).
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, Optional

# ── Locked parameters (RFQ v1.4 + operator sign-off) ─────────────────────

START = float(os.environ.get("FORK_LAB_FEE_START", "1000000"))
FLOOR = float(os.environ.get("FORK_LAB_FEE_FLOOR", "100000"))
DECAY = float(os.environ.get("FORK_LAB_FEE_DECAY_FACTOR", "0.90"))
STEP_BLOCKS = int(os.environ.get("FORK_LAB_FEE_STEP_BLOCKS", "350640"))
STONE_GENESIS_HEIGHT = int(os.environ.get("STONE_GENESIS_HEIGHT", "0"))

# Difficulty gate seeds — from live node, not guessed
# Gate uses SHA256d (merge-mine / economic security lane)
GENESIS_DIFF_SHA256D = float(
    os.environ.get("STONE_GENESIS_DIFF_SHA256D", "0.00390625")
)
GENESIS_DIFF_NEOSCRYPT = float(
    os.environ.get("STONE_GENESIS_DIFF_NEOSCRYPT", "0.000244140625")
)

# Step n unlocks when tip_sha256d_diff >= GENESIS_DIFF_SHA256D * (2 ** n)
# Rate-cap: at most one newly-unlocked step beyond scheduled (no blip dump)
DIFF_GATE_BASE = float(os.environ.get("FORK_LAB_DIFF_GATE_BASE", str(GENESIS_DIFF_SHA256D)))

FEE_DECAY_ENABLED = str(
    os.environ.get("FORK_LAB_FEE_DECAY", "0")
).strip().lower() in ("1", "true", "yes", "on")

PUBLIC_ROOT = os.environ.get(
    "BLOODSTONE_PUBLIC_ROOT", "https://bloodstone.rocks"
).rstrip("/")


def _cli_json(*args: str) -> Any:
    cmd = ["bloodstone-cli", *args]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=20, text=True)
        out = out.strip()
        if out[:1] in "{[":
            return json.loads(out)
        try:
            return int(out)
        except ValueError:
            try:
                return float(out)
            except ValueError:
                return out
    except Exception:
        return None


def live_stone_signals() -> Dict[str, Any]:
    """Read STONE height + multi-algo tip difficulty from the node."""
    height = _cli_json("getblockcount")
    try:
        height = int(height or 0)
    except Exception:
        height = 0
    mi = _cli_json("getmininginfo") or {}
    diff = mi.get("difficulty") or {}
    if not isinstance(diff, dict):
        diff = {"sha256d": float(diff or 0)}
    return {
        "height": height,
        "difficulty": {
            "sha256d": float(diff.get("sha256d") or 0),
            "neoscrypt": float(diff.get("neoscrypt") or 0),
            "yespower": float(diff.get("yespower") or 0),
        },
        "stone_genesis_height": STONE_GENESIS_HEIGHT,
        "genesis_diff_sha256d": GENESIS_DIFF_SHA256D,
        "genesis_diff_neoscrypt": GENESIS_DIFF_NEOSCRYPT,
    }


def steps_from_height(stone_height: int) -> int:
    h = max(0, int(stone_height) - int(STONE_GENESIS_HEIGHT))
    step = max(1, int(STEP_BLOCKS))
    return h // step


def scheduled_requirement(steps: int) -> float:
    """START * DECAY**steps, floored at FLOOR."""
    s = max(0, int(steps))
    val = START * (DECAY ** s)
    return max(FLOOR, val)


def max_unlocked_step(stone_diff_sha256d: float) -> int:
    """Highest step index unlocked by difficulty (0 = start, no decay yet)."""
    base = max(1e-18, float(DIFF_GATE_BASE))
    d = max(0.0, float(stone_diff_sha256d))
    if d < base:
        return 0
    # step n requires base * 2^n
    n = 0
    thr = base
    # cap steps so we don't loop forever
    while n < 64 and d >= thr * 2:
        n += 1
        thr *= 2
    return n


def requirement(
    stone_height: int,
    stone_diff_sha256d: float,
    *,
    enabled: Optional[bool] = None,
) -> Dict[str, Any]:
    """Compute current launch fee (not frozen — caller freezes at draft)."""
    en = FEE_DECAY_ENABLED if enabled is None else bool(enabled)
    if not en:
        return {
            "ok": True,
            "enabled": False,
            "requirement_stone": START,
            "note": "fee decay disabled (FORK_LAB_FEE_DECAY=0); returning START",
            "start": START,
            "floor": FLOOR,
        }

    sched_steps = steps_from_height(stone_height)
    unlocked = max_unlocked_step(stone_diff_sha256d)
    # Gate: cannot decay more steps than difficulty has unlocked
    effective_steps = min(sched_steps, unlocked)
    # Rate-cap: never jump more than +1 step vs previous unlocked floor of schedule
    # (scheduled already discrete; gate is the clamp)
    req = scheduled_requirement(effective_steps)
    gated_hold = scheduled_requirement(unlocked) if unlocked < sched_steps else req
    # If schedule is ahead of difficulty, hold at last unlocked schedule value
    if sched_steps > unlocked:
        req = scheduled_requirement(unlocked)

    return {
        "ok": True,
        "enabled": True,
        "requirement_stone": round(req, 2),
        "start": START,
        "floor": FLOOR,
        "decay": DECAY,
        "step_blocks": STEP_BLOCKS,
        "stone_genesis_height": STONE_GENESIS_HEIGHT,
        "stone_height": int(stone_height),
        "elapsed_height": max(0, int(stone_height) - STONE_GENESIS_HEIGHT),
        "scheduled_steps": sched_steps,
        "diff_unlocked_steps": unlocked,
        "effective_steps": effective_steps,
        "stone_diff_sha256d": float(stone_diff_sha256d),
        "diff_gate_base": DIFF_GATE_BASE,
        "held_by_difficulty_gate": sched_steps > unlocked,
        "formula": "max(FLOOR, START * DECAY**effective_steps); effective=min(height_steps, diff_steps)",
    }


def current_requirement() -> Dict[str, Any]:
    sig = live_stone_signals()
    out = requirement(
        sig["height"],
        sig["difficulty"]["sha256d"],
    )
    out["live"] = sig
    out["public_root"] = PUBLIC_ROOT
    out["schema"] = "bloodstone/fork-lab-fee-curve/v1"
    # Tripwire: warn long before first STEP_BLOCKS boundary (not a human calendar)
    elapsed = max(0, int(sig.get("height") or 0) - STONE_GENESIS_HEIGHT)
    next_boundary = ((elapsed // STEP_BLOCKS) + 1) * STEP_BLOCKS
    blocks_to_next = max(0, next_boundary - elapsed)
    out["next_step_boundary_height"] = STONE_GENESIS_HEIGHT + next_boundary
    out["blocks_to_next_step"] = blocks_to_next
    # Fire soft alert when within ~10% of a step (or first step when past 50% of STEP_BLOCKS)
    out["step_boundary_approach_alert"] = bool(
        FEE_DECAY_ENABLED and blocks_to_next <= max(1000, STEP_BLOCKS // 10)
    )
    return out


if __name__ == "__main__":
    print(json.dumps(current_requirement(), indent=2))
