"""Wave J — offline-first Condenser fork: local feed + mesh playback without uplink."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from chain_mesh import blog_manifest as blog
from chain_mesh import db as mesh_db
from chain_mesh import store as chunk_store

OFFLINE_FORMAT = "bloodstone_condenser_offline/v1"
OFFLINE_ENABLE = os.environ.get("CONDENSER_OFFLINE_ENABLE", "1").strip() not in (
    "0",
    "false",
    "no",
)
BLURT_RPC_NODES = [
    n.strip()
    for n in os.environ.get(
        "BLURT_REGISTRY_RPC_NODES", "https://rpc.blurt.blog,https://blurt-rpc.saboin.com"
    ).split(",")
    if n.strip()
]
REGISTRY_ACCOUNTS = [
    a.strip().lstrip("@").lower()
    for a in os.environ.get(
        "BLURT_MESH_REGISTRY_ACCOUNTS", "megadrive,bloodstone"
    ).split(",")
    if a.strip()
]

_LAST_INDEX: Dict[str, Any] = {}


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def init_condenser_offline_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS condenser_offline_posts (
                post_key TEXT PRIMARY KEY,
                author TEXT NOT NULL DEFAULT '',
                post_id TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                asset_keys TEXT NOT NULL DEFAULT '[]',
                source TEXT NOT NULL DEFAULT 'local',
                playable_local INTEGER NOT NULL DEFAULT 0,
                manifest_json TEXT NOT NULL DEFAULT '{}',
                updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_condenser_offline_author
                ON condenser_offline_posts(author, updated_at DESC);
            """
        )


def _post_key(author: str, post_id: str) -> str:
    auth = (author or "").lstrip("@").lower()
    pid = (post_id or "").strip()
    return f"{auth}|{pid}"


def local_playback_url(asset_key: str) -> str:
    key = (asset_key or "").strip().lstrip("/")
    return f"/api/chain-mesh/asset/{key}/download"


def _asset_playable_local(asset_key: str) -> bool:
    from chain_mesh import blurt_registry_v2 as blurt_reg

    anchor = blurt_reg.get_anchor(asset_key)
    if not anchor:
        return False
    hashes = list(anchor.get("chunk_hashes") or [])
    if not hashes:
        return False
    return all(chunk_store.chunk_exists(h) for h in hashes[:3])


def offline_embed_html(asset_key: str, *, mime_type: str = "") -> str:
    url = local_playback_url(asset_key)
    mime = (mime_type or "").lower()
    if mime.startswith("video/"):
        return (
            f'<video controls preload="metadata" style="max-width:100%">'
            f'<source src="{url}" type="{mime or "video/mp4"}"></video>'
        )
    if mime.startswith("image/"):
        return f'<img src="{url}" alt="mesh asset" style="max-width:100%" loading="lazy" />'
    return f'<a href="{url}">Download mesh asset (offline)</a>'


