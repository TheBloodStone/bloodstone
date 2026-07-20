"""QUASAR AI review settings (admin panel toggle + runtime gate).

Controls whether *full* SpaceXAI review runs on mesh tip-height disagreements.
When off, detection and optional heuristic still work; no api.x.ai calls are made.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict

CONFIG_PATH = os.environ.get(
    "QUASAR_AI_SETTINGS_PATH",
    "/var/lib/bloodstone/quasar-ai-settings.json",
)

_LOCK = threading.Lock()
_CACHE: Dict[str, Any] = {"mtime": None, "data": None}


def _env_default_enabled() -> bool:
    return os.environ.get("QUASAR_WITNESS_AI_ENABLE", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _defaults() -> Dict[str, Any]:
    return {
        "full_ai_review_enabled": _env_default_enabled(),
        "updated_by": "",
        "updated_at": 0,
    }


def _read_file() -> Dict[str, Any]:
    out = _defaults()
    if not os.path.isfile(CONFIG_PATH):
        return out
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            raw = json.load(fh)
        if not isinstance(raw, dict):
            return out
        if "full_ai_review_enabled" in raw:
            out["full_ai_review_enabled"] = bool(raw.get("full_ai_review_enabled"))
        if raw.get("updated_by") is not None:
            out["updated_by"] = str(raw.get("updated_by") or "")[:64]
        if raw.get("updated_at") is not None:
            try:
                out["updated_at"] = int(raw.get("updated_at") or 0)
            except (TypeError, ValueError):
                out["updated_at"] = 0
    except Exception:
        return out
    return out


def load_quasar_ai_settings(*, use_cache: bool = True) -> Dict[str, Any]:
    """Load settings; re-reads file when mtime changes (live admin toggle)."""
    mtime = None
    try:
        if os.path.isfile(CONFIG_PATH):
            mtime = os.path.getmtime(CONFIG_PATH)
    except OSError:
        mtime = None

    with _LOCK:
        if (
            use_cache
            and _CACHE.get("data") is not None
            and _CACHE.get("mtime") == mtime
        ):
            data = dict(_CACHE["data"])
        else:
            data = _read_file()
            _CACHE["data"] = dict(data)
            _CACHE["mtime"] = mtime

    data["config_path"] = CONFIG_PATH
    data["full_ai_review_enabled"] = bool(data.get("full_ai_review_enabled"))
    # Convenience aliases for templates / API
    data["enabled"] = data["full_ai_review_enabled"]
    data["spacexai_key_configured"] = bool((os.environ.get("XAI_API_KEY") or "").strip())
    data["model"] = (os.environ.get("XAI_MODEL") or "grok-4.5").strip()
    return data


def save_quasar_ai_settings(
    *,
    full_ai_review_enabled: bool,
    updated_by: str = "admin",
) -> Dict[str, Any]:
    import time

    payload = {
        "full_ai_review_enabled": bool(full_ai_review_enabled),
        "updated_by": (updated_by or "admin")[:64],
        "updated_at": int(time.time()),
    }
    os.makedirs(os.path.dirname(CONFIG_PATH) or "/var/lib/bloodstone", exist_ok=True)
    tmp = f"{CONFIG_PATH}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, CONFIG_PATH)
    with _LOCK:
        _CACHE["data"] = dict(payload)
        try:
            _CACHE["mtime"] = os.path.getmtime(CONFIG_PATH)
        except OSError:
            _CACHE["mtime"] = None
    return load_quasar_ai_settings(use_cache=False)


def full_ai_review_enabled() -> bool:
    """True when admin/env allows full SpaceXAI QUASAR tip reviews."""
    return bool(load_quasar_ai_settings().get("full_ai_review_enabled"))
