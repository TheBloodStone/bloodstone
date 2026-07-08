"""One-time beta tester codes and device access tokens for release channels."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

DB_PATH = os.environ.get(
    "BLOODSTONE_BETA_CODES_DB", "/var/lib/bloodstone/beta_codes.db"
)
_CODE_RE = re.compile(r"^[A-Z0-9]{4}(?:-[A-Z0-9]{4}){2,3}$")
_DB_LOCK = threading.Lock()


def _hash_secret(value: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()
    return f"sha256${salt}${digest}"


def _verify_secret(stored: str, value: str) -> bool:
    try:
        algo, salt, digest = str(stored or "").split("$", 2)
    except ValueError:
        return False
    if algo != "sha256":
        return False
    check = hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()
    return hmac.compare_digest(check, digest)


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _DB_LOCK:
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS beta_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code_hash TEXT NOT NULL UNIQUE,
                    label TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    created_by TEXT NOT NULL DEFAULT '',
                    redeemed_at REAL,
                    redeemed_device_id TEXT,
                    redeemed_ip TEXT
                );
                CREATE TABLE IF NOT EXISTS beta_access_tokens (
                    token_hash TEXT PRIMARY KEY,
                    code_id INTEGER,
                    device_id TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL,
                    revoked_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_beta_codes_redeemed
                    ON beta_codes(redeemed_at);
                CREATE TABLE IF NOT EXISTS lan_validated_releases (
                    lan_key TEXT PRIMARY KEY,
                    apk_version TEXT NOT NULL,
                    apk_filename TEXT NOT NULL,
                    web_bundle_version TEXT NOT NULL,
                    web_bundle_filename TEXT NOT NULL,
                    validated_at REAL NOT NULL,
                    validated_by_device_id TEXT NOT NULL DEFAULT '',
                    validated_by_token_id TEXT NOT NULL DEFAULT ''
                );
                """
            )
            conn.commit()
        finally:
            conn.close()


def _normalize_code(code: str) -> str:
    raw = str(code or "").strip().upper()
    raw = raw.replace(" ", "").replace("_", "-")
    if raw.startswith("BSBETA-"):
        raw = raw[len("BSBETA-") :]
    if raw.startswith("BS-BETA-"):
        raw = raw[len("BS-BETA-") :]
    return raw


def _format_code(raw: str) -> str:
    parts = [p for p in raw.split("-") if p]
    if not parts:
        parts = [secrets.token_hex(2).upper()[:4] for _ in range(3)]
    while len(parts) < 3:
        parts.append(secrets.token_hex(2).upper()[:4])
    return "BS-BETA-" + "-".join(parts[:3])


def _new_raw_code() -> str:
    return "-".join(secrets.token_hex(2).upper()[:4] for _ in range(3))


def generate_code(*, label: str = "", created_by: str = "") -> Dict[str, Any]:
    """Create a one-time beta tester code. Plaintext is returned once."""
    init_db()
    plaintext = _format_code(_new_raw_code())
    code_hash = _hash_secret(plaintext)
    now = time.time()
    with _DB_LOCK:
        conn = _connect()
        try:
            cur = conn.execute(
                """
                INSERT INTO beta_codes (code_hash, label, created_at, created_by)
                VALUES (?, ?, ?, ?)
                """,
                (code_hash, str(label or "").strip(), now, str(created_by or "").strip()),
            )
            conn.commit()
            code_id = int(cur.lastrowid)
        finally:
            conn.close()
    return {
        "ok": True,
        "code": plaintext,
        "code_id": code_id,
        "label": str(label or "").strip(),
        "created_at": now,
    }


def _lookup_pending_code(code: str) -> Optional[sqlite3.Row]:
    init_db()
    normalized = _normalize_code(code)
    if not normalized:
        return None
    with _DB_LOCK:
        conn = _connect()
        try:
            rows = conn.execute(
                """
                SELECT id, code_hash, label, created_at, redeemed_at
                FROM beta_codes
                WHERE redeemed_at IS NULL
                ORDER BY id DESC
                """
            ).fetchall()
            for row in rows:
                if _verify_secret(row["code_hash"], normalized):
                    return row
                if _verify_secret(row["code_hash"], _format_code(normalized)):
                    return row
        finally:
            conn.close()
    return None


