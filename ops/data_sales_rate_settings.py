"""Data & processing rate settings — admin costs + AI auto-adjust.

Operators enter **provider/operating costs** in the mining admin panel.
Rates charged for mesh data (storage / bandwidth / upkeep) and processing
(compute) are then auto-adjusted:

1. **Heuristic** — cost × (1 + target margin) → USDT rates → STONE via FX
2. **SpaceXAI** (optional) — refine rates from costs, capacity, and STONE price

Published rates are read by ``chain_mesh.stone_data_payments`` and
``chain_mesh.usdt_monetization`` so /data-sales and claim math stay in sync.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional, Tuple

import requests

CONFIG_PATH = os.environ.get(
    "DATA_SALES_RATE_SETTINGS_PATH",
    "/var/lib/bloodstone/data-sales-rate-settings.json",
)

_LOCK = threading.Lock()
_CACHE: Dict[str, Any] = {"mtime": None, "data": None}

# Env fallbacks match stone_data_payments / usdt_monetization defaults
_ENV_STONE = {
    "storage": Decimal(os.environ.get("DATA_SALES_STONE_PER_GIB", "1")),
    "bandwidth": Decimal(os.environ.get("DATA_SALES_STONE_PER_100MIB", "1")),
    "compute": Decimal(os.environ.get("DATA_SALES_STONE_PER_GFLOP", "1")),
    "upkeep": Decimal(os.environ.get("DATA_SALES_UPKEEP_STONE_PER_GIB_MONTH", "0.1")),
}
_ENV_USDT = {
    "storage": Decimal(os.environ.get("MONETIZE_USDT_PER_GIB", "0.05")),
    "bandwidth": Decimal(os.environ.get("MONETIZE_USDT_PER_100MIB", "0.02")),
    "compute": Decimal(os.environ.get("MONETIZE_USDT_PER_GFLOP", "0.01")),
    "upkeep": Decimal(os.environ.get("MONETIZE_USDT_UPKEEP_PER_GIB_MONTH", "0.005")),
}


def _d(v: Any) -> Decimal:
    return Decimal(str(v if v is not None else 0))


def _q(v: Decimal, places: str = "0.00000001") -> Decimal:
    return _d(v).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _xai_api_key() -> str:
    return (os.environ.get("XAI_API_KEY") or "").strip()


def _xai_base_url() -> str:
    return (os.environ.get("XAI_BASE_URL") or "https://api.x.ai/v1").rstrip("/")


def _xai_model() -> str:
    return (os.environ.get("XAI_MODEL") or "grok-4.5").strip()


def _xai_timeout_sec() -> int:
    return max(5, int(os.environ.get("XAI_TIMEOUT_SEC", "45")))


def _defaults() -> Dict[str, Any]:
    return {
        "costs": {
            # Operator / provider cost inputs (USD)
            "storage_usd_per_gib": 0.02,
            "bandwidth_usd_per_100mib": 0.005,
            "compute_usd_per_gflop": 0.002,
            "upkeep_usd_per_gib_month": 0.001,
            "fixed_usd_per_month": 0.0,
            "notes": "",
        },
        "policy": {
            "target_margin_pct": 40.0,
            "min_margin_pct": 15.0,
            "max_rate_change_pct": 25.0,
            "ai_auto_adjust_enabled": True,
            "prefer_ai": True,
            "min_usdt_per_unit": 0.000001,
            "min_stone_per_unit": 0.00000001,
        },
        # Published commercial rates (filled by adjust)
        "rates_usdt": {
            "storage": float(_ENV_USDT["storage"]),
            "bandwidth": float(_ENV_USDT["bandwidth"]),
            "compute": float(_ENV_USDT["compute"]),
            "upkeep": float(_ENV_USDT["upkeep"]),
        },
        "rates_stone": {
            "storage": float(_ENV_STONE["storage"]),
            "bandwidth": float(_ENV_STONE["bandwidth"]),
            "compute": float(_ENV_STONE["compute"]),
            "upkeep": float(_ENV_STONE["upkeep"]),
        },
        "last_adjustment": {
            "at": 0,
            "method": "defaults",
            "rationale": "env / package defaults until first admin save or AI adjust",
            "model": "",
            "confidence": 0.0,
        },
        "updated_by": "",
        "updated_at": 0,
    }


def _merge_defaults(raw: Dict[str, Any]) -> Dict[str, Any]:
    base = _defaults()
    if not isinstance(raw, dict):
        return base
    for section in ("costs", "policy", "rates_usdt", "rates_stone", "last_adjustment"):
        if isinstance(raw.get(section), dict):
            base[section].update(raw[section])
    if raw.get("updated_by") is not None:
        base["updated_by"] = str(raw.get("updated_by") or "")[:64]
    if raw.get("updated_at") is not None:
        try:
            base["updated_at"] = int(raw.get("updated_at") or 0)
        except (TypeError, ValueError):
            pass
    return base


def _read_file() -> Dict[str, Any]:
    if not os.path.isfile(CONFIG_PATH):
        return _defaults()
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            raw = json.load(fh)
        return _merge_defaults(raw if isinstance(raw, dict) else {})
    except Exception:
        return _defaults()


def load_settings(*, use_cache: bool = True) -> Dict[str, Any]:
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
            data = json.loads(json.dumps(_CACHE["data"]))
        else:
            data = _read_file()
            _CACHE["data"] = json.loads(json.dumps(data))
            _CACHE["mtime"] = mtime

    data["config_path"] = CONFIG_PATH
    data["spacexai_key_configured"] = bool(_xai_api_key())
    data["model"] = _xai_model()
    data["file_exists"] = os.path.isfile(CONFIG_PATH)
    return data


def _write(payload: Dict[str, Any]) -> Dict[str, Any]:
    os.makedirs(os.path.dirname(CONFIG_PATH) or "/var/lib/bloodstone", exist_ok=True)
    tmp = f"{CONFIG_PATH}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, CONFIG_PATH)
    with _LOCK:
        _CACHE["data"] = json.loads(json.dumps(payload))
        try:
            _CACHE["mtime"] = os.path.getmtime(CONFIG_PATH)
        except OSError:
            _CACHE["mtime"] = None
    return load_settings(use_cache=False)


def save_costs(
    costs: Dict[str, Any],
    policy: Optional[Dict[str, Any]] = None,
    *,
    updated_by: str = "admin",
    run_adjust: bool = True,
    force_ai: bool = False,
) -> Dict[str, Any]:
    """Persist operator costs / policy; optionally recompute rates immediately."""
    cur = load_settings(use_cache=False)
    c = dict(cur["costs"])
    for key in (
        "storage_usd_per_gib",
        "bandwidth_usd_per_100mib",
        "compute_usd_per_gflop",
        "upkeep_usd_per_gib_month",
        "fixed_usd_per_month",
    ):
        if key in costs and costs[key] is not None and str(costs[key]).strip() != "":
            val = _f(costs[key], c.get(key, 0))
            if val < 0:
                raise ValueError(f"{key} cannot be negative")
            c[key] = val
    if "notes" in costs and costs["notes"] is not None:
        c["notes"] = str(costs["notes"])[:500]

    p = dict(cur["policy"])
    if policy:
        for key in (
            "target_margin_pct",
            "min_margin_pct",
            "max_rate_change_pct",
            "min_usdt_per_unit",
            "min_stone_per_unit",
        ):
            if key in policy and policy[key] is not None and str(policy[key]).strip() != "":
                val = _f(policy[key], p.get(key, 0))
                if val < 0:
                    raise ValueError(f"{key} cannot be negative")
                p[key] = val
        if "ai_auto_adjust_enabled" in policy:
            p["ai_auto_adjust_enabled"] = bool(policy["ai_auto_adjust_enabled"])
        if "prefer_ai" in policy:
            p["prefer_ai"] = bool(policy["prefer_ai"])

    cur["costs"] = c
    cur["policy"] = p
    cur["updated_by"] = (updated_by or "admin")[:64]
    cur["updated_at"] = int(time.time())
    # strip runtime-only keys before write
    write_body = {
        k: v
        for k, v in cur.items()
        if k
        not in (
            "config_path",
            "spacexai_key_configured",
            "model",
            "file_exists",
        )
    }
    _write(write_body)
    if run_adjust:
        return adjust_rates(
            updated_by=updated_by,
            force_ai=force_ai,
            prefer_ai=bool(p.get("prefer_ai", True)),
        )
    return load_settings(use_cache=False)


def usdt_per_stone() -> Decimal:
    """Resolve STONE price in USDT for conversion."""
    try:
        from chain_mesh import usdt_monetization as mon

        return _d(mon.usdt_per_stone())
    except Exception:
        return _d(
            os.environ.get(
                "MONETIZE_STONE_USDT_RATE",
                os.environ.get("SWAP_STONE_USDT_RATE", "0.0001"),
            )
        )


def _capacity_snapshot() -> Dict[str, Any]:
    try:
        from chain_mesh import capacity_demand as cd

        if hasattr(cd, "capacity_demand_payload"):
            return cd.capacity_demand_payload()  # type: ignore[attr-defined]
        if hasattr(cd, "summary"):
            return cd.summary()  # type: ignore[attr-defined]
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}
    return {"ok": False, "error": "capacity module has no summary"}


def _clamp_change(
    old: float, new: float, max_change_pct: float, floor: float
) -> float:
    if old <= 0:
        return max(floor, new)
    cap = abs(old) * (max_change_pct / 100.0)
    delta = new - old
    if delta > cap:
        new = old + cap
    elif delta < -cap:
        new = old - cap
    return max(floor, new)


def heuristic_rates(settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Cost × (1 + margin) → USDT; STONE = USDT / usdt_per_stone."""
    s = settings or load_settings()
    costs = s["costs"]
    policy = s["policy"]
    margin = max(
        _f(policy.get("min_margin_pct"), 15),
        _f(policy.get("target_margin_pct"), 40),
    )
    mult = 1.0 + margin / 100.0
    # Spread fixed monthly cost lightly across products (equal weight)
    fixed = max(0.0, _f(costs.get("fixed_usd_per_month"), 0))
    fixed_share = fixed / 30.0 / 4.0  # daily share per product (rough)

    cost_map = {
        "storage": _f(costs.get("storage_usd_per_gib")) + fixed_share * 0.1,
        "bandwidth": _f(costs.get("bandwidth_usd_per_100mib")) + fixed_share * 0.1,
        "compute": _f(costs.get("compute_usd_per_gflop")) + fixed_share * 0.1,
        "upkeep": _f(costs.get("upkeep_usd_per_gib_month")) + fixed_share * 0.05,
    }
    min_usdt = max(1e-9, _f(policy.get("min_usdt_per_unit"), 1e-6))
    min_stone = max(1e-12, _f(policy.get("min_stone_per_unit"), 1e-8))
    fx = float(usdt_per_stone())
    if fx <= 0:
        fx = 0.0001

    rates_usdt = {}
    rates_stone = {}
    for product, unit_cost in cost_map.items():
        usdt = max(min_usdt, unit_cost * mult)
        rates_usdt[product] = float(_q(_d(usdt), "0.000001"))
        rates_stone[product] = float(_q(_d(usdt) / _d(fx), "0.00000001"))
        rates_stone[product] = max(min_stone, rates_stone[product])

    return {
        "method": "heuristic",
        "margin_pct": margin,
        "usdt_per_stone": fx,
        "rates_usdt": rates_usdt,
        "rates_stone": rates_stone,
        "rationale": (
            f"Unit cost × (1 + {margin:g}% margin); STONE via "
            f"{fx:g} USDT/STONE. Fixed monthly ${fixed:g} amortized."
        ),
        "confidence": 0.65,
        "model": "",
    }


