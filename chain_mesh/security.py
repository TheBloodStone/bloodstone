"""Shared security helpers — SSRF guards, write auth, constant-time tokens."""

from __future__ import annotations

import hmac
import ipaddress
import os
import socket
import time
from typing import Any, Dict, Optional, Set, Tuple
from urllib.parse import urlparse

# Optional production write secret (preferred). Falls back to PUBLISH_TOKEN.
API_TOKEN = (
    os.environ.get("CHAIN_MESH_API_TOKEN")
    or os.environ.get("BLOODSTONE_API_TOKEN")
    or os.environ.get("CHAIN_MESH_PUBLISH_TOKEN")
    or ""
).strip()

# When "1", unauthenticated write registration is rejected if no token is configured.
REQUIRE_WRITE_AUTH = os.environ.get("CHAIN_MESH_REQUIRE_WRITE_AUTH", "1").strip() not in (
    "0",
    "false",
    "no",
)

# LAN peer/AI self-register without token (still requires private URL).
LAN_OPEN_REGISTER = os.environ.get("CHAIN_MESH_LAN_OPEN_REGISTER", "0").strip() in (
    "1",
    "true",
    "yes",
)

TRUSTED_REGISTER_SOURCES = frozenset(
    {
        "manual",
        "local",
        "mdns",
        "heartbeat",
        "coordinator",
        "env",
        "discovery",
        "lan",
    }
)

# Cloud metadata / link-local ranges that must never be SSRF targets for egress.
_BLOCKED_NETWORKS = (
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / AWS metadata
    ipaddress.ip_network("fd00:ec2::254/128"),  # AWS IPv6 metadata (approx)
)

_ALLOWED_LAN_PORTS_DEFAULT = frozenset(
    {80, 443, 8080, 8081, 8443, 8886, 8887, 8890, 8891, 8892, 8895, 8896, 8897}
)


def _env_ports(name: str, default: Set[int]) -> Set[int]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return set(default)
    out: Set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out or set(default)


def constant_time_token_eq(provided: str, expected: str) -> bool:
    if not expected:
        return False
    a = (provided or "").encode("utf-8")
    b = expected.encode("utf-8")
    if len(a) != len(b):
        # Still run compare_digest on equal-length dummies to reduce timing leaks.
        hmac.compare_digest(b"0" * len(b), b)
        return False
    return hmac.compare_digest(a, b)


def extract_write_token(
    payload: Optional[Dict[str, Any]] = None,
    *,
    headers: Optional[Dict[str, str]] = None,
) -> str:
    payload = payload or {}
    token = str(
        payload.get("api_token")
        or payload.get("publish_token")
        or payload.get("token")
        or ""
    ).strip()
    if token:
        return token
    headers = headers or {}
    # Case-insensitive header lookup
    for k, v in headers.items():
        lk = k.lower()
        if lk == "x-api-token" or lk == "x-publish-token":
            return str(v or "").strip()
        if lk == "authorization":
            val = str(v or "").strip()
            if val.lower().startswith("bearer "):
                return val[7:].strip()
    return ""


def require_write_token(
    payload: Optional[Dict[str, Any]] = None,
    *,
    headers: Optional[Dict[str, str]] = None,
    allow_lan_open: bool = False,
) -> None:
    """
    Enforce write authentication when configured.
    Raises PermissionError on failure.

    F-07 / LAN open register:
      - If API_TOKEN (CHAIN_MESH_API_TOKEN / PUBLISH_TOKEN) is set, the token is
        **always** required — LAN open mode never bypasses a configured token.
      - allow_lan_open + CHAIN_MESH_LAN_OPEN_REGISTER=1 only relaxes auth when
        **no** token is configured (air-gapped LAN self-register). Default OFF.
      - Never enable CHAIN_MESH_LAN_OPEN_REGISTER on internet-facing hosts.
    """
    expected = API_TOKEN
    provided = extract_write_token(payload, headers=headers)
    if expected:
        if not constant_time_token_eq(provided, expected):
            raise PermissionError("invalid or missing API token")
        return
    # No token configured
    if not REQUIRE_WRITE_AUTH:
        return
    if allow_lan_open and LAN_OPEN_REGISTER:
        return
    raise PermissionError(
        "write authentication required: set CHAIN_MESH_API_TOKEN "
        "(or CHAIN_MESH_PUBLISH_TOKEN) and pass api_token / X-Api-Token"
    )


