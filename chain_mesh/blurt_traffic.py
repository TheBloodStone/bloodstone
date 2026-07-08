"""Public Blurt ↔ Bloodstone chain-mesh traffic accounting."""

from __future__ import annotations

import base64
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db
from chain_mesh.partner import BLURT_PARTNER_KEY_PREFIX


def is_blurt_asset_key(asset_key: str) -> bool:
    key = str(asset_key or "").strip().lstrip("/")
    return key.startswith(BLURT_PARTNER_KEY_PREFIX)


def format_bytes(byte_count: int) -> str:
    n = max(0, int(byte_count))
    if n >= 1024 ** 3:
        return f"{n / (1024 ** 3):.2f} GiB"
    if n >= 1024 ** 2:
        return f"{n / (1024 ** 2):.2f} MiB"
    if n >= 1024:
        return f"{n / 1024:.2f} KiB"
    return f"{n} B"


def partner_upload_bytes(payload: Dict[str, Any]) -> int:
    total = 0
    for item in payload.get("chunks") or []:
        if not isinstance(item, dict):
            continue
        raw_b64 = item.get("data_b64") or item.get("data")
        if not raw_b64:
            continue
        try:
            total += len(base64.b64decode(raw_b64, validate=True))
        except Exception:
            continue
    return total


def record_inbound(byte_count: int, *, requests: int = 1) -> None:
    mesh_db.record_blurt_traffic_daily(
        direction="in", byte_count=byte_count, requests=requests
    )


def record_outbound(byte_count: int, *, requests: int = 1) -> None:
    mesh_db.record_blurt_traffic_daily(
        direction="out", byte_count=byte_count, requests=requests
    )


def record_partner_upload(payload: Dict[str, Any]) -> int:
    nbytes = partner_upload_bytes(payload)
    if nbytes > 0:
        record_inbound(nbytes)
    return nbytes


def _day_to_date(day_utc: str) -> datetime:
    return datetime.strptime(day_utc, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _period_totals(
    rows: List[Dict[str, Any]],
) -> Dict[str, Dict[str, int]]:
    by_week: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"in_bytes": 0, "out_bytes": 0, "in_requests": 0, "out_requests": 0}
    )
    by_month: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"in_bytes": 0, "out_bytes": 0, "in_requests": 0, "out_requests": 0}
    )
    by_year: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"in_bytes": 0, "out_bytes": 0, "in_requests": 0, "out_requests": 0}
    )
    all_time = {
        "in_bytes": 0,
        "out_bytes": 0,
        "in_requests": 0,
        "out_requests": 0,
    }

    for row in rows:
        day = row["day_utc"]
        dt = _day_to_date(day)
        iso = dt.isocalendar()
        week_key = f"{iso[0]}-W{iso[1]:02d}"
        month_key = day[:7]
        year_key = day[:4]
        direction = row["direction"]
        nbytes = int(row["bytes"] or 0)
        nreq = int(row["requests"] or 0)

        for bucket in (by_week[week_key], by_month[month_key], by_year[year_key], all_time):
            if direction == "in":
                bucket["in_bytes"] += nbytes
                bucket["in_requests"] += nreq
            else:
                bucket["out_bytes"] += nbytes
                bucket["out_requests"] += nreq

    return {
        "by_week": dict(by_week),
        "by_month": dict(by_month),
        "by_year": dict(by_year),
        "all_time": all_time,
    }


def _summarize_period(label: str, totals: Dict[str, int]) -> Dict[str, Any]:
    in_b = int(totals.get("in_bytes") or 0)
    out_b = int(totals.get("out_bytes") or 0)
    return {
        "label": label,
        "in_bytes": in_b,
        "out_bytes": out_b,
        "net_bytes": in_b - out_b,
        "in_requests": int(totals.get("in_requests") or 0),
        "out_requests": int(totals.get("out_requests") or 0),
        "in_human": format_bytes(in_b),
        "out_human": format_bytes(out_b),
        "net_human": format_bytes(abs(in_b - out_b)),
    }


def _history_list(
    bucket: Dict[str, Dict[str, int]],
    *,
    limit: int,
    reverse: bool = True,
) -> List[Dict[str, Any]]:
    keys = sorted(bucket.keys(), reverse=reverse)
    out: List[Dict[str, Any]] = []
    for key in keys[:limit]:
        out.append(_summarize_period(key, bucket[key]))
    return out


def public_payload(*, history_limit: int = 52) -> Dict[str, Any]:
    rows = mesh_db.list_blurt_traffic_daily()
    grouped = _period_totals(rows)
    now = datetime.now(timezone.utc)
    week_label = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"
    month_label = now.strftime("%Y-%m")
    year_label = now.strftime("%Y")

    periods = {
        "week": _summarize_period(
            week_label, grouped["by_week"].get(week_label, {})
        ),
        "month": _summarize_period(
            month_label, grouped["by_month"].get(month_label, {})
        ),
        "year": _summarize_period(
            year_label, grouped["by_year"].get(year_label, {})
        ),
        "all_time": _summarize_period("all_time", grouped["all_time"]),
    }

    return {
        "ok": True,
        "partner": "blurt",
        "namespace": BLURT_PARTNER_KEY_PREFIX,
        "updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "description": (
            "Blurt partner traffic on Bloodstone chain mesh: "
            "inbound = chunk uploads via /api/chain-mesh/partner/upload; "
            "outbound = downloads and previews of assets/blurt/*."
        ),
        "periods": periods,
        "history": {
            "by_week": _history_list(grouped["by_week"], limit=history_limit),
            "by_month": _history_list(grouped["by_month"], limit=min(history_limit, 24)),
            "by_year": _history_list(grouped["by_year"], limit=10),
        },
    }