"""Wave I — Starlink / satellite uplink handoff bridge for DTN store-and-forward."""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any, Dict, List, Optional

import requests

from chain_mesh import db as mesh_db

HANDOFF_FORMAT = "bloodstone_dtn_starlink/v1"
STARLINK_ENABLE = os.environ.get("DTN_STARLINK_ENABLE", "1").strip() not in ("0", "false", "no")
PROBE_URL = (
    os.environ.get("DTN_STARLINK_PROBE_URL", "").strip()
    or os.environ.get(
        "DTN_UPSTREAM_URL",
        os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"),
    ).rstrip("/")
    + "/api/convergence/status"
)
PROBE_TIMEOUT_SEC = max(3, int(os.environ.get("DTN_STARLINK_PROBE_TIMEOUT_SEC", "12")))
PROBE_MAX_LATENCY_MS = max(500, int(os.environ.get("DTN_STARLINK_MAX_LATENCY_MS", "8000")))
PROBE_STREAK_REQUIRED = max(1, int(os.environ.get("DTN_STARLINK_PROBE_STREAK", "2")))
HANDOFF_COOLDOWN_SEC = max(60, int(os.environ.get("DTN_STARLINK_HANDOFF_COOLDOWN_SEC", "300")))
HANDOFF_FLUSH_LIMIT = max(1, int(os.environ.get("DTN_STARLINK_FLUSH_LIMIT", "5")))
STARLINK_INTERFACE = (os.environ.get("DTN_STARLINK_INTERFACE") or "").strip()
BYPASS_FLUSH_WINDOW = os.environ.get("DTN_STARLINK_BYPASS_FLUSH_WINDOW", "1").strip() not in (
    "0",
    "false",
    "no",
)

_LAST_HANDOFF: Dict[str, Any] = {}


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def init_starlink_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS dtn_starlink_state (
                key TEXT PRIMARY KEY,
                int_value INTEGER NOT NULL DEFAULT 0,
                text_value TEXT NOT NULL DEFAULT '',
                updated_at INTEGER NOT NULL
            );
            """
        )


def _state_get(key: str) -> Dict[str, Any]:
    init_starlink_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT int_value, text_value, updated_at FROM dtn_starlink_state WHERE key = ?",
            (key,),
        ).fetchone()
    if not row:
        return {"int_value": 0, "text_value": "", "updated_at": 0}
    return {
        "int_value": int(row["int_value"]),
        "text_value": str(row["text_value"] or ""),
        "updated_at": int(row["updated_at"]),
    }


def _state_set(key: str, *, int_value: int = 0, text_value: str = "") -> None:
    init_starlink_db()
    now = _now()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO dtn_starlink_state (key, int_value, text_value, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                int_value = excluded.int_value,
                text_value = excluded.text_value,
                updated_at = excluded.updated_at
            """,
            (key, int(int_value), str(text_value or ""), now),
        )


def _interface_status(name: str) -> Dict[str, Any]:
    iface = (name or "").strip()
    if not iface:
        return {"configured": False, "up": None, "carrier": None}
    up = False
    carrier = False
    operstate = ""
    carrier_path = f"/sys/class/net/{iface}/carrier"
    oper_path = f"/sys/class/net/{iface}/operstate"
    try:
        if os.path.isfile(oper_path):
            operstate = open(oper_path, encoding="utf-8").read().strip()
            up = operstate.lower() in ("up", "unknown")
        if os.path.isfile(carrier_path):
            carrier = open(carrier_path, encoding="utf-8").read().strip() == "1"
    except OSError:
        pass
    if not operstate:
        try:
            out = subprocess.check_output(
                ["ip", "-json", "link", "show", iface],
                stderr=subprocess.DEVNULL,
                timeout=5,
                text=True,
            )
            up = '"operstate": "UP"' in out.upper() or '"operstate":"UP"' in out.upper()
        except (subprocess.SubprocessError, FileNotFoundError):
            up = False
    return {
        "configured": True,
        "name": iface,
        "up": up,
        "carrier": carrier,
        "operstate": operstate or None,
    }


def probe_uplink(*, url: str = "") -> Dict[str, Any]:
    """Probe coordinator reachability — models brief Starlink / satellite windows."""
    init_starlink_db()
    target = (url or PROBE_URL).strip()
    iface = _interface_status(STARLINK_INTERFACE)
    if STARLINK_INTERFACE and not iface.get("up"):
        result = {
            "ok": True,
            "format": HANDOFF_FORMAT,
            "connected": False,
            "reason": f"interface {STARLINK_INTERFACE} not up",
            "probe_url": target,
            "interface": iface,
            "latency_ms": None,
        }
        _state_set("probe_streak", int_value=0)
        _state_set("last_probe", text_value=result.get("reason") or "iface down")
        return result

    started = time.time()
    connected = False
    latency_ms: Optional[float] = None
    err = ""
    payload: Dict[str, Any] = {}
    try:
        resp = requests.get(target, timeout=PROBE_TIMEOUT_SEC)
        latency_ms = round((time.time() - started) * 1000.0, 1)
        if resp.status_code == 200:
            payload = resp.json()
            connected = bool(payload.get("ok"))
        else:
            err = f"HTTP {resp.status_code}"
    except Exception as exc:
        err = str(exc)
        latency_ms = round((time.time() - started) * 1000.0, 1)

    if connected and latency_ms is not None and latency_ms > PROBE_MAX_LATENCY_MS:
        connected = False
        err = err or f"latency {latency_ms}ms exceeds max {PROBE_MAX_LATENCY_MS}ms"

    streak_row = _state_get("probe_streak")
    streak = int(streak_row["int_value"])
    streak = streak + 1 if connected else 0
    _state_set("probe_streak", int_value=streak)
    if latency_ms is not None:
        _state_set("last_latency_ms", int_value=int(latency_ms))
    _state_set("last_probe_at", int_value=_now())
    _state_set("last_connected", int_value=1 if connected else 0)

    return {
        "ok": True,
        "format": HANDOFF_FORMAT,
        "connected": connected,
        "latency_ms": latency_ms,
        "probe_url": target,
        "probe_streak": streak,
        "probe_streak_required": PROBE_STREAK_REQUIRED,
        "max_latency_ms": PROBE_MAX_LATENCY_MS,
        "interface": iface,
        "coordinator_roadmap": payload.get("roadmap") if connected else None,
        "error": err or None,
    }


