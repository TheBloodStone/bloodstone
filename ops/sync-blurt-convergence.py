#!/usr/bin/env python3
"""Blurt-Bloodstone convergence upkeep — registry sync + storage credit rail."""

import sys

sys.path.insert(0, "/root")

from chain_mesh import agent_identity as agent
from chain_mesh import blurt_registry_v2 as br
from chain_mesh import depin_credits as depin
from chain_mesh import provenance as prov
from chain_mesh import storage_credits as sc


def main() -> int:
    reg = br.sync_registry_accounts()
    credits = sc.sync_outpost_transfers()
    provenance = prov.sync_registry_provenance()
    agents = agent.sync_registry_agents()
    depin_sync = depin.sync_depin_transfers()
    prov_indexed = sum(
        int(a.get("indexed") or 0)
        for a in (provenance.get("accounts") or [])
        if a.get("ok")
    )
    agent_indexed = sum(
        int(a.get("indexed") or 0)
        for a in (agents.get("accounts") or [])
        if a.get("ok")
    )
    print(
        "convergence",
        "registry_accounts=" + str(len(reg.get("accounts") or [])),
        "credits=" + str(credits.get("credited", 0)),
        "provenance_indexed=" + str(prov_indexed),
        "agents_indexed=" + str(agent_indexed),
        "compute_credited=" + str(depin_sync.get("compute_credited", 0)),
        "bandwidth_credited=" + str(depin_sync.get("bandwidth_credited", 0)),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())