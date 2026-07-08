"""Search published mesh assets — fetch only matching files, not the full catalog."""

import fnmatch
import re
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db

_TOKEN_RE = re.compile(r"[a-z0-9_./+-]+", re.IGNORECASE)


def _has_glob_syntax(query: str) -> bool:
    return "*" in query or "?" in query


def glob_to_sql_like(pattern: str) -> str:
    """Translate shell-style glob wildcards to a SQL LIKE pattern (lowercase).

    ``*`` and ``?`` are glob wildcards; other characters (including ``_`` and ``%``)
    are matched literally and escaped for SQL LIKE.
    """
    out: List[str] = []
    for ch in (pattern or "").lower():
        if ch == "*":
            out.append("%")
        elif ch == "?":
            out.append("_")
        elif ch in ("%", "_"):
            out.append(f"\\{ch}")
        else:
            out.append(ch)
    return "".join(out)


def _tokens(query: str) -> List[str]:
    raw = (query or "").strip().lower()
    if not raw or _has_glob_syntax(raw):
        return []
    parts = _TOKEN_RE.findall(raw)
    return [p for p in parts if len(p) >= 2 or p.isdigit()]


def _glob_matches_asset(asset: Dict[str, Any], pattern: str) -> bool:
    key = str(asset.get("asset_key") or "")
    name = str(asset.get("display_name") or "")
    pat = (pattern or "").strip().lower()
    if not pat:
        return False
    if fnmatch.fnmatchcase(key.lower(), pat) or fnmatch.fnmatchcase(name.lower(), pat):
        return True
    base_key = key.rsplit("/", 1)[-1]
    base_name = name.rsplit("/", 1)[-1]
    return fnmatch.fnmatchcase(base_key.lower(), pat) or fnmatch.fnmatchcase(
        base_name.lower(), pat
    )


def _score_asset(asset: Dict[str, Any], tokens: List[str], raw_query: str) -> int:
    if not tokens:
        return 0
    key = str(asset.get("asset_key") or "").lower()
    name = str(asset.get("display_name") or "").lower()
    version = str(asset.get("version") or "").lower()
    mime = str(asset.get("mime_type") or "").lower()
    sha = str(asset.get("file_sha256") or "").lower()
    hay = f"{key} {name} {version} {mime} {sha}"
    q = raw_query.strip().lower()

    score = 0
    if q and key == q:
        score += 1000
    elif q and q in key:
        score += 400
    if q and q in name:
        score += 300
    for tok in tokens:
        if tok in key:
            score += 80
        if tok in name:
            score += 60
        if tok in version:
            score += 20
        if tok in mime:
            score += 15
        if tok in hay:
            score += 10
    return score


def search_assets(
    query: str,
    *,
    prefix: Optional[str] = None,
    mime_contains: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """Return mesh catalog rows matching query, ranked by relevance."""
    raw_query = (query or "").strip()
    use_glob = _has_glob_syntax(raw_query)
    tokens = _tokens(raw_query)
    prefix_norm = (prefix or "").strip()
    if prefix_norm and not prefix_norm.endswith("/"):
        prefix_norm += "/"

    rows = mesh_db.search_assets(
        tokens=tokens if not use_glob else None,
        glob_like=glob_to_sql_like(raw_query) if use_glob else None,
        prefix=prefix_norm or None,
        mime_contains=(mime_contains or "").strip().lower() or None,
        limit=max(limit * 4, 80) if (tokens or use_glob) else max(limit, 50),
        offset=0,
    )

    if use_glob:
        ranked = []
        for row in rows:
            if _glob_matches_asset(row, raw_query):
                ranked.append({**row, "relevance": 500})
        ranked.sort(
            key=lambda r: (
                -int(r.get("relevance") or 0),
                -int(r.get("created_at") or 0),
            )
        )
        total = len(ranked)
        page = ranked[offset : offset + limit]
    elif tokens:
        ranked = []
        for row in rows:
            s = _score_asset(row, tokens, raw_query)
            if s > 0:
                ranked.append({**row, "relevance": s})
        ranked.sort(
            key=lambda r: (
                -int(r.get("relevance") or 0),
                -int(r.get("created_at") or 0),
            )
        )
        total = len(ranked)
        page = ranked[offset : offset + limit]
    else:
        total = len(rows)
        page = rows[offset : offset + limit]
        for row in page:
            row["relevance"] = 0

    chunk_total = sum(int(r.get("chunk_count") or 0) for r in page)
    bytes_total = sum(int(r.get("file_size") or 0) for r in page)

    return {
        "ok": True,
        "query": (query or "").strip(),
        "prefix": prefix_norm or "",
        "count": len(page),
        "total_matches": total,
        "offset": max(0, int(offset)),
        "limit": max(1, min(int(limit), 200)),
        "selected_chunks": chunk_total,
        "selected_bytes": bytes_total,
        "results": page,
    }