def _extract_json(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("empty model response")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("no JSON object in model response")
    return json.loads(m.group(0))


def _call_spacexai(settings: Dict[str, Any], heuristic: Dict[str, Any]) -> Dict[str, Any]:
    api_key = _xai_api_key()
    if not api_key:
        raise RuntimeError("XAI_API_KEY not set")

    capacity = _capacity_snapshot()
    system = (
        "You set commercial rates for Bloodstone mesh data products. "
        "Products: storage (per GiB), bandwidth (per 100 MiB), compute/processing "
        "(per GFLOP), upkeep (per GiB·month). "
        "Operators give USD costs; you recommend customer rates in USDT and STONE. "
        "Respect target margin; never price below cost + min_margin. "
        "Tighten prices if capacity is tight; ease if surplus. "
        "Reply with ONLY one JSON object, no markdown."
    )
    user = {
        "costs_usd": settings.get("costs"),
        "policy": settings.get("policy"),
        "current_rates_usdt": settings.get("rates_usdt"),
        "current_rates_stone": settings.get("rates_stone"),
        "heuristic_suggestion": {
            "rates_usdt": heuristic.get("rates_usdt"),
            "rates_stone": heuristic.get("rates_stone"),
            "margin_pct": heuristic.get("margin_pct"),
            "usdt_per_stone": heuristic.get("usdt_per_stone"),
        },
        "capacity_signal": capacity,
        "required_json_schema": {
            "rates_usdt": {
                "storage": "number",
                "bandwidth": "number",
                "compute": "number",
                "upkeep": "number",
            },
            "rates_stone": {
                "storage": "number",
                "bandwidth": "number",
                "compute": "number",
                "upkeep": "number",
            },
            "confidence": "0..1",
            "rationale": "short string",
            "factors": ["string"],
        },
    }
    url = f"{_xai_base_url()}/chat/completions"
    payload = {
        "model": _xai_model(),
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user)},
        ],
    }
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=_xai_timeout_sec(),
    )
    resp.raise_for_status()
    body = resp.json()
    content = (
        ((body.get("choices") or [{}])[0].get("message") or {}).get("content")
        or ""
    )
    raw = _extract_json(content)
    rates_usdt = raw.get("rates_usdt") or {}
    rates_stone = raw.get("rates_stone") or {}
    for product in ("storage", "bandwidth", "compute", "upkeep"):
        if product not in rates_usdt:
            rates_usdt[product] = heuristic["rates_usdt"][product]
        if product not in rates_stone:
            rates_stone[product] = heuristic["rates_stone"][product]
        rates_usdt[product] = float(_q(_d(rates_usdt[product]), "0.000001"))
        rates_stone[product] = float(_q(_d(rates_stone[product]), "0.00000001"))
    conf = _f(raw.get("confidence"), 0.6)
    conf = max(0.0, min(1.0, conf))
    factors = raw.get("factors") if isinstance(raw.get("factors"), list) else []
    factors = [str(f)[:120] for f in factors[:12]]
    rationale = str(raw.get("rationale") or "").strip()[:2000]
    if not rationale:
        rationale = "SpaceXAI rate adjustment completed."
    return {
        "method": "spacexai",
        "rates_usdt": rates_usdt,
        "rates_stone": rates_stone,
        "confidence": conf,
        "rationale": rationale,
        "factors": factors,
        "model": _xai_model(),
        "usdt_per_stone": heuristic.get("usdt_per_stone"),
        "margin_pct": heuristic.get("margin_pct"),
    }


