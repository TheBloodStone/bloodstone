"""Redirect helpers when Flask apps run behind nginx path prefixes."""

from typing import Optional

from flask import request, url_for


def prefixed_path(path: str, query: Optional[str] = None) -> str:
    root = (request.script_root or "").rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    url = f"{root}{path}" if root else path
    if query:
        url = f"{url}?{query}"
    return url


def safe_redirect_target(next_param: Optional[str], default_endpoint: str = "index") -> str:
    root = (request.script_root or "").rstrip("/")
    target = (next_param or "").strip()
    if not target:
        return url_for(default_endpoint)
    if target.startswith("//"):
        return url_for(default_endpoint)
    if root and not target.startswith(root):
        if target.startswith("/"):
            target = root + target
        else:
            return url_for(default_endpoint)
    return target