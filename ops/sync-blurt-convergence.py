#!/usr/bin/env python3
"""Blurt-Bloodstone convergence upkeep — registry sync + storage credit rail."""

import sys

sys.path.insert(0, "/root")

from chain_mesh import blurt_registry_v2 as br
from chain_mesh import storage_credits as sc


def main() -> int:
    reg = br.sync_registry_accounts()
    credits = sc.sync_outpost_transfers()
    print(
        "convergence",
        "registry_accounts=" + str(len(reg.get("accounts") or [])),
        "credits=" + str(credits.get("credited", 0)),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())