#!/usr/bin/env python3
"""Coordinator federation upkeep tick — roster publish, prune, founding seat."""

import os
import sys

sys.path.insert(0, "/root")
os.environ.setdefault("QUASAR_COORDINATOR_DEVICE_ID", "coord-a-primary")
os.environ.setdefault("COORD_FEDERATION_OPERATOR_ID", "bloodstone-ops")

import bloodstone_coordinator_federation as bcf


def main() -> int:
    rpc = None
    try:
        rpc = bcf._wallet_rpc()
    except Exception as exc:
        print("rpc_warn", exc)
    result = bcf.federation_tick(rpc)
    print("federation_tick", result.get("ok"), "publish", (result.get("publish") or {}).get("roster_version"))
    prune = result.get("prune") or {}
    print(
        "prune_assets",
        prune.get("assets_marked_stale"),
        "capsules",
        prune.get("capsules_deleted"),
    )
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