def _handoff_allowed(probe: Dict[str, Any], *, force: bool = False) -> tuple:
    if not STARLINK_ENABLE:
        return False, "DTN_STARLINK_ENABLE off"
    if force:
        return True, "forced handoff"
    if not probe.get("connected"):
        return False, probe.get("reason") or probe.get("error") or "uplink down"
    if int(probe.get("probe_streak") or 0) < PROBE_STREAK_REQUIRED:
        return False, f"probe streak {probe.get('probe_streak')} < {PROBE_STREAK_REQUIRED}"
    last = _state_get("last_handoff_at")
    if last["int_value"] and _now() - last["int_value"] < HANDOFF_COOLDOWN_SEC:
        return False, f"handoff cooldown ({HANDOFF_COOLDOWN_SEC}s)"
    return True, "uplink ready"


def starlink_handoff(*, force: bool = False, limit: int = 0) -> Dict[str, Any]:
    """Flush DTN forward queue upstream when satellite uplink is detected."""
    from chain_mesh import dtn_sync as dtn

    if not STARLINK_ENABLE and not force:
        return {"ok": True, "skipped": True, "reason": "DTN_STARLINK_ENABLE off"}

    dtn.init_dtn_db()
    probe = probe_uplink()
    allowed, reason = _handoff_allowed(probe, force=force)
    pending = dtn.list_pending_forwards(limit=1).get("pending_count", 0)

    if not allowed:
        result = {
            "ok": True,
            "skipped": True,
            "reason": reason,
            "probe": probe,
            "pending_forwards": pending,
        }
        _LAST_HANDOFF.clear()
        _LAST_HANDOFF.update(result)
        return result

    flush_limit = max(1, int(limit or HANDOFF_FLUSH_LIMIT))
    flush = dtn.flush_forward_queue(
        limit=flush_limit,
        force=BYPASS_FLUSH_WINDOW or force,
        try_peers_first=False,
    )
    _state_set("last_handoff_at", int_value=_now())
    _state_set("last_handoff_delivered", int_value=int(flush.get("delivered") or 0))

    result = {
        "ok": True,
        "skipped": False,
        "reason": reason,
        "format": HANDOFF_FORMAT,
        "probe": probe,
        "flush": flush,
        "delivered": int(flush.get("delivered") or 0),
        "pending_forwards": flush.get("remaining", pending),
        "bypass_flush_window": BYPASS_FLUSH_WINDOW,
    }
    _LAST_HANDOFF.clear()
    _LAST_HANDOFF.update(result)
    return result


def status_payload() -> Dict[str, Any]:
    init_starlink_db()
    public = os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org").rstrip("/")
    last_handoff = _state_get("last_handoff_at")
    last_delivered = _state_get("last_handoff_delivered")
    streak = _state_get("probe_streak")
    last_latency = _state_get("last_latency_ms")
    return {
        "ok": True,
        "format": HANDOFF_FORMAT,
        "enabled": STARLINK_ENABLE,
        "probe_url": PROBE_URL,
        "probe_timeout_sec": PROBE_TIMEOUT_SEC,
        "max_latency_ms": PROBE_MAX_LATENCY_MS,
        "probe_streak_required": PROBE_STREAK_REQUIRED,
        "probe_streak": streak["int_value"],
        "handoff_cooldown_sec": HANDOFF_COOLDOWN_SEC,
        "flush_limit": HANDOFF_FLUSH_LIMIT,
        "bypass_flush_window": BYPASS_FLUSH_WINDOW,
        "interface": _interface_status(STARLINK_INTERFACE),
        "last_probe_at": _state_get("last_probe_at")["int_value"] or None,
        "last_connected": bool(_state_get("last_connected")["int_value"]),
        "last_latency_ms": last_latency["int_value"] or None,
        "last_handoff_at": last_handoff["int_value"] or None,
        "last_handoff_delivered": last_delivered["int_value"],
        "last_handoff": dict(_LAST_HANDOFF),
        "apis": {
            "status": f"{public}/api/convergence/dtn/starlink/status",
            "probe": f"{public}/api/convergence/dtn/starlink/probe",
            "handoff": f"{public}/api/convergence/dtn/starlink/handoff",
        },
    }