def _enforce_floor(
    rates_usdt: Dict[str, float],
    rates_stone: Dict[str, float],
    settings: Dict[str, Any],
    heuristic: Dict[str, Any],
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Never sell below cost + min margin (USDT); keep STONE consistent-ish."""
    costs = settings["costs"]
    policy = settings["policy"]
    min_margin = _f(policy.get("min_margin_pct"), 15) / 100.0
    floors_usdt = {
        "storage": _f(costs.get("storage_usd_per_gib")) * (1 + min_margin),
        "bandwidth": _f(costs.get("bandwidth_usd_per_100mib")) * (1 + min_margin),
        "compute": _f(costs.get("compute_usd_per_gflop")) * (1 + min_margin),
        "upkeep": _f(costs.get("upkeep_usd_per_gib_month")) * (1 + min_margin),
    }
    min_usdt = max(1e-9, _f(policy.get("min_usdt_per_unit"), 1e-6))
    min_stone = max(1e-12, _f(policy.get("min_stone_per_unit"), 1e-8))
    fx = float(heuristic.get("usdt_per_stone") or usdt_per_stone())
    if fx <= 0:
        fx = 0.0001
    out_u, out_s = {}, {}
    for p in ("storage", "bandwidth", "compute", "upkeep"):
        u = max(min_usdt, floors_usdt[p], _f(rates_usdt.get(p), 0))
        s = max(min_stone, _f(rates_stone.get(p), 0))
        # If STONE price drifted below cost floor via FX, lift STONE
        stone_floor = floors_usdt[p] / fx if fx else min_stone
        s = max(s, stone_floor, min_stone)
        out_u[p] = float(_q(_d(u), "0.000001"))
        out_s[p] = float(_q(_d(s), "0.00000001"))
    return out_u, out_s


def adjust_rates(
    *,
    updated_by: str = "system",
    force_ai: bool = False,
    prefer_ai: Optional[bool] = None,
) -> Dict[str, Any]:
    """Recompute published rates from admin costs (AI or heuristic)."""
    settings = load_settings(use_cache=False)
    policy = settings["policy"]
    if prefer_ai is None:
        prefer_ai = bool(policy.get("prefer_ai", True))
    ai_enabled = bool(policy.get("ai_auto_adjust_enabled", True))

    heuristic = heuristic_rates(settings)
    result = heuristic
    ai_error = None
    if ai_enabled and prefer_ai and (force_ai or True):
        if _xai_api_key():
            try:
                result = _call_spacexai(settings, heuristic)
            except Exception as exc:
                ai_error = str(exc)[:300]
                result = heuristic
                result = dict(result)
                result["rationale"] = (
                    f"AI adjust failed ({ai_error}); used heuristic. "
                    + str(heuristic.get("rationale") or "")
                )[:2000]
        else:
            result = dict(heuristic)
            result["rationale"] = (
                "XAI_API_KEY not set; heuristic rates from admin costs. "
                + str(heuristic.get("rationale") or "")
            )[:2000]
    else:
        result = dict(heuristic)
        if not ai_enabled:
            result["rationale"] = (
                "AI auto-adjust disabled in admin; heuristic only. "
                + str(heuristic.get("rationale") or "")
            )[:2000]

    max_chg = _f(policy.get("max_rate_change_pct"), 25)
    prev_u = settings.get("rates_usdt") or {}
    prev_s = settings.get("rates_stone") or {}
    min_usdt = max(1e-9, _f(policy.get("min_usdt_per_unit"), 1e-6))
    min_stone = max(1e-12, _f(policy.get("min_stone_per_unit"), 1e-8))

    clamped_u, clamped_s = {}, {}
    for p in ("storage", "bandwidth", "compute", "upkeep"):
        clamped_u[p] = _clamp_change(
            _f(prev_u.get(p), result["rates_usdt"][p]),
            _f(result["rates_usdt"].get(p), 0),
            max_chg,
            min_usdt,
        )
        clamped_s[p] = _clamp_change(
            _f(prev_s.get(p), result["rates_stone"][p]),
            _f(result["rates_stone"].get(p), 0),
            max_chg,
            min_stone,
        )
    clamped_u, clamped_s = _enforce_floor(clamped_u, clamped_s, settings, heuristic)

    settings["rates_usdt"] = clamped_u
    settings["rates_stone"] = clamped_s
    settings["last_adjustment"] = {
        "at": int(time.time()),
        "method": result.get("method") or "heuristic",
        "rationale": str(result.get("rationale") or "")[:2000],
        "model": str(result.get("model") or ""),
        "confidence": _f(result.get("confidence"), 0.5),
        "factors": result.get("factors") if isinstance(result.get("factors"), list) else [],
        "ai_error": ai_error or "",
        "usdt_per_stone": float(heuristic.get("usdt_per_stone") or 0),
        "margin_pct": float(heuristic.get("margin_pct") or 0),
    }
    settings["updated_by"] = (updated_by or "system")[:64]
    settings["updated_at"] = int(time.time())

    write_body = {
        k: v
        for k, v in settings.items()
        if k
        not in (
            "config_path",
            "spacexai_key_configured",
            "model",
            "file_exists",
        )
    }
    saved = _write(write_body)
    saved["adjust_result"] = {
        "method": settings["last_adjustment"]["method"],
        "rates_usdt": clamped_u,
        "rates_stone": clamped_s,
        "rationale": settings["last_adjustment"]["rationale"],
        "ai_error": ai_error,
    }
    return saved


# ---------------------------------------------------------------------------
# Public getters for payment modules
# ---------------------------------------------------------------------------

def get_stone_rate(product: str) -> Decimal:
    """STONE per unit for storage|bandwidth|compute|upkeep."""
    p = (product or "").strip().lower()
    if p in ("data", "transfer"):
        p = "bandwidth"
    if p in ("storage-upkeep", "storage_upkeep", "retention"):
        p = "upkeep"
    s = load_settings()
    rates = s.get("rates_stone") or {}
    if p in rates and _f(rates[p]) > 0:
        return _d(rates[p])
    return _ENV_STONE.get(p, Decimal("1"))


def get_usdt_rate(product: str) -> Decimal:
    p = (product or "").strip().lower()
    if p in ("data", "transfer"):
        p = "bandwidth"
    if p in ("storage-upkeep", "storage_upkeep", "retention"):
        p = "upkeep"
    s = load_settings()
    rates = s.get("rates_usdt") or {}
    if p in rates and _f(rates[p]) > 0:
        return _d(rates[p])
    return _ENV_USDT.get(p, Decimal("0.01"))


def public_payload() -> Dict[str, Any]:
    s = load_settings()
    return {
        "ok": True,
        "costs": s.get("costs"),
        "policy": {
            k: v
            for k, v in (s.get("policy") or {}).items()
            if k
            in (
                "target_margin_pct",
                "min_margin_pct",
                "max_rate_change_pct",
                "ai_auto_adjust_enabled",
            )
        },
        "rates_usdt": s.get("rates_usdt"),
        "rates_stone": s.get("rates_stone"),
        "last_adjustment": s.get("last_adjustment"),
        "usdt_per_stone": float(usdt_per_stone()),
        "config_path": CONFIG_PATH,
        "spacexai_key_configured": bool(_xai_api_key()),
        "model": _xai_model(),
    }


def admin_context() -> Dict[str, Any]:
    s = load_settings()
    return {
        "data_rate_settings": s,
        "data_rate_costs": s.get("costs") or {},
        "data_rate_policy": s.get("policy") or {},
        "data_rate_usdt": s.get("rates_usdt") or {},
        "data_rate_stone": s.get("rates_stone") or {},
        "data_rate_last": s.get("last_adjustment") or {},
        "data_rate_spacexai": {
            "key_configured": bool(_xai_api_key()),
            "model": _xai_model(),
            "enabled": bool((s.get("policy") or {}).get("ai_auto_adjust_enabled")),
        },
    }