def _upsert_post(
    *,
    author: str,
    post_id: str,
    title: str = "",
    asset_keys: Optional[List[str]] = None,
    source: str = "local",
    manifest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    init_condenser_offline_db()
    keys = [str(k).strip().lstrip("/") for k in (asset_keys or []) if str(k).strip()]
    playable = any(_asset_playable_local(k) for k in keys) if keys else False
    pk = _post_key(author, post_id)
    manifest_body = manifest or {
        "v": "1",
        "post_id": post_id,
        "author": author,
        "title": title,
        "asset_keys": keys,
    }
    now = _now()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO condenser_offline_posts (
                post_key, author, post_id, title, asset_keys, source,
                playable_local, manifest_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(post_key) DO UPDATE SET
                title = CASE WHEN excluded.title != '' THEN excluded.title ELSE title END,
                asset_keys = excluded.asset_keys,
                source = excluded.source,
                playable_local = excluded.playable_local,
                manifest_json = excluded.manifest_json,
                updated_at = excluded.updated_at
            """,
            (
                pk,
                (author or "").lstrip("@").lower(),
                (post_id or "").strip(),
                (title or "")[:200],
                json.dumps(keys),
                (source or "local")[:16],
                1 if playable else 0,
                json.dumps(manifest_body),
                now,
            ),
        )
    return {
        "post_key": pk,
        "author": author,
        "post_id": post_id,
        "asset_keys": keys,
        "playable_local": playable,
    }


def index_from_local_anchors() -> int:
    """Build offline feed entries from indexed mesh anchors under assets/blurt/media/."""
    from chain_mesh import blurt_registry_v2 as blurt_reg

    blurt_reg.init_blurt_registry_db()
    init_condenser_offline_db()
    grouped: Dict[str, Dict[str, Any]] = {}
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT asset_key, author, mime_type, created_at
            FROM blurt_mesh_anchors
            WHERE is_current = 1 AND asset_key LIKE 'assets/blurt/media/%'
            ORDER BY created_at DESC
            """
        ).fetchall()
    for row in rows:
        key = str(row["asset_key"] or "")
        match = blog.ASSET_KEY_RE.match(key)
        if not match:
            continue
        pid = match.group(1)
        author = str(row["author"] or "").lstrip("@").lower() or "unknown"
        pk = _post_key(author, pid)
        entry = grouped.setdefault(
            pk,
            {"author": author, "post_id": pid, "asset_keys": [], "title": pid},
        )
        if key not in entry["asset_keys"]:
            entry["asset_keys"].append(key)
    indexed = 0
    for entry in grouped.values():
        _upsert_post(
            author=entry["author"],
            post_id=entry["post_id"],
            title=entry["title"],
            asset_keys=entry["asset_keys"],
            source="local",
        )
        indexed += 1
    return indexed


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


def sync_post_manifests_from_blurt(*, account: str = "", limit: int = 200) -> Dict[str, Any]:
    """Scan Blurt account history for bloodstone_post_manifest/v1 ops."""
    init_condenser_offline_db()
    acct = (account or "").lstrip("@").lower()
    if not acct:
        return {"ok": False, "error": "account required"}
    history = _blurt_rpc(
        "database_api.get_account_history",
        [acct, -1, limit, 1000000000],
    )
    indexed = 0
    for entry in history or []:
        op = entry.get("op") or []
        if len(op) < 2 or op[0] != "custom_json":
            continue
        data = op[1] or {}
        if str(data.get("id") or "") != blog.POST_MANIFEST_ID:
            continue
        raw = data.get("json")
        try:
            body = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        except (json.JSONDecodeError, TypeError):
            continue
        if str(body.get("v") or "") != "1":
            continue
        author = str(body.get("author") or acct).lstrip("@").lower()
        post_id = str(body.get("post_id") or body.get("permlink") or "").strip()
        if not post_id:
            continue
        _upsert_post(
            author=author,
            post_id=post_id,
            title=str(body.get("title") or ""),
            asset_keys=list(body.get("asset_keys") or []),
            source="blurt",
            manifest=body,
        )
        indexed += 1
    return {"ok": True, "account": acct, "indexed": indexed}


def import_post_manifest_rows(rows: List[Dict[str, Any]]) -> int:
    imported = 0
    for row in rows:
        try:
            body = json.loads(row.get("manifest_json") or "{}")
        except json.JSONDecodeError:
            body = row
        if str(body.get("v") or "") != "1" and not body.get("post_id"):
            continue
        author = str(row.get("author") or body.get("author") or "").lstrip("@").lower()
        post_id = str(row.get("post_id") or body.get("post_id") or "").strip()
        if not author or not post_id:
            continue
        _upsert_post(
            author=author,
            post_id=post_id,
            title=str(row.get("title") or body.get("title") or ""),
            asset_keys=list(
                json.loads(row.get("asset_keys") or "[]")
                if isinstance(row.get("asset_keys"), str)
                else (row.get("asset_keys") or body.get("asset_keys") or [])
            ),
            source="dtn",
            manifest=body if body.get("post_id") else None,
        )
        imported += 1
    return imported


def collect_post_manifest_rows(*, since: int = 0) -> List[Dict[str, Any]]:
    init_condenser_offline_db()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT author, post_id, title, asset_keys, manifest_json, updated_at
            FROM condenser_offline_posts
            WHERE updated_at >= ?
            ORDER BY updated_at ASC
            """,
            (since,),
        ).fetchall()
    return [dict(r) for r in rows]


def index_offline_feed(*, sync_blurt: bool = True) -> Dict[str, Any]:
    if not OFFLINE_ENABLE:
        return {"ok": True, "skipped": True, "reason": "CONDENSER_OFFLINE_ENABLE off"}
    local_n = index_from_local_anchors()
    blurt_results: List[Dict[str, Any]] = []
    blurt_n = 0
    if sync_blurt:
        for acct in REGISTRY_ACCOUNTS:
            try:
                r = sync_post_manifests_from_blurt(account=acct)
                blurt_results.append(r)
                blurt_n += int(r.get("indexed") or 0)
            except Exception as exc:
                blurt_results.append({"ok": False, "account": acct, "error": str(exc)})
    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM condenser_offline_posts").fetchone()["c"]
        playable = conn.execute(
            "SELECT COUNT(*) AS c FROM condenser_offline_posts WHERE playable_local = 1"
        ).fetchone()["c"]
    result = {
        "ok": True,
        "format": OFFLINE_FORMAT,
        "indexed_local": local_n,
        "indexed_blurt": blurt_n,
        "posts_total": int(total),
        "posts_playable_local": int(playable),
        "blurt_accounts": blurt_results,
    }
    _LAST_INDEX.clear()
    _LAST_INDEX.update(result)
    return result


def list_feed(*, author: str = "", limit: int = 40) -> Dict[str, Any]:
    init_condenser_offline_db()
    clauses = ["1=1"]
    params: List[Any] = []
    if (author or "").strip():
        clauses.append("author = ?")
        params.append((author or "").lstrip("@").lower())
    params.append(max(1, int(limit)))
    with _conn() as conn:
        rows = conn.execute(
            f"""
            SELECT author, post_id, title, asset_keys, source, playable_local, updated_at
            FROM condenser_offline_posts
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    posts = []
    for row in rows:
        keys = json.loads(row["asset_keys"] or "[]")
        posts.append(
            {
                "author": row["author"],
                "post_id": row["post_id"],
                "title": row["title"] or row["post_id"],
                "asset_keys": keys,
                "source": row["source"],
                "playable_local": bool(row["playable_local"]),
                "offline_url": f"/convergence/offline/{row['author']}/{row['post_id']}",
                "updated_at": int(row["updated_at"]),
            }
        )
    return {
        "ok": True,
        "format": OFFLINE_FORMAT,
        "offline": True,
        "count": len(posts),
        "posts": posts,
    }


def resolve_offline_post(*, author: str, post_id: str) -> Dict[str, Any]:
    init_condenser_offline_db()
    pk = _post_key(author, post_id)
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM condenser_offline_posts WHERE post_key = ?",
            (pk,),
        ).fetchone()
    if not row:
        return {"ok": False, "error": "post not in offline feed — run index or import DTN bundle"}
    keys = json.loads(row["asset_keys"] or "[]")
    media = []
    for key in keys:
        from chain_mesh import mesh_v2_lite as v2

        resolved = v2.resolve_manifest(key)
        mime = ""
        if resolved.get("ok"):
            mime = str((resolved.get("manifest") or {}).get("mime_type") or "")
        playable = _asset_playable_local(key)
        media.append(
            {
                "asset_key": key,
                "ok": resolved.get("ok", False) or playable,
                "playable_local": playable,
                "playback_url": local_playback_url(key),
                "mime_type": mime,
                "embed_html": offline_embed_html(key, mime_type=mime),
                "error": None if playable or resolved.get("ok") else resolved.get("error"),
            }
        )
    return {
        "ok": True,
        "format": OFFLINE_FORMAT,
        "offline": True,
        "author": row["author"],
        "post_id": row["post_id"],
        "title": row["title"] or row["post_id"],
        "source": row["source"],
        "playable_local": bool(row["playable_local"]),
        "media": media,
        "page_url": f"/convergence/offline/{row['author']}/{row['post_id']}",
    }


