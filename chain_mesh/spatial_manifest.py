"""Wave D — spatial WebXR manifests (assets/spatial/ + geo-anchored AR overlays)."""

from __future__ import annotations

import json
import math
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from chain_mesh import blurt_registry_v2 as blurt_reg
from chain_mesh import mesh_v2_lite as v2

SPATIAL_MANIFEST_ID = "bloodstone_spatial_manifest/v1"
VALID_FORMATS = frozenset({"glb", "gltf", "usdz", "usd"})
VALID_PLACEMENT = frozenset({"surface", "wall", "geo", "viewer"})

BLURT_RPC_NODES = blurt_reg.BLURT_RPC_NODES
REGISTRY_ACCOUNTS = blurt_reg.REGISTRY_ACCOUNTS


def _now() -> int:
    return int(time.time())


def _conn():
    from chain_mesh import db as mesh_db

    mesh_db.init_db()
    return mesh_db._conn()


def init_spatial_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bloodstone_spatial_manifests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scene_id TEXT NOT NULL,
                author TEXT NOT NULL DEFAULT '',
                post_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                asset_keys TEXT NOT NULL DEFAULT '[]',
                model_format TEXT NOT NULL DEFAULT 'glb',
                placement TEXT NOT NULL DEFAULT 'surface',
                scale_json TEXT NOT NULL DEFAULT '[1,1,1]',
                geo_lat REAL,
                geo_lon REAL,
                geo_alt_m REAL,
                geo_heading_deg REAL,
                geo_accuracy_m REAL,
                provenance_id TEXT NOT NULL DEFAULT '',
                manifest_json TEXT NOT NULL DEFAULT '{}',
                trx_id TEXT NOT NULL DEFAULT '',
                block_num INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                is_current INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_spatial_scene
                ON bloodstone_spatial_manifests(scene_id, is_current DESC);
            CREATE INDEX IF NOT EXISTS idx_spatial_geo
                ON bloodstone_spatial_manifests(geo_lat, geo_lon, is_current DESC);
            CREATE INDEX IF NOT EXISTS idx_spatial_post
                ON bloodstone_spatial_manifests(author, post_id, is_current DESC);
            """
        )


def spatial_asset_key(*, scene_id: str, filename: str = "model.glb") -> str:
    sid = re.sub(r"[^a-zA-Z0-9\-_]", "-", (scene_id or "").strip())[:64]
    fname = (filename or "model.glb").strip().lstrip("/")
    if ".." in fname:
        raise ValueError("invalid filename")
    return f"assets/spatial/{sid}/{fname}"


def _normalize_scale(raw: Any) -> List[float]:
    if isinstance(raw, (list, tuple)) and len(raw) >= 3:
        return [float(raw[0]), float(raw[1]), float(raw[2])]
    if isinstance(raw, (int, float)):
        v = float(raw)
        return [v, v, v]
    return [1.0, 1.0, 1.0]


def build_spatial_manifest(
    *,
    scene_id: str,
    author: str,
    asset_keys: List[str],
    title: str = "",
    post_id: str = "",
    model_format: str = "glb",
    placement: str = "surface",
    scale: Optional[List[float]] = None,
    geo: Optional[Dict[str, Any]] = None,
    provenance_id: str = "",
) -> Dict[str, Any]:
    """Layer 5+ — Blurt custom_json for spatial mesh assets."""
    sid = re.sub(r"[^a-zA-Z0-9\-_]", "-", (scene_id or "").strip())[:64]
    if not sid:
        raise ValueError("scene_id required")
    auth = (author or "").lstrip("@").lower()
    keys = [str(k).strip().lstrip("/") for k in asset_keys if str(k).strip()]
    if not keys:
        keys = [spatial_asset_key(scene_id=sid)]
    for key in keys:
        if not key.startswith("assets/spatial/"):
            raise ValueError(f"asset_key must be under assets/spatial/: {key}")
    fmt = (model_format or "glb").strip().lower()
    if fmt not in VALID_FORMATS:
        raise ValueError(f"model_format must be one of: {sorted(VALID_FORMATS)}")
    place = (placement or "surface").strip().lower()
    if place not in VALID_PLACEMENT:
        raise ValueError(f"placement must be one of: {sorted(VALID_PLACEMENT)}")

    body: Dict[str, Any] = {
        "v": "1",
        "scene_id": sid,
        "author": auth,
        "title": (title or sid)[:200],
        "asset_keys": keys,
        "model_format": fmt,
        "placement": place,
        "scale": _normalize_scale(scale),
        "mesh_spec": blurt_reg.RFC_VERSION,
        "published_at": _now(),
    }
    if post_id:
        body["post_id"] = str(post_id).strip()
    if provenance_id:
        body["provenance_id"] = provenance_id.strip()
    if geo:
        lat = geo.get("lat")
        lon = geo.get("lon")
        if lat is not None and lon is not None:
            body["geo"] = {
                "lat": float(lat),
                "lon": float(lon),
                "alt_m": float(geo.get("alt_m") or geo.get("alt") or 0),
                "heading_deg": float(geo.get("heading_deg") or geo.get("heading") or 0),
                "accuracy_m": float(geo.get("accuracy_m") or geo.get("accuracy") or 10),
            }

    return {
        "id": SPATIAL_MANIFEST_ID,
        "required_posting_auths": [auth] if auth else [],
        "required_auths": [],
        "json": json.dumps(body, separators=(",", ":"), sort_keys=True),
        "body": body,
    }


def index_spatial_manifest(
    *,
    body: Dict[str, Any],
    author: str = "",
    trx_id: str = "",
    block_num: int = 0,
) -> Dict[str, Any]:
    init_spatial_db()
    sid = str(body.get("scene_id") or "").strip()
    geo = body.get("geo") or {}
    now = _now()
    with _conn() as conn:
        conn.execute(
            "UPDATE bloodstone_spatial_manifests SET is_current = 0 WHERE scene_id = ?",
            (sid,),
        )
        cur = conn.execute(
            """
            INSERT INTO bloodstone_spatial_manifests (
                scene_id, author, post_id, title, asset_keys, model_format,
                placement, scale_json, geo_lat, geo_lon, geo_alt_m,
                geo_heading_deg, geo_accuracy_m, provenance_id,
                manifest_json, trx_id, block_num, created_at, is_current
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                sid,
                str(author or body.get("author") or "").lstrip("@").lower(),
                str(body.get("post_id") or ""),
                str(body.get("title") or ""),
                json.dumps(body.get("asset_keys") or []),
                str(body.get("model_format") or "glb"),
                str(body.get("placement") or "surface"),
                json.dumps(body.get("scale") or [1, 1, 1]),
                geo.get("lat"),
                geo.get("lon"),
                geo.get("alt_m"),
                geo.get("heading_deg"),
                geo.get("accuracy_m"),
                str(body.get("provenance_id") or ""),
                json.dumps(body),
                str(trx_id or ""),
                int(block_num),
                now,
            ),
        )
        return {"ok": True, "id": int(cur.lastrowid), "scene_id": sid}