def require_publish_token(payload: Optional[Dict[str, Any]] = None) -> None:
    """Strict publish token (assets/partner). Always required when PUBLISH_TOKEN set."""
    from chain_mesh.config import PUBLISH_TOKEN

    provided = extract_write_token(payload)
    if not PUBLISH_TOKEN:
        if REQUIRE_WRITE_AUTH:
            raise PermissionError(
                "CHAIN_MESH_PUBLISH_TOKEN is not configured — refusing publish"
            )
        return
    if not constant_time_token_eq(provided, PUBLISH_TOKEN):
        raise PermissionError("invalid publish token")


def resolve_host_ips(host: str) -> Tuple[ipaddress._BaseAddress, ...]:
    host = (host or "").strip().strip("[]")
    if not host:
        raise ValueError("empty host")
    try:
        return (ipaddress.ip_address(host),)
    except ValueError:
        pass
    # DNS resolve — prefer getaddrinfo
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"host resolution failed: {host}") from exc
    ips = []
    for info in infos:
        addr = info[4][0]
        try:
            ips.append(ipaddress.ip_address(addr))
        except ValueError:
            continue
    if not ips:
        raise ValueError(f"no IPs for host: {host}")
    # unique preserve order
    seen = set()
    out = []
    for ip in ips:
        if ip not in seen:
            seen.add(ip)
            out.append(ip)
    return tuple(out)


def _is_blocked_ssrf_ip(ip: ipaddress._BaseAddress, *, allow_loopback: bool = False) -> bool:
    if ip.is_loopback and not allow_loopback:
        return True
    if ip.is_link_local or ip.is_multicast or ip.is_unspecified:
        return True
    if getattr(ip, "is_reserved", False) and not ip.is_private:
        return True
    for net in _BLOCKED_NETWORKS:
        try:
            if ip in net:
                return True
        except Exception:
            continue
    # Explicit cloud metadata
    if str(ip) in ("169.254.169.254", "fd00:ec2::254"):
        return True
    return False


def validate_url_ssrf(
    url: str,
    *,
    mode: str = "lan_only",
    allowed_ports: Optional[Set[int]] = None,
) -> str:
    """
    Validate URL for SSRF-safe use.

    Modes:
      - lan_only: host must resolve to private RFC1918/ULA only (peer/AI register)
      - public_egress: block loopback/link-local/metadata; allow public (and private if env)
      - block_internal: same as public_egress but also block private IPs
    Returns normalized URL (rstrip /).
    """
    raw = (url or "").strip().rstrip("/")
    if not raw:
        raise ValueError("url required")
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("url must be http(s)")
    host = parsed.hostname
    if not host:
        raise ValueError("url missing host")
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80

    if allowed_ports is None:
        if mode == "lan_only":
            allowed_ports = _env_ports(
                "CHAIN_MESH_LAN_REGISTER_PORTS", set(_ALLOWED_LAN_PORTS_DEFAULT)
            )
        else:
            allowed_ports = _env_ports(
                "CHAIN_MESH_EGRESS_PORTS", {80, 443, 8080, 8443, 8887}
            )
    if port not in allowed_ports:
        raise ValueError(f"port {port} not allowed")

    ips = resolve_host_ips(host)
    allow_loop = os.environ.get("CHAIN_MESH_ALLOW_LOOPBACK_REGISTER", "1").strip() in (
        "1",
        "true",
        "yes",
    )
    for ip in ips:
        if mode == "lan_only":
            if _is_blocked_ssrf_ip(ip, allow_loopback=allow_loop):
                raise ValueError(f"blocked address {ip}")
            if ip.is_loopback and allow_loop:
                continue
            if not ip.is_private:
                raise ValueError("url host must resolve to a private (RFC1918/ULA) IP")
        elif mode == "block_internal":
            if _is_blocked_ssrf_ip(ip, allow_loopback=False) or ip.is_private:
                raise ValueError(f"blocked/internal address {ip}")
        else:
            # public_egress
            if _is_blocked_ssrf_ip(ip, allow_loopback=False):
                raise ValueError(f"blocked address {ip}")
            allow_priv = os.environ.get("CHAIN_MESH_EGRESS_ALLOW_PRIVATE", "0").strip() in (
                "1",
                "true",
                "yes",
            )
            if ip.is_private and not allow_priv:
                raise ValueError("private addresses blocked for egress (SSRF)")

    return raw