def feed_page_html() -> str:
    public = os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org").rstrip(
        "/"
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Blurt–Bloodstone Offline Reader</title>
  <style>
    :root {{ color-scheme: dark; }}
    body {{ margin: 0; font-family: system-ui, sans-serif; background: #0d1117; color: #e6edf3; }}
    main {{ max-width: 720px; margin: 0 auto; padding: 1.25rem; }}
    h1 {{ font-size: 1.4rem; }}
    .badge {{ display: inline-block; background: #238636; color: #fff; font-size: 0.75rem;
      padding: 0.15rem 0.5rem; border-radius: 4px; margin-left: 0.5rem; }}
    ul {{ list-style: none; padding: 0; }}
    li {{ border: 1px solid #30363d; border-radius: 8px; margin: 0.75rem 0; padding: 0.85rem; }}
    li.offline-ready {{ border-color: #238636; }}
    a {{ color: #58a6ff; text-decoration: none; }}
    .meta {{ color: #8b949e; font-size: 0.85rem; }}
    #status {{ color: #8b949e; font-size: 0.9rem; margin-bottom: 1rem; }}
  </style>
</head>
<body>
  <main>
    <h1>Offline Condenser <span class="badge">Wave J</span></h1>
    <p id="status">Loading local feed…</p>
    <ul id="feed"></ul>
    <p class="meta">Served from this node — no Blurt uplink required when media chunks are local.
      <a href="{public}/api/convergence/status">Convergence status</a></p>
  </main>
  <script>
    fetch('/api/convergence/condenser/offline/feed')
      .then(r => r.json())
      .then(data => {{
        const ul = document.getElementById('feed');
        const st = document.getElementById('status');
        if (!data.ok || !data.posts || !data.posts.length) {{
          st.textContent = 'No offline posts indexed yet. Import a DTN bundle or run index.';
          return;
        }}
        st.textContent = data.count + ' post(s) · ' +
          data.posts.filter(p => p.playable_local).length + ' playable offline';
        ul.innerHTML = data.posts.map(p => `
          <li class="${{p.playable_local ? 'offline-ready' : ''}}">
            <a href="${{p.offline_url}}"><strong>${{p.title || p.post_id}}</strong></a>
            <div class="meta">@${{p.author}} · ${{p.playable_local ? 'offline ready' : 'metadata only'}} · ${{p.source}}</div>
          </li>`).join('');
      }})
      .catch(() => {{
        document.getElementById('status').textContent =
          'Feed unavailable — node may be fully offline without cached index.';
      }});
  </script>
</body>
</html>"""


def post_page_html(*, author: str, post_id: str) -> str:
    import html as html_mod

    post = resolve_offline_post(author=author, post_id=post_id)
    if not post.get("ok"):
        return f"<html><body><p>{html_mod.escape(post.get('error') or 'not found')}</p></body></html>"
    blocks = "\n".join(
        f'<figure class="mesh-asset">{m.get("embed_html") or ""}</figure>'
        for m in (post.get("media") or [])
        if m.get("embed_html")
    )
    safe_title = html_mod.escape(str(post.get("title") or post_id))
    safe_author = html_mod.escape(str(post.get("author") or ""))
    status = "offline playback ready" if post.get("playable_local") else "metadata only"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title} · Offline Condenser</title>
  <style>
    body {{ margin: 0; font-family: system-ui, sans-serif; background: #0d1117; color: #e6edf3; }}
    main {{ max-width: 960px; margin: 0 auto; padding: 1.25rem; }}
    .meta {{ color: #8b949e; }}
    video, img {{ max-width: 100%; border-radius: 8px; }}
    a {{ color: #58a6ff; }}
  </style>
</head>
<body>
  <main>
    <p><a href="/convergence/offline">← Offline feed</a></p>
    <h1>{safe_title}</h1>
    <p class="meta">@{safe_author} · {status} · Wave J offline Condenser</p>
    {blocks or '<p>No local media chunks for this post.</p>'}
  </main>
</body>
</html>"""


def status_payload() -> Dict[str, Any]:
    init_condenser_offline_db()
    public = os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org").rstrip(
        "/"
    )
    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM condenser_offline_posts").fetchone()["c"]
        playable = conn.execute(
            "SELECT COUNT(*) AS c FROM condenser_offline_posts WHERE playable_local = 1"
        ).fetchone()["c"]
    return {
        "ok": True,
        "format": OFFLINE_FORMAT,
        "enabled": OFFLINE_ENABLE,
        "posts_indexed": int(total),
        "posts_playable_local": int(playable),
        "last_index": dict(_LAST_INDEX),
        "apis": {
            "status": f"{public}/api/convergence/condenser/offline/status",
            "feed": f"{public}/api/convergence/condenser/offline/feed",
            "post": f"{public}/api/convergence/condenser/offline/post",
            "index": f"{public}/api/convergence/condenser/offline/index",
            "reader": f"{public}/convergence/offline",
        },
    }