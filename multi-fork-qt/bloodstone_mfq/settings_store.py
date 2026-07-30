"""Persistent settings for Multi-Fork Qt Wallet."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

from PyQt5.QtCore import QSettings

from . import APP_NAME, APP_ORG

_IS_WIN = sys.platform.startswith("win")


def qsettings() -> QSettings:
    return QSettings(APP_ORG, APP_NAME)


def config_dir() -> Path:
    if _IS_WIN:
        base = Path(
            os.environ.get("LOCALAPPDATA")
            or (Path.home() / "AppData" / "Local")
        )
        p = base / "Bloodstone" / "MultiForkQt"
    else:
        p = Path.home() / ".bloodstone-multi-fork-qt"
    p.mkdir(parents=True, exist_ok=True)
    return p


def rpc_dir() -> Path:
    p = config_dir() / "rpc"
    p.mkdir(parents=True, exist_ok=True)
    return p


def conf_overrides() -> Dict[str, str]:
    s = qsettings()
    raw = s.value("conf_overrides_json", "{}")
    try:
        data = json.loads(str(raw or "{}"))
        if isinstance(data, dict):
            out = {}
            for k, v in data.items():
                path = str(v or "").strip()
                if not path:
                    continue
                # Drop stale Linux operator paths that break Windows installs
                if _IS_WIN and path.startswith(("/root/", "/var/", "/home/")):
                    continue
                out[str(k).upper()] = path
            return out
    except Exception:
        pass
    return {}


def set_conf_overrides(mapping: Dict[str, str]) -> None:
    s = qsettings()
    clean = {}
    for k, v in mapping.items():
        path = str(v or "").strip()
        if not path:
            continue
        if _IS_WIN and path.startswith(("/root/", "/var/", "/home/")):
            continue
        clean[str(k).upper()] = path
    s.setValue("conf_overrides_json", json.dumps(clean))


def rpc_overrides() -> Dict[str, Dict[str, Any]]:
    """Per-ticker RPC settings: host/port/user/password/conf."""
    s = qsettings()
    raw = s.value("rpc_overrides_json", "{}")
    try:
        data = json.loads(str(raw or "{}"))
        if not isinstance(data, dict):
            return {}
        out: Dict[str, Dict[str, Any]] = {}
        for k, v in data.items():
            if not isinstance(v, dict):
                continue
            ticker = str(k).upper()
            entry = {}
            for key in (
                "rpc_host",
                "rpc_port",
                "rpc_user",
                "rpc_password",
                "conf",
            ):
                if v.get(key) is not None and str(v.get(key)) != "":
                    entry[key] = v[key]
            if entry.get("conf") and _IS_WIN and str(entry["conf"]).startswith(
                ("/root/", "/var/", "/home/")
            ):
                entry.pop("conf", None)
            if entry:
                out[ticker] = entry
        return out
    except Exception:
        return {}


def set_rpc_overrides(mapping: Dict[str, Dict[str, Any]]) -> None:
    s = qsettings()
    clean: Dict[str, Dict[str, Any]] = {}
    for k, v in mapping.items():
        if not isinstance(v, dict):
            continue
        ticker = str(k).upper()
        entry = {}
        for key in ("rpc_host", "rpc_port", "rpc_user", "rpc_password", "conf"):
            val = v.get(key)
            if val is None or str(val) == "":
                continue
            if key == "conf" and _IS_WIN and str(val).startswith(
                ("/root/", "/var/", "/home/")
            ):
                continue
            if key == "rpc_port":
                try:
                    entry[key] = int(val)
                except (TypeError, ValueError):
                    continue
            else:
                entry[key] = str(val)
        if entry:
            clean[ticker] = entry
    s.setValue("rpc_overrides_json", json.dumps(clean))


def write_conf_template(
    ticker: str,
    *,
    rpc_user: str,
    rpc_password: str,
    rpc_port: int,
    rpc_host: str = "127.0.0.1",
    path: str = "",
) -> str:
    """Write a local conf file the wallet can read (Windows-friendly path)."""
    t = ticker.upper()
    dest = Path(path) if path else (rpc_dir() / f"{t.lower()}.conf")
    dest.parent.mkdir(parents=True, exist_ok=True)
    host = rpc_host or "127.0.0.1"
    if host in ("0.0.0.0", "::"):
        host = "127.0.0.1"
    body = (
        f"# Bloodstone Multi-Fork Qt — auto template for {t}\n"
        f"# Point this at a *local* daemon (rpcbind stays localhost).\n"
        f"# Edit rpcuser/rpcpassword to match your node conf.\n"
        f"rpcuser={rpc_user or (t.lower() + 'rpc')}\n"
        f"rpcpassword={rpc_password or 'CHANGE_ME'}\n"
        f"rpcport={int(rpc_port or 0)}\n"
        f"rpcbind={host}\n"
        f"rpcallowip=127.0.0.1\n"
    )
    dest.write_text(body, encoding="utf-8")
    try:
        os.chmod(dest, 0o600)
    except OSError:
        pass
    return str(dest)


def selected_wallet(ticker: str) -> str:
    s = qsettings()
    return str(s.value(f"wallet/{ticker.upper()}", "") or "")


def set_selected_wallet(ticker: str, wallet: str) -> None:
    s = qsettings()
    s.setValue(f"wallet/{ticker.upper()}", wallet or "")


def last_ticker() -> str:
    s = qsettings()
    return str(s.value("last_ticker", "STONE") or "STONE")


def set_last_ticker(ticker: str) -> None:
    s = qsettings()
    s.setValue("last_ticker", (ticker or "STONE").upper())


def refresh_ms() -> int:
    s = qsettings()
    try:
        return max(5000, int(s.value("refresh_ms", 15000)))
    except (TypeError, ValueError):
        return 15000


def set_refresh_ms(ms: int) -> None:
    s = qsettings()
    s.setValue("refresh_ms", int(ms))


def export_snapshot() -> Dict[str, Any]:
    return {
        "conf_overrides": conf_overrides(),
        "rpc_overrides": {
            k: {kk: ("***" if kk == "rpc_password" else vv) for kk, vv in v.items()}
            for k, v in rpc_overrides().items()
        },
        "last_ticker": last_ticker(),
        "refresh_ms": refresh_ms(),
        "config_dir": str(config_dir()),
    }