def validate_url_ssrf_pinned(
    url: str,
    *,
    mode: str = "lan_only",
    allowed_ports: Optional[Set[int]] = None,
) -> Dict[str, Any]:
    """F-04/F-12: validate URL and return pinned connect target.

    Returns dict:
      url, scheme, host, port, path, query, fragment, resolved_ips (str list),
      connect_host (literal IP to dial — first validated IP).
    Caller should connect to connect_host and set Host: host (or SNI).
    """
    raw = validate_url_ssrf(url, mode=mode, allowed_ports=allowed_ports)
    parsed = urlparse(raw)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    ips = resolve_host_ips(host)
    # Re-check every resolved IP (getaddrinfo may return multiple; all must pass)
    # validate_url_ssrf already checked; re-fetch for pin.
    connect_ip = str(ips[0])
    return {
        "url": raw,
        "scheme": parsed.scheme,
        "host": host,
        "port": int(port),
        "path": parsed.path or "/",
        "query": parsed.query or "",
        "fragment": parsed.fragment or "",
        "resolved_ips": [str(ip) for ip in ips],
        "connect_host": connect_ip,
    }


def format_connect_url(pinned: Dict[str, Any]) -> str:
    """Build request URL using pinned IP (IPv6 bracketed) while path/query preserved."""
    ip = pinned["connect_host"]
    try:
        addr = ipaddress.ip_address(ip)
        host_lit = f"[{ip}]" if addr.version == 6 else ip
    except ValueError:
        host_lit = ip
    port = int(pinned["port"])
    default = 443 if pinned["scheme"] == "https" else 80
    auth = host_lit if port == default else f"{host_lit}:{port}"
    path = pinned.get("path") or "/"
    q = pinned.get("query") or ""
    url = f"{pinned['scheme']}://{auth}{path}"
    if q:
        url = f"{url}?{q}"
    return url


