"""HTTP-facing helpers for chain mesh endpoints."""

import base64
import os
from typing import Any, Dict, List, Optional

from chain_mesh import assignment as mesh_assign
from chain_mesh import db as mesh_db
from chain_mesh.manifest import current_manifest
from chain_mesh import lan_registry as lan
from chain_mesh import local_node as ln
from chain_mesh import assets as mesh_assets
from chain_mesh import submissions as mesh_submissions
from chain_mesh.restore import ingest_uploaded_chunks, local_coverage
from chain_mesh.store import chunk_exists, get_chunk, put_chunk
from chain_mesh import backup as mesh_backup
from chain_mesh import search as mesh_search
from chain_mesh import time_capsule as tc


def manifest_payload() -> Dict[str, Any]:
    manifest = current_manifest()
    if not manifest:
        return {"ok": False, "error": "no manifest"}
    chunks = []
    for c in manifest["chunks"]:
        chunks.append(
            {
                **c,
                "coordinator_has": chunk_exists(c["chunk_hash"]),
                "peer_count": len(mesh_db.peers_for_chunk(c["chunk_hash"])),
            }
        )
    assign = mesh_assign.assignment_info()
    return {
        "ok": True,
        "best_block_hash": manifest["best_block_hash"],
        "block_height": manifest["block_height"],
        "created_at": manifest["created_at"],
        "chunk_count": manifest["chunk_count"],
        "total_bytes": manifest["total_bytes"],
        "assignment": assign,
        "chunks": chunks,
    }


def chunk_payload(chunk_hash: str) -> Optional[Dict[str, Any]]:
    data = get_chunk(chunk_hash)
    if data is None:
        return None
    return {
        "chunk_hash": chunk_hash.strip().lower(),
        "size": len(data),
        "data_b64": base64.b64encode(data).decode("ascii"),
    }


def upload_chunk(chunk_hash: str, data: bytes) -> Dict[str, Any]:
    digest = put_chunk(data, expected_hash=chunk_hash)
    return {"ok": True, "chunk_hash": digest, "size": len(data)}


def register_peer(payload: Dict[str, Any]) -> Dict[str, Any]:
    device_id = str(payload.get("device_id") or "").strip()
    hashes = payload.get("chunk_hashes") or payload.get("chunks") or []
    if isinstance(hashes, str):
        hashes = [h.strip() for h in hashes.split(",") if h.strip()]
    result = mesh_db.upsert_peer(
        device_id=device_id,
        peer_kind=str(payload.get("peer_kind") or payload.get("miner_kind") or "browser"),
        model=str(payload.get("model") or payload.get("device_model") or ""),
        capacity_bytes=int(payload.get("capacity_bytes") or 0),
        chunk_hashes=list(hashes),
    )
    lan_ip = str(payload.get("lan_ip") or "").strip()
    chunk_port = int(payload.get("chunk_port") or 0)
    if device_id and lan_ip and chunk_port > 0:
        public_ip = str(payload.get("public_ip") or "").strip()
        try:
            lan.register_lan_node(
                device_id=device_id,
                public_ip=public_ip,
                lan_ip=lan_ip,
                chunk_port=chunk_port,
                peer_kind=str(payload.get("peer_kind") or "android"),
                model=str(payload.get("model") or ""),
                mode=str(payload.get("mode") or "chunk-peer"),
            )
        except ValueError:
            pass
    return result


def upload_batch(payload: Dict[str, Any]) -> Dict[str, Any]:
    items = payload.get("chunks") or []
    pairs: List[tuple] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        h = str(item.get("chunk_hash") or item.get("hash") or "").strip().lower()
        raw_b64 = item.get("data_b64") or item.get("data")
        if not h or not raw_b64:
            continue
        try:
            data = base64.b64decode(raw_b64, validate=True)
        except Exception:
            continue
        pairs.append((h, data))
    result = ingest_uploaded_chunks(pairs)
    device_id = str(payload.get("device_id") or "").strip()
    if device_id and pairs:
        mesh_db.upsert_peer(
            device_id=device_id,
            peer_kind=str(payload.get("peer_kind") or "browser"),
            model=str(payload.get("model") or ""),
            capacity_bytes=int(payload.get("capacity_bytes") or 0),
            chunk_hashes=[p[0] for p in pairs],
        )
    return {"ok": True, **result}


def status_payload() -> Dict[str, Any]:
    from chain_mesh.config import MAX_ASSET_PUBLISH_BYTES, MAX_ASSET_PUBLISH_CHUNKS

    coverage = local_coverage()
    capsule = tc.status_payload()
    return {
        "ok": True,
        **mesh_db.public_stats(),
        "assignment": mesh_assign.assignment_info(),
        "limits": {
            "max_asset_bytes": MAX_ASSET_PUBLISH_BYTES,
            "max_asset_chunks": MAX_ASSET_PUBLISH_CHUNKS,
        },
        "coverage": coverage,
        "local_nodes": ln.local_node_stats(),
        "time_capsule": {
            "name": capsule.get("name"),
            "capsule_complete": capsule.get("capsule_complete"),
            "pruned": capsule.get("pruned"),
            "potential_savings_bytes": capsule.get("potential_savings_bytes"),
            "block_height": capsule.get("block_height"),
        },
    }


def time_capsule_status_payload() -> Dict[str, Any]:
    return tc.status_payload()


def time_capsule_archive_payload(*, force: bool = False) -> Dict[str, Any]:
    return tc.archive_capsule(force_publish=force)


def time_capsule_prune_payload(*, confirm: bool = False) -> Dict[str, Any]:
    return tc.apply_prune(confirm=confirm)


def mesh_backup_manifest_payload() -> Dict[str, Any]:
    return mesh_backup.backup_manifest()


def mesh_backup_import_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return mesh_backup.import_backup_payload(payload)


def mesh_backup_build_zip() -> tuple:
    return mesh_backup.build_capsule_zip()