def get_spatial_manifest(
    *,
    scene_id: str = "",
    author: str = "",
    post_id: str = "",
) -> Optional[Dict[str, Any]]:
    init_spatial_db()
    with _conn() as conn:
        if scene_id:
            row = conn.execute(
                """
                SELECT * FROM bloodstone_spatial_manifests
                WHERE scene_id = ? AND is_current = 1
                ORDER BY created_at DESC LIMIT 1
                """,
                (scene_id.strip(),),
            ).fetchone()
        elif author and post_id:
            row = conn.execute(
                """
                SELECT * FROM bloodstone_spatial_manifests
                WHERE author = ? AND post_id = ? AND is_current = 1
                ORDER BY created_at DESC LIMIT 1
                """,
                (author.lstrip("@").lower(), post_id.strip()),
            ).fetchone()
        else:
            return None
    if not row:
        return None
    item = dict(row)
    item["asset_keys"] = json.loads(item.get("asset_keys") or "[]")
    item["scale"] = json.loads(item.get("scale_json") or "[1,1,1]")
    item["body"] = json.loads(item.get("manifest_json") or "{}")
    if item.get("geo_lat") is not None and item.get("geo_lon") is not None:
        item["geo"] = {
            "lat": item["geo_lat"],
            "lon": item["geo_lon"],
            "alt_m": item.get("geo_alt_m"),
            "heading_deg": item.get("geo_heading_deg"),
            "accuracy_m": item.get("geo_accuracy_m"),
        }
    return item