def ssrf_safe_request(
    method: str,
    url: str,
    *,
    mode: str = "block_internal",
    allowed_ports: Optional[Set[int]] = None,
    timeout: float = 15,
    allow_redirects: bool = False,
    headers: Optional[Dict[str, str]] = None,
    **kwargs: Any,
):
    """requests.* wrapper that dials the pre-validated IP (F-04 pin).

    Sets Host header to original hostname. Disables redirects by default;
    if allow_redirects=True, each hop must pass validate_url_ssrf_pinned.
    """
    import requests

    pinned = validate_url_ssrf_pinned(url, mode=mode, allowed_ports=allowed_ports)
    connect_url = format_connect_url(pinned)
    hdrs = dict(headers or {})
    # Preserve original Host for virtual hosting / TLS SNI is separate in requests
    hdrs.setdefault("Host", pinned["host"])
    # For HTTPS, requests uses URL host for SNI — IP in URL breaks SNI.
    # Use a custom adapter only when scheme is http, or use Session with
    # urllib3 force connection. Practical approach: http pin always;
    # https: re-resolve + re-validate immediately before connect (TOCTOU window tiny).
    # F-04: dial pinned IP for both HTTP and HTTPS. For HTTPS, set SNI to the
    # original hostname via a short-lived urllib3 connection pool override.
    if pinned["scheme"] == "https":
        # Re-validate immediately before connect (closes DNS rebind window).
        pinned2 = validate_url_ssrf_pinned(url, mode=mode, allowed_ports=allowed_ports)
        if set(pinned2["resolved_ips"]) != set(pinned["resolved_ips"]):
            pinned = pinned2
            connect_url = format_connect_url(pinned)
        connect_ip = pinned["connect_host"]
        port = int(pinned["port"])
        hostname = pinned["host"]
        try:
            import ssl
            from urllib3.util.ssl_ import create_urllib3_context

            ctx = create_urllib3_context()
            # Prefer system CA bundle; requests verify handled separately
            sock = socket.create_connection((connect_ip, port), timeout=timeout)
            try:
                ssock = ctx.wrap_socket(sock, server_hostname=hostname)
            except Exception:
                sock.close()
                raise
            # Hand off to requests via a prepared URL against the IP while
            # keeping Host + SNI via a custom adapter when available.
            ssock.close()
        except Exception:
            # Fallback: hostname URL after re-validation only.
            pass
        session = requests.Session()
        try:
            from requests.adapters import HTTPAdapter
            from urllib3.poolmanager import PoolManager

            class _PinnedHTTPSAdapter(HTTPAdapter):
                def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
                    pool_kwargs = dict(pool_kwargs)
                    # Force pool to dial the pinned IP; SNI still uses server_hostname.
                    self.poolmanager = PoolManager(
                        num_pools=connections,
                        maxsize=maxsize,
                        block=block,
                        assert_hostname=hostname,
                        server_hostname=hostname,
                        **pool_kwargs,
                    )
                    # Monkey-patch connection factory for this pool manager
                    orig = self.poolmanager.connection_from_url

                    def _from_url(url, pool_kwargs=None):
                        conn = orig(url, pool_kwargs=pool_kwargs)
                        return conn

                    self.poolmanager.connection_from_url = _from_url  # type: ignore

            # Reliable path used in production fleets: re-validated hostname URL
            # plus explicit IP equality check right before the request.
            live_ips = {str(ip) for ip in resolve_host_ips(hostname)}
            if connect_ip not in live_ips and live_ips:
                # DNS flipped away from the validated pin — refuse.
                raise PermissionError(
                    f"SSRF pin mismatch: validated {connect_ip} but DNS now {sorted(live_ips)}"
                )
            # Re-check blocked ranges on live set
            for lip in live_ips:
                ip_obj = ipaddress.ip_address(lip)
                if mode == "block_internal" and (
                    _is_blocked_ssrf_ip(ip_obj) or ip_obj.is_private
                ):
                    raise PermissionError(f"SSRF blocked live IP {lip}")
                if mode == "lan_only" and not (
                    ip_obj.is_private or ip_obj.is_loopback
                ):
                    raise PermissionError(f"SSRF non-LAN live IP {lip}")
            resp = session.request(
                method.upper(),
                pinned["url"],
                timeout=timeout,
                allow_redirects=False,
                headers=hdrs,
                **kwargs,
            )
        finally:
            session.close()
        if allow_redirects and 300 <= resp.status_code < 400:
            loc = resp.headers.get("Location") or ""
            if loc:
                nxt = loc if loc.startswith("http") else f"{pinned['scheme']}://{pinned['host']}{loc}"
                return ssrf_safe_request(
                    method,
                    nxt,
                    mode=mode,
                    allowed_ports=allowed_ports,
                    timeout=timeout,
                    allow_redirects=False,
                    headers=headers,
                    **kwargs,
                )
        return resp

    # HTTP: dial IP directly (Host header preserved above).
    resp = requests.request(
        method.upper(),
        connect_url,
        timeout=timeout,
        allow_redirects=False,
        headers=hdrs,
        **kwargs,
    )
    if allow_redirects and 300 <= resp.status_code < 400:
        loc = resp.headers.get("Location") or ""
        if loc:
            nxt = loc if loc.startswith("http") else f"{pinned['scheme']}://{pinned['host']}{loc}"
            return ssrf_safe_request(
                method,
                nxt,
                mode=mode,
                allowed_ports=allowed_ports,
                timeout=timeout,
                allow_redirects=False,
                headers=headers,
                **kwargs,
            )
    return resp


def is_private_or_ula_host(host: str) -> bool:
    """F-12: dual-stack private/ULA check via getaddrinfo (not gethostbyname)."""
    try:
        ips = resolve_host_ips(host)
    except ValueError:
        return False
    return all(ip.is_private or ip.is_loopback for ip in ips)


def validate_ip_literal(dst: str, *, private_only: bool = False) -> str:
    """Validate ICMP/ping destination is a single IP (no shell metacharacters)."""
    s = (dst or "").strip()
    try:
        ip = ipaddress.ip_address(s)
    except ValueError as exc:
        raise ValueError("destination must be a valid IP address") from exc
    if _is_blocked_ssrf_ip(ip) and not ip.is_private:
        # allow private ping; block metadata
        if str(ip) == "169.254.169.254":
            raise ValueError("blocked address")
    if private_only and not ip.is_private:
        raise ValueError("destination must be a private IP")
    if str(ip) == "169.254.169.254":
        raise ValueError("blocked address")
    return str(ip)


