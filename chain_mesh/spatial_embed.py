"""Wave D — WebXR Condenser embed for spatial mesh assets."""

from __future__ import annotations

import html
import json
import os
from typing import Any, Dict, List, Optional

from chain_mesh import spatial_manifest as spatial


def spatial_page_path(*, author: str, scene_id: str, public_root: Optional[str] = None) -> str:
    root = (public_root or os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    )).rstrip("/")
    auth = (author or "").lstrip("@").lower()
    sid = (scene_id or "").strip()
    return f"{root}/convergence/spatial/{auth}/{sid}"


def _provenance_badge(asset_key: str) -> str:
    if not asset_key:
        return ""
    try:
        from chain_mesh import provenance as prov

        return str(prov.verify_provenance(asset_key=asset_key).get("badge_html") or "")
    except Exception:
        return ""


def webxr_page_html(
    *,
    scene_id: str,
    author: str,
    title: str = "",
    body: Optional[Dict[str, Any]] = None,
    resolved: Optional[Dict[str, Any]] = None,
    public_root: Optional[str] = None,
) -> str:
    """Pi-hostable WebXR / model-viewer spatial page."""
    root = (public_root or os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    )).rstrip("/")
    manifest_body = body or {}
    assets = list((resolved or {}).get("assets") or [])
    primary = (resolved or {}).get("primary_model_url") or ""
    if not primary and assets:
        primary = str(assets[0].get("model_url") or "")

    safe_title = html.escape(title or manifest_body.get("title") or scene_id)
    safe_author = html.escape((author or "").lstrip("@"))
    safe_model = html.escape(primary)
    page_url = spatial_page_path(author=author, scene_id=scene_id, public_root=root)

    geo = manifest_body.get("geo") or {}
    geo_line = ""
    if geo.get("lat") is not None:
        geo_line = (
            f'<p class="geo">📍 {geo.get("lat"):.5f}, {geo.get("lon"):.5f}'
            f' · placement: {html.escape(str(manifest_body.get("placement") or "surface"))}</p>'
        )

    scale = manifest_body.get("scale") or [1, 1, 1]
    scale_attr = html.escape(json.dumps(scale))
    fmt = html.escape(str(manifest_body.get("model_format") or "glb"))
    placement = html.escape(str(manifest_body.get("placement") or "surface"))

    primary_key = ""
    for a in assets:
        if a.get("ok"):
            primary_key = str(a.get("asset_key") or "")
            break
    badge = _provenance_badge(primary_key)
    badge_row = f'<p class="provenance">{badge}</p>' if badge else ""

    if not primary:
        viewer = '<p class="mesh-error">Spatial model not yet on mesh — publish glTF to asset_keys path.</p>'
    else:
        ios_src = ""
        if fmt == "usdz":
            ios_src = f'ios-src="{safe_model}"'
        viewer = f"""
    <model-viewer
      id="spatial-scene"
      src="{safe_model}"
      {ios_src}
      alt="{safe_title}"
      ar
      ar-modes="webxr scene-viewer quick-look"
      camera-controls
      touch-action="pan-y"
      shadow-intensity="1"
      exposure="1"
      style="width:100%;height:min(70vh,560px);background:#161b22;border-radius:12px;"
      data-placement="{placement}"
      data-scale='{scale_attr}'>
      <button slot="ar-button" style="position:absolute;bottom:16px;right:16px;padding:8px 14px;border-radius:8px;border:0;background:#238636;color:#fff;font-weight:600;cursor:pointer;">
        View in AR
      </button>
    </model-viewer>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title} · Spatial · Blurt–Bloodstone</title>
  <meta name="robots" content="noindex">
  <link rel="canonical" href="{html.escape(page_url)}">
  <script type="module" src="https://ajax.googleapis.com/ajax/libs/model-viewer/3.5.0/model-viewer.min.js"></script>
  <style>
    :root {{ color-scheme: dark; }}
    body {{
      margin: 0; font-family: system-ui, sans-serif;
      background: #0d1117; color: #e6edf3; line-height: 1.5;
    }}
    main {{ max-width: 960px; margin: 0 auto; padding: 1.25rem; }}
    h1 {{ font-size: 1.35rem; margin: 0 0 0.35rem; }}
    .meta, .geo {{ color: #8b949e; font-size: 0.9rem; margin-bottom: 0.75rem; }}
    .viewer-wrap {{ position: relative; margin: 1rem 0; }}
    .mesh-error {{ color: #f85149; }}
    footer {{ margin-top: 2rem; font-size: 0.8rem; color: #6e7681; }}
    a {{ color: #58a6ff; }}
  </style>
</head>
<body>
  <main>
    <h1>{safe_title}</h1>
    <p class="meta">@{safe_author} · spatial scene <code>{html.escape(scene_id)}</code> · <a href="{html.escape(root)}/api/convergence/status">Convergence</a></p>
    {geo_line}
    {badge_row}
    <div class="viewer-wrap">{viewer}</div>
    <footer>Blurt–Bloodstone Wave D — WebXR spatial embed (model-viewer + AR overlay)</footer>
  </main>
</body>
</html>"""