def lan_key_from_ip(ip: str) -> Optional[str]:
    """Stable household LAN id (/24 for IPv4 private subnets)."""
    value = str(ip or "").strip()
    if not value:
        return None
    if value.startswith("::ffff:"):
        value = value.split("::ffff:", 1)[1]
    if not is_private_client_ip(value):
        return None
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return None
    if addr.version == 4:
        net = ipaddress.ip_network(f"{addr}/24", strict=False)
        return f"lan4:{net.network_address}"
    net = ipaddress.ip_network(f"{addr}/64", strict=False)
    return f"lan6:{net.network_address}"


def is_private_client_ip(ip: str) -> bool:
    value = str(ip or "").strip()
    if not value:
        return False
    if value.startswith("::ffff:"):
        value = value.split("::ffff:", 1)[1]
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(addr.is_private or addr.is_loopback or addr.is_link_local)


def redeem_code(
    code: str,
    *,
    device_id: str = "",
    client_ip: str = "",
    lan_ip: str = "",
    require_lan: bool = True,
) -> Dict[str, Any]:
    """Consume a one-time code and issue a long-lived beta access token."""
    if require_lan:
        on_lan = is_private_client_ip(lan_ip) or is_private_client_ip(client_ip)
        if not on_lan:
            return {
                "ok": False,
                "error": "beta_redeem_requires_lan",
                "message": "Beta codes can only be redeemed while on a LAN connection.",
            }

    row = _lookup_pending_code(code)
    if not row:
        return {
            "ok": False,
            "error": "invalid_or_used_code",
            "message": "Invalid or already used beta code.",
        }

    token = secrets.token_urlsafe(32)
    token_hash = _hash_secret(token)
    now = time.time()
    device = str(device_id or "").strip()[:128]

    with _DB_LOCK:
        conn = _connect()
        try:
            updated = conn.execute(
                """
                UPDATE beta_codes
                SET redeemed_at = ?, redeemed_device_id = ?, redeemed_ip = ?
                WHERE id = ? AND redeemed_at IS NULL
                """,
                (now, device, str(client_ip or "").strip()[:64], int(row["id"])),
            )
            if updated.rowcount != 1:
                return {
                    "ok": False,
                    "error": "invalid_or_used_code",
                    "message": "Invalid or already used beta code.",
                }
            conn.execute(
                """
                INSERT INTO beta_access_tokens
                    (token_hash, code_id, device_id, created_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (token_hash, int(row["id"]), device, now, now),
            )
            conn.commit()
        finally:
            conn.close()

    return {
        "ok": True,
        "token": token,
        "release_channel": "beta",
        "label": row["label"] or "",
    }


def verify_access_token(token: str) -> bool:
    value = str(token or "").strip()
    if len(value) < 16:
        return False
    init_db()
    now = time.time()
    with _DB_LOCK:
        conn = _connect()
        try:
            rows = conn.execute(
                """
                SELECT token_hash, revoked_at
                FROM beta_access_tokens
                WHERE revoked_at IS NULL
                ORDER BY created_at DESC
                LIMIT 500
                """
            ).fetchall()
            for row in rows:
                if _verify_secret(row["token_hash"], value):
                    conn.execute(
                        "UPDATE beta_access_tokens SET last_seen_at = ? WHERE token_hash = ?",
                        (now, row["token_hash"]),
                    )
                    conn.commit()
                    return True
        finally:
            conn.close()
    return False


def get_lan_validated_release(lan_key: str) -> Optional[Dict[str, Any]]:
    key = str(lan_key or "").strip()
    if not key:
        return None
    init_db()
    with _DB_LOCK:
        conn = _connect()
        try:
            row = conn.execute(
                """
                SELECT lan_key, apk_version, apk_filename,
                       web_bundle_version, web_bundle_filename,
                       validated_at, validated_by_device_id
                FROM lan_validated_releases
                WHERE lan_key = ?
                """,
                (key,),
            ).fetchone()
        finally:
            conn.close()
    return dict(row) if row else None


def validate_lan_release(
    *,
    beta_token: str,
    lan_ip: str,
    device_id: str = "",
    apk_version: str,
    apk_filename: str,
    web_bundle_version: str,
    web_bundle_filename: str,
) -> Dict[str, Any]:
    """Beta tester approves current beta build for everyone on this LAN."""
    if not verify_access_token(beta_token):
        return {
            "ok": False,
            "error": "beta_token_required",
            "message": "Active beta tester access is required.",
        }
    if not is_private_client_ip(lan_ip):
        return {
            "ok": False,
            "error": "beta_validate_requires_lan",
            "message": "LAN validation must be done from your local network.",
        }
    lan_key = lan_key_from_ip(lan_ip)
    if not lan_key:
        return {
            "ok": False,
            "error": "invalid_lan_ip",
            "message": "Could not determine LAN identity.",
        }

    now = time.time()
    device = str(device_id or "").strip()[:128]
    with _DB_LOCK:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO lan_validated_releases (
                    lan_key, apk_version, apk_filename,
                    web_bundle_version, web_bundle_filename,
                    validated_at, validated_by_device_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(lan_key) DO UPDATE SET
                    apk_version = excluded.apk_version,
                    apk_filename = excluded.apk_filename,
                    web_bundle_version = excluded.web_bundle_version,
                    web_bundle_filename = excluded.web_bundle_filename,
                    validated_at = excluded.validated_at,
                    validated_by_device_id = excluded.validated_by_device_id
                """,
                (
                    lan_key,
                    str(apk_version or "").strip(),
                    str(apk_filename or "").strip(),
                    str(web_bundle_version or "").strip(),
                    str(web_bundle_filename or "").strip(),
                    now,
                    device,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    return {
        "ok": True,
        "lan_key": lan_key,
        "apk_version": apk_version,
        "web_bundle_version": web_bundle_version,
        "message": "This LAN will now receive the validated build as stable OTA.",
    }


def list_lan_validations(*, limit: int = 100) -> List[Dict[str, Any]]:
    init_db()
    limit = max(1, min(int(limit), 500))
    with _DB_LOCK:
        conn = _connect()
        try:
            rows = conn.execute(
                """
                SELECT lan_key, apk_version, web_bundle_version,
                       validated_at, validated_by_device_id
                FROM lan_validated_releases
                ORDER BY validated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            conn.close()
    return [dict(row) for row in rows]


def resolve_release_channel(
    *,
    beta_token: str = "",
    channel: str = "",
) -> str:
    requested = str(channel or "").strip().lower()
    if requested == "beta":
        if verify_access_token(beta_token):
            return "beta"
        return "stable"
    if verify_access_token(beta_token):
        return "beta"
    return "stable"


def list_codes(*, include_redeemed: bool = True, limit: int = 100) -> List[Dict[str, Any]]:
    init_db()
    limit = max(1, min(int(limit), 500))
    with _DB_LOCK:
        conn = _connect()
        try:
            if include_redeemed:
                rows = conn.execute(
                    """
                    SELECT id, label, created_at, created_by, redeemed_at,
                           redeemed_device_id, redeemed_ip
                    FROM beta_codes
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, label, created_at, created_by, redeemed_at,
                           redeemed_device_id, redeemed_ip
                    FROM beta_codes
                    WHERE redeemed_at IS NULL
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        finally:
            conn.close()
    return [dict(row) for row in rows]


def revoke_token(token: str) -> bool:
    value = str(token or "").strip()
    if not value:
        return False
    init_db()
    now = time.time()
    with _DB_LOCK:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT token_hash FROM beta_access_tokens WHERE revoked_at IS NULL"
            ).fetchall()
            for row in rows:
                if _verify_secret(row["token_hash"], value):
                    conn.execute(
                        "UPDATE beta_access_tokens SET revoked_at = ? WHERE token_hash = ?",
                        (now, row["token_hash"]),
                    )
                    conn.commit()
                    return True
        finally:
            conn.close()
    return False