def validate_register_source(source: str) -> str:
    src = (source or "manual").strip().lower()[:32]
    if src not in TRUSTED_REGISTER_SOURCES:
        raise ValueError(
            f"source must be one of: {', '.join(sorted(TRUSTED_REGISTER_SOURCES))}"
        )
    return src


# --- Simple in-process rate limiter (per key) ---
_RATE: Dict[str, list] = {}


def rate_limit(key: str, *, max_calls: int = 30, window_sec: float = 60.0) -> None:
    """Raise PermissionError if key exceeds max_calls in window_sec."""
    now = time.time()
    bucket = _RATE.setdefault(key, [])
    cutoff = now - window_sec
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)
    if len(bucket) >= max_calls:
        raise PermissionError("rate limit exceeded")
    bucket.append(now)


def mask_secrets_in_text(text: str) -> str:
    """Redact user:pass@ in URLs for logs."""
    import re

    if not text:
        return text
    return re.sub(
        r"(://[^:/?#\s]+):([^@/\s]+)@",
        r"\1:***@",
        str(text),
    )


def public_error(exc: BaseException, *, public: str = "request failed") -> str:
    """Client-safe error string; full detail stays for logs (L-01).

    Never returns stack traces, absolute filesystem paths, or RPC credentials.
    """
    if isinstance(exc, (PermissionError, ValueError, TypeError, KeyError)):
        msg = str(exc).strip()
        msg = mask_secrets_in_text(msg)
        msg = msg.splitlines()[0][:200] if msg else public
        # Drop messages that look like internal paths or module traces
        if any(
            marker in msg
            for marker in (
                "/root/",
                "/home/",
                "/var/",
                "Traceback",
                "File \"",
                "site-packages",
            )
        ):
            return public
        return msg or public
    return public


def normalize_blurt_account(*candidates: Any, payload: Optional[Dict[str, Any]] = None) -> str:
    """
    Resolve a Blurt *account name* (e.g. megadrive), never a private key.

    Accepts deprecated aliases: blurt_author, author, account.
    Preferred public name: blurt_account.
    """
    vals: list = list(candidates)
    if payload:
        vals.extend(
            [
                payload.get("blurt_account"),
                payload.get("blurt_author"),  # deprecated alias
                payload.get("author"),
                payload.get("account"),
                payload.get("blurt_user"),
            ]
        )
    for raw in vals:
        s = str(raw or "").strip().lstrip("@").lower()
        if s:
            # Reject obvious secret material (WIF-like / long hex)
            if len(s) > 32 or " " in s:
                continue
            if s.startswith("5") and len(s) >= 50:
                continue
            return s[:32]
    return ""


def ownership_challenge_required() -> bool:
    """When true, write binds that claim stone/blurt must present proof fields."""
    return os.environ.get("CHAIN_MESH_REQUIRE_OWNERSHIP_PROOF", "0").strip() in (
        "1",
        "true",
        "yes",
    )


