"""Blurt-Bloodstone Convergence stack status — Layers 0–5."""

from __future__ import annotations

import os
from typing import Any, Dict, List

from chain_mesh import agent_identity as agents
from chain_mesh import ai_routing as ai
from chain_mesh import bridge_swap as bridge
from chain_mesh import blurt_registry_v2 as blurt_reg
from chain_mesh import blog_manifest as blog
from chain_mesh import condenser_offline as coff
from chain_mesh import compute_job as cjobs
from chain_mesh import depin_credits as depin
from chain_mesh import dtn_gossip as gossip
from chain_mesh import dtn_starlink as starlink
from chain_mesh import dtn_sync as dtn
from chain_mesh import planetary_quorum as planetary
from chain_mesh import mesh_providers as providers
from chain_mesh import mesh_v2_lite as v2
from chain_mesh import spatial_manifest as spatial
from chain_mesh import storage_credits as credits


def _tenant_sovereign_status() -> Dict[str, Any]:
    from chain_mesh import tenant_sovereign as tsov

    return tsov.status_payload()


def layer_status() -> List[Dict[str, Any]]:
    public = os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org")
    return [
        {
            "layer": 0,
            "name": "Sovereign Identity (human + AI agents)",
            "status": "beta",
            "detail": f"Blurt keys + {agents.AGENT_ID} machine identity manifests",
            "api": f"{public}/api/convergence/agent/register",
            "verify_api": f"{public}/api/convergence/agent/verify",
        },
        {
            "layer": 1,
            "name": "Trust Anchor (provenance + blogging)",
            "status": "beta",
            "detail": f"Digital provenance {blog.POST_MANIFEST_ID} + bloodstone_provenance/v1",
            "api": f"{public}/api/convergence/provenance/anchor",
            "verify_api": f"{public}/api/convergence/provenance/verify",
            "blog_api": f"{public}/api/convergence/blog/manifest",
        },
        {
            "layer": 2,
            "name": "Memory Fabric + DTN sync",
            "status": "beta",
            "detail": (
                f"RFC {blurt_reg.RFC_VERSION} chunks + DTN bundles + "
                f"{starlink.HANDOFF_FORMAT} satellite handoff + "
                f"{planetary.PLANETARY_FORMAT} planetary quorum"
            ),
            "api": f"{public}/api/chain-mesh/v2/manifest",
            "dtn_export": f"{public}/api/convergence/dtn/export",
            "dtn_import": f"{public}/api/convergence/dtn/import",
        },
        {
            "layer": 3,
            "name": "Edge DePIN (storage + compute + bandwidth)",
            "status": "beta",
            "detail": (
                f"Provider roles + {cjobs.COMPUTE_JOB_ID} + DTN gossip ({gossip.GOSSIP_FORMAT}) + "
                f"{ai.AI_ROUTING_FORMAT} on-device AI routing + unified tenant dashboard + ONNX/TFLite delegates"
            ),
            "api": f"{public}/api/chain-mesh/v2/providers",
            "compute_quota_api": f"{public}/api/convergence/compute/quota",
            "compute_job_api": f"{public}/api/convergence/compute/job/submit",
            "bandwidth_quota_api": f"{public}/api/convergence/bandwidth/quota",
        },
        {
            "layer": 4,
            "name": "Circulatory Economy (STONE + BLURT memo rails)",
            "status": "beta",
            "detail": (
                f"storage | compute | bandwidth BLURT→STONE memo rails + "
                f"{bridge.BRIDGE_FORMAT} atomic swaps (enforcement on)"
            ),
            "api": f"{public}/api/convergence/depin/quota",
            "storage_api": f"{public}/api/convergence/storage/quota",
        },
        {
            "layer": 5,
            "name": "Ambient UI (Condenser + Spatial WebXR)",
            "status": "beta",
            "detail": f"Condenser embed + {coff.OFFLINE_FORMAT} offline reader + {spatial.SPATIAL_MANIFEST_ID} AR",
            "api": f"{public}/api/convergence/condenser/embed",
            "page": f"{public}/convergence/embed/{{author}}/{{post_id}}",
            "spatial_embed": f"{public}/api/convergence/spatial/embed",
            "spatial_page": f"{public}/convergence/spatial/{{author}}/{{scene_id}}",
            "ar_overlay": f"{public}/api/convergence/spatial/overlay",
        },
    ]


def status_payload() -> Dict[str, Any]:
    v2_sys = v2.system_status_payload()
    credits.init_storage_credits_db()
    return {
        "ok": True,
        "vision": "Sovereign Mesh 2030 — Blurt trust anchor + Bloodstone memory fabric",
        "tagline": "Autonomous, self-healing nervous system — identity owns truth, hardware owns the network",
        "roadmap": "Wave A–Y ✓ · Wave Z: tenant planetary quorum + sovereign mesh reconcile ✓",
        "layers": layer_status(),
        "mesh_v2": {
            "spec": v2_sys.get("spec"),
            "provider_count": v2_sys.get("provider_count"),
            "registry_accounts": v2_sys.get("registry_accounts"),
        },
        "storage_rail": {
            "outpost_account": credits.OUTPOST_ACCOUNT,
            "memo_format": "storage:<STONE_ADDRESS>:<bytes>",
            "bytes_per_blurt": credits.BYTES_PER_BLURT,
            "enforce_quota": credits.ENFORCE_QUOTA,
        },
        "depin_rails": {
            "outpost_account": depin.DEPIN_OUTPOST_ACCOUNT,
            "compute_memo_format": "compute:<STONE_ADDRESS>:<job_id>",
            "bandwidth_memo_format": "bandwidth:<STONE_ADDRESS>:<bytes>",
            "flops_per_blurt": depin.FLOPS_PER_BLURT,
            "bandwidth_bytes_per_blurt": depin.BYTES_PER_BLURT_BANDWIDTH,
            "enforce_compute": depin.ENFORCE_COMPUTE,
            "enforce_bandwidth": depin.ENFORCE_BANDWIDTH,
        },
        "agent_id": agents.AGENT_ID,
        "compute_job_id": cjobs.COMPUTE_JOB_ID,
        "compute_jobs": cjobs.status_payload(),
        "provider_roles": ["storage", "compute", "bandwidth", "sensor", "coordinator"],
        "provider_counts": {
            role: len(providers.list_providers(role=role))
            for role in ("storage", "compute", "bandwidth", "sensor")
        },
        "post_manifest_id": blog.POST_MANIFEST_ID,
        "provenance_id": "bloodstone_provenance/v1",
        "mesh_anchor_id": blurt_reg.CUSTOM_JSON_ID,
        "dtn": dtn.status_payload(),
        "planetary_quorum": planetary.status_payload(),
        "tenant_sovereign": _tenant_sovereign_status(),
        "bridge_swap": bridge.status_payload(),
        "ai_routing": ai.status_payload(include_uplink=False),
        "condenser_offline": coff.status_payload(),
        "spatial_manifest_id": spatial.SPATIAL_MANIFEST_ID,
        "spatial_asset_prefix": "assets/spatial/",
        "use_cases": [
            "post_truth_reality_engine",
            "autonomous_ai_creator_economy",
            "censorship_proof_blogger",
            "off_grid_dtn_mesh",
            "spatial_web_ar_vr",
        ],
    }