def embed_fragment_html(
    *,
    scene_id: str,
    author: str,
    title: str = "",
    page_url: str = "",
) -> str:
    """Condenser paste fragment — iframe to spatial WebXR page."""
    safe_url = html.escape(page_url)
    safe_title = html.escape(title or scene_id)
    return (
        f'<div class="bs-spatial-embed" data-scene="{html.escape(scene_id)}" '
        f'data-author="{html.escape((author or "").lstrip("@"))}">'
        f'<iframe src="{safe_url}" title="{safe_title}" '
        f'style="width:100%;min-height:420px;border:0;border-radius:12px" loading="lazy" '
        f'allow="xr-spatial-tracking; gyroscope; accelerometer"></iframe>'
        f'<p><a href="{safe_url}">Open spatial scene</a> · WebXR / AR</p></div>'
    )


def embed_payload(
    *,
    scene_id: str,
    author: str = "",
    title: str = "",
    post_id: str = "",
) -> Dict[str, Any]:
    row = spatial.get_spatial_manifest(scene_id=scene_id)
    if not row and author and post_id:
        row = spatial.get_spatial_manifest(author=author, post_id=post_id)
    if not row:
        built = spatial.manifest_payload(
            {
                "scene_id": scene_id,
                "author": author,
                "title": title,
                "post_id": post_id,
            }
        )
        body = built["body"]
        resolved = built.get("assets") or spatial.resolve_spatial_assets(body)
    else:
        body = row.get("body") or {}
        author = str(row.get("author") or author)
        title = str(row.get("title") or title)
        resolved = spatial.resolve_spatial_assets(body)

    public_root = os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org")
    page_url = spatial_page_path(
        author=author,
        scene_id=str(body.get("scene_id") or scene_id),
        public_root=public_root,
    )
    provenance = {}
    badge_html = ""
    assets = list(resolved.get("assets") or [])
    if assets and assets[0].get("asset_key"):
        try:
            from chain_mesh import provenance as prov

            provenance = prov.verify_provenance(asset_key=str(assets[0]["asset_key"]))
            badge_html = str(provenance.get("badge_html") or "")
        except Exception:
            provenance = {}

    return {
        "ok": True,
        "layer": 5,
        "wave": "D",
        "scene_id": body.get("scene_id") or scene_id,
        "author": author,
        "title": title or body.get("title"),
        "geo": body.get("geo"),
        "assets": resolved,
        "provenance": provenance,
        "badge_html": badge_html,
        "embed_html": embed_fragment_html(
            scene_id=str(body.get("scene_id") or scene_id),
            author=author,
            title=str(title or body.get("title") or ""),
            page_url=page_url,
        ),
        "page_html": webxr_page_html(
            scene_id=str(body.get("scene_id") or scene_id),
            author=author,
            title=str(title or body.get("title") or ""),
            body=body,
            resolved=resolved,
            public_root=public_root,
        ),
        "page_url": page_url,
        "overlay_url": f"{public_root.rstrip('/')}/api/convergence/spatial/overlay?scene_id={body.get('scene_id') or scene_id}",
        "usage": {
            "condenser": "Paste embed_html into Blurt post body",
            "ar": "Open page_url on mobile → tap View in AR",
            "geo": "Query overlay API with lat/lon for nearby scenes",
        },
    }