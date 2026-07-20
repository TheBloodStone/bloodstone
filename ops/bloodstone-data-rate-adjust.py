#!/usr/bin/env python3
"""Hourly (or on-demand) data/processing rate re-adjust.

Invoked by systemd timer ``bloodstone-data-rate-adjust.timer``.
Reads operator costs from ``/var/lib/bloodstone/data-sales-rate-settings.json``
and recomputes USDT + STONE rates via SpaceXAI (or heuristic fallback).

Env:
  DATA_SALES_RATE_HOURLY_ENABLE=0  — exit 0 without adjusting
  DATA_SALES_RATE_FORCE_AI=1       — prefer AI even if last method was heuristic
  DATA_SALES_RATE_SETTINGS_PATH    — config path override
  XAI_API_KEY / XAI_MODEL / XAI_BASE_URL — SpaceXAI
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

# VPS layout: modules under /root
if "/root" not in sys.path:
    sys.path.insert(0, "/root")


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"{ts} {msg}", flush=True)


def main() -> int:
    if os.environ.get("DATA_SALES_RATE_HOURLY_ENABLE", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        _log("hourly adjust disabled (DATA_SALES_RATE_HOURLY_ENABLE=0)")
        return 0

    import data_sales_rate_settings as drs

    settings = drs.load_settings(use_cache=False)
    policy = settings.get("policy") or {}
    if not policy.get("ai_auto_adjust_enabled", True) and os.environ.get(
        "DATA_SALES_RATE_IGNORE_POLICY", ""
    ).strip().lower() not in ("1", "true", "yes", "on"):
        # Still run heuristic if admin left AI off but costs exist — use adjust with prefer_ai=False
        prefer_ai = False
        _log("policy.ai_auto_adjust_enabled=false → heuristic-only adjust")
    else:
        prefer_ai = bool(policy.get("prefer_ai", True))

    force_ai = os.environ.get("DATA_SALES_RATE_FORCE_AI", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    t0 = time.time()
    try:
        result = drs.adjust_rates(
            updated_by="hourly-timer",
            force_ai=force_ai,
            prefer_ai=prefer_ai,
        )
    except Exception as exc:
        _log(f"ERROR adjust_rates failed: {exc}")
        return 1

    last = result.get("last_adjustment") or {}
    rates_u = result.get("rates_usdt") or {}
    rates_s = result.get("rates_stone") or {}
    elapsed = time.time() - t0
    _log(
        "ok method={method} model={model} conf={conf} elapsed_s={elapsed:.1f}".format(
            method=last.get("method"),
            model=last.get("model") or "-",
            conf=last.get("confidence"),
            elapsed=elapsed,
        )
    )
    _log(
        "rates_usdt storage={s} bw={b} compute={c} upkeep={u}".format(
            s=rates_u.get("storage"),
            b=rates_u.get("bandwidth"),
            c=rates_u.get("compute"),
            u=rates_u.get("upkeep"),
        )
    )
    _log(
        "rates_stone storage={s} bw={b} compute={c} upkeep={u}".format(
            s=rates_s.get("storage"),
            b=rates_s.get("bandwidth"),
            c=rates_s.get("compute"),
            u=rates_s.get("upkeep"),
        )
    )
    if last.get("ai_error"):
        _log(f"ai_error={last.get('ai_error')}")
    rationale = (last.get("rationale") or "")[:300]
    if rationale:
        _log(f"rationale={rationale}")

    # Optional machine-readable line for log scrapers
    summary = {
        "ok": True,
        "at": last.get("at"),
        "method": last.get("method"),
        "rates_usdt": rates_u,
        "rates_stone": rates_s,
    }
    _log("json " + json.dumps(summary, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
