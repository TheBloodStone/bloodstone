"""Wave C — DTN sync bundles, store-and-forward, regional replication quorum."""

from __future__ import annotations

import hashlib
import io
import json
import os
import time
import uuid
import zipfile
from typing import Any, Dict, List, Optional, Tuple

import requests

from chain_mesh import agent_identity as agents
from chain_mesh import blurt_registry_v2 as blurt_reg
from chain_mesh import db as mesh_db
from chain_mesh import mesh_providers as providers
from chain_mesh import provenance as prov
from chain_mesh.store import chunk_exists, get_chunk, put_chunk

DTN_BUNDLE_FORMAT = "bloodstone-dtn-bundle-v1"
DTN_SYNC_WINDOW_SEC = int(os.environ.get("DTN_SYNC_WINDOW_SEC", str(72 * 3600)))
DTN_MAX_BUNDLE_BYTES = int(os.environ.get("DTN_MAX_BUNDLE_BYTES", str(256 * 1024 * 1024)))
DTN_QUEUE_DIR = os.environ.get(
    "DTN_FORWARD_QUEUE_DIR", "/root/chain_mesh/dtn_forward_queue"
)
DTN_DEFAULT_REGION = os.environ.get("DTN_DEFAULT_REGION", "global")
DTN_QUORUM_N = int(os.environ.get("DTN_QUORUM_N", "2"))
DTN_QUORUM_M = int(os.environ.get("DTN_QUORUM_M", "3"))
DTN_UPSTREAM_URL = os.environ.get(
    "DTN_UPSTREAM_URL",
    os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"),
).rstrip("/")
DTN_BUNDLE_TTL_SEC = int(os.environ.get("DTN_BUNDLE_TTL_SEC", str(7 * 86400)))
DTN_MAX_HOPS = int(os.environ.get("DTN_MAX_HOPS", "8"))
DTN_MAX_RETRIES = int(os.environ.get("DTN_MAX_RETRIES", "5"))
DTN_RETRY_BACKOFF_SEC = [
    int(x.strip())
    for x in os.environ.get("DTN_RETRY_BACKOFF_SEC", "60,300,900,3600,7200").split(",")
    if x.strip().isdigit()
] or [60, 300, 900, 3600, 7200]
DTN_FLUSH_WINDOWS_UTC = os.environ.get("DTN_FLUSH_WINDOWS_UTC", "02:00-02:30,14:00-14:30")
DTN_COMPACT_DELIVERED_SEC = int(os.environ.get("DTN_COMPACT_DELIVERED_SEC", str(86400)))
DTN_PEER_TTL_SEC = int(os.environ.get("DTN_PEER_TTL_SEC", "300"))
DTN_LAN_WEB_PORT = int(os.environ.get("DTN_LAN_WEB_PORT", "8887"))
DTN_PEER_URLS = [
    u.strip().rstrip("/")
    for u in os.environ.get("DTN_PEER_URLS", "").split(",")
    if u.strip()
]
DTN_ALERT_FAILED_THRESHOLD = int(os.environ.get("DTN_ALERT_FAILED_THRESHOLD", "3"))
DTN_ALERT_PENDING_THRESHOLD = int(os.environ.get("DTN_ALERT_PENDING_THRESHOLD", "25"))
DTN_ALERT_COOLDOWN_SEC = int(os.environ.get("DTN_ALERT_COOLDOWN_SEC", "3600"))
DTN_ALERT_WEBHOOK_URL = (os.environ.get("DTN_ALERT_WEBHOOK_URL") or "").strip()


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def _ensure_queue_dir() -> None:
    os.makedirs(DTN_QUEUE_DIR, mode=0o700, exist_ok=True)


def _migrate_dtn_schema(conn) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(dtn_forward_queue)").fetchall()}
    for name, ddl in (
        ("bundle_sha256", "ALTER TABLE dtn_forward_queue ADD COLUMN bundle_sha256 TEXT NOT NULL DEFAULT ''"),
        ("retry_count", "ALTER TABLE dtn_forward_queue ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0"),
        ("last_attempt_at", "ALTER TABLE dtn_forward_queue ADD COLUMN last_attempt_at INTEGER NOT NULL DEFAULT 0"),
        ("next_retry_at", "ALTER TABLE dtn_forward_queue ADD COLUMN next_retry_at INTEGER NOT NULL DEFAULT 0"),
        ("expires_at", "ALTER TABLE dtn_forward_queue ADD COLUMN expires_at INTEGER NOT NULL DEFAULT 0"),
        ("max_hops", "ALTER TABLE dtn_forward_queue ADD COLUMN max_hops INTEGER NOT NULL DEFAULT 8"),
    ):
        if name not in cols:
            conn.execute(ddl)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_dtn_forward_sha ON dtn_forward_queue(bundle_sha256, status)"
    )


