"""Wave M — AI provider manifests (bloodstone_ai_provider/v1)."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db

AI_PROVIDER_ID = "bloodstone_ai_provider/v1"
VALID_RUNTIMES = frozenset({"onnx", "llama.cpp", "tflite", "cpu-inference"})
VALID_HARDWARE_KINDS = frozenset({
    "raspberry-pi-4",
    "raspberry-pi-5",
    "android",
    "desktop",
    "coordinator",
    "custom",
})


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def init_ai_provider_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bloodstone_ai_providers (
                provider_id TEXT PRIMARY KEY,
                peer_id TEXT NOT NULL DEFAULT '',
                node_id TEXT NOT NULL DEFAULT '',
                stone_address TEXT NOT NULL DEFAULT '',
                agent_id TEXT NOT NULL DEFAULT '',
                display_name TEXT NOT NULL DEFAULT '',
                runtimes TEXT NOT NULL DEFAULT '[]',
                models_json TEXT NOT NULL DEFAULT '[]',
                hardware_json TEXT NOT NULL DEFAULT '{}',
                endpoints_json TEXT NOT NULL DEFAULT '{}',
                region TEXT NOT NULL DEFAULT 'global',
                offline_capable INTEGER NOT NULL DEFAULT 1,
                max_concurrent INTEGER NOT NULL DEFAULT 1,
                flops_per_sec INTEGER NOT NULL DEFAULT 0,
                load_ratio REAL NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'local',
                provider_json TEXT NOT NULL DEFAULT '{}',
                last_seen INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ai_provider_region
                ON bloodstone_ai_providers(region, last_seen DESC);
            CREATE INDEX IF NOT EXISTS idx_ai_provider_last_seen
                ON bloodstone_ai_providers(last_seen DESC);

            CREATE TABLE IF NOT EXISTS ai_provider_runtimes (
                provider_id TEXT NOT NULL,
                runtime TEXT NOT NULL,
                PRIMARY KEY (provider_id, runtime)
            );
            CREATE INDEX IF NOT EXISTS idx_ai_provider_runtime_lookup
                ON ai_provider_runtimes(runtime, provider_id);
            """
        )


def validate_ai_spec(spec: Any, *, job_type: str) -> Optional[Dict[str, Any]]:
    if job_type != "inference":
        return None
    if not spec:
        return None
    if not isinstance(spec, dict):
        raise ValueError("ai_spec must be an object")
    runtime = str(spec.get("runtime") or "").strip().lower()
    if runtime and runtime not in VALID_RUNTIMES:
        raise ValueError(f"ai_spec.runtime must be one of: {sorted(VALID_RUNTIMES)}")
    prompt_key = str(spec.get("prompt_asset_key") or "").strip().lower()
    if prompt_key and len(prompt_key) != 64:
        raise ValueError("ai_spec.prompt_asset_key must be 64-char hex chunk hash")
    return {
        "runtime": runtime,
        "model_id": str(spec.get("model_id") or "").strip()[:128],
        "prompt_asset_key": prompt_key,
        "max_tokens": max(1, min(8192, int(spec.get("max_tokens") or 256))),
        "temperature": max(0.0, min(2.0, float(spec.get("temperature") or 0.7))),
        "prefer_offline": bool(spec.get("prefer_offline", True)),
        "min_flops_per_sec": max(0, int(spec.get("min_flops_per_sec") or 0)),
    }


