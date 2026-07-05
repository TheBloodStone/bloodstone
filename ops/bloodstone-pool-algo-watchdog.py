#!/usr/bin/env python3
"""Balance proportional pool weight across neoscrypt, yespower, and sha256d."""

import argparse
import json
import logging
import os
import subprocess
import sys
import time

sys.path.insert(0, "/root")
import pool_algo_balance as balance  # noqa: E402

LOG_PATH = os.environ.get(
    "BLOODSTONE_POOL_ALGO_WATCHDOG_LOG",
    "/var/log/bloodstone-pool-algo-watchdog.log",
)
RECENT_SEC = int(os.environ.get("BLOODSTONE_ALGO_BALANCE_WINDOW_SEC", "1800"))
POOL_MINERS = {
    "neoscrypt": "bloodstone-neoscrypt-pool-miner.service",
    "yespower": "bloodstone-yespower-miner.service",
}

UPKEEP_CONF = os.environ.get("BLOODSTONE_UPKEEP_CONF", "/root/bloodstone-upkeep.conf")
LOCAL_MINERS_DISABLED: set = set()


def _load_upkeep_role() -> None:
    global LOCAL_MINERS_DISABLED
    if not os.path.isfile(UPKEEP_CONF):
        return
    try:
        with open(UPKEEP_CONF, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("UPKEEP_ROLE="):
                    role = line.split("=", 1)[1].strip().strip('"')
                    if role != "main":
                        return
                if line.startswith("LOCAL_MINERS_DISABLED=("):
                    units = []
                    for raw in fh:
                        raw = raw.strip()
                        if raw == ")":
                            break
                        units.append(raw.strip('"'))
                    LOCAL_MINERS_DISABLED = set(units)
                    return
    except OSError:
        pass


_load_upkeep_role()


def _log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
    print(line)
    try:
        os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def _service_active(unit: str) -> bool:
    try:
        out = subprocess.check_output(
            ["systemctl", "is-active", unit],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out == "active"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _set_service(unit: str, active: bool) -> bool:
    action = "start" if active else "stop"
    try:
        subprocess.run(
            ["systemctl", action, unit],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def adjust_server_miners(
    multipliers: dict,
    recent_weight: dict,
    rebalance_active: bool = False,
) -> list:
    """Throttle CPU pool miners on overrepresented algos."""
    if LOCAL_MINERS_DISABLED:
        return []
    actions = []
    weights = [float(recent_weight.get(a, 0) or 0) for a in balance.POOL_ALGOS]
    avg = sum(weights) / max(len(weights), 1) or 1.0

    for algo, unit in POOL_MINERS.items():
        w = float(recent_weight.get(algo, 0) or 0)
        mult = float(multipliers.get(algo, 1.0))
        active = _service_active(unit)

        if rebalance_active:
            if not active and _set_service(unit, True):
                actions.append(f"started {unit} (sha256 block rebalance)")
            continue

        if w > avg * 2.5 and mult < 0.75:
            if active and _set_service(unit, False):
                actions.append(f"stopped {unit} (algo overweight)")
        elif w < avg * 0.35 and mult > 1.5:
            if not active and _set_service(unit, True):
                actions.append(f"started {unit} (algo underweight)")

    return actions


def run_once() -> dict:
    prev = balance.load_state()
    recent = balance.recent_share_weight_by_algo(RECENT_SEC)
    open_w = balance.open_round_weight_by_algo()
    multipliers, actions, target = balance.compute_multipliers(
        recent,
        open_w,
        previous=prev.get("multipliers"),
    )

    rebalance = dict(prev.get("sha256_block_rebalance") or balance._default_rebalance())
    rebalance, guard_actions = balance.apply_even_share_guard(open_w, rebalance)
    actions.extend(guard_actions)
    multipliers, rebalance, rebalance_actions = balance.apply_sha256_block_rebalance(
        multipliers,
        recent,
        open_w,
        rebalance,
    )
    actions.extend(rebalance_actions)

    sha256_miner_weight = balance.recent_sha256_miner_weight(RECENT_SEC)
    sha256_miner_mult, sha256_actions = balance.compute_sha256_miner_multipliers(
        sha256_miner_weight,
        previous=prev.get("sha256_miner_multipliers"),
    )

    miner_actions = adjust_server_miners(
        multipliers,
        recent,
        rebalance_active=bool(rebalance.get("active")),
    )
    state = {
        "updated_at": int(time.time()),
        "multipliers": multipliers,
        "sha256_miner_multipliers": sha256_miner_mult,
        "sha256_miner_weight": sha256_miner_weight,
        "sha256_block_rebalance": rebalance,
        "recent_weight_sec": RECENT_SEC,
        "recent_weight": recent,
        "open_round_weight": open_w,
        "target_weight": target,
        "actions": actions + sha256_actions + miner_actions,
    }
    balance.save_state(state)
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description="Bloodstone pool algo balance watchdog")
    parser.add_argument("--once", action="store_true", help="run one balance pass")
    parser.add_argument("--show", action="store_true", help="print current balance state")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.show:
        print(json.dumps(balance.load_state(), indent=2))
        return 0

    state = run_once()
    rb = state.get("sha256_block_rebalance") or {}
    rb_note = ""
    if rb.get("active"):
        other_open = balance.other_open_weight(state.get("open_round_weight") or {})
        rb_note = (
            f" | sha256-rebalance ON height={rb.get('block_height')} "
            f"CPU={other_open:.0f}/{float(rb.get('target_other_weight') or 0):.0f}"
        )
    _log(
        "algo balance "
        + " ".join(
            f"{algo}={state['multipliers'][algo]:.3f}"
            for algo in balance.POOL_ALGOS
        )
        + " | sha256 android="
        + f"{state['sha256_miner_multipliers'].get('android', 1.0):.3f}"
        + " asic="
        + f"{state['sha256_miner_multipliers'].get('asic', 1.0):.3f}"
        + rb_note
    )
    for action in state.get("actions") or []:
        _log(action)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())