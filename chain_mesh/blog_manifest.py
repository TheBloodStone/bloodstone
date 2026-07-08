"""Blurt-Bloodstone convergence — Layer 1 blogging manifests (pointer-only custom_json)."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

from chain_mesh import blurt_registry_v2 as blurt_reg
from chain_mesh import mesh_v2_lite as v2

POST_MANIFEST_ID = "bloodstone_post_manifest/v1"
ASSET_KEY_RE = re.compile(r"^assets/blurt/media/([a-z0-9\-_]+)/.+$", re.I)


def _now() -> int:
    return int(time.time())


def media_asset_key(*, post_id: str, filename: str) -> str:
    pid = re.sub(r"[^a-zA-Z0-9\-_]", "-", (post_id or "").strip())[:64]
    fname = (filename or "media").strip().lstrip("/")
    if ".." in fname or fname.startswith("/"):
        raise ValueError("invalid filename")
    return f"assets/blurt/media/{pid}/{fname}"


def build_post_manifest(
    *,
    post_id: str,
    author: str,
    asset_keys: List[str],
    title: str = "",
    permlink: str = "",
    blurt_url: str = "",
) -> Dict[str, Any]:
    """Layer 1 — small custom_json pointing at mesh assets (not blobs)."""
    keys = [str(k).strip().lstrip("/") for k in asset_keys if str(k).strip()]
    if not keys:
        raise ValueError("at least one asset_key required")
    for key in keys:
        if not key.startswith("assets/blurt/"):
            raise ValueError(f"asset_key must be under assets/blurt/: {key}")
    body = {
        "v": "1",
        "post_id": (post_id or "").strip(),
        "author": (author or "").lstrip("@").lower(),
        "permlink": (permlink or "").strip(),
        "title": (title or "")[:200],
        "asset_keys": keys,
        "mesh_spec": blurt_reg.RFC_VERSION,
        "published_at": _now(),
    }
    if blurt_url:
        body["blurt_url"] = blurt_url.strip()
    return {
        "id": POST_MANIFEST_ID,
        "required_posting_auths": [body["author"]] if body["author"] else [],
        "required_auths": [],
        "json": json.dumps(body, separators=(",", ":"), sort_keys=True),
        "body": body,
    }


def embed_playback_url(asset_key: str, public_root: Optional[str] = None) -> str:
    root = (public_root or os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    )).rstrip("/")
    key = (asset_key or "").strip().lstrip("/")
    return f"{root}/api/chain-mesh/asset/{key}/download"


def condenser_embed_html(asset_key: str, *, mime_type: str = "", public_root: Optional[str] = None) -> str:
    url = embed_playback_url(asset_key, public_root)
    mime = (mime_type or "").lower()
    if mime.startswith("video/"):
        return (
            f'<video controls preload="metadata" style="max-width:100%">'
            f'<source src="{url}" type="{mime or "video/mp4"}"></video>'
        )
    if mime.startswith("image/"):
        return f'<img src="{url}" alt="mesh asset" style="max-width:100%" loading="lazy" />'
    return f'<a href="{url}">Download mesh asset</a>'


def resolve_post_media(post_manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve all mesh manifests for a blog post."""
    keys = list(post_manifest.get("asset_keys") or [])
    media = []
    for key in keys:
        resolved = v2.resolve_manifest(key)
        item = {
            "asset_key": key,
            "playback_url": embed_playback_url(key),
            "ok": resolved.get("ok", False),
        }
        if resolved.get("ok"):
            manifest = resolved.get("manifest") or {}
            item["mime_type"] = manifest.get("mime_type")
            item["file_size"] = manifest.get("file_size")
            item["file_sha256"] = manifest.get("file_sha256")
            item["source"] = resolved.get("source")
            item["embed_html"] = condenser_embed_html(
                key, mime_type=str(manifest.get("mime_type") or "")
            )
        else:
            item["error"] = resolved.get("error")
        media.append(item)
    return {
        "ok": True,
        "post_id": post_manifest.get("post_id"),
        "author": post_manifest.get("author"),
        "media": media,
        "media_count": len(media),
        "resolved_count": sum(1 for m in media if m.get("ok")),
    }


def publish_post_flow_payload(
    *,
    post_id: str,
    author: str,
    filename: str,
    publish_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """End-to-end Layer 1+2 flow after partner publish."""
    asset_key = media_asset_key(post_id=post_id, filename=filename)
    post_json = build_post_manifest(
        post_id=post_id,
        author=author,
        asset_keys=[asset_key],
        permlink=post_id,
    )
    mesh = None
    if publish_result and publish_result.get("ok"):
        mesh = publish_result.get("v2_lite") or {}
    return {
        "ok": True,
        "layers": {
            "L1_blurt_custom_json": post_json,
            "L2_mesh_asset_key": asset_key,
            "L2_mesh_anchor": (publish_result or {}).get("v2_lite", {}).get("blurt_custom_json"),
        },
        "condenser_embed": condenser_embed_html(
            asset_key,
            mime_type=str((publish_result or {}).get("mime_type") or "video/mp4"),
        ),
        "next_steps": [
            "Broadcast bloodstone_post_manifest/v1 custom_json on Blurt (post body pointer)",
            "Broadcast chain_mesh_anchor custom_json from v2_lite (if not already)",
            "Embed condenser_embed HTML in post body for immediate playback",
            f"Playback URL: {embed_playback_url(asset_key)}",
        ],
        "mesh": mesh,
    }