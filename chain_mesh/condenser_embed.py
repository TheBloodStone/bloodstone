"""Blurt-Bloodstone Convergence — Layer 5 Local Condenser embed preview."""

from __future__ import annotations

import html
import os
from typing import Any, Dict, List, Optional

from chain_mesh import blog_manifest as blog


def embed_page_path(*, author: str, post_id: str, public_root: Optional[str] = None) -> str:
    root = (public_root or os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    )).rstrip("/")
    auth = (author or "").lstrip("@").lower()
    pid = (post_id or "").strip()
    return f"{root}/convergence/embed/{auth}/{pid}"


def _media_blocks(media_items: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for item in media_items:
        if not item.get("ok"):
            parts.append(
                f'<p class="mesh-error">Unavailable: {html.escape(str(item.get("asset_key") or ""))}'
                f' — {html.escape(str(item.get("error") or "not on mesh"))}</p>'
            )
            continue
        embed = item.get("embed_html") or blog.condenser_embed_html(
            str(item.get("asset_key") or ""),
            mime_type=str(item.get("mime_type") or ""),
        )
        parts.append(f'<figure class="mesh-asset">{embed}</figure>')
    if not parts:
        return '<p class="mesh-empty">No mesh media resolved for this post.</p>'
    return "\n".join(parts)


def _provenance_badge_html(
    media_items: Optional[List[Dict[str, Any]]] = None,
) -> str:
    keys = [
        str(item.get("asset_key") or "").strip()
        for item in (media_items or [])
        if item.get("ok") and item.get("asset_key")
    ]
    if not keys:
        return ""
    try:
        from chain_mesh import provenance as prov

        result = prov.verify_provenance(asset_key=keys[0])
        return str(result.get("badge_html") or "")
    except Exception:
        return ""


def standalone_page_html(
    *,
    post_id: str,
    author: str,
    title: str = "",
    media_items: Optional[List[Dict[str, Any]]] = None,
    public_root: Optional[str] = None,
    provenance_badge: str = "",
) -> str:
    """Minimal Pi-hostable Condenser embed page (Range-aware mesh playback)."""
    root = (public_root or os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    )).rstrip("/")
    safe_title = html.escape(title or post_id or "Bloodstone mesh post")
    safe_author = html.escape((author or "").lstrip("@"))
    body = _media_blocks(list(media_items or []))
    badge = provenance_badge or _provenance_badge_html(media_items)
    badge_row = f'<p class="provenance">{badge}</p>' if badge else ""
    page_url = embed_page_path(author=author, post_id=post_id, public_root=root)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title} · Blurt–Bloodstone</title>
  <meta name="robots" content="noindex">
  <link rel="canonical" href="{html.escape(page_url)}">
  <style>
    :root {{ color-scheme: dark; }}
    body {{
      margin: 0; font-family: system-ui, sans-serif;
      background: #0d1117; color: #e6edf3; line-height: 1.5;
    }}
    main {{ max-width: 960px; margin: 0 auto; padding: 1.25rem; }}
    h1 {{ font-size: 1.35rem; margin: 0 0 0.35rem; }}
    .meta {{ color: #8b949e; font-size: 0.9rem; margin-bottom: 1rem; }}
    .mesh-asset {{ margin: 1rem 0; }}
    .mesh-asset video, .mesh-asset img {{ max-width: 100%; border-radius: 8px; }}
    .mesh-error, .mesh-empty {{ color: #f85149; }}
    footer {{ margin-top: 2rem; font-size: 0.8rem; color: #6e7681; }}
    a {{ color: #58a6ff; }}
  </style>
</head>
<body>
  <main>
    <h1>{safe_title}</h1>
    <p class="meta">@{safe_author} · served from Chain Mesh · <a href="{html.escape(root)}/api/convergence/status">Convergence</a></p>
    {badge_row}
    {body}
    <footer>Blurt–Bloodstone Convergence Layer 5 preview — mesh playback with HTTP Range</footer>
  </main>
</body>
</html>"""


def embed_fragment_html(media_items: List[Dict[str, Any]]) -> str:
    """HTML fragment for pasting into Blurt Condenser post bodies."""
    return _media_blocks(media_items)


def embed_payload(
    *,
    post_id: str,
    author: str = "",
    asset_keys: Optional[List[str]] = None,
    title: str = "",
    permlink: str = "",
) -> Dict[str, Any]:
    keys = [str(k).strip().lstrip("/") for k in (asset_keys or []) if str(k).strip()]
    if not keys and post_id:
        keys = [blog.media_asset_key(post_id=post_id, filename="media.mp4")]
    if not keys:
        return {"ok": False, "error": "post_id or asset_keys required"}

    custom = blog.build_post_manifest(
        post_id=post_id or permlink,
        author=author,
        asset_keys=keys,
        title=title,
        permlink=permlink or post_id,
    )
    media = blog.resolve_post_media(custom["body"])
    items = list(media.get("media") or [])
    public_root = os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org")
    provenance = {}
    badge_html = ""
    primary_key = keys[0] if keys else ""
    if primary_key:
        try:
            from chain_mesh import provenance as prov

            provenance = prov.verify_provenance(asset_key=primary_key)
            badge_html = str(provenance.get("badge_html") or "")
        except Exception:
            provenance = {}

    return {
        "ok": True,
        "layer": 5,
        "post_id": custom["body"].get("post_id"),
        "author": custom["body"].get("author"),
        "title": custom["body"].get("title") or title,
        "media": media,
        "embed_html": embed_fragment_html(items),
        "provenance": provenance,
        "badge_html": badge_html,
        "page_html": standalone_page_html(
            post_id=str(custom["body"].get("post_id") or post_id),
            author=str(custom["body"].get("author") or author),
            title=str(custom["body"].get("title") or title),
            media_items=items,
            public_root=public_root,
            provenance_badge=badge_html,
        ),
        "page_url": embed_page_path(
            author=str(custom["body"].get("author") or author),
            post_id=str(custom["body"].get("post_id") or post_id),
            public_root=public_root,
        ),
        "blurt_custom_json": {
            "id": custom["id"],
            "required_posting_auths": custom.get("required_posting_auths") or [],
            "json": custom["json"],
        },
        "usage": {
            "condenser": "Paste embed_html into post body",
            "iframe": f'<iframe src="{{page_url}}" style="width:100%;min-height:360px;border:0" loading="lazy"></iframe>',
            "direct": [m.get("playback_url") for m in items if m.get("playback_url")],
        },
    }