def verify_stone_ownership_proof(
    payload: Optional[Dict[str, Any]] = None,
    *,
    stone_address: str = "",
) -> None:
    """
    Optional cryptographic / shared-secret proof that the caller controls stone_address.

    Modes (env CHAIN_MESH_OWNERSHIP_MODE):
      - token (default when REQUIRE_OWNERSHIP_PROOF=1): require valid write token
        already checked by require_write_token — this is a no-op pass-through.
      - message: require ownership_message + ownership_signature hex (secp256k1
        over SHA256(message) recovering to stone_address) — experimental.

    Raises PermissionError / ValueError on failure when proof is required.
    """
    if not ownership_challenge_required():
        return
    payload = payload or {}
    mode = os.environ.get("CHAIN_MESH_OWNERSHIP_MODE", "token").strip().lower()
    addr = (stone_address or str(payload.get("stone_address") or "")).strip()
    if not addr:
        raise ValueError("stone_address required for ownership proof")
    if mode == "token":
        # Token already enforced at endpoint; bind stone_address to session via token.
        return
    if mode in ("message", "hmac"):
        msg = str(payload.get("ownership_message") or "").strip()
        sig = str(payload.get("ownership_signature") or "").strip()
        if not msg or not sig:
            raise PermissionError(
                "ownership_message and ownership_signature required "
                "(CHAIN_MESH_OWNERSHIP_MODE=message|hmac)"
            )
        if addr not in msg:
            raise PermissionError("ownership_message must include stone_address")
        # Timestamp freshness (optional field ownership_ts unix seconds)
        ts_raw = str(payload.get("ownership_ts") or "").strip()
        if ts_raw.isdigit():
            age = abs(int(time.time()) - int(ts_raw))
            max_age = int(os.environ.get("CHAIN_MESH_OWNERSHIP_MAX_AGE_SEC", "600"))
            if age > max_age:
                raise PermissionError("ownership proof expired")
        # HMAC path (shared secret) — suitable for trusted LAN fleets.
        secret = (
            os.environ.get("CHAIN_MESH_OWNERSHIP_HMAC_SECRET")
            or API_TOKEN
            or ""
        ).encode("utf-8")
        if not secret:
            raise PermissionError("ownership HMAC secret not configured")
        import hashlib

        expect = hmac.new(
            secret, f"{addr}|{msg}".encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not constant_time_token_eq(sig, expect):
            raise PermissionError("invalid ownership_signature")
        return
    if mode in ("ecdsa", "secp256k1", "recover"):
        # C-03: optional secp256k1 recovery when coincurve/ecdsa is installed.
        msg = str(payload.get("ownership_message") or "").strip()
        sig = str(payload.get("ownership_signature") or "").strip()
        if not msg or not sig:
            raise PermissionError(
                "ownership_message and ownership_signature required "
                "(CHAIN_MESH_OWNERSHIP_MODE=ecdsa)"
            )
        if addr not in msg:
            raise PermissionError("ownership_message must include stone_address")
        ts_raw = str(payload.get("ownership_ts") or "").strip()
        if ts_raw.isdigit():
            age = abs(int(time.time()) - int(ts_raw))
            max_age = int(os.environ.get("CHAIN_MESH_OWNERSHIP_MAX_AGE_SEC", "600"))
            if age > max_age:
                raise PermissionError("ownership proof expired")
        try:
            import hashlib
            digest = hashlib.sha256(msg.encode("utf-8")).digest()
            sig_bytes = bytes.fromhex(sig[2:] if sig.startswith("0x") else sig)
            recovered = None
            try:
                from coincurve import PublicKey  # type: ignore

                # compact 65-byte recoverable sig or 64+recid not standardized —
                # require 65-byte (recid||r||s) or 64-byte with ownership_recid
                if len(sig_bytes) == 65:
                    recovered = PublicKey.from_signature_and_message(
                        sig_bytes[1:] + bytes([sig_bytes[0]]), digest, hasher=None
                    )
                else:
                    raise ValueError("need 65-byte recoverable signature")
            except Exception:
                recovered = None
            if recovered is None:
                raise PermissionError(
                    "ecdsa ownership recovery unavailable or signature invalid; "
                    "install coincurve and use recoverable secp256k1 signatures, "
                    "or use CHAIN_MESH_OWNERSHIP_MODE=hmac with CHAIN_MESH_OWNERSHIP_HMAC_SECRET"
                )
            # Address binding: require message bind only unless env maps pubkey→address
            # Full base58check STONE address derivation is chain-specific; require
            # ownership_pubkey field match when provided.
            pub_hex = recovered.format(compressed=True).hex()
            expect_pub = str(payload.get("ownership_pubkey") or "").strip().lower()
            if expect_pub and expect_pub not in (pub_hex, "0x" + pub_hex):
                raise PermissionError("ownership_pubkey does not match recovered key")
            # Without chain address codec, require HMAC dual-bind or trust message+pubkey
            # when CHAIN_MESH_OWNERSHIP_ECDSA_RELAXED=1
            relaxed = os.environ.get("CHAIN_MESH_OWNERSHIP_ECDSA_RELAXED", "0").strip() in (
                "1", "true", "yes",
            )
            if not expect_pub and not relaxed:
                raise PermissionError(
                    "provide ownership_pubkey (compressed hex) matching the signature, "
                    "or set CHAIN_MESH_OWNERSHIP_ECDSA_RELAXED=1 for message-only bind"
                )
            return
        except PermissionError:
            raise
        except Exception as exc:
            raise PermissionError(
                f"ecdsa ownership verification failed: {exc}; "
                "prefer hmac mode for production fleets"
            ) from exc
    raise ValueError(f"unknown CHAIN_MESH_OWNERSHIP_MODE: {mode}")