def init_dtn_db() -> None:
    _ensure_queue_dir()
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS dtn_forward_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bundle_id TEXT NOT NULL UNIQUE,
                node_id TEXT NOT NULL DEFAULT '',
                region TEXT NOT NULL DEFAULT 'global',
                file_path TEXT NOT NULL,
                byte_size INTEGER NOT NULL DEFAULT 0,
                anchor_count INTEGER NOT NULL DEFAULT 0,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                hop_count INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                delivered_at INTEGER NOT NULL DEFAULT 0,
                bundle_sha256 TEXT NOT NULL DEFAULT '',
                retry_count INTEGER NOT NULL DEFAULT 0,
                last_attempt_at INTEGER NOT NULL DEFAULT 0,
                next_retry_at INTEGER NOT NULL DEFAULT 0,
                expires_at INTEGER NOT NULL DEFAULT 0,
                max_hops INTEGER NOT NULL DEFAULT 8
            );
            CREATE INDEX IF NOT EXISTS idx_dtn_forward_status
                ON dtn_forward_queue(status, created_at ASC);

            CREATE TABLE IF NOT EXISTS dtn_sync_watermarks (
                node_id TEXT PRIMARY KEY,
                last_export_at INTEGER NOT NULL DEFAULT 0,
                last_import_at INTEGER NOT NULL DEFAULT 0,
                last_bundle_id TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS dtn_region_quorum (
                region TEXT NOT NULL,
                chunk_hash TEXT NOT NULL,
                providers_found INTEGER NOT NULL DEFAULT 0,
                quorum_n INTEGER NOT NULL DEFAULT 2,
                quorum_m INTEGER NOT NULL DEFAULT 3,
                satisfied INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (region, chunk_hash)
            );

            CREATE TABLE IF NOT EXISTS dtn_seen_bundles (
                bundle_sha256 TEXT PRIMARY KEY,
                bundle_id TEXT NOT NULL DEFAULT '',
                first_seen_at INTEGER NOT NULL,
                last_seen_at INTEGER NOT NULL,
                import_count INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS dtn_peers (
                peer_id TEXT PRIMARY KEY,
                node_id TEXT NOT NULL DEFAULT '',
                base_url TEXT NOT NULL,
                region TEXT NOT NULL DEFAULT 'global',
                source TEXT NOT NULL DEFAULT 'manual',
                roles TEXT NOT NULL DEFAULT '["dtn"]',
                last_seen INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_dtn_peers_seen
                ON dtn_peers(last_seen DESC);

            CREATE TABLE IF NOT EXISTS dtn_alert_state (
                alert_key TEXT PRIMARY KEY,
                last_value INTEGER NOT NULL DEFAULT 0,
                last_alert_at INTEGER NOT NULL DEFAULT 0,
                last_cleared_at INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        _migrate_dtn_schema(conn)


def _bundle_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _record_bundle_seen(*, sha: str, bundle_id: str) -> None:
    init_dtn_db()
    now = _now()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO dtn_seen_bundles (bundle_sha256, bundle_id, first_seen_at, last_seen_at, import_count)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(bundle_sha256) DO UPDATE SET
                bundle_id = excluded.bundle_id,
                last_seen_at = excluded.last_seen_at,
                import_count = import_count + 1
            """,
            (sha, bundle_id, now, now),
        )


def _is_bundle_seen(sha: str) -> bool:
    init_dtn_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM dtn_seen_bundles WHERE bundle_sha256 = ?",
            (sha,),
        ).fetchone()
    return row is not None


def _parse_flush_windows() -> List[Tuple[int, int]]:
    """Return list of (start_minute, end_minute) from UTC day for flush windows."""
    windows: List[Tuple[int, int]] = []
    for part in (DTN_FLUSH_WINDOWS_UTC or "").split(","):
        part = part.strip()
        if "-" not in part:
            continue
        start_s, end_s = part.split("-", 1)
        try:
            sh, sm = [int(x) for x in start_s.strip().split(":")]
            eh, em = [int(x) for x in end_s.strip().split(":")]
            windows.append((sh * 60 + sm, eh * 60 + em))
        except (ValueError, TypeError):
            continue
    return windows


def is_flush_window_open(*, now: Optional[int] = None) -> bool:
    """True when current UTC time falls in a configured uplink flush window."""
    windows = _parse_flush_windows()
    if not windows:
        return True
    t = time.gmtime(now or _now())
    minute = t.tm_hour * 60 + t.tm_min
    for start, end in windows:
        if start <= minute <= end:
            return True
    return False


def flush_window_status() -> Dict[str, Any]:
    open_now = is_flush_window_open()
    return {
        "ok": True,
        "flush_window_open": open_now,
        "windows_utc": DTN_FLUSH_WINDOWS_UTC,
        "parsed_windows": _parse_flush_windows(),
        "utc_now": time.strftime("%H:%M", time.gmtime(_now())),
    }


def _bundle_id() -> str:
    return uuid.uuid4().hex[:16]


def _collect_blurt_anchors(*, since: int) -> List[Dict[str, Any]]:
    blurt_reg.init_blurt_registry_db()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT asset_key, block_num, trx_id, author, manifest_merkle_root,
                   file_sha256, file_size, mime_type, provider_ids, replication_factor,
                   chunk_hashes, anchor_json, created_at
            FROM blurt_mesh_anchors
            WHERE created_at >= ? AND is_current = 1
            ORDER BY created_at ASC
            """,
            (since,),
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["provider_ids"] = json.loads(item.get("provider_ids") or "[]")
        item["chunk_hashes"] = json.loads(item.get("chunk_hashes") or "[]")
        out.append(item)
    return out


def _collect_provenance_anchors(*, since: int) -> List[Dict[str, Any]]:
    prov.init_provenance_db()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT provenance_id, asset_key, author, content_sha256,
                   mesh_merkle_root, anchor_json, trx_id, block_num, created_at
            FROM bloodstone_provenance_anchors
            WHERE created_at >= ? AND is_current = 1
            ORDER BY created_at ASC
            """,
            (since,),
        ).fetchall()
    return [dict(r) for r in rows]


def _collect_spatial_manifests(*, since: int) -> List[Dict[str, Any]]:
    from chain_mesh import spatial_manifest as spatial

    spatial.init_spatial_db()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT scene_id, author, post_id, title, asset_keys, model_format,
                   placement, scale_json, geo_lat, geo_lon, manifest_json,
                   trx_id, block_num, created_at
            FROM bloodstone_spatial_manifests
            WHERE created_at >= ? AND is_current = 1
            ORDER BY created_at ASC
            """,
            (since,),
        ).fetchall()
    return [dict(r) for r in rows]


def _collect_post_manifests(*, since: int) -> List[Dict[str, Any]]:
    from chain_mesh import condenser_offline as coff

    return coff.collect_post_manifest_rows(since=since)


def _collect_compute_jobs(*, since: int) -> List[Dict[str, Any]]:
    from chain_mesh import compute_job as cjobs

    cjobs.init_compute_job_db()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT job_id, stone_address, blurt_author, agent_id, job_type, status,
                   flops_budget, input_asset_keys, output_asset_key, region, provider_id,
                   job_json, trx_id, block_num, created_at, updated_at
            FROM bloodstone_compute_jobs
            WHERE updated_at >= ? AND is_current = 1
            ORDER BY updated_at ASC
            """,
            (since,),
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["input_asset_keys"] = json.loads(item.get("input_asset_keys") or "[]")
        out.append(item)
    return out


def _import_compute_jobs(rows: List[Dict[str, Any]]) -> int:
    from chain_mesh import compute_job as cjobs

    return cjobs.import_job_rows(rows)


def _import_post_manifests(rows: List[Dict[str, Any]]) -> int:
    from chain_mesh import condenser_offline as coff

    return coff.import_post_manifest_rows(rows)


def _collect_ai_route_assignments(*, since: int) -> List[Dict[str, Any]]:
    try:
        from chain_mesh import ai_routing as ai

        ai.init_ai_routing_db()
        with _conn() as conn:
            rows = conn.execute(
                """
                SELECT job_id, stone_address, provider_id, route_status, score, reason,
                       uplink_available, offline_mode, route_json, created_at, updated_at
                FROM ai_route_assignments
                WHERE is_current = 1 AND updated_at >= ?
                ORDER BY updated_at ASC
                """,
                (since,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _import_ai_route_assignments(rows: List[Dict[str, Any]]) -> int:
    from chain_mesh import ai_routing as ai

    result = ai.ingest_route_assignments(rows)
    return int(result.get("recorded") or 0)


def _collect_ai_providers(*, since: int) -> List[Dict[str, Any]]:
    try:
        from chain_mesh import ai_provider as aip

        aip.init_ai_provider_db()
        with _conn() as conn:
            rows = conn.execute(
                """
                SELECT provider_id, peer_id, node_id, stone_address, agent_id,
                       display_name, runtimes, models_json, hardware_json,
                       endpoints_json, region, offline_capable, max_concurrent,
                       flops_per_sec, load_ratio, source, provider_json,
                       last_seen, created_at
                FROM bloodstone_ai_providers
                WHERE last_seen >= ?
                ORDER BY last_seen ASC
                """,
                (since,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _import_ai_providers(rows: List[Dict[str, Any]]) -> int:
    from chain_mesh import ai_provider as aip

    imported = 0
    for row in rows or []:
        pid = str(row.get("provider_id") or "").strip()
        if not pid:
            continue
        existing = aip.get_ai_provider(provider_id=pid)
        last_seen = int(row.get("last_seen") or _now())
        if existing and existing.get("source") in ("local", "mdns", "lan"):
            if int(existing.get("last_seen") or 0) >= last_seen:
                continue
        aip.register_ai_provider(provider_id=pid, source="dtn", merge=True, body=row)
        imported += 1
    return imported


def _collect_agent_identities(*, since: int) -> List[Dict[str, Any]]:
    agents.init_agent_db()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT agent_id, blurt_author, stone_address, capabilities,
                   display_name, agent_json, trx_id, block_num, created_at
            FROM bloodstone_agent_identities
            WHERE created_at >= ? AND is_current = 1
            ORDER BY created_at ASC
            """,
            (since,),
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        item["capabilities"] = json.loads(item.get("capabilities") or "[]")
        out.append(item)
    return out


def _chunk_hashes_from_anchors(blurt_anchors: List[Dict[str, Any]]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for anchor in blurt_anchors:
        for raw in anchor.get("chunk_hashes") or []:
            h = str(raw or "").strip().lower()
            if len(h) == 64 and h not in seen:
                seen.add(h)
                ordered.append(h)
    return ordered


def build_minimal_chunk_bundle(
    *,
    chunk_hashes: List[str],
    node_id: str = "",
    region: str = "",
    purpose: str = "replication_heal",
) -> Tuple[bytes, str, Dict[str, Any]]:
    """Pack only specified chunks — for quorum heal without full anchor diff."""
    init_dtn_db()
    nid = (node_id or os.environ.get("DTN_NODE_ID", "pi-edge")).strip()[:64]
    reg = (region or DTN_DEFAULT_REGION).strip()[:32]
    hashes = [str(h).strip().lower() for h in chunk_hashes if len(str(h).strip()) == 64]
    meta = {
        "format": DTN_BUNDLE_FORMAT,
        "bundle_id": _bundle_id(),
        "node_id": nid,
        "region": reg,
        "exported_at": _now(),
        "purpose": purpose,
        "chunk_count": len(hashes),
        "include_chunks": True,
    }
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(meta["exported_at"]))
    filename = f"bloodstone-dtn-heal-{nid}-{stamp}.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("dtn-meta.json", json.dumps(meta, indent=2))
        zf.writestr("blurt-anchors.json", "[]")
        zf.writestr("provenance-anchors.json", "[]")
        zf.writestr("agent-identities.json", "[]")
        zf.writestr("spatial-manifests.json", "[]")
        zf.writestr("compute-jobs.json", "[]")
        packed = 0
        for h in hashes:
            if not chunk_exists(h):
                continue
            data = get_chunk(h)
            if data is None:
                continue
            zf.writestr(f"chunks/{h}.bin", data)
            packed += 1
        meta["chunks_packed"] = packed
        zf.writestr("dtn-meta.json", json.dumps(meta, indent=2))
    return buf.getvalue(), filename, meta


def build_dtn_bundle(
    *,
    node_id: str = "",
    since: Optional[int] = None,
    include_chunks: bool = True,
    region: str = "",
) -> Tuple[bytes, str, Dict[str, Any]]:
    """Export mesh state + Blurt anchor diff as a portable DTN capsule."""
    init_dtn_db()
    window = max(3600, DTN_SYNC_WINDOW_SEC)
    watermark = int(since if since is not None else (_now() - window))
    nid = (node_id or os.environ.get("DTN_NODE_ID", "pi-edge")).strip()[:64]
    reg = (region or DTN_DEFAULT_REGION).strip()[:32]

    blurt_anchors = _collect_blurt_anchors(since=watermark)
    provenance_anchors = _collect_provenance_anchors(since=watermark)
    agent_rows = _collect_agent_identities(since=watermark)
    spatial_rows = _collect_spatial_manifests(since=watermark)
    compute_rows = _collect_compute_jobs(since=watermark)
    post_rows = _collect_post_manifests(since=watermark)
    ai_provider_rows = _collect_ai_providers(since=watermark)
    ai_route_rows: List[Dict[str, Any]] = []
    try:
        from chain_mesh import ai_routing as ai

        if ai.AI_DTN_EXPORT_ROUTES:
            ai_route_rows = _collect_ai_route_assignments(since=watermark)
    except Exception:
        ai_route_rows = []
    tenant_rows: List[Dict[str, Any]] = []
    try:
        from chain_mesh import tenant_fleet_sync as tfleet

        tenant_rows = tfleet.collect_tenant_snapshots()
    except Exception:
        tenant_rows = []
    chunk_hashes = _chunk_hashes_from_anchors(blurt_anchors)

    meta = {
        "format": DTN_BUNDLE_FORMAT,
        "bundle_id": _bundle_id(),
        "node_id": nid,
        "region": reg,
        "exported_at": _now(),
        "watermark_since": watermark,
        "sync_window_sec": window,
        "blurt_anchor_count": len(blurt_anchors),
        "provenance_count": len(provenance_anchors),
        "agent_count": len(agent_rows),
        "spatial_count": len(spatial_rows),
        "compute_job_count": len(compute_rows),
        "post_manifest_count": len(post_rows),
        "ai_provider_count": len(ai_provider_rows),
        "ai_route_count": len(ai_route_rows),
        "tenant_snapshot_count": len(tenant_rows),
        "chunk_count": len(chunk_hashes),
        "include_chunks": bool(include_chunks),
        "use_case": "off_grid_dtn_mesh",
    }

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(meta["exported_at"]))
    filename = f"bloodstone-dtn-{nid}-{stamp}.zip"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("dtn-meta.json", json.dumps(meta, indent=2))
        zf.writestr("blurt-anchors.json", json.dumps(blurt_anchors, indent=2))
        zf.writestr("provenance-anchors.json", json.dumps(provenance_anchors, indent=2))
        zf.writestr("agent-identities.json", json.dumps(agent_rows, indent=2))
        zf.writestr("spatial-manifests.json", json.dumps(spatial_rows, indent=2))
        zf.writestr("compute-jobs.json", json.dumps(compute_rows, indent=2))
        zf.writestr("post-manifests.json", json.dumps(post_rows, indent=2))
        zf.writestr("ai-providers.json", json.dumps(ai_provider_rows, indent=2))
        if ai_route_rows:
            zf.writestr("ai-route-assignments.json", json.dumps(ai_route_rows, indent=2, default=str))
        if tenant_rows:
            zf.writestr("tenant-bindings.json", json.dumps(tenant_rows, indent=2, default=str))
        zf.writestr(
            "README.txt",
            "Bloodstone DTN sync bundle (Wave C+)\n"
            "Import: POST /api/convergence/dtn/import\n"
            "Offline Pi nodes queue bundles via /api/convergence/dtn/forward/submit\n"
            "Flush on brief uplink: POST /api/convergence/dtn/forward/flush\n",
        )
        if include_chunks:
            packed = 0
            for h in chunk_hashes:
                if not chunk_exists(h):
                    continue
                data = get_chunk(h)
                if data is None:
                    continue
                zf.writestr(f"chunks/{h}.bin", data)
                packed += 1
            meta["chunks_packed"] = packed
            zf.writestr("dtn-meta.json", json.dumps(meta, indent=2))

    blob = buf.getvalue()
    if len(blob) > DTN_MAX_BUNDLE_BYTES:
        raise ValueError(
            f"DTN bundle exceeds limit ({len(blob)} > {DTN_MAX_BUNDLE_BYTES} bytes); "
            "narrow sync window or set include_chunks=false"
        )

    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO dtn_sync_watermarks (node_id, last_export_at, last_bundle_id)
            VALUES (?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                last_export_at = excluded.last_export_at,
                last_bundle_id = excluded.last_bundle_id
            """,
            (nid, meta["exported_at"], meta["bundle_id"]),
        )

    return blob, filename, meta


def _import_blurt_anchors(rows: List[Dict[str, Any]]) -> int:
    blurt_reg.init_blurt_registry_db()
    imported = 0
    for row in rows:
        body = blurt_reg.parse_custom_json_body(row.get("anchor_json") or row)
        if not body:
            try:
                body = json.loads(row.get("anchor_json") or "{}")
            except json.JSONDecodeError:
                continue
        if not body:
            continue
        asset_key = str(body.get("asset_key") or row.get("asset_key") or "").strip()
        if not asset_key:
            continue
        with _conn() as conn:
            conn.execute(
                "UPDATE blurt_mesh_anchors SET is_current = 0 WHERE asset_key = ?",
                (asset_key,),
            )
            conn.execute(
                """
                INSERT INTO blurt_mesh_anchors (
                    asset_key, block_num, trx_id, author, manifest_merkle_root,
                    file_sha256, file_size, mime_type, provider_ids, replication_factor,
                    chunk_hashes, uploader_signature, anchor_json, created_at, is_current
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    asset_key,
                    int(row.get("block_num") or body.get("block_num") or 0),
                    str(row.get("trx_id") or ""),
                    str(row.get("author") or body.get("author") or ""),
                    str(body.get("manifest_merkle_root") or row.get("manifest_merkle_root") or ""),
                    str(body.get("file_sha256") or row.get("file_sha256") or ""),
                    int(body.get("file_size") or row.get("file_size") or 0),
                    str(body.get("mime_type") or row.get("mime_type") or ""),
                    json.dumps(body.get("provider_ids") or row.get("provider_ids") or []),
                    int(body.get("replication_factor") or row.get("replication_factor") or 1),
                    json.dumps(body.get("chunk_hashes") or row.get("chunk_hashes") or []),
                    str(body.get("uploader_signature") or ""),
                    json.dumps(body),
                    int(row.get("created_at") or body.get("timestamp") or _now()),
                ),
            )
        imported += 1
    return imported


def _import_provenance(rows: List[Dict[str, Any]]) -> int:
    imported = 0
    for row in rows:
        try:
            body = json.loads(row.get("anchor_json") or "{}")
        except json.JSONDecodeError:
            continue
        if str(body.get("v") or "") != "1":
            continue
        prov.index_provenance_anchor(
            body=body,
            author=str(row.get("author") or body.get("author") or ""),
            trx_id=str(row.get("trx_id") or ""),
            block_num=int(row.get("block_num") or 0),
        )
        imported += 1
    return imported


def _import_spatial(rows: List[Dict[str, Any]]) -> int:
    from chain_mesh import spatial_manifest as spatial

    imported = 0
    for row in rows:
        try:
            body = json.loads(row.get("manifest_json") or "{}")
        except json.JSONDecodeError:
            continue
        if str(body.get("v") or "") != "1":
            continue
        spatial.index_spatial_manifest(
            body=body,
            author=str(row.get("author") or body.get("author") or ""),
            trx_id=str(row.get("trx_id") or ""),
            block_num=int(row.get("block_num") or 0),
        )
        imported += 1
    return imported


def _import_agents(rows: List[Dict[str, Any]]) -> int:
    imported = 0
    for row in rows:
        try:
            body = json.loads(row.get("agent_json") or "{}")
        except json.JSONDecodeError:
            continue
        if str(body.get("v") or "") != "1":
            continue
        agents.index_agent_identity(
            body=body,
            author=str(row.get("blurt_author") or body.get("blurt_author") or ""),
            trx_id=str(row.get("trx_id") or ""),
            block_num=int(row.get("block_num") or 0),
        )
        imported += 1
    return imported


def import_dtn_bundle(raw: bytes, *, skip_dedup: bool = False) -> Dict[str, Any]:
    """Ingest DTN capsule — merge Blurt diffs + optional mesh chunks."""
    init_dtn_db()
    if len(raw) > DTN_MAX_BUNDLE_BYTES:
        raise ValueError("DTN bundle too large")
    if raw[:2] != b"PK":
        raise ValueError("DTN bundle must be a zip file")

    sha = _bundle_sha256(raw)
    if not skip_dedup and _is_bundle_seen(sha):
        return {
            "ok": True,
            "duplicate": True,
            "bundle_sha256": sha,
            "reason": "bundle already imported (SHA256 dedup)",
        }

    meta: Dict[str, Any] = {}
    blurt_rows: List[Dict[str, Any]] = []
    prov_rows: List[Dict[str, Any]] = []
    agent_rows: List[Dict[str, Any]] = []
    chunk_pairs: List[Tuple[str, bytes]] = []

    with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
        if "dtn-meta.json" in zf.namelist():
            meta = json.loads(zf.read("dtn-meta.json").decode("utf-8"))
        if str(meta.get("format") or "") != DTN_BUNDLE_FORMAT:
            raise ValueError(f"unsupported DTN format: {meta.get('format')}")
        if "blurt-anchors.json" in zf.namelist():
            blurt_rows = json.loads(zf.read("blurt-anchors.json").decode("utf-8"))
        if "provenance-anchors.json" in zf.namelist():
            prov_rows = json.loads(zf.read("provenance-anchors.json").decode("utf-8"))
        if "agent-identities.json" in zf.namelist():
            agent_rows = json.loads(zf.read("agent-identities.json").decode("utf-8"))
        spatial_rows: List[Dict[str, Any]] = []
        if "spatial-manifests.json" in zf.namelist():
            spatial_rows = json.loads(zf.read("spatial-manifests.json").decode("utf-8"))
        compute_rows: List[Dict[str, Any]] = []
        if "compute-jobs.json" in zf.namelist():
            compute_rows = json.loads(zf.read("compute-jobs.json").decode("utf-8"))
        post_rows: List[Dict[str, Any]] = []
        if "post-manifests.json" in zf.namelist():
            post_rows = json.loads(zf.read("post-manifests.json").decode("utf-8"))
        ai_provider_rows: List[Dict[str, Any]] = []
        if "ai-providers.json" in zf.namelist():
            ai_provider_rows = json.loads(zf.read("ai-providers.json").decode("utf-8"))
        ai_route_rows: List[Dict[str, Any]] = []
        if "ai-route-assignments.json" in zf.namelist():
            ai_route_rows = json.loads(zf.read("ai-route-assignments.json").decode("utf-8"))
        tenant_rows: List[Dict[str, Any]] = []
        if "tenant-bindings.json" in zf.namelist():
            tenant_rows = json.loads(zf.read("tenant-bindings.json").decode("utf-8"))
        for name in zf.namelist():
            if not name.startswith("chunks/") or not name.endswith(".bin"):
                continue
            h = os.path.basename(name)[:-4].strip().lower()
            if len(h) != 64:
                continue
            chunk_pairs.append((h, zf.read(name)))

    stored_chunks = 0
    for h, blob in chunk_pairs:
        try:
            put_chunk(blob, expected_hash=h)
            stored_chunks += 1
        except ValueError:
            continue

    blurt_imported = _import_blurt_anchors(blurt_rows)
    prov_imported = _import_provenance(prov_rows)
    agent_imported = _import_agents(agent_rows)
    spatial_imported = _import_spatial(spatial_rows)
    compute_imported = _import_compute_jobs(compute_rows)
    post_imported = _import_post_manifests(post_rows)
    ai_providers_imported = _import_ai_providers(ai_provider_rows)
    ai_routes_imported = _import_ai_route_assignments(ai_route_rows)
    tenant_imported = 0
    try:
        from chain_mesh import tenant_fleet_sync as tfleet

        tenant_result = tfleet.ingest_tenant_snapshots(tenant_rows)
        tenant_imported = int(tenant_result.get("recorded") or 0)
    except Exception:
        tenant_imported = 0

    node_id = str(meta.get("node_id") or "imported")
    bundle_id = str(meta.get("bundle_id") or "")
    _record_bundle_seen(sha=sha, bundle_id=bundle_id)
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO dtn_sync_watermarks (node_id, last_import_at, last_bundle_id)
            VALUES (?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                last_import_at = excluded.last_import_at,
                last_bundle_id = excluded.last_bundle_id
            """,
            (node_id, _now(), bundle_id),
        )

    return {
        "ok": True,
        "bundle_id": bundle_id,
        "bundle_sha256": sha,
        "node_id": node_id,
        "watermark_since": meta.get("watermark_since"),
        "blurt_anchors_imported": blurt_imported,
        "provenance_imported": prov_imported,
        "agents_imported": agent_imported,
        "spatial_imported": spatial_imported,
        "compute_jobs_imported": compute_imported,
        "post_manifests_imported": post_imported,
        "ai_providers_imported": ai_providers_imported,
        "ai_routes_imported": ai_routes_imported,
        "tenant_bindings_imported": tenant_imported,
        "chunks_stored": stored_chunks,
        "total_chunks_in_bundle": len(chunk_pairs),
    }


def queue_bundle_for_forward(
    raw: bytes,
    *,
    node_id: str = "",
    region: str = "",
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Store-and-forward — queue bundle for delivery when uplink returns."""
    init_dtn_db()
    if len(raw) > DTN_MAX_BUNDLE_BYTES:
        raise ValueError("bundle too large for forward queue")
    sha = _bundle_sha256(raw)
    with _conn() as conn:
        existing = conn.execute(
            """
            SELECT bundle_id, status FROM dtn_forward_queue
            WHERE bundle_sha256 = ? AND status IN ('pending', 'delivered')
            ORDER BY created_at DESC LIMIT 1
            """,
            (sha,),
        ).fetchone()
    if existing:
        return {
            "ok": True,
            "duplicate": True,
            "bundle_id": existing["bundle_id"],
            "bundle_sha256": sha,
            "status": existing["status"],
            "reason": "bundle already queued or delivered",
        }

    bundle_id = str((meta or {}).get("bundle_id") or _bundle_id())
    nid = (node_id or os.environ.get("DTN_NODE_ID", "pi-edge")).strip()[:64]
    reg = (region or DTN_DEFAULT_REGION).strip()[:32]
    path = os.path.join(DTN_QUEUE_DIR, f"{bundle_id}.zip")
    with open(path, "wb") as fh:
        fh.write(raw)

    anchor_count = int((meta or {}).get("blurt_anchor_count") or 0)
    chunk_count = int((meta or {}).get("chunks_packed") or (meta or {}).get("chunk_count") or 0)
    now = _now()
    expires = now + DTN_BUNDLE_TTL_SEC
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO dtn_forward_queue (
                bundle_id, node_id, region, file_path, byte_size,
                anchor_count, chunk_count, status, hop_count, created_at,
                bundle_sha256, expires_at, max_hops, next_retry_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, ?, ?, ?)
            ON CONFLICT(bundle_id) DO UPDATE SET
                byte_size = excluded.byte_size,
                anchor_count = excluded.anchor_count,
                chunk_count = excluded.chunk_count,
                bundle_sha256 = excluded.bundle_sha256,
                status = 'pending',
                created_at = excluded.created_at,
                expires_at = excluded.expires_at,
                retry_count = 0,
                next_retry_at = 0
            """,
            (
                bundle_id, nid, reg, path, len(raw), anchor_count, chunk_count, now,
                sha, expires, DTN_MAX_HOPS, now,
            ),
        )
    return {
        "ok": True,
        "bundle_id": bundle_id,
        "bundle_sha256": sha,
        "node_id": nid,
        "region": reg,
        "byte_size": len(raw),
        "status": "pending",
        "expires_at": expires,
        "file_path": path,
    }


def list_pending_forwards(*, limit: int = 20) -> Dict[str, Any]:
    init_dtn_db()
    now = _now()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT bundle_id, node_id, region, byte_size, anchor_count,
                   chunk_count, status, hop_count, created_at, bundle_sha256,
                   retry_count, next_retry_at, expires_at
            FROM dtn_forward_queue
            WHERE status = 'pending' AND (next_retry_at <= ? OR next_retry_at = 0)
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (now, max(1, int(limit))),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM dtn_forward_queue WHERE status = 'pending'"
        ).fetchone()["c"]
        expired = conn.execute(
            "SELECT COUNT(*) AS c FROM dtn_forward_queue WHERE status = 'expired'"
        ).fetchone()["c"]
        failed = conn.execute(
            "SELECT COUNT(*) AS c FROM dtn_forward_queue WHERE status = 'failed'"
        ).fetchone()["c"]
    return {
        "ok": True,
        "pending_count": int(total),
        "expired_count": int(expired),
        "failed_count": int(failed),
        "flush_window_open": is_flush_window_open(),
        "bundles": [dict(r) for r in rows],
    }


def receive_peer_bundle(
    raw: bytes,
    *,
    from_node_id: str = "",
    requeue_upstream: bool = True,
) -> Dict[str, Any]:
    """Accept bundle from peer — import locally and optionally queue for upstream."""
    result = import_dtn_bundle(raw)
    queued = None
    if requeue_upstream:
        try:
            meta = {}
            if raw[:2] == b"PK":
                with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
                    if "dtn-meta.json" in zf.namelist():
                        meta = json.loads(zf.read("dtn-meta.json").decode("utf-8"))
            queued = queue_bundle_for_forward(
                raw,
                node_id=from_node_id or str(meta.get("node_id") or "peer"),
                region=str(meta.get("region") or DTN_DEFAULT_REGION),
                meta=meta,
            )
        except Exception as exc:
            queued = {"ok": False, "error": str(exc)}
    result["forward_queued"] = queued
    return result


def _push_bundle_to_url(
    raw: bytes,
    *,
    base_url: str,
    bundle_id: str,
) -> Dict[str, Any]:
    import base64

    from chain_mesh import dtn_tls as tls

    body = {"data_b64": base64.b64encode(raw).decode("ascii"), "from_forward": True}
    last_err = ""
    for candidate in tls.forward_url_candidates(base_url):
        url = candidate.rstrip("/")
        try:
            resp = tls.post_json(f"{url}/api/convergence/dtn/import", body)
            resp.raise_for_status()
            payload = resp.json()
            if not payload.get("ok"):
                raise RuntimeError(payload.get("error") or "import failed")
            return {
                "ok": True,
                "target": url,
                "bundle_id": bundle_id,
                "tls": url.startswith("https://"),
                "response": payload,
            }
        except Exception as exc:
            last_err = str(exc)
    raise RuntimeError(last_err or "all TLS/HTTP candidates failed")


def _schedule_retry(conn, *, bundle_id: str, retry_count: int) -> None:
    backoff = DTN_RETRY_BACKOFF_SEC[min(retry_count, len(DTN_RETRY_BACKOFF_SEC) - 1)]
    now = _now()
    status = "failed" if retry_count >= DTN_MAX_RETRIES else "pending"
    conn.execute(
        """
        UPDATE dtn_forward_queue
        SET retry_count = ?, last_attempt_at = ?, next_retry_at = ?, status = ?
        WHERE bundle_id = ?
        """,
        (retry_count, now, now + backoff, status, bundle_id),
    )


def register_dtn_peer(
    *,
    base_url: str,
    node_id: str = "",
    region: str = "",
    source: str = "manual",
    tls_hint: Optional[bool] = None,
    tls_port: Optional[int] = None,
) -> Dict[str, Any]:
    from chain_mesh import dtn_tls as tls

    init_dtn_db()
    url = tls.normalize_peer_base_url(
        (base_url or "").strip().rstrip("/"),
        tls_hint=tls_hint,
        tls_port=tls_port,
    )
    if not url.startswith("http"):
        raise ValueError("base_url must be http(s)")
    nid = (node_id or url).strip()[:64]
    reg = (region or DTN_DEFAULT_REGION).strip()[:32]
    peer_id = hashlib.sha256(f"{url}|{nid}".encode()).hexdigest()[:16]
    now = _now()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO dtn_peers (peer_id, node_id, base_url, region, source, last_seen, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(peer_id) DO UPDATE SET
                base_url = excluded.base_url,
                node_id = excluded.node_id,
                region = excluded.region,
                source = excluded.source,
                last_seen = excluded.last_seen
            """,
            (peer_id, nid, url, reg, source[:16], now, now),
        )
    return {"ok": True, "peer_id": peer_id, "base_url": url, "node_id": nid, "region": reg}


def discover_dtn_peers() -> Dict[str, Any]:
    """Discover DTN peers from mDNS, LAN heartbeat, and DTN_PEER_URLS env."""
    from chain_mesh import lan_registry as lan
    from chain_mesh import mdns_discovery as mdns

    init_dtn_db()
    lan.init_lan_db()
    discovered = 0
    mdns_result: Dict[str, Any] = {}
    try:
        mdns_result = mdns.discover_mdns_dtn_peers(register=True)
        discovered += int(mdns_result.get("peers_registered") or 0)
    except Exception as exc:
        mdns_result = {"ok": False, "error": str(exc)}

    now = _now()
    cutoff = now - DTN_PEER_TTL_SEC

    for url in DTN_PEER_URLS:
        try:
            register_dtn_peer(base_url=url, source="env")
            discovered += 1
        except ValueError:
            continue

    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT device_id, lan_ip, peer_kind, model, last_seen
            FROM chain_lan_nodes
            WHERE last_seen >= ?
            ORDER BY last_seen DESC
            LIMIT 50
            """,
            (cutoff,),
        ).fetchall()

    for row in rows:
        lan_ip = str(row["lan_ip"] or "").strip()
        if not lan_ip:
            continue
        from chain_mesh import dtn_tls as tls

        base = tls.peer_url(lan_ip, DTN_LAN_WEB_PORT)
        try:
            register_dtn_peer(
                base_url=base,
                node_id=str(row["device_id"] or ""),
                source="lan",
            )
            discovered += 1
        except ValueError:
            continue

    peers = list_dtn_peers(limit=30)
    return {
        "ok": True,
        "discovered": discovered,
        "mdns": mdns_result,
        "peers": peers.get("peers") or [],
    }


def list_dtn_peers(*, limit: int = 30) -> Dict[str, Any]:
    init_dtn_db()
    cutoff = _now() - max(DTN_PEER_TTL_SEC, 3600)
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT peer_id, node_id, base_url, region, source, last_seen
            FROM dtn_peers
            WHERE last_seen >= ?
            ORDER BY last_seen DESC
            LIMIT ?
            """,
            (cutoff, max(1, int(limit))),
        ).fetchall()
    return {"ok": True, "peers": [dict(r) for r in rows]}


def expire_stale_queue_items() -> Dict[str, Any]:
    init_dtn_db()
    now = _now()
    with _conn() as conn:
        cur = conn.execute(
            """
            UPDATE dtn_forward_queue
            SET status = 'expired'
            WHERE status = 'pending' AND expires_at > 0 AND expires_at < ?
            """,
            (now,),
        )
        expired = int(cur.rowcount)
    return {"ok": True, "expired": expired}


def compact_forward_queue() -> Dict[str, Any]:
    """Prune delivered rows and dedupe pending bundles by SHA256."""
    init_dtn_db()
    now = _now()
    cutoff = now - DTN_COMPACT_DELIVERED_SEC
    removed_delivered = 0
    deduped = 0
    files_removed = 0

    with _conn() as conn:
        old = conn.execute(
            """
            SELECT bundle_id, file_path FROM dtn_forward_queue
            WHERE status = 'delivered' AND delivered_at > 0 AND delivered_at < ?
            """,
            (cutoff,),
        ).fetchall()
        for row in old:
            path = str(row["file_path"])
            if os.path.isfile(path):
                try:
                    os.remove(path)
                    files_removed += 1
                except OSError:
                    pass
        cur = conn.execute(
            """
            DELETE FROM dtn_forward_queue
            WHERE (status = 'delivered' AND delivered_at > 0 AND delivered_at < ?)
               OR status = 'expired'
            """,
            (cutoff,),
        )
        removed_delivered = int(cur.rowcount)

        dupes = conn.execute(
            """
            SELECT bundle_sha256, MIN(id) AS keep_id
            FROM dtn_forward_queue
            WHERE status = 'pending' AND bundle_sha256 != ''
            GROUP BY bundle_sha256
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        for dup in dupes:
            sha = str(dup["bundle_sha256"])
            keep_id = int(dup["keep_id"])
            extras = conn.execute(
                """
                SELECT id, file_path FROM dtn_forward_queue
                WHERE bundle_sha256 = ? AND status = 'pending' AND id != ?
                """,
                (sha, keep_id),
            ).fetchall()
            for ex in extras:
                path = str(ex["file_path"])
                if os.path.isfile(path):
                    try:
                        os.remove(path)
                        files_removed += 1
                    except OSError:
                        pass
                conn.execute("DELETE FROM dtn_forward_queue WHERE id = ?", (int(ex["id"]),))
                deduped += 1

    return {
        "ok": True,
        "removed_delivered": removed_delivered,
        "deduped_pending": deduped,
        "files_removed": files_removed,
    }


def flush_forward_queue(
    *,
    upstream_url: str = "",
    limit: int = 3,
    force: bool = False,
    try_peers_first: bool = True,
) -> Dict[str, Any]:
    """Push pending bundles upstream (respects flush windows unless force=True)."""
    init_dtn_db()
    if not force and not is_flush_window_open():
        return {
            "ok": True,
            "skipped": True,
            "reason": "outside DTN flush window",
            "flush_window": flush_window_status(),
            "delivered": 0,
        }

    upstream = (upstream_url or DTN_UPSTREAM_URL).rstrip("/")
    targets: List[str] = []
    if try_peers_first:
        for peer in (list_dtn_peers(limit=10).get("peers") or []):
            targets.append(str(peer.get("base_url") or ""))
    if upstream not in targets:
        targets.append(upstream)

    delivered = 0
    errors: List[Dict[str, Any]] = []
    now = _now()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT id, bundle_id, file_path, hop_count, retry_count, max_hops
            FROM dtn_forward_queue
            WHERE status = 'pending'
              AND (next_retry_at <= ? OR next_retry_at = 0)
              AND (expires_at = 0 OR expires_at >= ?)
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (now, now, max(1, int(limit))),
        ).fetchall()

    for row in rows:
        path = str(row["file_path"])
        bundle_id = str(row["bundle_id"])
        hops = int(row["hop_count"] or 0)
        retries = int(row["retry_count"] or 0)
        max_hops = int(row["max_hops"] or DTN_MAX_HOPS)

        if hops >= max_hops:
            with _conn() as conn:
                conn.execute(
                    "UPDATE dtn_forward_queue SET status = 'failed' WHERE bundle_id = ?",
                    (bundle_id,),
                )
            errors.append({"bundle_id": bundle_id, "error": "max hops exceeded"})
            continue
        if not os.path.isfile(path):
            errors.append({"bundle_id": bundle_id, "error": "file missing"})
            continue

        with open(path, "rb") as fh:
            raw = fh.read()

        success = False
        last_err = ""
        for target in targets:
            if not target:
                continue
            try:
                _push_bundle_to_url(raw, base_url=target, bundle_id=bundle_id)
                with _conn() as conn:
                    conn.execute(
                        """
                        UPDATE dtn_forward_queue
                        SET status = 'delivered', delivered_at = ?, hop_count = hop_count + 1,
                            last_attempt_at = ?
                        WHERE bundle_id = ?
                        """,
                        (now, now, bundle_id),
                    )
                delivered += 1
                success = True
                break
            except Exception as exc:
                last_err = str(exc)

        if not success:
            errors.append({"bundle_id": bundle_id, "error": last_err or "all targets failed"})
            with _conn() as conn:
                _schedule_retry(conn, bundle_id=bundle_id, retry_count=retries + 1)

    return {
        "ok": True,
        "upstream": upstream,
        "targets_tried": targets,
        "delivered": delivered,
        "errors": errors,
        "flush_window_open": is_flush_window_open(),
        "remaining": list_pending_forwards(limit=1).get("pending_count", 0),
    }


def replication_heal(*, region: str = "", limit: int = 10) -> Dict[str, Any]:
    """Queue minimal DTN bundles for chunks under regional quorum."""
    init_dtn_db()
    reg = (region or DTN_DEFAULT_REGION).strip()[:32]
    update_region_quorum(region=reg)
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT chunk_hash FROM dtn_region_quorum
            WHERE region = ? AND satisfied = 0
            ORDER BY providers_found ASC
            LIMIT ?
            """,
            (reg, max(1, int(limit))),
        ).fetchall()
    if not rows:
        return {"ok": True, "region": reg, "heal_queued": 0, "reason": "all chunks at quorum"}

    hashes = [str(r["chunk_hash"]) for r in rows]
    blob, _filename, meta = build_minimal_chunk_bundle(
        chunk_hashes=hashes,
        node_id=os.environ.get("DTN_NODE_ID", "heal-coordinator"),
        region=reg,
    )
    meta["target_chunks"] = hashes
    queued = queue_bundle_for_forward(
        blob,
        node_id=str(meta.get("node_id") or "heal"),
        region=reg,
        meta=meta,
    )
    return {
        "ok": True,
        "region": reg,
        "under_quorum_chunks": len(hashes),
        "heal_queued": 0 if queued.get("duplicate") else 1,
        "queue": queued,
    }


def _load_alert_state(conn, alert_key: str) -> Dict[str, int]:
    row = conn.execute(
        "SELECT last_value, last_alert_at, last_cleared_at FROM dtn_alert_state WHERE alert_key = ?",
        (alert_key,),
    ).fetchone()
    if not row:
        return {"last_value": 0, "last_alert_at": 0, "last_cleared_at": 0}
    return {
        "last_value": int(row["last_value"]),
        "last_alert_at": int(row["last_alert_at"]),
        "last_cleared_at": int(row["last_cleared_at"]),
    }


def _save_alert_state(
    conn,
    *,
    alert_key: str,
    last_value: int,
    last_alert_at: int,
    last_cleared_at: int,
) -> None:
    conn.execute(
        """
        INSERT INTO dtn_alert_state (alert_key, last_value, last_alert_at, last_cleared_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(alert_key) DO UPDATE SET
            last_value = excluded.last_value,
            last_alert_at = excluded.last_alert_at,
            last_cleared_at = excluded.last_cleared_at
        """,
        (alert_key, last_value, last_alert_at, last_cleared_at),
    )


def _emit_dtn_alert(event: Dict[str, Any]) -> None:
    if not DTN_ALERT_WEBHOOK_URL:
        return
    try:
        requests.post(DTN_ALERT_WEBHOOK_URL, json=event, timeout=15)
    except Exception:
        pass


def check_forward_alerts(*, notify: bool = True) -> Dict[str, Any]:
    """Raise alerts when failed/pending forward queues exceed thresholds."""
    init_dtn_db()
    counts = list_pending_forwards(limit=1)
    failed = int(counts.get("failed_count") or 0)
    pending = int(counts.get("pending_count") or 0)
    now = _now()
    node_id = os.environ.get("DTN_NODE_ID", "dtn-node")
    active: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []

    checks = (
        ("failed_forwards", failed, DTN_ALERT_FAILED_THRESHOLD, "warning"),
        ("pending_forwards", pending, DTN_ALERT_PENDING_THRESHOLD, "info"),
    )

    with _conn() as conn:
        for key, value, threshold, severity in checks:
            if threshold <= 0:
                continue
            state = _load_alert_state(conn, key)
            firing = value >= threshold
            cooldown_ok = (now - state["last_alert_at"]) >= DTN_ALERT_COOLDOWN_SEC
            if firing:
                active.append(
                    {
                        "key": key,
                        "value": value,
                        "threshold": threshold,
                        "severity": severity,
                    }
                )
                if notify and cooldown_ok and value != state["last_value"]:
                    event = {
                        "ok": True,
                        "source": "bloodstone-dtn",
                        "alert": key,
                        "severity": severity,
                        "value": value,
                        "threshold": threshold,
                        "node_id": node_id,
                        "ts": now,
                    }
                    events.append(event)
                    _emit_dtn_alert(event)
                    _save_alert_state(
                        conn,
                        alert_key=key,
                        last_value=value,
                        last_alert_at=now,
                        last_cleared_at=state["last_cleared_at"],
                    )
                elif firing:
                    _save_alert_state(
                        conn,
                        alert_key=key,
                        last_value=value,
                        last_alert_at=state["last_alert_at"],
                        last_cleared_at=state["last_cleared_at"],
                    )
            elif state["last_value"] >= threshold:
                _save_alert_state(
                    conn,
                    alert_key=key,
                    last_value=value,
                    last_alert_at=state["last_alert_at"],
                    last_cleared_at=now,
                )

    return {
        "ok": True,
        "active": active,
        "failed_forwards": failed,
        "pending_forwards": pending,
        "thresholds": {
            "failed": DTN_ALERT_FAILED_THRESHOLD,
            "pending": DTN_ALERT_PENDING_THRESHOLD,
        },
        "cooldown_sec": DTN_ALERT_COOLDOWN_SEC,
        "webhook_configured": bool(DTN_ALERT_WEBHOOK_URL),
        "events_emitted": len(events),
    }


def alerts_payload() -> Dict[str, Any]:
    from chain_mesh import dtn_tls as tls

    status = check_forward_alerts(notify=False)
    return {
        "ok": True,
        "alerts": status.get("active") or [],
        "alert_count": len(status.get("active") or []),
        "failed_forwards": status.get("failed_forwards", 0),
        "pending_forwards": status.get("pending_forwards", 0),
        "thresholds": status.get("thresholds") or {},
        "cooldown_sec": DTN_ALERT_COOLDOWN_SEC,
        "webhook_configured": bool(DTN_ALERT_WEBHOOK_URL),
        "tls": tls.tls_status(),
    }


def upkeep_dtn(*, force_flush: bool = False) -> Dict[str, Any]:
    """Unified DTN hardening cycle — expire, compact, discover peers, gossip, quorum, flush."""
    expired = expire_stale_queue_items()
    compact = compact_forward_queue()
    peers = discover_dtn_peers()
    gossip = None
    try:
        from chain_mesh import dtn_gossip as gossip_mod

        if gossip_mod.GOSSIP_ENABLE:
            gossip = gossip_mod.gossip_round()
    except Exception as exc:
        gossip = {"ok": False, "error": str(exc)}
    starlink = None
    try:
        from chain_mesh import dtn_starlink as starlink_mod

        if starlink_mod.STARLINK_ENABLE:
            starlink = starlink_mod.starlink_handoff()
    except Exception as exc:
        starlink = {"ok": False, "error": str(exc)}
    quorum = update_region_quorum()
    planetary = None
    try:
        from chain_mesh import planetary_quorum as planetary_mod

        if planetary_mod.PLANETARY_ENABLE:
            planetary = planetary_mod.update_planetary_quorum()
    except Exception as exc:
        planetary = {"ok": False, "error": str(exc)}
    alerts = check_forward_alerts()
    heal = None
    auto_heal = os.environ.get("DTN_AUTO_HEAL", "1").strip() not in ("0", "false", "no")
    if auto_heal:
        heal = replication_heal(region=DTN_DEFAULT_REGION)
    planetary_heal = None
    if auto_heal:
        try:
            from chain_mesh import planetary_quorum as planetary_mod

            if planetary_mod.PLANETARY_ENABLE and planetary and not planetary.get("planetary_satisfied"):
                planetary_heal = planetary_mod.planetary_heal()
        except Exception as exc:
            planetary_heal = {"ok": False, "error": str(exc)}
    flush = None
    auto = os.environ.get("DTN_AUTO_FLUSH", "0").strip() in ("1", "true", "yes")
    if force_flush or auto:
        flush = flush_forward_queue(force=force_flush or not DTN_FLUSH_WINDOWS_UTC)
    return {
        "ok": True,
        "expired": expired,
        "compact": compact,
        "peers": {"discovered": peers.get("discovered", 0), "count": len(peers.get("peers") or [])},
        "gossip": gossip,
        "starlink": starlink,
        "quorum": {
            "chunks_checked": quorum.get("chunks_checked"),
            "chunks_satisfied": quorum.get("chunks_satisfied"),
        },
        "planetary": planetary,
        "heal": heal,
        "planetary_heal": planetary_heal,
        "alerts": alerts,
        "flush": flush,
        "flush_window": flush_window_status(),
        "pending": list_pending_forwards(limit=5).get("pending_count", 0),
    }


def update_region_quorum(
    *,
    region: str = "",
    chunk_hashes: Optional[List[str]] = None,
    quorum_n: int = 0,
    quorum_m: int = 0,
) -> Dict[str, Any]:
    """Self-healing scaffold — track N-of-M chunk presence per region."""
    init_dtn_db()
    reg = (region or DTN_DEFAULT_REGION).strip()[:32]
    n = int(quorum_n or DTN_QUORUM_N)
    m = int(quorum_m or DTN_QUORUM_M)
    hashes = [str(h).strip().lower() for h in (chunk_hashes or []) if str(h).strip()]
    if not hashes:
        providers.init_providers_db()
        with _conn() as conn:
            rows = conn.execute(
                "SELECT chunk_hash FROM mesh_chunk_providers GROUP BY chunk_hash LIMIT 200"
            ).fetchall()
        hashes = [str(r["chunk_hash"]) for r in rows]

    checked = 0
    satisfied = 0
    now = _now()
    details: List[Dict[str, Any]] = []
    for h in hashes:
        if len(h) != 64:
            continue
        peer_ids = providers.providers_for_chunk(h)
        found = len(peer_ids)
        ok = found >= n
        checked += 1
        if ok:
            satisfied += 1
        with _conn() as conn:
            conn.execute(
                """
                INSERT INTO dtn_region_quorum (
                    region, chunk_hash, providers_found, quorum_n, quorum_m,
                    satisfied, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(region, chunk_hash) DO UPDATE SET
                    providers_found = excluded.providers_found,
                    quorum_n = excluded.quorum_n,
                    quorum_m = excluded.quorum_m,
                    satisfied = excluded.satisfied,
                    updated_at = excluded.updated_at
                """,
                (reg, h, found, n, m, 1 if ok else 0, now),
            )
        details.append(
            {
                "chunk_hash": h,
                "providers_found": found,
                "quorum_n": n,
                "quorum_m": m,
                "satisfied": ok,
            }
        )

    return {
        "ok": True,
        "region": reg,
        "chunks_checked": checked,
        "chunks_satisfied": satisfied,
        "quorum": f"{n}-of-{m}",
        "details": details[:50],
    }


def replication_status(*, region: str = "") -> Dict[str, Any]:
    init_dtn_db()
    reg = (region or DTN_DEFAULT_REGION).strip()[:32]
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT chunk_hash, providers_found, quorum_n, quorum_m, satisfied, updated_at
            FROM dtn_region_quorum
            WHERE region = ?
            ORDER BY satisfied ASC, providers_found ASC
            LIMIT 100
            """,
            (reg,),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM dtn_region_quorum WHERE region = ?",
            (reg,),
        ).fetchone()["c"]
        unsatisfied = conn.execute(
            "SELECT COUNT(*) AS c FROM dtn_region_quorum WHERE region = ? AND satisfied = 0",
            (reg,),
        ).fetchone()["c"]
    return {
        "ok": True,
        "region": reg,
        "quorum_n": DTN_QUORUM_N,
        "quorum_m": DTN_QUORUM_M,
        "chunks_tracked": int(total),
        "chunks_under_quorum": int(unsatisfied),
        "samples": [dict(r) for r in rows[:20]],
    }


def _mdns_status_brief() -> Dict[str, Any]:
    try:
        from chain_mesh import mdns_discovery as mdns

        st = mdns.mdns_status()
        return {
            "enabled": st.get("enabled"),
            "service_type": st.get("service_type"),
            "zeroconf": st.get("zeroconf"),
            "avahi": st.get("avahi"),
        }
    except Exception as exc:
        return {"enabled": False, "error": str(exc)}


def _gossip_status_brief() -> Dict[str, Any]:
    try:
        from chain_mesh import dtn_gossip as gossip

        st = gossip.status_payload()
        return {
            "enabled": st.get("enabled"),
            "format": st.get("format"),
            "last_round": st.get("last_round") or {},
        }
    except Exception as exc:
        return {"enabled": False, "error": str(exc)}


def _ai_routing_status_brief() -> Dict[str, Any]:
    try:
        from chain_mesh import ai_routing as ai

        st = ai.status_payload()
        return {
            "enabled": ai.AI_ROUTING_ENABLE,
            "format": ai.AI_ROUTING_FORMAT,
            "providers_count": st.get("providers_count"),
            "uplink_stable": (st.get("uplink") or {}).get("uplink_stable"),
            "last_upkeep": st.get("last_upkeep") or {},
        }
    except Exception as exc:
        return {"enabled": False, "error": str(exc)}


def _planetary_status_brief() -> Dict[str, Any]:
    try:
        from chain_mesh import planetary_quorum as planetary

        st = planetary.status_payload()
        rollup = st.get("rollup") or {}
        return {
            "enabled": planetary.PLANETARY_ENABLE,
            "format": planetary.PLANETARY_FORMAT,
            "planetary_satisfied": rollup.get("planetary_satisfied"),
            "regions_total": rollup.get("regions_total"),
            "regions_under_quorum": rollup.get("regions_under_quorum"),
        }
    except Exception as exc:
        return {"enabled": False, "error": str(exc)}


def _starlink_status_brief() -> Dict[str, Any]:
    try:
        from chain_mesh import dtn_starlink as starlink

        st = starlink.status_payload()
        return {
            "enabled": st.get("enabled"),
            "format": st.get("format"),
            "last_connected": st.get("last_connected"),
            "last_handoff_delivered": st.get("last_handoff_delivered"),
            "probe_streak": st.get("probe_streak"),
        }
    except Exception as exc:
        return {"enabled": False, "error": str(exc)}


def status_payload() -> Dict[str, Any]:
    from chain_mesh import dtn_tls as tls

    init_dtn_db()
    pending = list_pending_forwards(limit=5)
    alert_status = check_forward_alerts(notify=False)
    with _conn() as conn:
        wm = conn.execute(
            "SELECT node_id, last_export_at, last_import_at, last_bundle_id FROM dtn_sync_watermarks LIMIT 10"
        ).fetchall()
    public = os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org").rstrip("/")
    fw = flush_window_status()
    return {
        "ok": True,
        "wave": "U",
        "hardened": True,
        "use_case": "off_grid_dtn_mesh",
        "format": DTN_BUNDLE_FORMAT,
        "sync_window_sec": DTN_SYNC_WINDOW_SEC,
        "sync_window_hours": round(DTN_SYNC_WINDOW_SEC / 3600, 1),
        "max_bundle_bytes": DTN_MAX_BUNDLE_BYTES,
        "bundle_ttl_sec": DTN_BUNDLE_TTL_SEC,
        "max_hops": DTN_MAX_HOPS,
        "max_retries": DTN_MAX_RETRIES,
        "default_region": DTN_DEFAULT_REGION,
        "quorum": f"{DTN_QUORUM_N}-of-{DTN_QUORUM_M}",
        "pending_forwards": pending.get("pending_count", 0),
        "failed_forwards": pending.get("failed_count", 0),
        "expired_forwards": pending.get("expired_count", 0),
        "flush_window": fw,
        "peer_count": len(list_dtn_peers(limit=50).get("peers") or []),
        "tls": tls.tls_status(),
        "alerts": {
            "active": alert_status.get("active") or [],
            "alert_count": len(alert_status.get("active") or []),
            "thresholds": alert_status.get("thresholds") or {},
            "webhook_configured": bool(DTN_ALERT_WEBHOOK_URL),
        },
        "mdns": _mdns_status_brief(),
        "gossip": _gossip_status_brief(),
        "starlink": _starlink_status_brief(),
        "planetary": _planetary_status_brief(),
        "ai_routing": _ai_routing_status_brief(),
        "watermarks": [dict(r) for r in wm],
        "apis": {
            "export": f"{public}/api/convergence/dtn/export",
            "import": f"{public}/api/convergence/dtn/import",
            "forward_pending": f"{public}/api/convergence/dtn/forward/pending",
            "forward_flush": f"{public}/api/convergence/dtn/forward/flush",
            "upkeep": f"{public}/api/convergence/dtn/upkeep",
            "peers": f"{public}/api/convergence/dtn/peers",
            "mdns": f"{public}/api/convergence/dtn/mdns/status",
            "mdns_browse": f"{public}/api/convergence/dtn/mdns/browse",
            "compact": f"{public}/api/convergence/dtn/compact",
            "replication_heal": f"{public}/api/convergence/dtn/replication/heal",
            "replication": f"{public}/api/convergence/dtn/replication/status",
            "alerts": f"{public}/api/convergence/dtn/alerts",
            "tls_status": f"{public}/api/convergence/dtn/tls/status",
            "gossip_exchange": f"{public}/api/convergence/dtn/gossip/exchange",
            "gossip_round": f"{public}/api/convergence/dtn/gossip/round",
            "gossip_status": f"{public}/api/convergence/dtn/gossip/status",
            "starlink_status": f"{public}/api/convergence/dtn/starlink/status",
            "starlink_probe": f"{public}/api/convergence/dtn/starlink/probe",
            "starlink_handoff": f"{public}/api/convergence/dtn/starlink/handoff",
            "planetary_status": f"{public}/api/convergence/dtn/planetary/status",
            "planetary_regions": f"{public}/api/convergence/dtn/planetary/regions",
            "planetary_heal": f"{public}/api/convergence/dtn/planetary/heal",
            "planetary_exchange": f"{public}/api/convergence/dtn/planetary/exchange",
        },
    }


def export_payload(
    *,
    node_id: str = "",
    since: Optional[int] = None,
    include_chunks: bool = True,
    region: str = "",
    queue_forward: bool = False,
    stone_address: str = "",
    blurt_author: str = "",
    tenant_id: str = "",
) -> Dict[str, Any]:
    from chain_mesh import depin_credits as depin

    addr = (stone_address or "").strip()
    author = (blurt_author or "").strip()
    if not author and addr:
        try:
            from chain_mesh import tenant_fleet_sync as tfleet

            author = tfleet.resolve_author_for_stone(addr, tenant_id=tenant_id)
        except Exception:
            author = ""
    if depin.ENFORCE_BANDWIDTH and addr:
        est = int(os.environ.get("DTN_BANDWIDTH_ESTIMATE_BYTES", str(DTN_MAX_BUNDLE_BYTES)))
        quota_check = depin.check_bandwidth_allowed(
            addr,
            est,
            blurt_author=author,
            tenant_id=tenant_id,
        )
        if not quota_check.get("allowed"):
            raise PermissionError(quota_check.get("reason") or "bandwidth quota exceeded")

    blob, filename, meta = build_dtn_bundle(
        node_id=node_id,
        since=since,
        include_chunks=include_chunks,
        region=region,
    )
    import base64

    if addr and len(blob) > 0:
        depin.record_bandwidth_usage(
            addr,
            delta_bytes=len(blob),
            blurt_author=author,
            tenant_id=tenant_id,
        )

    result: Dict[str, Any] = {
        "ok": True,
        "filename": filename,
        "meta": meta,
        "byte_size": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
    }
    if addr:
        result["bandwidth_quota"] = depin.bandwidth_quota(addr)
    if queue_forward:
        result["queued"] = queue_bundle_for_forward(
            blob, node_id=node_id, region=region, meta=meta
        )
    if len(blob) <= 4 * 1024 * 1024:
        result["data_b64"] = base64.b64encode(blob).decode("ascii")
    public = os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org").rstrip("/")
    result["download_url"] = (
        f"{public}/api/convergence/dtn/export/download"
        f"?node_id={meta.get('node_id', '')}&include_chunks={'1' if include_chunks else '0'}"
    )
    return result