def build_ai_provider_manifest(
    *,
    provider_id: str,
    node_id: str = "",
    peer_id: str = "",
    stone_address: str = "",
    agent_id: str = "",
    display_name: str = "",
    runtimes: Optional[List[str]] = None,
    models: Optional[List[Dict[str, Any]]] = None,
    hardware: Optional[Dict[str, Any]] = None,
    endpoints: Optional[Dict[str, Any]] = None,
    region: str = "global",
    offline_capable: bool = True,
    max_concurrent: int = 1,
    flops_per_sec: int = 0,
) -> Dict[str, Any]:
    pid = (provider_id or "").strip()[:64]
    if not pid:
        raise ValueError("provider_id required")
    rt = [
        str(r).strip().lower()
        for r in (runtimes or ["cpu-inference"])
        if str(r).strip().lower() in VALID_RUNTIMES
    ]
    if not rt:
        rt = ["cpu-inference"]
    body: Dict[str, Any] = {
        "v": "1",
        "provider_id": pid,
        "peer_id": (peer_id or pid).strip()[:64],
        "node_id": (node_id or pid).strip()[:64],
        "stone_address": (stone_address or "").strip(),
        "agent_id": (agent_id or "").strip()[:64],
        "display_name": (display_name or pid)[:120],
        "runtimes": rt,
        "models": list(models or []),
        "hardware": dict(hardware or {"kind": "custom"}),
        "endpoints": dict(endpoints or {}),
        "region": (region or "global").strip()[:32],
        "offline_capable": bool(offline_capable),
        "max_concurrent": max(1, int(max_concurrent)),
        "flops_per_sec": max(0, int(flops_per_sec)),
        "created_at": _now(),
    }
    return {"id": AI_PROVIDER_ID, "body": body}


