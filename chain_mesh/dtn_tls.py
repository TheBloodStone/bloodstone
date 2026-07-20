"""DTN peer TLS — HTTPS bundle forwards between Pi nodes (self-signed LAN trust)."""

from __future__ import annotations

import ipaddress
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import requests

DTN_TLS_PEER = os.environ.get("DTN_TLS_PEER", "1").strip() not in ("0", "false", "no")
DTN_TLS_UPSTREAM = os.environ.get("DTN_TLS_UPSTREAM", "1").strip() not in ("0", "false", "no")
# H-01: default verify ON in production; set DTN_TLS_VERIFY=0 only for lab self-signed without CA.
DTN_TLS_VERIFY = os.environ.get("DTN_TLS_VERIFY", "1").strip() in ("1", "true", "yes")
DTN_TLS_CA_FILE = (os.environ.get("DTN_TLS_CA_FILE") or "").strip()
DTN_LAN_TLS_PORT = int(os.environ.get("DTN_LAN_TLS_PORT", "8443"))
DTN_LAN_WEB_PORT = int(os.environ.get("DTN_LAN_WEB_PORT", "8887"))
# Prefer TLS-only; HTTP fallback off by default (set DTN_TLS_FALLBACK_HTTP=1 for lab).
DTN_TLS_FALLBACK_HTTP = os.environ.get("DTN_TLS_FALLBACK_HTTP", "0").strip() not in (
    "0",
    "false",
    "no",
)
DTN_TLS_TIMEOUT_SEC = int(os.environ.get("DTN_TLS_TIMEOUT_SEC", "120"))

_SESSION: Optional[requests.Session] = None


def tls_verify_arg() -> Any:
    if not DTN_TLS_VERIFY:
        return False
    return DTN_TLS_CA_FILE or True


def get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        sess = requests.Session()
        sess.verify = tls_verify_arg()
        _SESSION = sess
    return _SESSION


def _host_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host.startswith("[") and host.endswith("]"):
        return host[1:-1]
    return host


def is_private_host(host: str) -> bool:
    h = (host or "").strip()
    if not h or h in ("localhost", "127.0.0.1", "::1"):
        return True
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", h):
        try:
            return ipaddress.ip_address(h).is_private
        except ValueError:
            return False
    if h.endswith(".local"):
        return True
    return False


def is_lan_peer_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = _host_from_url(url)
    if not host:
        return False
    if is_private_host(host):
        return True
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return False
    return port in (DTN_LAN_WEB_PORT, DTN_LAN_TLS_PORT)


def peer_url(
    host: str,
    port: int,
    *,
    tls: Optional[bool] = None,
    tls_port: Optional[int] = None,
) -> str:
    ip = (host or "").strip()
    if not ip or ip.endswith(".local"):
        return ""
    if ":" in ip and not ip.startswith("["):
        ip = ip.split("%", 1)[0]
    use_tls = DTN_TLS_PEER if tls is None else bool(tls)
    web_port = int(port or DTN_LAN_WEB_PORT)
    secure_port = int(tls_port if tls_port is not None else DTN_LAN_TLS_PORT)
    if use_tls:
        return f"https://{ip}:{secure_port}"
    return f"http://{ip}:{web_port}"


def normalize_peer_base_url(
    url: str,
    *,
    tls_hint: Optional[bool] = None,
    tls_port: Optional[int] = None,
) -> str:
    """Normalize peer base URL for DTN bundle push (LAN → HTTPS when enabled)."""
    raw = (url or "").strip().rstrip("/")
    if not raw.startswith("http"):
        return raw

    parsed = urlparse(raw)
    host = _host_from_url(raw)
    if not host:
        return raw

    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80

    use_tls = tls_hint
    if use_tls is None:
        if parsed.scheme == "https":
            use_tls = True
        elif is_lan_peer_url(raw):
            use_tls = DTN_TLS_PEER
        else:
            use_tls = DTN_TLS_UPSTREAM

    if use_tls and parsed.scheme == "http":
        secure_port = int(tls_port if tls_port is not None else DTN_LAN_TLS_PORT)
        if is_private_host(host) or port in (DTN_LAN_WEB_PORT, 80):
            port = secure_port
        scheme = "https"
    elif not use_tls and parsed.scheme == "https" and is_private_host(host):
        if port in (DTN_LAN_TLS_PORT, 443):
            port = DTN_LAN_WEB_PORT
        scheme = "http"
    else:
        scheme = parsed.scheme

    if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
        netloc = host
    else:
        netloc = f"{host}:{port}"

    return urlunparse((scheme, netloc, "", "", "", ""))


def forward_url_candidates(base_url: str) -> List[str]:
    """Return ordered URL bases to try when pushing a bundle (TLS first, optional HTTP fallback)."""
    primary = normalize_peer_base_url(base_url)
    if not primary:
        return []
    candidates = [primary]
    if DTN_TLS_FALLBACK_HTTP and primary.startswith("https://") and is_lan_peer_url(primary):
        parsed = urlparse(primary)
        host = _host_from_url(primary)
        port = parsed.port or 443
        if port != DTN_LAN_WEB_PORT:
            fallback = urlunparse(("http", f"{host}:{DTN_LAN_WEB_PORT}", "", "", "", ""))
            if fallback not in candidates:
                candidates.append(fallback)
    return candidates


def post_json(
    url: str,
    payload: Dict[str, Any],
    *,
    timeout: Optional[int] = None,
) -> requests.Response:
    return get_session().post(
        url,
        json=payload,
        timeout=timeout if timeout is not None else DTN_TLS_TIMEOUT_SEC,
    )


def tls_status() -> Dict[str, Any]:
    return {
        "ok": True,
        "peer_tls": DTN_TLS_PEER,
        "upstream_tls": DTN_TLS_UPSTREAM,
        "verify": DTN_TLS_VERIFY,
        "ca_file": DTN_TLS_CA_FILE or None,
        "lan_tls_port": DTN_LAN_TLS_PORT,
        "lan_web_port": DTN_LAN_WEB_PORT,
        "fallback_http": DTN_TLS_FALLBACK_HTTP,
        "timeout_sec": DTN_TLS_TIMEOUT_SEC,
    }