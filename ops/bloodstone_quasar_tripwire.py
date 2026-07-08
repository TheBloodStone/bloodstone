"""QUASAR Phase 2 — anomaly tripwires on pool telemetry + node tip."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import pool_algos as palgos

ALERT_STATE = os.environ.get(
    "QUASAR_ALERT_STATE_FILE", "/var/lib/bloodstone/quasar-alerts.json"
)
POOL_DB = os.environ.get("BLOODSTONE_POOL_DB", "/var/lib/bloodstone/pool.db")
SURGE_RATIO = float(os.environ.get("QUASAR_SHA256D_SURGE_RATIO", "4.0"))
ORPHAN_GRACE_SEC = int(os.environ.get("QUASAR_ORPHAN_GRACE_SEC", "180"))


def _now() -> int:
    return int(time.time())


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pool_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(POOL_DB, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


def _share_weight_by_algo(since_ts: int) -> Dict[str, float]:
    if not os.path.isfile(POOL_DB):
        return {}
    weights: Dict[str, float] = {}
    try:
        with _pool_conn() as conn:
            rows = conn.execute(
                """
                SELECT algo, SUM(weight) AS w
                FROM shares
                WHERE created_at >= ?
                GROUP BY algo
                """,
                (since_ts,),
            ).fetchall()
        for row in rows:
            algo = palgos.normalize_algo(str(row["algo"] or ""))
            weights[algo] = float(row["w"] or 0)
    except Exception:
        return {}
    return weights


def _cpu_block_finds_since(since_ts: int) -> int:
    if not os.path.isfile(POOL_DB):
        return 0
    try:
        with _pool_conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n FROM block_finds
                WHERE found_at >= ?
                  AND algo IN ('neoscrypt', 'neoscrypt-xaya', 'yespower')
                """,
                (since_ts,),
            ).fetchone()
        return int(row["n"] if row else 0)
    except Exception:
        return 0


def _recent_pool_block_find() -> Optional[Dict[str, Any]]:
    if not os.path.isfile(POOL_DB):
        return None
    try:
        with _pool_conn() as conn:
            row = conn.execute(
                """
                SELECT algo, block_height, block_hash, found_at
                FROM block_finds
                ORDER BY found_at DESC
                LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def evaluate_tripwires(rpc: Callable) -> Dict[str, Any]:
    now = _now()
    alerts: List[Dict[str, Any]] = []

    w1h = _share_weight_by_algo(now - 3600)
    w24h = _share_weight_by_algo(now - 86400)
    sha1 = float(w1h.get(palgos.SHA256D) or 0)
    sha24 = float(w24h.get(palgos.SHA256D) or 0) / 24.0
    cpu_finds_1h = _cpu_block_finds_since(now - 3600)
    cpu_finds_prior = _cpu_block_finds_since(now - 7200) - cpu_finds_1h

    if sha24 > 0 and sha1 > SURGE_RATIO * sha24:
        if cpu_finds_1h < max(1, cpu_finds_prior):
            alerts.append(
                {
                    "code": "QUASAR_ALERT_SHA256D_RENTAL",
                    "severity": "high",
                    "message": (
                        "SHA256d share rate surged vs 24h median while CPU block finds dropped."
                    ),
                    "sha256d_weight_1h": round(sha1, 2),
                    "sha256d_weight_24h_hourly": round(sha24, 2),
                    "cpu_block_finds_1h": cpu_finds_1h,
                }
            )

    try:
        tip = int(rpc("getblockcount"))
        pool_find = _recent_pool_block_find()
        if pool_find:
            find_height = int(pool_find.get("block_height") or 0)
            find_at = int(pool_find.get("found_at") or 0)
            lag = tip - find_height
            age = now - find_at if find_at else 0
            if lag > 2 and age >= ORPHAN_GRACE_SEC:
                alerts.append(
                    {
                        "code": "QUASAR_ALERT_POSSIBLE_PRIVATE_FORK",
                        "severity": "critical",
                        "message": (
                            "Recent pool block find not reflected at local node tip "
                            f"(pool {find_height}, tip {tip})."
                        ),
                        "pool_block_height": find_height,
                        "node_tip": tip,
                        "lag_blocks": lag,
                        "age_sec": age,
                    }
                )
    except Exception:
        pass

    active = any(a.get("severity") in ("high", "critical") for a in alerts)
    payload = {
        "ok": True,
        "active": active,
        "alert_count": len(alerts),
        "alerts": alerts,
        "evaluated_at": _utc_now(),
        "share_weight_1h": w1h,
        "share_weight_24h": w24h,
    }
    _persist_alerts(payload)
    return payload


def _persist_alerts(payload: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(ALERT_STATE) or "/var/lib/bloodstone", exist_ok=True)
        with open(ALERT_STATE, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
    except OSError:
        pass


def load_alerts() -> Dict[str, Any]:
    if not os.path.isfile(ALERT_STATE):
        return {"ok": True, "active": False, "alerts": [], "alert_count": 0}
    try:
        with open(ALERT_STATE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"ok": False, "active": False, "alerts": [], "alert_count": 0}


def publish_alerts_mesh(alerts: Dict[str, Any]) -> str:
    if not alerts.get("alerts"):
        return ""
    try:
        import tempfile
        from chain_mesh import assets as mesh_assets

        month = datetime.now(timezone.utc).strftime("%Y-%m")
        asset_key = f"assets/alerts/quasar/{month}/latest.json"
        fd, path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(alerts, fh, indent=2)
                fh.write("\n")
            mesh_assets.publish_asset(
                path,
                asset_key=asset_key,
                display_name="quasar-alerts",
                mime_type="application/json",
                anchor=False,
            )
            return asset_key
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
    except Exception:
        return ""