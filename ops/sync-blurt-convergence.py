#!/usr/bin/env python3
"""Blurt-Bloodstone convergence upkeep — registry sync + storage credit rail."""

import sys

sys.path.insert(0, "/root")

import os

from chain_mesh import agent_identity as agent
from chain_mesh import condenser_offline as coff
from chain_mesh import blurt_registry_v2 as br
from chain_mesh import compute_job as cjobs
from chain_mesh import depin_credits as depin
from chain_mesh import dtn_sync as dtn
from chain_mesh import provenance as prov
from chain_mesh import spatial_manifest as spatial
from chain_mesh import storage_credits as sc


def main() -> int:
    reg = br.sync_registry_accounts()
    credits = sc.sync_outpost_transfers()
    provenance = prov.sync_registry_provenance()
    agents = agent.sync_registry_agents()
    spatial_sync = spatial.sync_registry_spatial()
    depin_sync = depin.sync_depin_transfers()
    compute_sync = cjobs.sync_registry_jobs()
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
    compute_indexed = sum(
        int(a.get("indexed") or 0)
        for a in (compute_sync.get("accounts") or [])
        if a.get("ok")
    )
    spatial_indexed = sum(
        int(a.get("indexed") or 0)
        for a in (spatial_sync.get("accounts") or [])
        if a.get("ok")
    )
    offline_index = coff.index_offline_feed(sync_blurt=os.environ.get("CONDENSER_OFFLINE_SYNC_BLURT", "1") == "1")
    dtn_upkeep = dtn.upkeep_dtn(
        force_flush=os.environ.get("DTN_AUTO_FLUSH", "0").strip() in ("1", "true", "yes")
    )
    print(
        "convergence",
        "registry_accounts=" + str(len(reg.get("accounts") or [])),
        "credits=" + str(credits.get("credited", 0)),
        "provenance_indexed=" + str(prov_indexed),
        "agents_indexed=" + str(agent_indexed),
        "compute_jobs_indexed=" + str(compute_indexed),
        "spatial_indexed=" + str(spatial_indexed),
        "compute_credited=" + str(depin_sync.get("compute_credited", 0)),
        "bandwidth_credited=" + str(depin_sync.get("bandwidth_credited", 0)),
        "dtn_pending=" + str(dtn_upkeep.get("pending", 0)),
        "dtn_delivered=" + str((dtn_upkeep.get("flush") or {}).get("delivered", 0)),
        "dtn_peers=" + str((dtn_upkeep.get("peers") or {}).get("count", 0)),
        "dtn_alerts=" + str(len((dtn_upkeep.get("alerts") or {}).get("active") or [])),
        "dtn_heal=" + str((dtn_upkeep.get("heal") or {}).get("heal_queued", 0)),
        "dtn_gossip=" + str((dtn_upkeep.get("gossip") or {}).get("exchanged", 0)),
        "dtn_starlink=" + str((dtn_upkeep.get("starlink") or {}).get("delivered", 0)),
        "offline_posts=" + str(offline_index.get("posts_total", 0)),
        "offline_playable=" + str(offline_index.get("posts_playable_local", 0)),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())