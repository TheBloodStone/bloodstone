"""Chain Mesh v2.0-Lite system — Blurt registry + providers + trustless retrieval."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from chain_mesh import assets as mesh_assets
from chain_mesh import db as mesh_db
from chain_mesh import blurt_registry_v2 as blurt_reg
from chain_mesh import mesh_providers as providers
from chain_mesh import trustless_retrieval as trustless

RFC_VERSION = blurt_reg.RFC_VERSION


def system_status_payload() -> Dict[str, Any]:
    providers.ensure_default_provider()
    blurt_reg.init_blurt_registry_db()
    provider_rows = providers.list_providers()
    return {
        "ok": True,
        "spec": RFC_VERSION,
        "custom_json_id": blurt_reg.CUSTOM_JSON_ID,
        "layers": {
            "registry": ["blurt_custom_json", "coordinator_catalog"],
            "chunk_plane": ["coordinator_store", "provider_registry", "dht_planned"],
            "verification": ["chunk_sha256", "merkle_root", "file_sha256"],
        },
        "coordinator": os.environ.get(
            "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
        ),
        "blurt_rpc_nodes": blurt_reg.BLURT_RPC_NODES,
        "registry_accounts": blurt_reg.REGISTRY_ACCOUNTS,
        "provider_count": len(provider_rows),
        "providers": provider_rows[:20],
        "default_provider_id": providers.DEFAULT_PROVIDER_ID,
        "trust_model": "verify_all_hashes_client_side",
        "notes": [
            "v2.0-Lite runs alongside v1 coordinator — Blurt registry is authoritative when present",
            "DHT bootstrap uses provider registry until libp2p nodes ship",
            "Blurt backend broadcasts custom_json; Bloodstone indexes and serves chunks",
        ],
    }


def resolve_manifest(asset_key: str) -> Dict[str, Any]:
    key = (asset_key or "").strip().lstrip("/")
    if not key:
        return {"ok": False, "error": "asset_key required"}

    anchor = blurt_reg.get_anchor(key)
    if anchor:
        body = anchor.get("anchor") or {}
        return {
            "ok": True,
            "asset_key": key,
            "source": "blurt_registry",
            "manifest": body,
            "anchor_meta": {
                "author": anchor.get("author"),
                "trx_id": anchor.get("trx_id"),
                "block_num": anchor.get("block_num"),
                "indexed_at": anchor.get("created_at"),
            },
        }

    try:
        asset = mesh_assets.asset_manifest_payload(key)
    except Exception:
        asset = None
    if asset and asset.get("ok"):
        body = blurt_reg.manifest_from_coordinator_asset(asset)
        provider_ids = [providers.DEFAULT_PROVIDER_ID]
        body["provider_ids"] = provider_ids
        return {
            "ok": True,
            "asset_key": key,
            "source": "coordinator_catalog",
            "manifest": body,
            "coordinator": asset,
        }

    return {"ok": False, "error": "manifest not found", "asset_key": key}


def after_partner_publish(
    publish_result: Dict[str, Any],
    *,
    uploader_account: str = "",
    provider_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Extend v1 partner publish with v2.0-Lite artifacts:
    custom_json for Blurt, local registry index, provider chunk announcements.
    """
    if not publish_result.get("ok"):
        return {"ok": False, "error": "publish failed"}

    providers.ensure_default_provider()
    pid_list = list(provider_ids or [])
    if not pid_list:
        pid_list = [providers.DEFAULT_PROVIDER_ID]

    asset_key = str(publish_result.get("asset_key") or "")
    chunks = publish_result.get("chunks") or []
    hashes = [str(c.get("chunk_hash") or "") for c in chunks if c.get("chunk_hash")]

    for pid in pid_list:
        providers.announce_chunks(pid, hashes)

    custom = blurt_reg.build_custom_json_anchor(
        asset_key=asset_key,
        manifest_merkle_root=str(publish_result.get("merkle_root") or ""),
        file_sha256=str(publish_result.get("file_sha256") or ""),
        file_size=int(publish_result.get("file_size") or 0),
        mime_type=str(publish_result.get("mime_type") or ""),
        provider_ids=pid_list,
        chunk_hashes=hashes,
        replication_factor=max(1, len(pid_list)),
        uploader_signature="",
    )
    body = custom["body"]
    if uploader_account:
        custom["required_posting_auths"] = [uploader_account.lstrip("@").lower()]
    blurt_reg.index_anchor(
        asset_key=asset_key,
        body=body,
        author=uploader_account or "bloodstone",
        trx_id=str((publish_result.get("anchor") or {}).get("txid") or ""),
    )

    return {
        "ok": True,
        "v2_lite": RFC_VERSION,
        "asset_key": asset_key,
        "provider_ids": pid_list,
        "blurt_custom_json": {
            "id": custom["id"],
            "required_posting_auths": custom.get("required_posting_auths") or [],
            "json": custom["json"],
        },
        "next_steps": [
            "Blurt backend signs and broadcasts the custom_json operation",
            "Clients resolve manifest via Blurt chain or GET /api/chain-mesh/v2/manifest",
            "Clients fetch chunks from providers and verify SHA-256 + Merkle root",
        ],
    }


def trustless_retrieve_payload(asset_key: str) -> Dict[str, Any]:
    resolved = resolve_manifest(asset_key)
    if not resolved.get("ok"):
        return resolved
    manifest = resolved.get("manifest") or {}
    chunk_sizes = []
    coord = resolved.get("coordinator") or {}
    for row in coord.get("chunks") or []:
        chunk_sizes.append(int(row.get("size") or 0))
    result = trustless.retrieve_chunks_trustless(manifest, chunk_sizes=chunk_sizes or None)
    result["asset_key"] = asset_key
    result["manifest_source"] = resolved.get("source")
    return result


def publish_flow_diagram() -> Dict[str, Any]:
    return {
        "ok": True,
        "phases": [
            {
                "id": "upload",
                "title": "Upload & hash",
                "steps": [
                    "Blurt backend splits file into 256 KiB chunks",
                    "POST /api/chain-mesh/partner/upload (batches of 2)",
                ],
            },
            {
                "id": "publish",
                "title": "Publish manifest",
                "steps": [
                    "POST /api/chain-mesh/partner/publish-asset",
                    "Bloodstone validates Merkle root + file SHA-256",
                    "Providers announce chunk_hashes in registry",
                ],
            },
            {
                "id": "anchor",
                "title": "Blurt registry",
                "steps": [
                    "Bloodstone returns custom_json payload (chain_mesh_anchor)",
                    "Blurt account broadcasts custom_json to Layer 1",
                    "Any client queries Blurt API or Bloodstone v2 manifest endpoint",
                ],
            },
            {
                "id": "retrieve",
                "title": "Trustless retrieval",
                "steps": [
                    "Resolve manifest (Blurt registry → coordinator fallback)",
                    "Lookup provider IDs + chunk locations",
                    "Download chunks, verify hashes, reassemble file",
                ],
            },
        ],
    }