def register_ai_provider(
    *,
    provider_id: str,
    source: str = "local",
    merge: bool = False,
    **fields: Any,
) -> Dict[str, Any]:
    init_ai_provider_db()
    pid = (provider_id or fields.get("provider_id") or "").strip()[:64]
    if not pid:
        raise ValueError("provider_id required")

    existing = get_ai_provider(provider_id=pid)
    if existing and merge and existing.get("source") in ("local", "mdns", "lan"):
        incoming_seen = int(fields.get("last_seen") or _now())
        if int(existing.get("last_seen") or 0) >= incoming_seen:
            return {"ok": True, "provider_id": pid, "duplicate": True}

    body = fields.get("body") if isinstance(fields.get("body"), dict) else fields
    runtimes = body.get("runtimes") if isinstance(body.get("runtimes"), list) else []
    if not runtimes and body.get("runtimes_json"):
        try:
            runtimes = json.loads(str(body.get("runtimes_json")))
        except Exception:
            runtimes = []
    if isinstance(runtimes, str):
        runtimes = [r.strip() for r in runtimes.split(",") if r.strip()]
    rt = [str(r).strip().lower() for r in runtimes if str(r).strip().lower() in VALID_RUNTIMES]
    if not rt:
        rt = ["cpu-inference"]

    now = _now()
    row = {
        "peer_id": str(body.get("peer_id") or pid)[:64],
        "node_id": str(body.get("node_id") or pid)[:64],
        "stone_address": str(body.get("stone_address") or "")[:64],
        "agent_id": str(body.get("agent_id") or "")[:64],
        "display_name": str(body.get("display_name") or pid)[:120],
        "runtimes": json.dumps(rt),
        "models_json": json.dumps(body.get("models") or body.get("models_json") or []),
        "hardware_json": json.dumps(body.get("hardware") or body.get("hardware_json") or {}),
        "endpoints_json": json.dumps(body.get("endpoints") or body.get("endpoints_json") or {}),
        "region": str(body.get("region") or "global")[:32],
        "offline_capable": 1 if body.get("offline_capable", True) else 0,
        "max_concurrent": max(1, int(body.get("max_concurrent") or 1)),
        "flops_per_sec": max(0, int(body.get("flops_per_sec") or 0)),
        "load_ratio": float(body.get("load_ratio") or 0),
        "source": (source or "local")[:16],
        "provider_json": json.dumps(body if isinstance(body, dict) else {}),
        "last_seen": int(body.get("last_seen") or now),
        "created_at": int(existing.get("created_at") if existing else now),
    }

    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO bloodstone_ai_providers (
                provider_id, peer_id, node_id, stone_address, agent_id,
                display_name, runtimes, models_json, hardware_json,
                endpoints_json, region, offline_capable, max_concurrent,
                flops_per_sec, load_ratio, source, provider_json,
                last_seen, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider_id) DO UPDATE SET
                peer_id = excluded.peer_id,
                node_id = excluded.node_id,
                stone_address = CASE WHEN excluded.stone_address != '' THEN excluded.stone_address ELSE stone_address END,
                agent_id = excluded.agent_id,
                display_name = excluded.display_name,
                runtimes = excluded.runtimes,
                models_json = excluded.models_json,
                hardware_json = excluded.hardware_json,
                endpoints_json = excluded.endpoints_json,
                region = excluded.region,
                offline_capable = excluded.offline_capable,
                max_concurrent = excluded.max_concurrent,
                flops_per_sec = excluded.flops_per_sec,
                load_ratio = excluded.load_ratio,
                source = excluded.source,
                provider_json = excluded.provider_json,
                last_seen = MAX(last_seen, excluded.last_seen)
            """,
            (pid, *row.values()),
        )
        conn.execute("DELETE FROM ai_provider_runtimes WHERE provider_id = ?", (pid,))
        for runtime in rt:
            conn.execute(
                "INSERT OR IGNORE INTO ai_provider_runtimes (provider_id, runtime) VALUES (?, ?)",
                (pid, runtime),
            )
    return {"ok": True, "provider_id": pid, "runtimes": rt, "source": source}


def get_ai_provider(*, provider_id: str) -> Optional[Dict[str, Any]]:
    init_ai_provider_db()
    pid = (provider_id or "").strip()
    if not pid:
        return None
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM bloodstone_ai_providers WHERE provider_id = ?",
            (pid,),
        ).fetchone()
    return dict(row) if row else None


def list_ai_providers(
    *,
    runtime: str = "",
    region: str = "",
    limit: int = 50,
) -> Dict[str, Any]:
    init_ai_provider_db()
    lim = max(1, min(200, int(limit)))
    rt = (runtime or "").strip().lower()
    reg = (region or "").strip()[:32]
    with _conn() as conn:
        if rt:
            rows = conn.execute(
                """
                SELECT p.* FROM bloodstone_ai_providers p
                JOIN ai_provider_runtimes r ON r.provider_id = p.provider_id
                WHERE r.runtime = ?
                ORDER BY p.last_seen DESC
                LIMIT ?
                """,
                (rt, lim),
            ).fetchall()
        elif reg:
            rows = conn.execute(
                """
                SELECT * FROM bloodstone_ai_providers
                WHERE region = ?
                ORDER BY last_seen DESC
                LIMIT ?
                """,
                (reg, lim),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM bloodstone_ai_providers
                ORDER BY last_seen DESC
                LIMIT ?
                """,
                (lim,),
            ).fetchall()
    return {"ok": True, "providers": [dict(r) for r in rows], "count": len(rows)}


def provider_health_payload(*, provider_id: str = "") -> Dict[str, Any]:
    pid = (provider_id or os.environ.get("DTN_NODE_ID", "pi-edge")).strip()
    if not pid.endswith("-ai"):
        pid = f"{pid}-ai"
    provider = get_ai_provider(provider_id=pid)
    active = 0
    with _conn() as conn:
        try:
            active = conn.execute(
                """
                SELECT COUNT(*) AS c FROM ai_route_assignments
                WHERE provider_id = ? AND is_current = 1
                  AND route_status IN ('assigned', 'running')
                """,
                (pid,),
            ).fetchone()["c"]
        except Exception:
            active = 0
    max_conc = int((provider or {}).get("max_concurrent") or 1)
    load = min(1.0, active / max(1, max_conc))
    return {
        "ok": True,
        "format": AI_PROVIDER_ID,
        "provider_id": pid,
        "active_jobs": active,
        "max_concurrent": max_conc,
        "load_ratio": round(load, 4),
        "runtimes": json.loads((provider or {}).get("runtimes") or "[]"),
    }