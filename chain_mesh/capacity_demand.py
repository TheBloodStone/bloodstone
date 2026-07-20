"""Mesh data capacity vs prepaid credit demand (provider planning meters).

Credits are purchased ahead of consumption, so outstanding prepaid credits are a
*demand signal* — providers see storage/bandwidth/compute commitment before it is
all burned. Surplus = effective capacity − demand.

Effective capacity = max(operator hard floor, soft fleet estimate).
Soft estimate grows with live mining / mesh / LAN / gateway / AI devices — mining
does not mint TiB, but an online fleet is a proxy for real capacity growth.

Windows (especially bandwidth & compute):
  burst   — peak concurrent / short-horizon headroom
  daily   — 24h network capacity limit vs demand
  monthly — 30d network capacity limit vs demand

Storage is treated as more static (capacity vs outstanding prepaid + used).
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Tuple

from chain_mesh import db as mesh_db
from chain_mesh import depin_credits as depin
from chain_mesh import storage_credits as storage

DAY_SEC = 86400
MONTH_SEC = 30 * DAY_SEC

# --- Supply (operator-configured fleet capacity; override via env) ---
# Storage: total durable bytes the fleet can hold.
STORAGE_CAPACITY_BYTES = int(
    os.environ.get("MESH_STORAGE_CAPACITY_BYTES", str(2 * 1024**4))  # 2 TiB default
)
# Bandwidth: burst (bytes/sec peak), daily and monthly transfer budgets.
BANDWIDTH_BURST_BYTES_PER_SEC = int(
    os.environ.get("MESH_BANDWIDTH_BURST_BPS", str(100 * 1024 * 1024))  # 100 MiB/s
)
BANDWIDTH_DAILY_BYTES = int(
    os.environ.get("MESH_BANDWIDTH_DAILY_BYTES", str(2 * 1024**4))  # 2 TiB/day
)
BANDWIDTH_MONTHLY_BYTES = int(
    os.environ.get("MESH_BANDWIDTH_MONTHLY_BYTES", str(40 * 1024**4))  # 40 TiB/mo
)
# Compute: burst concurrent FLOPS capacity, plus daily/monthly FLOP budgets.
COMPUTE_BURST_FLOPS = int(
    os.environ.get("MESH_COMPUTE_BURST_FLOPS", str(50_000_000_000))  # 50 GFLOP burst pool
)
COMPUTE_DAILY_FLOPS = int(
    os.environ.get("MESH_COMPUTE_DAILY_FLOPS", str(5_000_000_000_000))  # 5 TFLOP·day
)
COMPUTE_MONTHLY_FLOPS = int(
    os.environ.get("MESH_COMPUTE_MONTHLY_FLOPS", str(100_000_000_000_000))
)

# Soft per-device estimates (fleet proxy — not consensus, not coin-supply-linked).
FLEET_ACTIVE_SEC = int(os.environ.get("MESH_FLEET_ACTIVE_SEC", "1800"))  # 30 min
SOFT_STORAGE_FULL_NODE_BYTES = int(
    os.environ.get("MESH_SOFT_STORAGE_FULL_BYTES", str(50 * 1024**3))
)
SOFT_STORAGE_PRUNED_BYTES = int(
    os.environ.get("MESH_SOFT_STORAGE_PRUNED_BYTES", str(10 * 1024**3))
)
SOFT_STORAGE_MESH_BYTES = int(
    os.environ.get("MESH_SOFT_STORAGE_MESH_BYTES", str(20 * 1024**3))
)
SOFT_STORAGE_PEER_DEFAULT_BYTES = int(
    os.environ.get("MESH_SOFT_STORAGE_PEER_DEFAULT_BYTES", str(512 * 1024**2))
)
SOFT_STORAGE_ANDROID_PEER_BYTES = int(
    os.environ.get("MESH_SOFT_STORAGE_ANDROID_BYTES", str(5 * 1024**3))
)
SOFT_BW_GATEWAY_BPS = int(
    os.environ.get("MESH_SOFT_BW_GATEWAY_BPS", str(20 * 1024 * 1024 // 8))
)  # ~20 Mbit/s → bytes/s
SOFT_BW_ANDROID_BPS = int(
    os.environ.get("MESH_SOFT_BW_ANDROID_BPS", str(5 * 1024 * 1024 // 8))
)
SOFT_BW_FULL_NODE_BPS = int(
    os.environ.get("MESH_SOFT_BW_FULL_NODE_BPS", str(10 * 1024 * 1024 // 8))
)
SOFT_BW_MINER_BPS = int(
    os.environ.get("MESH_SOFT_BW_MINER_BPS", str(1 * 1024 * 1024 // 8))
)
SOFT_BW_DUTY_DAILY = float(os.environ.get("MESH_SOFT_BW_DUTY_DAILY", "0.25"))
SOFT_FLOPS_PER_AI_DEFAULT = int(
    os.environ.get("MESH_SOFT_FLOPS_PER_AI_DEFAULT", str(500_000_000))
)
SOFT_FLOPS_PER_ANDROID = int(
    os.environ.get("MESH_SOFT_FLOPS_PER_ANDROID", str(1_000_000_000))
)
SOFT_FLOPS_PER_ACTIVE_MINER = int(
    os.environ.get("MESH_SOFT_FLOPS_PER_ACTIVE_MINER", str(200_000_000))
)
SOFT_FLOPS_PER_PI = int(
    os.environ.get("MESH_SOFT_FLOPS_PER_PI", str(2_000_000_000))
)
# How soft fleet estimate combines with operator hard floor.
# max = fleet can raise meters above floor; sum = fleet adds on top of floor.
SOFT_BLEND = (os.environ.get("MESH_SOFT_CAPACITY_BLEND", "max") or "max").strip().lower()

# Surplus color thresholds (fraction of capacity remaining).
# green: surplus_ratio >= GREEN_MIN
# yellow: 0 <= surplus_ratio < GREEN_MIN
# red: surplus < 0 (negative surplus / oversold)
GREEN_MIN = float(os.environ.get("MESH_CAPACITY_GREEN_MIN", "0.20"))
YELLOW_MIN = float(os.environ.get("MESH_CAPACITY_YELLOW_MIN", "0.0"))


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def _blend(hard: int, soft: int) -> int:
    hard = max(0, int(hard))
    soft = max(0, int(soft))
    if SOFT_BLEND == "sum":
        return hard + soft
    if SOFT_BLEND == "soft":
        return soft if soft > 0 else hard
    # default: max — operator floor until fleet estimate exceeds it
    return max(hard, soft)


def _estimate_fleet_soft_capacity() -> Dict[str, Any]:
    """Live fleet → soft capacity proxy (mining/mesh devices, not coin mint)."""
    now = _now()
    cutoff = now - FLEET_ACTIVE_SEC
    signals: Dict[str, Any] = {
        "window_sec": FLEET_ACTIVE_SEC,
        "as_of": now,
        "lan_nodes_active": 0,
        "lan_full": 0,
        "lan_pruned": 0,
        "lan_mesh": 0,
        "lan_consensus": 0,
        "lan_android": 0,
        "storage_peers_active": 0,
        "storage_peers_reported_bytes": 0,
        "gateways_active": 0,
        "local_nodes_active": 0,
        "witness_devices_recent": 0,
        "pool_active_devices": 0,
        "pool_android_native": 0,
        "pool_miners_with_hashrate": 0,
        "ai_providers_active": 0,
        "ai_flops_per_sec": 0,
    }
    soft_storage = 0
    soft_bw_bps = 0
    soft_compute_burst = 0

    # --- Mesh LAN / storage / gateways ---
    try:
        with _conn() as conn:
            lan_rows = conn.execute(
                """
                SELECT device_id, peer_kind, mode, consensus_only, chain_bytes,
                       last_seen, pruned
                FROM chain_lan_nodes
                WHERE last_seen >= ?
                """,
                (cutoff,),
            ).fetchall()
            signals["lan_nodes_active"] = len(lan_rows)
            seen_lan = set()
            for r in lan_rows:
                did = str(r["device_id"] or "")
                if did in seen_lan:
                    continue
                seen_lan.add(did)
                mode = str(r["mode"] or "").lower()
                kind = str(r["peer_kind"] or "").lower()
                consensus_only = int(r["consensus_only"] or 0)
                if kind == "android":
                    signals["lan_android"] += 1
                if mode in ("full",) and not consensus_only:
                    signals["lan_full"] += 1
                    soft_storage += SOFT_STORAGE_FULL_NODE_BYTES
                    soft_bw_bps += SOFT_BW_FULL_NODE_BPS
                    soft_compute_burst += SOFT_FLOPS_PER_ANDROID if kind == "android" else SOFT_FLOPS_PER_PI
                elif mode in ("mesh", "mesh-federation", "federation"):
                    signals["lan_mesh"] += 1
                    soft_storage += SOFT_STORAGE_MESH_BYTES
                    soft_bw_bps += SOFT_BW_FULL_NODE_BPS // 2
                    soft_compute_burst += SOFT_FLOPS_PER_ANDROID // 2
                elif mode in ("pruned", "prune"):
                    signals["lan_pruned"] += 1
                    soft_storage += SOFT_STORAGE_PRUNED_BYTES
                    soft_bw_bps += SOFT_BW_ANDROID_BPS if kind == "android" else SOFT_BW_MINER_BPS
                    soft_compute_burst += SOFT_FLOPS_PER_ANDROID // 2
                elif mode in ("consensus", "consensus-witness", "consensus_witness") or consensus_only:
                    signals["lan_consensus"] += 1
                    soft_storage += SOFT_STORAGE_PRUNED_BYTES // 2
                    soft_compute_burst += SOFT_FLOPS_PER_ACTIVE_MINER
                else:
                    soft_storage += SOFT_STORAGE_PEER_DEFAULT_BYTES
                    soft_bw_bps += SOFT_BW_MINER_BPS
                    soft_compute_burst += SOFT_FLOPS_PER_ACTIVE_MINER

            peers = conn.execute(
                """
                SELECT device_id, peer_kind, capacity_bytes, chunks_held, last_seen
                FROM chain_storage_peers
                WHERE last_seen >= ?
                """,
                (cutoff,),
            ).fetchall()
            signals["storage_peers_active"] = len(peers)
            for r in peers:
                cap = int(r["capacity_bytes"] or 0)
                kind = str(r["peer_kind"] or "").lower()
                if cap > 0:
                    soft_storage += cap
                    signals["storage_peers_reported_bytes"] += cap
                elif kind == "android":
                    soft_storage += SOFT_STORAGE_ANDROID_PEER_BYTES
                else:
                    soft_storage += SOFT_STORAGE_PEER_DEFAULT_BYTES

            gws = conn.execute(
                """
                SELECT device_id, peer_kind, share_internet, last_seen
                FROM chain_mesh_internet_gateways
                WHERE last_seen >= ? AND COALESCE(share_internet, 0) = 1
                """,
                (cutoff,),
            ).fetchall()
            signals["gateways_active"] = len(gws)
            soft_bw_bps += len(gws) * SOFT_BW_GATEWAY_BPS

            local_n = conn.execute(
                "SELECT COUNT(*) AS n FROM chain_local_nodes WHERE last_seen >= ?",
                (cutoff,),
            ).fetchone()
            signals["local_nodes_active"] = int(local_n["n"] if local_n else 0)

            wit = conn.execute(
                """
                SELECT COUNT(DISTINCT device_id) AS n
                FROM quasar_witness_capsules
                WHERE created_at >= ?
                """,
                (cutoff,),
            ).fetchone()
            signals["witness_devices_recent"] = int(wit["n"] if wit else 0)
            # Witness-only devices: light soft compute (observation), not storage mint
            soft_compute_burst += signals["witness_devices_recent"] * (
                SOFT_FLOPS_PER_ACTIVE_MINER // 2
            )
    except Exception as exc:
        signals["mesh_error"] = str(exc)

    # --- Pool mining fleet (hash nodes; soft BW/compute proxy only) ---
    try:
        import pool_device_fleet as pdf

        stats = pdf.fleet_public_stats() or {}
        signals["pool_active_devices"] = int(stats.get("active_devices") or 0)
        signals["pool_android_native"] = int(stats.get("android_native_tcp") or 0)
        signals["pool_browser_bridge"] = int(stats.get("browser_bridge") or 0)
        signals["pool_total_reported_hashrate"] = float(
            stats.get("total_reported_hashrate") or 0
        )
        soft_bw_bps += signals["pool_android_native"] * SOFT_BW_ANDROID_BPS
        soft_bw_bps += int(stats.get("browser_bridge") or 0) * (SOFT_BW_MINER_BPS // 2)
        soft_compute_burst += signals["pool_active_devices"] * SOFT_FLOPS_PER_ACTIVE_MINER
        soft_compute_burst += signals["pool_android_native"] * SOFT_FLOPS_PER_ANDROID
    except Exception as exc:
        signals["pool_fleet_error"] = str(exc)

    try:
        import pool_db

        hr = pool_db.get_miner_hashrates() or {}
        if isinstance(hr, dict):
            signals["pool_miners_with_hashrate"] = len(hr)
            soft_compute_burst += len(hr) * SOFT_FLOPS_PER_ACTIVE_MINER
    except Exception as exc:
        signals["pool_hashrate_error"] = str(exc)

    # --- AI / compute providers ---
    try:
        from chain_mesh import ai_provider as aip

        payload = aip.list_ai_providers(limit=200) or {}
        providers = payload.get("providers") if isinstance(payload, dict) else payload
        if not isinstance(providers, list):
            providers = []
        active_ai = 0
        flops_ps = 0
        for p in providers:
            ls = int(p.get("last_seen") or 0)
            if ls and ls < cutoff:
                continue
            active_ai += 1
            fps = int(p.get("flops_per_sec") or 0)
            if fps <= 0:
                fps = SOFT_FLOPS_PER_AI_DEFAULT
            flops_ps += fps
            # Burst pool ≈ 1 hour at advertised flops/sec
            soft_compute_burst += fps * 3600
            name = str(p.get("display_name") or p.get("node_id") or "").lower()
            if "pi" in name:
                soft_storage += SOFT_STORAGE_PRUNED_BYTES
                soft_bw_bps += SOFT_BW_MINER_BPS
        signals["ai_providers_active"] = active_ai
        signals["ai_flops_per_sec"] = flops_ps
    except Exception as exc:
        signals["ai_error"] = str(exc)

    soft_bw_daily = int(soft_bw_bps * DAY_SEC * SOFT_BW_DUTY_DAILY)
    soft_bw_monthly = soft_bw_daily * 30
    soft_bw_burst_pool = soft_bw_bps * 3600
    soft_compute_daily = soft_compute_burst * 4  # assume burst pool recycles ~4×/day
    soft_compute_monthly = soft_compute_daily * 30

    return {
        "signals": signals,
        "soft": {
            "storage_bytes": int(soft_storage),
            "storage_bytes_display": _human_bytes(int(soft_storage)),
            "bandwidth_bps": int(soft_bw_bps),
            "bandwidth_rate_display": _human_rate(int(soft_bw_bps)),
            "bandwidth_burst_pool_1h": int(soft_bw_burst_pool),
            "bandwidth_burst_pool_1h_display": _human_bytes(int(soft_bw_burst_pool)),
            "bandwidth_daily_bytes": int(soft_bw_daily),
            "bandwidth_daily_display": _human_bytes(int(soft_bw_daily)),
            "bandwidth_monthly_bytes": int(soft_bw_monthly),
            "bandwidth_monthly_display": _human_bytes(int(soft_bw_monthly)),
            "compute_burst_flops": int(soft_compute_burst),
            "compute_burst_display": _human_flops(int(soft_compute_burst)),
            "compute_daily_flops": int(soft_compute_daily),
            "compute_daily_display": _human_flops(int(soft_compute_daily)),
            "compute_monthly_flops": int(soft_compute_monthly),
            "compute_monthly_display": _human_flops(int(soft_compute_monthly)),
        },
        "note": (
            "Soft capacity is estimated from live mining/mesh fleet signals "
            "(LAN nodes, storage peers, gateways, pool devices, AI providers). "
            "Coins mined do not mint capacity; online devices do."
        ),
        "blend": SOFT_BLEND,
    }


def _human_bytes(n: int) -> str:
    n = int(n)
    sign = "-" if n < 0 else ""
    n = abs(n)
    for unit, div in (
        ("TiB", 1024**4),
        ("GiB", 1024**3),
        ("MiB", 1024**2),
        ("KiB", 1024),
    ):
        if n >= div:
            return f"{sign}{n / div:.2f} {unit}"
    return f"{sign}{n} B"


def _human_flops(n: int) -> str:
    n = int(n)
    sign = "-" if n < 0 else ""
    n = abs(n)
    for unit, div in (
        ("PFLOP", 10**15),
        ("TFLOP", 10**12),
        ("GFLOP", 10**9),
        ("MFLOP", 10**6),
    ):
        if n >= div:
            return f"{sign}{n / div:.2f} {unit}"
    return f"{sign}{n} FLOP"


def _human_rate(bps: int) -> str:
    return f"{_human_bytes(bps)}/s"


def _level(surplus: float, capacity: float) -> str:
    if capacity <= 0:
        return "unknown"
    ratio = float(surplus) / float(capacity)
    if surplus < 0 or ratio < YELLOW_MIN:
        return "red"
    if ratio < GREEN_MIN:
        return "yellow"
    return "green"


def _meter(surplus: float, capacity: float) -> Dict[str, Any]:
    cap = float(capacity)
    sur = float(surplus)
    util = 0.0
    surplus_fill = 0.0
    if cap > 0:
        util = max(0.0, min(2.0, (cap - sur) / cap))  # 1.0 = full demand, >1 oversold
        # Bar fill = remaining surplus (1.0 = fully free/healthy; 0 = exhausted; clamp)
        surplus_fill = max(0.0, min(1.0, sur / cap))
    level = _level(sur, cap)
    return {
        "surplus": int(sur),
        "capacity": int(cap),
        "utilization": round(util, 4),
        "surplus_ratio": round(sur / cap, 4) if cap > 0 else None,
        "surplus_fill": round(surplus_fill, 4),  # UI meter: full green = healthy surplus
        "level": level,  # green | yellow | red | unknown
        "label": {
            "green": "surplus healthy",
            "yellow": "surplus thin — scale soon",
            "red": "negative surplus — oversold / deploy capacity",
            "unknown": "capacity not configured",
        }.get(level, level),
    }


def _sum_ledger(
    table: str,
    credit_col: str,
    *,
    since: Optional[int] = None,
) -> int:
    sql = f"SELECT COALESCE(SUM({credit_col}), 0) AS total FROM {table}"
    params: Tuple = ()
    if since is not None:
        sql += " WHERE created_at >= ?"
        params = (int(since),)
    try:
        with _conn() as conn:
            row = conn.execute(sql, params).fetchone()
            return int(row["total"] if row else 0)
    except Exception:
        return 0


def _sum_usage(table: str, used_col: str) -> int:
    try:
        with _conn() as conn:
            row = conn.execute(
                f"SELECT COALESCE(SUM({used_col}), 0) AS total FROM {table}"
            ).fetchone()
            return int(row["total"] if row else 0)
    except Exception:
        return 0


def _count_buyers(table: str) -> int:
    try:
        with _conn() as conn:
            row = conn.execute(
                f"SELECT COUNT(DISTINCT stone_address) AS n FROM {table}"
            ).fetchone()
            return int(row["n"] if row else 0)
    except Exception:
        return 0


def _ledger_snapshot(
    *,
    table: str,
    credit_col: str,
    usage_table: str,
    usage_col: str,
) -> Dict[str, Any]:
    now = _now()
    storage.init_storage_credits_db()
    depin.init_depin_db()
    total_credited = _sum_ledger(table, credit_col)
    purchased_24h = _sum_ledger(table, credit_col, since=now - DAY_SEC)
    purchased_30d = _sum_ledger(table, credit_col, since=now - MONTH_SEC)
    total_used = _sum_usage(usage_table, usage_col)
    remaining = max(0, total_credited - total_used)
    buyers = _count_buyers(table)
    return {
        "total_credited": total_credited,
        "total_used": total_used,
        "outstanding_prepaid": remaining,
        "purchased_24h": purchased_24h,
        "purchased_30d": purchased_30d,
        "unique_buyers": buyers,
    }


def _storage_product(fleet: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    snap = _ledger_snapshot(
        table="storage_credit_ledger",
        credit_col="bytes_credited",
        usage_table="storage_usage",
        usage_col="bytes_used",
    )
    hard = STORAGE_CAPACITY_BYTES
    soft = int((fleet or {}).get("soft", {}).get("storage_bytes") or 0)
    capacity = _blend(hard, soft)
    # Occupied disk ≈ used; outstanding prepaid = signalled-but-not-yet-written demand.
    demand = snap["total_used"] + snap["outstanding_prepaid"]
    surplus = capacity - demand
    meter = _meter(surplus, capacity)
    return {
        "product": "storage",
        "unit": "bytes",
        "display_unit": "bytes",
        "note": (
            "Storage is relatively static: outstanding prepaid credits signal future "
            "write demand; used bytes occupy capacity now. Soft capacity rises with "
            "online full/pruned/mesh nodes and storage peers."
        ),
        "demand": {
            "outstanding_prepaid": snap["outstanding_prepaid"],
            "outstanding_prepaid_display": _human_bytes(snap["outstanding_prepaid"]),
            "used": snap["total_used"],
            "used_display": _human_bytes(snap["total_used"]),
            "total_committed": demand,
            "total_committed_display": _human_bytes(demand),
            "purchased_24h": snap["purchased_24h"],
            "purchased_24h_display": _human_bytes(snap["purchased_24h"]),
            "purchased_30d": snap["purchased_30d"],
            "purchased_30d_display": _human_bytes(snap["purchased_30d"]),
            "unique_buyers": snap["unique_buyers"],
        },
        "supply": {
            "hard_capacity": hard,
            "hard_capacity_display": _human_bytes(hard),
            "soft_capacity": soft,
            "soft_capacity_display": _human_bytes(soft),
            "capacity": capacity,
            "capacity_display": _human_bytes(capacity),
            "blend": SOFT_BLEND,
            "source": "max/sum(MESH_STORAGE_CAPACITY_BYTES, fleet soft estimate)",
        },
        "windows": {
            # Storage uses a single static window + purchase rates for reaction time.
            "static": {
                **meter,
                "surplus_display": _human_bytes(int(meter["surplus"])),
                "capacity_display": _human_bytes(int(meter["capacity"])),
            },
            "daily_inflow": {
                "purchased": snap["purchased_24h"],
                "purchased_display": _human_bytes(snap["purchased_24h"]),
                "hint": "New prepaid demand in last 24h — scale disks if sustained",
            },
            "monthly_inflow": {
                "purchased": snap["purchased_30d"],
                "purchased_display": _human_bytes(snap["purchased_30d"]),
                "hint": "New prepaid demand in last 30d",
            },
        },
        "level": meter["level"],
        "headline": meter["label"],
    }


def _bandwidth_product(fleet: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    snap = _ledger_snapshot(
        table="bandwidth_credit_ledger",
        credit_col="bytes_credited",
        usage_table="bandwidth_usage",
        usage_col="bytes_used",
    )
    soft = (fleet or {}).get("soft") or {}
    hard_bps = BANDWIDTH_BURST_BYTES_PER_SEC
    soft_bps = int(soft.get("bandwidth_bps") or 0)
    eff_bps = _blend(hard_bps, soft_bps)
    # Burst: treat outstanding prepaid as if it could be drawn quickly —
    # compare to burst capacity * 1 hour as a short-horizon pool, plus bps meter.
    hard_burst_pool = hard_bps * 3600
    soft_burst_pool = int(soft.get("bandwidth_burst_pool_1h") or soft_bps * 3600)
    burst_pool = _blend(hard_burst_pool, soft_burst_pool)
    daily_cap = _blend(
        BANDWIDTH_DAILY_BYTES, int(soft.get("bandwidth_daily_bytes") or 0)
    )
    monthly_cap = _blend(
        BANDWIDTH_MONTHLY_BYTES, int(soft.get("bandwidth_monthly_bytes") or 0)
    )

    # Demand signals:
    # - burst: outstanding prepaid (could burst-download)
    # - daily: max(purchased_24h, usage if available portion) — use outstanding
    #   amortized + 24h purchases as reaction signal
    demand_burst = snap["outstanding_prepaid"]
    demand_daily = max(snap["purchased_24h"], min(snap["outstanding_prepaid"], daily_cap))
    # If nothing purchased but large outstanding, daily demand ≈ outstanding / 30
    # capped — prefer explicit purchases; fall back to outstanding slice.
    if snap["purchased_24h"] == 0 and snap["outstanding_prepaid"] > 0:
        demand_daily = max(demand_daily, snap["outstanding_prepaid"] // 30)
    demand_monthly = max(snap["purchased_30d"], snap["outstanding_prepaid"])

    m_burst = _meter(burst_pool - demand_burst, burst_pool)
    m_daily = _meter(daily_cap - demand_daily, daily_cap)
    m_monthly = _meter(monthly_cap - demand_monthly, monthly_cap)

    # Worst level among windows drives headline (red > yellow > green).
    levels = [m_burst["level"], m_daily["level"], m_monthly["level"]]
    headline_level = "green"
    if "red" in levels:
        headline_level = "red"
    elif "yellow" in levels:
        headline_level = "yellow"

    def _win(m: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **m,
            "surplus_display": _human_bytes(int(m["surplus"])),
            "capacity_display": _human_bytes(int(m["capacity"])),
        }

    return {
        "product": "bandwidth",
        "unit": "bytes",
        "note": (
            "Bandwidth is dynamic: outstanding credits can be burned in bursts. "
            "Watch burst surplus for peak headroom; daily/monthly for sustained load."
        ),
        "demand": {
            "outstanding_prepaid": snap["outstanding_prepaid"],
            "outstanding_prepaid_display": _human_bytes(snap["outstanding_prepaid"]),
            "used": snap["total_used"],
            "used_display": _human_bytes(snap["total_used"]),
            "purchased_24h": snap["purchased_24h"],
            "purchased_24h_display": _human_bytes(snap["purchased_24h"]),
            "purchased_30d": snap["purchased_30d"],
            "purchased_30d_display": _human_bytes(snap["purchased_30d"]),
            "unique_buyers": snap["unique_buyers"],
            "burst_demand": demand_burst,
            "burst_demand_display": _human_bytes(demand_burst),
            "daily_demand": demand_daily,
            "daily_demand_display": _human_bytes(demand_daily),
            "monthly_demand": demand_monthly,
            "monthly_demand_display": _human_bytes(demand_monthly),
        },
        "supply": {
            "hard_burst_bytes_per_sec": hard_bps,
            "soft_burst_bytes_per_sec": soft_bps,
            "burst_bytes_per_sec": eff_bps,
            "burst_rate_display": _human_rate(eff_bps),
            "hard_burst_pool_1h": hard_burst_pool,
            "soft_burst_pool_1h": soft_burst_pool,
            "burst_pool_1h": burst_pool,
            "burst_pool_1h_display": _human_bytes(burst_pool),
            "hard_daily_capacity": BANDWIDTH_DAILY_BYTES,
            "soft_daily_capacity": int(soft.get("bandwidth_daily_bytes") or 0),
            "daily_capacity": daily_cap,
            "daily_capacity_display": _human_bytes(daily_cap),
            "hard_monthly_capacity": BANDWIDTH_MONTHLY_BYTES,
            "soft_monthly_capacity": int(soft.get("bandwidth_monthly_bytes") or 0),
            "monthly_capacity": monthly_cap,
            "monthly_capacity_display": _human_bytes(monthly_cap),
            "blend": SOFT_BLEND,
            "source": "hard MESH_BANDWIDTH_* blended with live gateway/LAN/pool soft estimate",
        },
        "windows": {
            "burst": _win(m_burst),
            "daily": _win(m_daily),
            "monthly": _win(m_monthly),
        },
        "level": headline_level,
        "headline": {
            "green": "bandwidth surplus healthy",
            "yellow": "bandwidth surplus thin — add uplink soon",
            "red": "bandwidth negative surplus — oversold",
            "unknown": "capacity not configured",
        }.get(headline_level, headline_level),
    }


def _compute_product(fleet: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    snap = _ledger_snapshot(
        table="compute_credit_ledger",
        credit_col="flops_credited",
        usage_table="compute_usage",
        usage_col="flops_used",
    )
    soft = (fleet or {}).get("soft") or {}
    burst_cap = _blend(
        COMPUTE_BURST_FLOPS, int(soft.get("compute_burst_flops") or 0)
    )
    daily_cap = _blend(
        COMPUTE_DAILY_FLOPS, int(soft.get("compute_daily_flops") or 0)
    )
    monthly_cap = _blend(
        COMPUTE_MONTHLY_FLOPS, int(soft.get("compute_monthly_flops") or 0)
    )

    demand_burst = snap["outstanding_prepaid"]
    demand_daily = max(snap["purchased_24h"], min(snap["outstanding_prepaid"], daily_cap))
    if snap["purchased_24h"] == 0 and snap["outstanding_prepaid"] > 0:
        demand_daily = max(demand_daily, snap["outstanding_prepaid"] // 30)
    demand_monthly = max(snap["purchased_30d"], snap["outstanding_prepaid"])

    m_burst = _meter(burst_cap - demand_burst, burst_cap)
    m_daily = _meter(daily_cap - demand_daily, daily_cap)
    m_monthly = _meter(monthly_cap - demand_monthly, monthly_cap)

    levels = [m_burst["level"], m_daily["level"], m_monthly["level"]]
    headline_level = "green"
    if "red" in levels:
        headline_level = "red"
    elif "yellow" in levels:
        headline_level = "yellow"

    def _win(m: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **m,
            "surplus_display": _human_flops(int(m["surplus"])),
            "capacity_display": _human_flops(int(m["capacity"])),
        }

    return {
        "product": "compute",
        "unit": "flops",
        "note": (
            "Compute credits are prepaid FLOPs. Burst surplus = can we absorb a large "
            "job queue now; daily/monthly = fleet FLOP budgets vs credit demand."
        ),
        "demand": {
            "outstanding_prepaid": snap["outstanding_prepaid"],
            "outstanding_prepaid_display": _human_flops(snap["outstanding_prepaid"]),
            "used": snap["total_used"],
            "used_display": _human_flops(snap["total_used"]),
            "purchased_24h": snap["purchased_24h"],
            "purchased_24h_display": _human_flops(snap["purchased_24h"]),
            "purchased_30d": snap["purchased_30d"],
            "purchased_30d_display": _human_flops(snap["purchased_30d"]),
            "unique_buyers": snap["unique_buyers"],
            "burst_demand": demand_burst,
            "burst_demand_display": _human_flops(demand_burst),
            "daily_demand": demand_daily,
            "daily_demand_display": _human_flops(demand_daily),
            "monthly_demand": demand_monthly,
            "monthly_demand_display": _human_flops(demand_monthly),
        },
        "supply": {
            "hard_burst_capacity": COMPUTE_BURST_FLOPS,
            "soft_burst_capacity": int(soft.get("compute_burst_flops") or 0),
            "burst_capacity": burst_cap,
            "burst_capacity_display": _human_flops(burst_cap),
            "hard_daily_capacity": COMPUTE_DAILY_FLOPS,
            "soft_daily_capacity": int(soft.get("compute_daily_flops") or 0),
            "daily_capacity": daily_cap,
            "daily_capacity_display": _human_flops(daily_cap),
            "hard_monthly_capacity": COMPUTE_MONTHLY_FLOPS,
            "soft_monthly_capacity": int(soft.get("compute_monthly_flops") or 0),
            "monthly_capacity": monthly_cap,
            "monthly_capacity_display": _human_flops(monthly_cap),
            "blend": SOFT_BLEND,
            "source": "hard MESH_COMPUTE_* blended with live AI/miners/LAN soft estimate",
        },
        "windows": {
            "burst": _win(m_burst),
            "daily": _win(m_daily),
            "monthly": _win(m_monthly),
        },
        "level": headline_level,
        "headline": {
            "green": "compute surplus healthy",
            "yellow": "compute surplus thin — add workers soon",
            "red": "compute negative surplus — oversold",
            "unknown": "capacity not configured",
        }.get(headline_level, headline_level),
    }


def capacity_demand_payload() -> Dict[str, Any]:
    """Full payload for explorer / API / data-sales."""
    try:
        storage.init_storage_credits_db()
    except Exception:
        pass
    try:
        depin.init_depin_db()
    except Exception:
        pass

    fleet = _estimate_fleet_soft_capacity()
    products = {
        "storage": _storage_product(fleet),
        "bandwidth": _bandwidth_product(fleet),
        "compute": _compute_product(fleet),
    }
    overall = "green"
    for p in products.values():
        if p.get("level") == "red":
            overall = "red"
            break
        if p.get("level") == "yellow" and overall != "red":
            overall = "yellow"

    sig = fleet.get("signals") or {}
    return {
        "ok": True,
        "updated": _now(),
        "model": "prepaid-credits-demand-signal+fleet-soft-capacity",
        "summary": (
            "Consumers buy STONE credits ahead of use (demand signal). "
            "Effective capacity = operator hard floor blended with soft estimates from "
            "the live mining/mesh fleet (LAN nodes, storage peers, gateways, pool devices, "
            "AI providers). Mining coins does not mint capacity — online devices do. "
            "Meters: green = healthy surplus, yellow = thin, red = negative surplus."
        ),
        "overall_level": overall,
        "thresholds": {
            "green_min_surplus_ratio": GREEN_MIN,
            "yellow_min_surplus_ratio": YELLOW_MIN,
            "red": "surplus < 0 (demand exceeds capacity)",
        },
        "fleet": fleet,
        "fleet_headline": (
            f"{sig.get('lan_nodes_active', 0)} LAN · "
            f"{sig.get('storage_peers_active', 0)} storage peers · "
            f"{sig.get('gateways_active', 0)} gateways · "
            f"{sig.get('pool_active_devices', 0)} pool devices · "
            f"{sig.get('pool_miners_with_hashrate', 0)} hashrate miners · "
            f"{sig.get('ai_providers_active', 0)} AI · "
            f"{sig.get('witness_devices_recent', 0)} witnesses"
        ),
        "products": products,
        "data_sales": "/data/",
        "claim_api": "/api/data-sales/claim",
    }