def resolve_spatial_assets(body: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve mesh manifests for spatial asset keys."""
    keys = list(body.get("asset_keys") or [])
    public = os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org").rstrip("/")
    assets = []
    primary_url = ""
    for key in keys:
        resolved = v2.resolve_manifest(key)
        url = f"{public}/api/chain-mesh/asset/{key}/download"
        item = {
            "asset_key": key,
            "model_url": url,
            "ok": bool(resolved.get("ok")),
            "mime_type": str((resolved.get("manifest") or {}).get("mime_type") or "model/gltf-binary"),
        }
        if not resolved.get("ok"):
            item["error"] = resolved.get("error") or "not on mesh"
        elif not primary_url:
            primary_url = url
        assets.append(item)
    return {
        "ok": any(a.get("ok") for a in assets),
        "assets": assets,
        "primary_model_url": primary_url,
    }


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def overlay_query(
    *,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_m: float = 500,
    author: str = "",
    post_id: str = "",
    scene_id: str = "",
    limit: int = 20,
) -> Dict[str, Any]:
    """AR overlay — geo-radius search or Blurt post anchor lookup."""
    init_spatial_db()
    public = os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org").rstrip("/")

    if scene_id:
        one = get_spatial_manifest(scene_id=scene_id)
        rows = [one] if one else []
    elif author and post_id:
        one = get_spatial_manifest(author=author, post_id=post_id)
        rows = [one] if one else []
    elif lat is not None and lon is not None:
        with _conn() as conn:
            raw = conn.execute(
                """
                SELECT * FROM bloodstone_spatial_manifests
                WHERE is_current = 1 AND geo_lat IS NOT NULL AND geo_lon IS NOT NULL
                ORDER BY created_at DESC LIMIT 200
                """
            ).fetchall()
        rows = []
        for row in raw:
            item = dict(row)
            dist = _haversine_m(lat, lon, float(item["geo_lat"]), float(item["geo_lon"]))
            if dist <= float(radius_m):
                item["distance_m"] = round(dist, 1)
                rows.append(item)
        rows.sort(key=lambda r: r.get("distance_m", 1e9))
        rows = rows[: max(1, int(limit))]
    else:
        return {"ok": False, "error": "lat+lon, scene_id, or author+post_id required"}

    overlays = []
    for row in rows:
        body = json.loads(row.get("manifest_json") or "{}")
        resolved = resolve_spatial_assets(body)
        overlays.append(
            {
                "scene_id": row.get("scene_id"),
                "author": row.get("author"),
                "post_id": row.get("post_id"),
                "title": row.get("title"),
                "geo": body.get("geo"),
                "distance_m": row.get("distance_m"),
                "placement": row.get("placement"),
                "model_format": row.get("model_format"),
                "primary_model_url": resolved.get("primary_model_url"),
                "mesh_resolved": resolved.get("ok"),
                "embed_url": f"{public}/convergence/spatial/{row.get('author')}/{row.get('scene_id')}",
                "overlay_api": f"{public}/api/convergence/spatial/overlay?scene_id={row.get('scene_id')}",
            }
        )

    return {
        "ok": True,
        "use_case": "spatial_web_ar_vr",
        "query": {
            "lat": lat,
            "lon": lon,
            "radius_m": radius_m if lat is not None else None,
            "author": author or None,
            "post_id": post_id or None,
            "scene_id": scene_id or None,
        },
        "count": len(overlays),
        "overlays": overlays,
    }


def manifest_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    asset_keys = payload.get("asset_keys") or []
    if not asset_keys and payload.get("filename"):
        asset_keys = [
            spatial_asset_key(
                scene_id=str(payload.get("scene_id") or ""),
                filename=str(payload.get("filename") or "model.glb"),
            )
        ]
    custom = build_spatial_manifest(
        scene_id=str(payload.get("scene_id") or ""),
        author=str(payload.get("author") or ""),
        asset_keys=list(asset_keys),
        title=str(payload.get("title") or ""),
        post_id=str(payload.get("post_id") or ""),
        model_format=str(payload.get("model_format") or "glb"),
        placement=str(payload.get("placement") or "surface"),
        scale=payload.get("scale"),
        geo=payload.get("geo"),
        provenance_id=str(payload.get("provenance_id") or ""),
    )
    body = custom["body"]
    index_spatial_manifest(body=body, author=body.get("author", ""))
    resolved = resolve_spatial_assets(body)
    public = os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org").rstrip("/")
    return {
        "ok": True,
        "layer": 5,
        "wave": "D",
        "blurt_custom_json": {
            "id": custom["id"],
            "required_posting_auths": custom.get("required_posting_auths") or [],
            "json": custom["json"],
        },
        "body": body,
        "assets": resolved,
        "embed_url": f"{public}/convergence/spatial/{body.get('author')}/{body.get('scene_id')}",
        "overlay_url": f"{public}/api/convergence/spatial/overlay?scene_id={body.get('scene_id')}",
        "next_steps": [
            "Publish glTF/USD model to mesh at asset_keys path",
            f"Broadcast {SPATIAL_MANIFEST_ID} custom_json on Blurt",
            "Open embed_url in WebXR-capable browser or paste spatial embed_html",
        ],
    }


def _parse_spatial_op(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if str(data.get("v") or "") != "1":
        return None
    sid = str(data.get("scene_id") or "").strip()
    keys = data.get("asset_keys") or []
    if not sid or not keys:
        return None
    return data


def _blurt_rpc(method: str, params: List[Any]) -> Any:
    last_err = None
    for node in BLURT_RPC_NODES:
        try:
            resp = requests.post(
                node,
                json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
                timeout=20,
            )
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("error"):
                raise RuntimeError(payload["error"])
            return payload.get("result")
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"Blurt RPC failed: {last_err}")


def sync_account_spatial(account: str, *, limit: int = 200) -> Dict[str, Any]:
    init_spatial_db()
    acct = (account or "").lstrip("@").lower()
    history = _blurt_rpc(
        "database_api.get_account_history",
        [acct, -1, limit, 1000000000],
    )
    indexed = 0
    for item in history or []:
        op = (item.get("op") or [])[1] if isinstance(item.get("op"), list) else {}
        if not isinstance(op, dict) or op.get("id") != SPATIAL_MANIFEST_ID:
            continue
        try:
            data = json.loads(op.get("json") or "{}")
        except json.JSONDecodeError:
            continue
        body = _parse_spatial_op(data)
        if not body:
            continue
        index_spatial_manifest(
            body=body,
            author=acct,
            trx_id=str(item.get("trx_id") or ""),
            block_num=int(item.get("block") or 0),
        )
        indexed += 1
    return {"ok": True, "account": acct, "indexed": indexed}


def sync_registry_spatial() -> Dict[str, Any]:
    results = []
    for acct in REGISTRY_ACCOUNTS:
        try:
            results.append(sync_account_spatial(acct))
        except Exception as exc:
            results.append({"ok": False, "account": acct, "error": str(exc)})
    return {"ok": True, "accounts": results}