def mesh_search_payload(
    *,
    query: str = "",
    prefix: str = "",
    mime: str = "",
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    return mesh_search.search_assets(
        query,
        prefix=prefix or None,
        mime_contains=mime or None,
        limit=limit,
        offset=offset,
    )


def peers_for_chunk_payload(
    chunk_hash: str,
    *,
    requester_public_ip: str = "",
) -> Dict[str, Any]:
    h = (chunk_hash or "").strip().lower()
    peers = mesh_db.peers_for_chunk(h)
    endpoints = mesh_db.peers_for_chunk_with_endpoints(
        h,
        requester_public_ip=requester_public_ip,
    )
    return {
        "ok": True,
        "chunk_hash": h,
        "peer_count": len(peers),
        "peers": peers[:32],
        "endpoints": endpoints[:32],
        "coordinator_has": chunk_exists(h),
    }


def local_node_register(payload: Dict[str, Any]) -> Dict[str, Any]:
    device_id = str(payload.get("device_id") or "").strip()
    return {
        "ok": True,
        **ln.upsert_local_node(
            device_id=device_id,
            peer_kind=str(payload.get("peer_kind") or payload.get("miner_kind") or "browser"),
            model=str(payload.get("model") or ""),
            block_height=int(payload.get("block_height") or 0),
            best_block_hash=str(payload.get("best_block_hash") or ""),
            chunks_held=int(payload.get("chunks_held") or 0),
            offline_capable=bool(payload.get("offline_capable")),
            job_cached=bool(payload.get("job_cached")),
            pending_shares=int(payload.get("pending_shares") or 0),
        ),
    }


def job_cache_store(payload: Dict[str, Any]) -> Dict[str, Any]:
    device_id = str(payload.get("device_id") or "").strip()
    return ln.store_job_cache(device_id, payload)


def job_cache_fetch(device_id: str) -> Dict[str, Any]:
    data = ln.get_job_cache(device_id)
    if not data:
        return {"ok": False, "error": "no cached job"}
    return {"ok": True, **data}


def pending_shares_store(payload: Dict[str, Any]) -> Dict[str, Any]:
    device_id = str(payload.get("device_id") or "").strip()
    shares = payload.get("shares") or []
    return {"ok": True, **ln.queue_pending_shares(device_id, shares)}


def pending_shares_fetch(device_id: str) -> Dict[str, Any]:
    shares = ln.drain_pending_shares(device_id)
    return {"ok": True, "shares": shares, "count": len(shares)}


def lan_register(payload: Dict[str, Any], *, public_ip: str) -> Dict[str, Any]:
    device_id = str(payload.get("device_id") or "").strip()
    return {
        "ok": True,
        **lan.register_lan_node(
            device_id=device_id,
            public_ip=public_ip,
            lan_ip=str(payload.get("lan_ip") or ""),
            rpc_port=int(payload.get("rpc_port") or 18340),
            stratum_port=int(payload.get("stratum_port") or 3437),
            stratum_port_yespower=int(payload.get("stratum_port_yespower") or 3438),
            chunk_port=int(payload.get("chunk_port") or 18341),
            rpc_user=str(payload.get("rpc_user") or ""),
            peer_kind=str(payload.get("peer_kind") or "android"),
            model=str(payload.get("model") or ""),
            mode=str(payload.get("mode") or "gateway"),
            block_height=int(payload.get("block_height") or 0),
            pruned=bool(payload.get("pruned", True)),
            sync_progress=float(payload.get("sync_progress") or 0),
            chain_bytes=int(payload.get("chain_bytes") or 0),
            consensus_only=bool(payload.get("consensus_only", False)),
            tip_hash=str(payload.get("tip_hash") or payload.get("best_block_hash") or ""),
            best_block_hash=str(payload.get("best_block_hash") or payload.get("tip_hash") or ""),
            ai_runtimes=payload.get("ai_runtimes"),
            ai_inference_port=int(payload.get("ai_inference_port") or 0),
        ),
    }


def lan_nearby(public_ip: str) -> Dict[str, Any]:
    nodes = lan.nearby_lan_nodes(public_ip)
    return {"ok": True, "nodes": nodes, "count": len(nodes)}


def assets_catalog(*, limit: int = 50) -> Dict[str, Any]:
    return mesh_assets.assets_catalog_payload(limit=limit)


def writable_keys(*, limit: int = 200, prefix: str = "") -> Dict[str, Any]:
    return mesh_assets.writable_keys_payload(limit=limit, prefix=prefix)


def asset_manifest(asset_key: str) -> Dict[str, Any]:
    return mesh_assets.asset_manifest_payload(asset_key)


def asset_lookup_payload(
    asset_key: str,
    *,
    range_header: str = "",
    range_query: str = "",
    public_root: str = "",
) -> Dict[str, Any]:
    """Compact chunk lookup for partial mesh download (no chunk bytes)."""
    from chain_mesh.lookup import file_lookup_payload, parse_lookup_range_header

    manifest = mesh_assets.asset_manifest_payload(asset_key)
    if not manifest.get("ok"):
        return manifest
    file_size = int(manifest.get("file_size") or 0)
    byte_range = None
    spec = (range_query or range_header or "").strip()
    if spec:
        if spec.lower().startswith("bytes="):
            spec = spec[6:].strip()
        header = f"bytes={spec}" if "=" not in spec else spec
        if not header.lower().startswith("bytes="):
            header = f"bytes={header}"
        byte_range = parse_lookup_range_header(header, file_size)
        if byte_range is None:
            return {"ok": False, "error": "invalid or unsatisfiable byte range"}
    return file_lookup_payload(asset_key, byte_range=byte_range, public_root=public_root)


def mesh_lookup_query_payload(
    *,
    asset_key: str = "",
    txid: str = "",
    merkle_root: str = "",
    range_header: str = "",
    range_query: str = "",
    public_root: str = "",
) -> Dict[str, Any]:
    """Resolve file chunk list by asset_key, BSM1 txid, or merkle_root."""
    from chain_mesh.lookup import (
        file_lookup_by_anchor_txid,
        file_lookup_by_merkle_root,
        file_lookup_payload,
        parse_lookup_range_header,
    )

    def _range_for(manifest: Dict[str, Any]) -> Optional[tuple]:
        if not (range_query or range_header):
            return None
        file_size = int(manifest.get("file_size") or 0)
        spec = (range_query or range_header or "").strip()
        if spec.lower().startswith("bytes="):
            spec = spec[6:].strip()
        header = f"bytes={spec}"
        return parse_lookup_range_header(header, file_size)

    key = (asset_key or "").strip().lstrip("/")
    if key:
        manifest = mesh_assets.asset_manifest_payload(key)
        if not manifest.get("ok"):
            return manifest
        byte_range = _range_for(manifest)
        if (range_query or range_header) and byte_range is None:
            return {"ok": False, "error": "invalid or unsatisfiable byte range"}
        return file_lookup_payload(key, byte_range=byte_range, public_root=public_root)

    tx = (txid or "").strip().lower()
    if tx:
        probe = file_lookup_by_anchor_txid(tx, public_root=public_root)
        if not probe.get("ok"):
            return probe
        byte_range = _range_for(probe) if (range_query or range_header) else None
        if (range_query or range_header) and byte_range is None:
            return {"ok": False, "error": "invalid or unsatisfiable byte range"}
        if byte_range is not None:
            key_from_tx = str(probe.get("asset_key") or "").strip()
            if key_from_tx:
                return file_lookup_payload(
                    key_from_tx, byte_range=byte_range, public_root=public_root
                )
        return probe

    root = (merkle_root or "").strip().lower()
    if root:
        return file_lookup_by_merkle_root(root, public_root=public_root)

    return {"ok": False, "error": "provide asset_key, txid, or merkle_root"}


def update_asset_metadata_payload(payload: Dict[str, Any], *, asset_key: str) -> Dict[str, Any]:
    from chain_mesh.config import PUBLISH_TOKEN

    token = str(payload.get("publish_token") or "").strip()
    if not PUBLISH_TOKEN or token != PUBLISH_TOKEN:
        raise PermissionError("invalid publish token")
    return mesh_assets.update_asset_metadata_payload(
        asset_key,
        display_name=payload.get("display_name"),
        version=payload.get("version"),
    )


def asset_versions(asset_key: str, *, limit: int = 20) -> Dict[str, Any]:
    return mesh_assets.asset_versions_payload(asset_key, limit=limit)


def asset_preview(asset_key: str) -> Dict[str, Any]:
    return mesh_assets.asset_preview_payload(asset_key)


def submit_asset_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return mesh_submissions.submit_asset_payload(payload)


def pending_submissions_payload(*, status: str = "pending", limit: int = 50) -> Dict[str, Any]:
    return mesh_submissions.pending_submissions_payload(status=status, limit=limit)


def pending_submission_payload(submission_id: int) -> Dict[str, Any]:
    return mesh_submissions.pending_submission_payload(submission_id)


def approve_submission_payload(
    submission_id: int,
    *,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    body = payload or {}
    return mesh_submissions.approve_submission_payload(
        submission_id,
        reviewed_by=str(body.get("reviewed_by") or "admin"),
        anchor=body.get("anchor") if "anchor" in body else None,
        anchor_wallet=str(body.get("anchor_wallet") or "").strip() or None,
    )


def reject_submission_payload(
    submission_id: int,
    *,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    body = payload or {}
    return mesh_submissions.reject_submission_payload(
        submission_id,
        reason=str(body.get("reason") or body.get("rejection_reason") or ""),
        reviewed_by=str(body.get("reviewed_by") or "admin"),
    )


def transfer_protocol_payload() -> Dict[str, Any]:
    from chain_mesh import transfer as mesh_transfer

    return mesh_transfer.transfer_status_payload()


def transfer_create_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import transfer as mesh_transfer

    return mesh_transfer.create_transfer_payload(payload)


def transfer_get_payload(transfer_id: str) -> Dict[str, Any]:
    from chain_mesh import transfer as mesh_transfer

    return mesh_transfer.get_transfer_payload(transfer_id)


def transfer_attest_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import transfer as mesh_transfer

    return mesh_transfer.attest_transfer_payload(payload)


def transfer_claim_payload(transfer_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import transfer as mesh_transfer

    return mesh_transfer.claim_transfer_payload(
        transfer_id,
        claimant=str(payload.get("recipient") or payload.get("claimant") or ""),
    )


def transfer_list_for_recipient(recipient: str, *, status: str = "") -> Dict[str, Any]:
    from chain_mesh import transfer as mesh_transfer

    return mesh_transfer.list_transfers_for_recipient(
        recipient,
        status=status or None,
    )


def packet_protocol_payload() -> Dict[str, Any]:
    from chain_mesh import packets as mesh_packets

    return mesh_packets.protocol_payload()


def packet_open_channel_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import packets as mesh_packets

    return mesh_packets.open_channel_payload(payload)


def packet_send_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import packets as mesh_packets

    return mesh_packets.send_packet_payload(payload)


def packet_inbox_payload(
    recipient: str,
    *,
    channel_id: str = "",
    since_seq: int = 0,
    limit: int = 50,
) -> Dict[str, Any]:
    from chain_mesh import packets as mesh_packets

    return mesh_packets.inbox_payload(
        recipient,
        channel_id=channel_id,
        since_seq=since_seq,
        limit=limit,
    )


def packet_channel_payload(channel_id: str) -> Dict[str, Any]:
    from chain_mesh import packets as mesh_packets

    return mesh_packets.channel_payload(channel_id)


def packet_relay_queue_payload(device_id: str, *, limit: int = 8) -> Dict[str, Any]:
    from chain_mesh import packets as mesh_packets

    return mesh_packets.relay_queue_payload(device_id, limit=limit)


def packet_attest_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import packets as mesh_packets

    return mesh_packets.attest_packet_payload(payload)


def packet_anchors_payload(*, channel_id_prefix: str = "", limit: int = 50) -> Dict[str, Any]:
    from chain_mesh import packet_index as pkt_index

    return pkt_index.list_anchors(channel_id_prefix=channel_id_prefix, limit=limit)


def packet_refresh_index_payload(*, lookback: int = 500) -> Dict[str, Any]:
    from chain_mesh import packet_index as pkt_index

    return pkt_index.refresh_index(lookback=lookback)


def ip_tunnel_protocol_payload() -> Dict[str, Any]:
    from chain_mesh import ip_tunnel as ip_tun

    return ip_tun.protocol_payload()


def ip_tunnel_open_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import ip_tunnel as ip_tun

    return ip_tun.open_tunnel_channel_payload(payload)


def ip_tunnel_send_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import ip_tunnel as ip_tun

    return ip_tun.send_ip_datagram_payload(payload)


def ip_tunnel_inbox_payload(
    recipient: str,
    *,
    channel_id: str = "",
    since_seq: int = 0,
    limit: int = 50,
) -> Dict[str, Any]:
    from chain_mesh import ip_tunnel as ip_tun
    from chain_mesh import packets as mesh_packets

    inbox = mesh_packets.inbox_payload(
        recipient,
        channel_id=channel_id,
        since_seq=since_seq,
        limit=limit,
    )
    return ip_tun.decode_inbox_ip_packets(inbox)


def ip_gateway_status_payload() -> Dict[str, Any]:
    from chain_mesh import internet_gateway as inet_gw

    return inet_gw.gateway_status_extended()


def internet_gateway_register_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import internet_gateway as inet_gw

    return inet_gw.register_gateway_payload(payload)


def internet_gateway_unregister_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import internet_gateway as inet_gw

    return inet_gw.unregister_gateway_payload(payload)


def internet_gateway_elect_payload(
    *,
    public_ip: str = "",
    requester_device_id: str = "",
) -> Dict[str, Any]:
    from chain_mesh import internet_gateway as inet_gw

    return inet_gw.elect_gateway_payload(
        public_ip=public_ip,
        requester_device_id=requester_device_id,
    )


def internet_gateway_peer_egress_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import internet_gateway as inet_gw

    return inet_gw.run_peer_egress_batch(
        device_id=str(payload.get("device_id") or ""),
        limit=int(payload.get("limit") or 12),
    )


def internet_gateway_pending_payload(*, device_id: str, limit: int = 12) -> Dict[str, Any]:
    from chain_mesh import internet_gateway as inet_gw

    return inet_gw.pending_peer_packets_payload(device_id=device_id, limit=limit)


def internet_gateway_reply_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import internet_gateway as inet_gw

    return inet_gw.submit_peer_reply_payload(payload)


def ip_gateway_egress_payload(*, limit: int = 16) -> Dict[str, Any]:
    from chain_mesh import ip_gateway as gw

    return gw.run_egress_batch(limit=limit)


def ip_tls_client_hello_template_payload(
    *,
    host: str = "",
    connect_host: str = "",
    port: int = 0,
    session: bool = True,
) -> Dict[str, Any]:
    from chain_mesh import ip_tunnel_openssl as tls_o
    from chain_mesh import ip_tunnel_tls13_client as tls13

    if session:
        return tls13.build_client_hello_session(
            host=host or tls_o.LAB_SNI,
            connect_host=connect_host or tls_o.LAB_HOST,
            port=int(port or tls_o.LAB_PORT),
        )
    return tls_o.build_client_hello_openssl(
        host=host or tls_o.LAB_SNI,
        connect_host=connect_host or tls_o.LAB_HOST,
        port=int(port or tls_o.LAB_PORT),
    )


def ip_tls_client_flight2_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import ip_tunnel_tls13_client as tls13

    return tls13.build_client_flight2(
        handshake_id=str(payload.get("handshake_id") or ""),
        server_flight_b64=str(
            payload.get("server_flight_b64") or payload.get("server_flight") or ""
        ),
    )


def ip_tls_encrypt_app_data_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import ip_tunnel_tls13_client as tls13

    return tls13.encrypt_client_app_data(
        handshake_id=str(payload.get("handshake_id") or ""),
        server_flight_b64=str(payload.get("server_flight_b64") or ""),
        plaintext_b64=str(payload.get("plaintext_b64") or ""),
        client_hello_b64=str(payload.get("client_hello_b64") or ""),
        private_key_b64=str(payload.get("private_key_b64") or ""),
        seq_offset=int(payload.get("seq_offset") or 0),
    )


def ip_tls_decrypt_app_data_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import ip_tunnel_tls13_client as tls13

    return tls13.decrypt_server_app_data(
        handshake_id=str(payload.get("handshake_id") or ""),
        server_flight_b64=str(payload.get("server_flight_b64") or ""),
        app_data_b64=str(payload.get("app_data_b64") or ""),
        client_hello_b64=str(payload.get("client_hello_b64") or ""),
        private_key_b64=str(payload.get("private_key_b64") or ""),
        seq_offset=int(payload.get("seq_offset") or 0),
    )


def network_chat_lobby_payload() -> Dict[str, Any]:
    from chain_mesh import network_chat as nc

    return nc.lobby_info_payload()


def network_chat_lobby_inbox_payload(
    *,
    since_seq: int = 0,
    limit: int = 80,
) -> Dict[str, Any]:
    from chain_mesh import network_chat as nc

    return nc.lobby_inbox_payload(since_seq=since_seq, limit=limit)


def network_chat_lobby_send_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import network_chat as nc

    return nc.lobby_send_payload(payload)


def network_chat_dm_open_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import network_chat as nc

    return nc.open_dm_channel_payload(payload)


def network_chat_channels_payload(participant: str, *, limit: int = 40) -> Dict[str, Any]:
    from chain_mesh import network_chat as nc

    return nc.channels_for_participant(participant, limit=limit)


def network_chat_heartbeat_payload(payload: Dict[str, Any], *, public_ip: str = "") -> Dict[str, Any]:
    from chain_mesh import network_chat as nc

    return nc.heartbeat_payload(payload, public_ip=public_ip)


def network_chat_presence_payload(
    *,
    public_ip: str = "",
    include_offline: bool = False,
    limit: int = 120,
) -> Dict[str, Any]:
    from chain_mesh import network_chat as nc

    return nc.presence_payload(
        public_ip=public_ip,
        include_offline=include_offline,
        limit=limit,
    )


def packet_peers_for_recipient(recipient: str, *, limit: int = 16) -> Dict[str, Any]:
    from chain_mesh import lan_registry as lan

    nodes = lan.nearby_lan_nodes("")[: max(1, min(32, int(limit)))]
    with mesh_db._conn() as conn:
        rows = conn.execute(
            """
            SELECT device_id FROM chain_mesh_packet_attestations
            WHERE created_at > ?
            GROUP BY device_id
            ORDER BY MAX(created_at) DESC
            LIMIT ?
            """,
            (int(__import__("time").time()) - 86400, max(1, min(32, int(limit)))),
        ).fetchall()
    endpoints = []
    for node in nodes:
        if node.get("lan_ip"):
            endpoints.append(
                {
                    "lan_ip": node["lan_ip"],
                    "chunk_port": int(node.get("chunk_port") or 18341),
                    "device_id": node.get("device_id") or "",
                    "peer_kind": "lan-node",
                }
            )
    return {
        "ok": True,
        "recipient": recipient.strip(),
        "endpoints": endpoints,
        "attesting_devices": [str(r["device_id"]) for r in rows],
    }


def publish_asset_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh.partner import verify_partner_publish_token

    verify_partner_publish_token(payload)

    chunks = payload.get("chunks") or []
    anchor = bool(payload.get("anchor", True))
    return mesh_assets.publish_asset_manifest(
        asset_key=str(payload.get("asset_key") or ""),
        display_name=str(payload.get("display_name") or ""),
        version=str(payload.get("version") or ""),
        mime_type=str(payload.get("mime_type") or ""),
        file_size=int(payload.get("file_size") or 0),
        file_sha256=str(payload.get("file_sha256") or ""),
        merkle_root_hex=str(payload.get("merkle_root") or ""),
        chunks=list(chunks),
        anchor=anchor,
        anchor_wallet=str(payload.get("anchor_wallet") or "").strip() or None,
    )


def partner_publish_asset_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Token-authenticated publish scoped to assets/blurt/ (external partner cron)."""
    from chain_mesh.partner import require_blurt_partner_asset_key, verify_partner_publish_token
    from chain_mesh import mesh_v2_lite as v2
    from chain_mesh import storage_credits as sc

    verify_partner_publish_token(payload)
    asset_key = require_blurt_partner_asset_key(str(payload.get("asset_key") or ""))
    stone_address = str(payload.get("stone_address") or payload.get("payer_stone") or "").strip()
    file_size = int(payload.get("file_size") or 0)
    quota_check = sc.check_publish_allowed(stone_address, file_size)
    if not quota_check.get("allowed"):
        raise PermissionError(quota_check.get("reason") or "storage quota exceeded")

    chunks = payload.get("chunks") or []
    anchor = bool(payload.get("anchor", True))
    result = mesh_assets.publish_asset_manifest(
        asset_key=asset_key,
        display_name=str(payload.get("display_name") or ""),
        version=str(payload.get("version") or ""),
        mime_type=str(payload.get("mime_type") or ""),
        file_size=int(payload.get("file_size") or 0),
        file_sha256=str(payload.get("file_sha256") or ""),
        merkle_root_hex=str(payload.get("merkle_root") or ""),
        chunks=list(chunks),
        anchor=anchor,
        anchor_wallet=str(payload.get("anchor_wallet") or "").strip() or None,
    )
    if result.get("ok"):
        if stone_address and file_size > 0:
            sc.record_usage(stone_address, delta_bytes=file_size)
            result["storage_quota"] = sc.quota_summary(stone_address)
        try:
            v2_pack = v2.after_partner_publish(
                result,
                uploader_account=str(payload.get("uploader_account") or ""),
                provider_ids=payload.get("provider_ids"),
            )
            result["v2_lite"] = v2_pack
        except Exception as exc:
            result["v2_lite"] = {"ok": False, "error": str(exc)}
    return result


def convergence_status_payload() -> Dict[str, Any]:
    from chain_mesh import convergence as conv

    return conv.status_payload()


def convergence_storage_quota_payload(stone_address: str) -> Dict[str, Any]:
    from chain_mesh import storage_credits as sc

    return sc.quota_summary(stone_address)


def convergence_storage_sync_payload() -> Dict[str, Any]:
    from chain_mesh import storage_credits as sc

    return sc.sync_outpost_transfers()


def convergence_blog_manifest_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import blog_manifest as blog

    post_id = str(payload.get("post_id") or payload.get("permlink") or "")
    author = str(payload.get("author") or "")
    asset_keys = payload.get("asset_keys") or []
    if not asset_keys and payload.get("filename"):
        asset_keys = [
            blog.media_asset_key(
                post_id=post_id,
                filename=str(payload.get("filename") or "media"),
            )
        ]
    custom = blog.build_post_manifest(
        post_id=post_id,
        author=author,
        asset_keys=list(asset_keys),
        title=str(payload.get("title") or ""),
        permlink=str(payload.get("permlink") or post_id),
        blurt_url=str(payload.get("blurt_url") or ""),
    )
    media = blog.resolve_post_media(custom["body"])
    return {
        "ok": True,
        "blurt_custom_json": {
            "id": custom["id"],
            "required_posting_auths": custom.get("required_posting_auths") or [],
            "json": custom["json"],
        },
        "body": custom["body"],
        "media": media,
        "embed_html": [
            blog.condenser_embed_html(
                k,
                mime_type=str(payload.get("mime_type") or ""),
            )
            for k in custom["body"].get("asset_keys") or []
        ],
    }


def convergence_blog_publish_flow_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import blog_manifest as blog

    return blog.publish_post_flow_payload(
        post_id=str(payload.get("post_id") or ""),
        author=str(payload.get("author") or ""),
        filename=str(payload.get("filename") or "media.mp4"),
        publish_result=payload.get("publish_result"),
    )


def convergence_condenser_embed_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import condenser_embed as ce

    asset_keys = payload.get("asset_keys") or []
    if not asset_keys and payload.get("asset_key"):
        asset_keys = [payload.get("asset_key")]
    if isinstance(asset_keys, str):
        asset_keys = [k.strip() for k in asset_keys.split(",") if k.strip()]
    return ce.embed_payload(
        post_id=str(payload.get("post_id") or payload.get("permlink") or ""),
        author=str(payload.get("author") or ""),
        asset_keys=list(asset_keys),
        title=str(payload.get("title") or ""),
        permlink=str(payload.get("permlink") or ""),
    )


def convergence_condenser_offline_status_payload() -> Dict[str, Any]:
    from chain_mesh import condenser_offline as coff

    return coff.status_payload()


def convergence_condenser_offline_feed_payload(
    *,
    author: str = "",
    limit: int = 40,
) -> Dict[str, Any]:
    from chain_mesh import condenser_offline as coff

    return coff.list_feed(author=author, limit=limit)


def convergence_condenser_offline_post_payload(
    *,
    author: str = "",
    post_id: str = "",
) -> Dict[str, Any]:
    from chain_mesh import condenser_offline as coff

    return coff.resolve_offline_post(author=author, post_id=post_id)


def convergence_condenser_offline_index_payload(*, sync_blurt: bool = True) -> Dict[str, Any]:
    from chain_mesh import condenser_offline as coff

    return coff.index_offline_feed(sync_blurt=sync_blurt)


def convergence_provenance_anchor_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import provenance as prov

    return prov.anchor_payload(payload)


def convergence_provenance_verify_payload(
    *,
    asset_key: str = "",
    provenance_id: str = "",
    content_sha256: str = "",
) -> Dict[str, Any]:
    from chain_mesh import provenance as prov

    return prov.verify_provenance(
        asset_key=asset_key,
        provenance_id=provenance_id,
        content_sha256=content_sha256,
    )


def convergence_provenance_sync_payload() -> Dict[str, Any]:
    from chain_mesh import provenance as prov

    return prov.sync_registry_provenance()


def convergence_agent_register_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import agent_identity as agent

    return agent.register_payload(payload)


def convergence_agent_verify_payload(
    *,
    agent_id: str = "",
    blurt_author: str = "",
) -> Dict[str, Any]:
    from chain_mesh import agent_identity as agent

    return agent.verify_agent(agent_id=agent_id, blurt_author=blurt_author)


def convergence_agent_sync_payload() -> Dict[str, Any]:
    from chain_mesh import agent_identity as agent

    return agent.sync_registry_agents()


def convergence_agent_publish_flow_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import agent_identity as agent

    return agent.publish_flow_payload(payload)


def convergence_compute_quota_payload(stone_address: str) -> Dict[str, Any]:
    from chain_mesh import depin_credits as depin

    return depin.compute_quota(stone_address)


def convergence_compute_job_submit_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import compute_job as cjobs

    return cjobs.submit_payload(payload)


def convergence_compute_job_verify_payload(
    *,
    job_id: str = "",
    stone_address: str = "",
) -> Dict[str, Any]:
    from chain_mesh import compute_job as cjobs

    return cjobs.verify_payload(job_id=job_id, stone_address=stone_address)


def convergence_compute_jobs_payload(
    *,
    stone_address: str = "",
    status: str = "",
    limit: int = 30,
) -> Dict[str, Any]:
    from chain_mesh import compute_job as cjobs

    return cjobs.list_compute_jobs(stone_address=stone_address, status=status, limit=limit)


def convergence_compute_job_status_payload() -> Dict[str, Any]:
    from chain_mesh import compute_job as cjobs

    return cjobs.status_payload()


def convergence_compute_job_sync_payload() -> Dict[str, Any]:
    from chain_mesh import compute_job as cjobs

    return cjobs.sync_registry_jobs()


def convergence_bandwidth_quota_payload(stone_address: str) -> Dict[str, Any]:
    from chain_mesh import depin_credits as depin

    return depin.bandwidth_quota(stone_address)


def convergence_depin_quota_payload(stone_address: str) -> Dict[str, Any]:
    from chain_mesh import depin_credits as depin

    return depin.depin_quota_summary(stone_address)


def convergence_depin_sync_payload() -> Dict[str, Any]:
    from chain_mesh import depin_credits as depin

    return depin.sync_depin_transfers()


def convergence_dtn_status_payload() -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    return dtn.status_payload()


def convergence_dtn_export_payload(
    *,
    node_id: str = "",
    since: Optional[int] = None,
    include_chunks: bool = True,
    region: str = "",
    queue_forward: bool = False,
    stone_address: str = "",
) -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    return dtn.export_payload(
        node_id=node_id,
        since=since,
        include_chunks=include_chunks,
        region=region,
        queue_forward=queue_forward,
        stone_address=stone_address,
    )


def convergence_dtn_build_zip(
    *,
    node_id: str = "",
    since: Optional[int] = None,
    include_chunks: bool = True,
    region: str = "",
    stone_address: str = "",
) -> tuple:
    from chain_mesh import depin_credits as depin
    from chain_mesh import dtn_sync as dtn

    addr = (stone_address or "").strip()
    if depin.ENFORCE_BANDWIDTH and addr:
        est = int(os.environ.get("DTN_BANDWIDTH_ESTIMATE_BYTES", str(dtn.DTN_MAX_BUNDLE_BYTES)))
        quota_check = depin.check_bandwidth_allowed(addr, est)
        if not quota_check.get("allowed"):
            raise PermissionError(quota_check.get("reason") or "bandwidth quota exceeded")

    blob, filename, meta = dtn.build_dtn_bundle(
        node_id=node_id,
        since=since,
        include_chunks=include_chunks,
        region=region,
    )
    if addr and len(blob) > 0:
        depin.record_bandwidth_usage(addr, delta_bytes=len(blob))
    return blob, filename, meta


def convergence_dtn_import_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn
    import base64

    raw_b64 = str(payload.get("data_b64") or "").strip()
    if raw_b64:
        raw = base64.b64decode(raw_b64, validate=True)
        if payload.get("store_and_forward"):
            return dtn.receive_peer_bundle(
                raw,
                from_node_id=str(payload.get("from_node_id") or ""),
                requeue_upstream=not payload.get("from_forward"),
            )
        return dtn.import_dtn_bundle(raw)
    raise ValueError("data_b64 required")


def convergence_dtn_forward_pending_payload(*, limit: int = 20) -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    return dtn.list_pending_forwards(limit=limit)


def convergence_dtn_forward_submit_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn
    import base64

    raw_b64 = str(payload.get("data_b64") or "").strip()
    if not raw_b64:
        raise ValueError("data_b64 required")
    raw = base64.b64decode(raw_b64, validate=True)
    return dtn.receive_peer_bundle(
        raw,
        from_node_id=str(payload.get("from_node_id") or payload.get("node_id") or ""),
        requeue_upstream=bool(payload.get("requeue_upstream", True)),
    )


def convergence_dtn_forward_flush_payload(
    *,
    upstream_url: str = "",
    limit: int = 3,
    force: bool = False,
) -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    return dtn.flush_forward_queue(upstream_url=upstream_url, limit=limit, force=force)


def convergence_dtn_flush_window_payload() -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    return dtn.flush_window_status()


def convergence_dtn_compact_payload() -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    return dtn.compact_forward_queue()


def convergence_dtn_upkeep_payload(*, force_flush: bool = False) -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    return dtn.upkeep_dtn(force_flush=force_flush)


def convergence_dtn_peers_payload(*, limit: int = 30) -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    return dtn.list_dtn_peers(limit=limit)


def convergence_dtn_peers_discover_payload() -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    return dtn.discover_dtn_peers()


def convergence_dtn_peer_register_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    return dtn.register_dtn_peer(
        base_url=str(payload.get("base_url") or ""),
        node_id=str(payload.get("node_id") or ""),
        region=str(payload.get("region") or ""),
        source=str(payload.get("source") or "manual"),
    )


def convergence_dtn_gossip_status_payload() -> Dict[str, Any]:
    from chain_mesh import dtn_gossip as gossip

    return gossip.status_payload()


def convergence_dtn_gossip_exchange_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import dtn_gossip as gossip

    result = gossip.ingest_exchange_payload(payload)
    reply = result.pop("reply", None) or gossip.build_exchange_payload()
    return {**result, **reply}


def convergence_dtn_gossip_round_payload(*, limit: int = 0) -> Dict[str, Any]:
    from chain_mesh import dtn_gossip as gossip

    return gossip.gossip_round(limit=limit)


def convergence_dtn_starlink_status_payload() -> Dict[str, Any]:
    from chain_mesh import dtn_starlink as starlink

    return starlink.status_payload()


def convergence_dtn_starlink_probe_payload(*, url: str = "") -> Dict[str, Any]:
    from chain_mesh import dtn_starlink as starlink

    return starlink.probe_uplink(url=url)


def convergence_dtn_starlink_handoff_payload(*, force: bool = False, limit: int = 0) -> Dict[str, Any]:
    from chain_mesh import dtn_starlink as starlink

    return starlink.starlink_handoff(force=force, limit=limit)


def convergence_dtn_planetary_status_payload() -> Dict[str, Any]:
    from chain_mesh import planetary_quorum as planetary

    return planetary.status_payload()


def convergence_dtn_planetary_regions_payload(*, limit: int = 50) -> Dict[str, Any]:
    from chain_mesh import planetary_quorum as planetary

    return planetary.list_regions(limit=limit)


def convergence_dtn_planetary_heal_payload(
    *,
    limit: int = 0,
    regions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    from chain_mesh import planetary_quorum as planetary

    return planetary.planetary_heal(limit=limit, regions=regions)


def convergence_dtn_planetary_exchange_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import planetary_quorum as planetary

    result = planetary.ingest_exchange_payload(payload)
    reply = result.pop("reply", None) or {
        "ok": True,
        "format": planetary.PLANETARY_FORMAT,
        "node_id": payload.get("node_id") or "",
        "quorum_snapshots": [planetary.build_quorum_snapshot()],
    }
    result["reply"] = reply
    return result


def convergence_dtn_planetary_round_payload(*, limit: int = 0) -> Dict[str, Any]:
    from chain_mesh import planetary_quorum as planetary

    return planetary.planetary_exchange_round(limit=limit)


def convergence_bridge_status_payload() -> Dict[str, Any]:
    from chain_mesh import bridge_swap as bridge

    return bridge.status_payload()


def convergence_bridge_quote_payload(
    *,
    direction: str = "",
    amount: Any = None,
    stone_address: str = "",
    blurt_account: str = "",
) -> Dict[str, Any]:
    from chain_mesh import bridge_swap as bridge

    return bridge.quote_swap(
        direction=direction,
        amount=amount,
        stone_address=stone_address,
        blurt_account=blurt_account,
    )


def convergence_bridge_initiate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import bridge_swap as bridge

    return bridge.initiate_swap(
        direction=str(payload.get("direction") or ""),
        amount=payload.get("amount") or payload.get("blurt_amount") or payload.get("stone_amount"),
        stone_address=str(payload.get("stone_address") or ""),
        blurt_account=str(payload.get("blurt_account") or ""),
    )


def convergence_bridge_claim_payload(*, swap_id: str, preimage: str) -> Dict[str, Any]:
    from chain_mesh import bridge_swap as bridge

    return bridge.claim_swap(swap_id=swap_id, preimage=preimage)


def convergence_bridge_attest_payload(*, swap_id: str, stone_txid: str) -> Dict[str, Any]:
    from chain_mesh import bridge_swap as bridge

    return bridge.attest_stone_funding(swap_id=swap_id, stone_txid=stone_txid)


def convergence_bridge_intents_payload(*, status: str = "", limit: int = 50) -> Dict[str, Any]:
    from chain_mesh import bridge_swap as bridge

    return bridge.list_intents(status=status, limit=limit)


def convergence_bridge_sync_payload() -> Dict[str, Any]:
    from chain_mesh import bridge_swap as bridge

    return bridge.sync_bridge_transfers()


def convergence_ai_status_payload() -> Dict[str, Any]:
    from chain_mesh import ai_routing as ai

    return ai.status_payload()


def convergence_ai_providers_payload(
    *,
    runtime: str = "",
    region: str = "",
    limit: int = 50,
) -> Dict[str, Any]:
    from chain_mesh import ai_provider as aip

    return aip.list_ai_providers(runtime=runtime, region=region, limit=limit)


def convergence_ai_register_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import ai_routing as ai

    return ai.register_local_provider(
        provider_id=str(payload.get("provider_id") or ""),
        node_id=str(payload.get("node_id") or ""),
        display_name=str(payload.get("display_name") or ""),
        runtimes=payload.get("runtimes"),
        region=str(payload.get("region") or ""),
        offline_capable=payload.get("offline_capable", True) not in (False, "0", 0),
        endpoints=payload.get("endpoints"),
        models=payload.get("models"),
        flops_per_sec=int(payload.get("flops_per_sec") or 0),
        max_concurrent=int(payload.get("max_concurrent") or 2),
        source=str(payload.get("source") or "manual"),
    )


def convergence_ai_route_payload(*, job_id: str = "", force: bool = False) -> Dict[str, Any]:
    from chain_mesh import ai_routing as ai

    return ai.route_inference_job(job_id=job_id, force=bool(force))


def convergence_ai_submit_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import ai_routing as ai

    return ai.submit_inference_payload(payload)


def convergence_ai_provider_health_payload(*, provider_id: str = "") -> Dict[str, Any]:
    from chain_mesh import ai_provider as aip

    return aip.provider_health_payload(provider_id=provider_id)


def convergence_ai_discover_payload() -> Dict[str, Any]:
    from chain_mesh import ai_routing as ai

    return ai.discover_ai_providers()


def convergence_ai_dispatch_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import ai_routing as ai

    job_id = str(payload.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("job_id required")
    return ai.coordinator_dispatch_job(
        job_id=job_id,
        callback_url=str(payload.get("callback_url") or ""),
        origin_node_id=str(payload.get("origin_node_id") or ""),
        payload=payload,
    )


def convergence_ai_callback_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import ai_routing as ai

    job_id = str(payload.get("job_id") or "").strip()
    if not job_id:
        raise ValueError("job_id required")
    return ai.ingest_ai_callback({**payload, "job_id": job_id})


def convergence_ai_npu_status_payload() -> Dict[str, Any]:
    from chain_mesh import ai_npu_detect as npu

    return npu.detect_npu_hardware()


def convergence_ai_gossip_sign_status_payload() -> Dict[str, Any]:
    from chain_mesh import ai_gossip_sign as gsign

    return gsign.status_payload()


def convergence_dtn_replication_heal_payload(
    *,
    region: str = "",
    limit: int = 10,
) -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    return dtn.replication_heal(region=region, limit=limit)


def convergence_dtn_mdns_status_payload(*, include_browse: bool = False) -> Dict[str, Any]:
    from chain_mesh import mdns_discovery as mdns

    return mdns.mdns_status(include_browse=include_browse)


def convergence_dtn_mdns_register_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import mdns_discovery as mdns

    port = None
    if payload.get("port") is not None:
        port = int(payload.get("port"))
    return mdns.register_dtn_service(
        node_id=str(payload.get("node_id") or ""),
        port=port,
        region=str(payload.get("region") or ""),
        host=str(payload.get("host") or ""),
    )


def convergence_dtn_mdns_browse_payload(*, register: bool = True) -> Dict[str, Any]:
    from chain_mesh import mdns_discovery as mdns

    return mdns.discover_mdns_dtn_peers(register=register)


def convergence_dtn_replication_status_payload(*, region: str = "") -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    return dtn.replication_status(region=region)


def convergence_dtn_replication_check_payload(
    *,
    region: str = "",
    chunk_hashes: Optional[List[str]] = None,
    quorum_n: int = 0,
    quorum_m: int = 0,
) -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    return dtn.update_region_quorum(
        region=region,
        chunk_hashes=chunk_hashes,
        quorum_n=quorum_n,
        quorum_m=quorum_m,
    )


def convergence_dtn_alerts_payload() -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    return dtn.alerts_payload()


def convergence_dtn_tls_status_payload() -> Dict[str, Any]:
    from chain_mesh import dtn_tls as tls

    return tls.tls_status()


def convergence_spatial_manifest_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import spatial_manifest as spatial

    return spatial.manifest_payload(payload)


def convergence_spatial_embed_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import spatial_embed as se

    return se.embed_payload(
        scene_id=str(payload.get("scene_id") or ""),
        author=str(payload.get("author") or ""),
        title=str(payload.get("title") or ""),
        post_id=str(payload.get("post_id") or ""),
    )


def convergence_spatial_overlay_payload(
    *,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_m: float = 500,
    author: str = "",
    post_id: str = "",
    scene_id: str = "",
    limit: int = 20,
) -> Dict[str, Any]:
    from chain_mesh import spatial_manifest as spatial

    return spatial.overlay_query(
        lat=lat,
        lon=lon,
        radius_m=radius_m,
        author=author,
        post_id=post_id,
        scene_id=scene_id,
        limit=limit,
    )


def convergence_spatial_sync_payload() -> Dict[str, Any]:
    from chain_mesh import spatial_manifest as spatial

    return spatial.sync_registry_spatial()


def mesh_v2_system_payload() -> Dict[str, Any]:
    from chain_mesh import mesh_v2_lite as v2

    return v2.system_status_payload()


def mesh_v2_manifest_payload(asset_key: str) -> Dict[str, Any]:
    from chain_mesh import mesh_v2_lite as v2

    return v2.resolve_manifest(asset_key)


def mesh_v2_trustless_verify_payload(asset_key: str) -> Dict[str, Any]:
    from chain_mesh import mesh_v2_lite as v2

    return v2.trustless_retrieve_payload(asset_key)


def mesh_v2_publish_flow_payload() -> Dict[str, Any]:
    from chain_mesh import mesh_v2_lite as v2

    return v2.publish_flow_diagram()


def mesh_v2_register_provider_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import mesh_providers as mp

    return mp.register_provider(
        peer_id=str(payload.get("peer_id") or ""),
        multiaddrs=list(payload.get("multiaddrs") or []),
        roles=list(payload.get("roles") or ["storage"]),
        display_name=str(payload.get("display_name") or ""),
        tenant=str(payload.get("tenant") or ""),
        read_only=bool(payload.get("read_only")),
        storage_enabled=bool(payload.get("storage_enabled", True)),
    )


def mesh_v2_list_providers_payload(*, tenant: str = "", role: str = "") -> Dict[str, Any]:
    from chain_mesh import mesh_providers as mp

    return {"ok": True, "providers": mp.list_providers(tenant=tenant, role=role)}


def mesh_v2_sync_blurt_registry_payload() -> Dict[str, Any]:
    from chain_mesh import blurt_registry_v2 as br

    return br.sync_registry_accounts()


def rental_upload_batch(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Renter chunk upload — debits rental compute credits."""
    from chain_mesh.partner import rental_auth_from_payload
    import pool_hashrate_rental as phr

    order, _asset_key = rental_auth_from_payload(payload)
    items = payload.get("chunks") or []
    total_bytes = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        raw_b64 = item.get("data_b64") or item.get("data")
        if raw_b64:
            total_bytes += len(base64.b64decode(raw_b64))
    if total_bytes > 0:
        phr.reserve_publish_bytes(str(order["id"]), total_bytes)
    try:
        result = upload_batch(payload)
        result["rental_order_id"] = order["id"]
        result["credit_bytes_reserved"] = total_bytes
        return result
    except Exception:
        if total_bytes > 0:
            phr.release_reserved_bytes(str(order["id"]), total_bytes)
        raise


def rental_publish_asset_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Renter manifest publish — keys under assets/rental/<order_id>/."""
    from chain_mesh.partner import rental_auth_from_payload
    import pool_hashrate_rental as phr

    order, asset_key = rental_auth_from_payload(payload)
    file_size = int(payload.get("file_size") or 0)
    if file_size > 0:
        phr.reserve_publish_bytes(str(order["id"]), file_size)
    chunks = payload.get("chunks") or []
    anchor = bool(payload.get("anchor", True))
    try:
        result = mesh_assets.publish_asset_manifest(
            asset_key=asset_key,
            display_name=str(payload.get("display_name") or ""),
            version=str(payload.get("version") or ""),
            mime_type=str(payload.get("mime_type") or ""),
            file_size=file_size,
            file_sha256=str(payload.get("file_sha256") or ""),
            merkle_root_hex=str(payload.get("merkle_root") or ""),
            chunks=list(chunks),
            anchor=anchor,
            anchor_wallet=str(payload.get("anchor_wallet") or order.get("renter_wallet") or "").strip()
            or None,
        )
        if file_size > 0:
            phr.commit_publish_bytes(str(order["id"]), file_size)
        meter = phr.order_meter(str(order["id"]))
        result["rental_order_id"] = order["id"]
        result["credit_bytes_available"] = meter.get("credit_bytes_available", 0)
        return result
    except Exception:
        if file_size > 0:
            phr.release_reserved_bytes(str(order["id"]), file_size)
        raise