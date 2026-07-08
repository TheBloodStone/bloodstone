"""Wave M/N/O — on-device AI routing for inference compute jobs."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from chain_mesh import ai_provider as aip
from chain_mesh import compute_job as cjobs
from chain_mesh import db as mesh_db
from chain_mesh import depin_credits as depin
from chain_mesh import mesh_providers as providers

AI_ROUTING_FORMAT = "bloodstone_ai_routing/v1"
AI_ROUTING_ENABLE = os.environ.get("AI_ROUTING_ENABLE", "1").strip() not in (
    "0",
    "false",
    "no",
)
AI_PREFER_OFFLINE = os.environ.get("AI_PREFER_OFFLINE", "1").strip() not in (
    "0",
    "false",
    "no",
)
AI_PROVIDER_TTL_SEC = max(60, int(os.environ.get("AI_PROVIDER_TTL_SEC", "300")))
AI_DISPATCH_TIMEOUT_SEC = max(5, int(os.environ.get("AI_DISPATCH_TIMEOUT_SEC", "120")))
AI_DISPATCH_RETRIES = max(0, int(os.environ.get("AI_DISPATCH_RETRIES", "1")))
AI_AUTO_ROUTE_LIMIT = max(1, int(os.environ.get("AI_AUTO_ROUTE_LIMIT", "5")))
AI_INFERENCE_PORT = int(os.environ.get("AI_INFERENCE_PORT", "8081"))
AI_UPLINK_PROBE_URL = (os.environ.get("AI_UPLINK_PROBE_URL") or "").strip()
AI_HEALTH_PROBE_PARALLEL = max(1, int(os.environ.get("AI_HEALTH_PROBE_PARALLEL", "4")))
AI_DTN_EXPORT_ROUTES = os.environ.get("AI_DTN_EXPORT_ROUTES", "0").strip() in (
    "1",
    "true",
    "yes",
)
AI_COORDINATOR_DISPATCH_ENABLE = os.environ.get(
    "AI_COORDINATOR_DISPATCH_ENABLE", "1"
).strip() not in ("0", "false", "no")
AI_COORDINATOR_STUB = os.environ.get("AI_COORDINATOR_STUB", "1").strip() not in (
    "0",
    "false",
    "no",
)
AI_COORDINATOR_DISPATCH_LIMIT = max(
    1, int(os.environ.get("AI_COORDINATOR_DISPATCH_LIMIT", "5"))
)
AI_UPLINK_CACHE_SEC = max(5, int(os.environ.get("AI_UPLINK_CACHE_SEC", "30")))
AI_UPLINK_PROBE_TIMEOUT_SEC = max(
    1, int(os.environ.get("AI_UPLINK_PROBE_TIMEOUT_SEC", "3"))
)

COORDINATOR_AI_ID = "bloodstone-coordinator-v1-ai"
COORDINATOR_NODE_IDS = frozenset(
    {"coordinator-vps", "heal-coordinator", "coordinator", "coordinator-vps-ai"}
)
_PRIVATE_NETS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
)

_ROUTE_TO_JOB_STATUS = {
    "assigned": "running",
    "running": "running",
    "completed": "completed",
    "failed": "failed",
    "queued_dtn": "pending",
    "coordinator": "pending",
    "pending": "pending",
}

_LAST_UPKEEP: Dict[str, Any] = {}
_LAST_UPLINK: Dict[str, Any] = {}
_LAST_UPLINK_AT = 0
_UPLINK_PROBING = False


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def _region() -> str:
    return (os.environ.get("DTN_DEFAULT_REGION", "global") or "global").strip()[:32]


def _node_id() -> str:
    return (os.environ.get("DTN_NODE_ID") or "pi-edge").strip()[:64]


def init_ai_routing_db() -> None:
    aip.init_ai_provider_db()
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ai_route_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                stone_address TEXT NOT NULL,
                provider_id TEXT NOT NULL DEFAULT '',
                route_status TEXT NOT NULL DEFAULT 'pending',
                score REAL NOT NULL DEFAULT 0,
                reason TEXT NOT NULL DEFAULT '',
                uplink_available INTEGER NOT NULL DEFAULT 0,
                offline_mode INTEGER NOT NULL DEFAULT 0,
                route_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                is_current INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_ai_route_job
                ON ai_route_assignments(job_id, is_current DESC);

            CREATE TABLE IF NOT EXISTS compute_usage_jobs (
                job_id TEXT PRIMARY KEY,
                stone_address TEXT NOT NULL,
                flops_debited INTEGER NOT NULL DEFAULT 0,
                debited_at INTEGER NOT NULL
            );
            """
        )


def _uplink_probe_url() -> str:
    from chain_mesh import dtn_starlink as starlink

    if AI_UPLINK_PROBE_URL:
        return AI_UPLINK_PROBE_URL
    if _is_coordinator_node():
        lan_port = int(os.environ.get("DTN_LAN_WEB_PORT", "8887"))
        return f"http://127.0.0.1:{lan_port}/health"
    return starlink.PROBE_URL


def uplink_available(*, use_cache: bool = False) -> Dict[str, Any]:
    global _LAST_UPLINK_AT, _UPLINK_PROBING
    from chain_mesh import dtn_starlink as starlink

    now = _now()
    if use_cache and _LAST_UPLINK and (now - _LAST_UPLINK_AT) < AI_UPLINK_CACHE_SEC:
        cached = dict(_LAST_UPLINK)
        cached["cached"] = True
        cached["cache_age_sec"] = now - _LAST_UPLINK_AT
        return cached

    if _UPLINK_PROBING:
        return {
            "connected": True,
            "latency_ms": None,
            "probe_url": _uplink_probe_url(),
            "probe_streak": 0,
            "source": "recursion_guard",
            "uplink_stable": False,
            "recursion_guard": True,
        }

    _UPLINK_PROBING = True
    try:
        probe_url = _uplink_probe_url()
        probe = starlink.probe_uplink(
            url=probe_url,
            timeout_sec=AI_UPLINK_PROBE_TIMEOUT_SEC,
        )
        streak = int(probe.get("probe_streak") or 0)
        connected = bool(probe.get("connected"))
        result = {
            "connected": connected,
            "latency_ms": probe.get("latency_ms"),
            "probe_url": probe.get("probe_url"),
            "probe_streak": streak,
            "source": "starlink" if connected else "none",
            "uplink_stable": connected and streak >= starlink.PROBE_STREAK_REQUIRED,
        }
        _LAST_UPLINK.clear()
        _LAST_UPLINK.update(result)
        _LAST_UPLINK_AT = now
        return result
    finally:
        _UPLINK_PROBING = False


def _job_ai_spec(job: Dict[str, Any]) -> Dict[str, Any]:
    body = job.get("body") if isinstance(job.get("body"), dict) else job
    spec = body.get("ai_spec") if isinstance(body, dict) and isinstance(body.get("ai_spec"), dict) else {}
    if not spec:
        try:
            spec = json.loads(job.get("job_json") or "{}").get("ai_spec") or {}
        except Exception:
            spec = {}
    return spec if isinstance(spec, dict) else {}


def _is_private_host(host: str) -> bool:
    try:
        addr = ipaddress.ip_address(socket.gethostbyname(host))
    except Exception:
        return False
    return any(addr in net for net in _PRIVATE_NETS)


def _validate_dispatch_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        raise ValueError("inference_url must be http(s)")
    if not parsed.hostname or not _is_private_host(parsed.hostname):
        raise ValueError("inference_url must target private/LAN host (SSRF guard)")
    return url.strip()


def _coordinator_base_url() -> str:
    from chain_mesh import dtn_sync as dtn

    return (
        os.environ.get("DTN_UPSTREAM_URL")
        or os.environ.get("BLOODSTONE_PUBLIC_ROOT")
        or dtn.DTN_UPSTREAM_URL
    ).rstrip("/")


def _public_callback_base() -> str:
    base = (os.environ.get("BLOODSTONE_PUBLIC_ROOT") or "").strip().rstrip("/")
    if base:
        return base
    lan_port = int(os.environ.get("DTN_LAN_WEB_PORT", "8887"))
    from chain_mesh import mdns_discovery as mdns

    host = mdns._lan_ip() or "127.0.0.1"
    return f"http://{host}:{lan_port}"


def _is_coordinator_node() -> bool:
    flag = os.environ.get("AI_COORDINATOR_MODE", "").strip().lower()
    if flag in ("1", "true", "yes"):
        return True
    if _node_id().lower() in COORDINATOR_NODE_IDS:
        return True
    public_host = (os.environ.get("BLOODSTONE_PUBLIC_HOST") or "").strip().lower()
    return bool(public_host and "mytunnel" in public_host)


def _inference_reachable(provider: Dict[str, Any]) -> bool:
    endpoints = json.loads(provider.get("endpoints_json") or "{}")
    url = str(endpoints.get("inference_url") or "").strip()
    if not url:
        return False
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except Exception:
        return False


def _parse_ai_runtimes(value: Any) -> List[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(r).strip().lower() for r in value if str(r).strip()]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(r).strip().lower() for r in parsed if str(r).strip()]
            except Exception:
                pass
        return [r.strip().lower() for r in raw.split(",") if r.strip()]
    return []


def score_provider(
    provider: Dict[str, Any],
    job: Dict[str, Any],
    *,
    offline_mode: bool,
) -> float:
    spec = _job_ai_spec(job)
    runtimes = json.loads(provider.get("runtimes") or "[]")
    score = 0.0

    req_runtime = str(spec.get("runtime") or "").lower()
    if req_runtime and req_runtime not in runtimes:
        return -1
    min_flops = int(spec.get("min_flops_per_sec") or 0)
    flops_per_sec = int(provider.get("flops_per_sec") or 0)
    if min_flops > 0 and flops_per_sec < min_flops:
        return -1
    if float(provider.get("load_ratio") or 0) >= 1.0:
        return -1
    if offline_mode and not bool(int(provider.get("offline_capable") or 0)):
        return -1

    flops_budget = int(job.get("flops_budget") or 0)
    if flops_budget > 0 and flops_per_sec > 0:
        est_sec = flops_budget / flops_per_sec
        if est_sec > 120:
            score -= 40
        elif est_sec > 60:
            score -= 15

    score += 100 if provider.get("region") == job.get("region") else 0
    score += 80 if provider.get("source") in ("local", "mdns", "lan") else 0
    score += 60 if int(provider.get("offline_capable") or 0) and offline_mode else 0
    model_id = str(spec.get("model_id") or "")
    models = json.loads(provider.get("models_json") or "[]")
    if model_id and any(m.get("model_id") == model_id for m in models):
        score += 40
    score += min(30, flops_per_sec / 1e9 * 10)
    score -= float(provider.get("load_ratio") or 0) * 50
    age = _now() - int(provider.get("last_seen") or 0)
    score -= age / 60
    try:
        from chain_mesh import tenant_ai_route as troute

        hint = troute.resolve_job_inference_spec(job)
        score += troute.tenant_route_bonus(provider, spec=hint)
    except Exception:
        pass
    return score


def pick_best_provider(
    candidates: List[Tuple[Dict[str, Any], float]],
) -> Optional[Tuple[Dict[str, Any], float]]:
    eligible = [(p, s) for p, s in candidates if s != -1]
    if not eligible:
        return None
    return max(eligible, key=lambda item: item[1])


def ensure_coordinator_ai_provider() -> None:
    providers.ensure_default_provider()
    public = _coordinator_base_url()
    lan_port = int(os.environ.get("DTN_LAN_WEB_PORT", "8887"))
    endpoints: Dict[str, Any] = {
        "health_url": f"{public}/api/convergence/ai/provider/health",
        "dispatch_url": f"{public}/api/convergence/ai/dispatch",
        "callback_url": f"{public}/api/convergence/ai/callback",
    }
    if _is_coordinator_node() and AI_INFERENCE_PORT:
        endpoints["inference_url"] = (
            f"http://127.0.0.1:{AI_INFERENCE_PORT}/v1/completions"
        )
    register_local_provider(
        provider_id=COORDINATOR_AI_ID,
        node_id="coordinator-vps",
        display_name="Bloodstone Coordinator AI",
        runtimes=["cpu-inference"],
        region="global",
        offline_capable=False,
        source="coordinator",
        endpoints=endpoints,
        flops_per_sec=int(os.environ.get("AI_COORDINATOR_FLOPS_PER_SEC", "1000000000")),
        max_concurrent=int(os.environ.get("AI_COORDINATOR_MAX_CONCURRENT", "4")),
    )


def register_local_provider(
    *,
    provider_id: str = "",
    node_id: str = "",
    display_name: str = "",
    runtimes: Optional[List[str]] = None,
    region: str = "",
    offline_capable: bool = True,
    endpoints: Optional[Dict[str, Any]] = None,
    models: Optional[List[Dict[str, Any]]] = None,
    flops_per_sec: int = 0,
    max_concurrent: int = 2,
    source: str = "local",
) -> Dict[str, Any]:
    nid = (node_id or _node_id()).strip()[:64]
    pid = (provider_id or f"{nid}-ai").strip()[:64]
    lan_port = int(os.environ.get("DTN_LAN_WEB_PORT", "8887"))
    from chain_mesh import mdns_discovery as mdns

    host = mdns._lan_ip() or "127.0.0.1"
    eps = dict(endpoints or {})
    if not eps.get("health_url"):
        eps["health_url"] = f"http://{host}:{lan_port}/api/convergence/ai/provider/health"
    if not eps.get("inference_url") and AI_INFERENCE_PORT:
        eps["inference_url"] = f"http://{host}:{AI_INFERENCE_PORT}/v1/completions"

    manifest = aip.build_ai_provider_manifest(
        provider_id=pid,
        node_id=nid,
        display_name=display_name or f"{nid} AI",
        runtimes=runtimes or ["cpu-inference", "llama.cpp"],
        endpoints=eps,
        region=region or _region(),
        offline_capable=offline_capable,
        max_concurrent=max_concurrent,
        flops_per_sec=flops_per_sec or int(os.environ.get("AI_FLOPS_PER_SEC", "500000000")),
        models=models,
    )
    return aip.register_ai_provider(
        provider_id=pid,
        source=source,
        body=manifest["body"],
    )


def discover_ai_providers() -> Dict[str, Any]:
    init_ai_routing_db()
    ensure_coordinator_ai_provider()
    npu_info: Dict[str, Any] = {}
    try:
        from chain_mesh import ai_npu_detect as npu

        npu_info = npu.detect_npu_hardware()
        if npu_info.get("runtimes"):
            register_local_provider(
                runtimes=npu_info.get("runtimes"),
                flops_per_sec=npu.suggested_flops_per_sec(npu_info.get("hardware") or {}),
                endpoints=None,
            )
        else:
            register_local_provider()
    except Exception:
        register_local_provider()
    discovered = 0

    try:
        from chain_mesh import mdns_discovery as mdns

        if os.environ.get("AI_MDNS_ENABLE", "1").strip() not in ("0", "false", "no"):
            browse = mdns.discover_mdns_ai_providers(register=True)
            discovered += int(browse.get("registered") or 0)
    except Exception:
        pass

    mesh_rows = providers.list_providers()
    for row in mesh_rows or []:
        roles = row.get("roles") or []
        if isinstance(roles, str):
            try:
                roles = json.loads(roles)
            except Exception:
                roles = []
        if "ai" in roles or "compute" in roles:
            pid = f"{row.get('peer_id')}-ai"
            aip.register_ai_provider(
                provider_id=pid,
                source="mesh",
                body={
                    "provider_id": pid,
                    "peer_id": row.get("peer_id"),
                    "display_name": row.get("display_name"),
                    "runtimes": ["cpu-inference"],
                    "region": _region(),
                    "offline_capable": True,
                },
            )
            discovered += 1

    try:
        from chain_mesh import lan_registry as lan

        lan_port = int(os.environ.get("DTN_LAN_WEB_PORT", "8887"))
        for node in lan.list_lan_ai_nodes():
            runtimes = _parse_ai_runtimes(node.get("ai_runtimes"))
            if not runtimes:
                continue
            device_id = str(node.get("device_id") or "").strip().lower()
            lan_ip = str(node.get("lan_ip") or "").strip()
            if not device_id or not lan_ip:
                continue
            port = int(node.get("ai_inference_port") or 0)
            endpoints: Dict[str, str] = {
                "health_url": (
                    f"http://{lan_ip}:{lan_port}/api/convergence/ai/provider/health"
                ),
            }
            if port > 0:
                endpoints["inference_url"] = f"http://{lan_ip}:{port}/v1/completions"
            aip.register_ai_provider(
                provider_id=f"{device_id}-ai",
                source="lan",
                body={
                    "provider_id": f"{device_id}-ai",
                    "node_id": device_id,
                    "display_name": str(node.get("model") or device_id),
                    "runtimes": runtimes,
                    "region": _region(),
                    "offline_capable": True,
                    "endpoints": endpoints,
                    "hardware": {"kind": str(node.get("peer_kind") or "android")},
                },
            )
            discovered += 1
    except Exception:
        pass

    total = aip.list_ai_providers(limit=200).get("count") or 0
    return {
        "ok": True,
        "discovered": discovered,
        "total": total,
        "npu": npu_info,
    }


def probe_ai_provider_health(provider: Dict[str, Any]) -> Dict[str, Any]:
    endpoints = json.loads(provider.get("endpoints_json") or "{}")
    url = str(endpoints.get("health_url") or "").strip()
    if not url:
        return {"ok": False, "provider_id": provider.get("provider_id"), "reason": "no health_url"}
    try:
        _validate_dispatch_url(url)
        resp = requests.get(url, timeout=2, allow_redirects=False)
        body = resp.json() if resp.status_code == 200 else {}
        active = int(body.get("active_jobs") or 0)
        max_conc = int(provider.get("max_concurrent") or 1)
        load = float(body.get("load_ratio") if "load_ratio" in body else active / max(1, max_conc))
        load = min(1.0, max(0.0, load))
    except Exception as exc:
        load = 1.0
        return {"ok": False, "provider_id": provider.get("provider_id"), "error": str(exc), "load_ratio": load}

    with _conn() as conn:
        conn.execute(
            "UPDATE bloodstone_ai_providers SET load_ratio = ?, last_seen = ? WHERE provider_id = ?",
            (load, _now(), provider.get("provider_id")),
        )
    return {"ok": True, "provider_id": provider.get("provider_id"), "load_ratio": load}


def probe_ai_providers() -> Dict[str, Any]:
    init_ai_routing_db()
    cutoff = _now() - AI_PROVIDER_TTL_SEC
    providers_list = aip.list_ai_providers(limit=AI_HEALTH_PROBE_PARALLEL * 2).get("providers") or []
    probed = 0
    for row in providers_list[:AI_HEALTH_PROBE_PARALLEL]:
        if int(row.get("last_seen") or 0) < cutoff:
            continue
        probe_ai_provider_health(row)
        probed += 1
    return {"ok": True, "probed": probed}


def purge_stale_ai_providers() -> Dict[str, Any]:
    init_ai_routing_db()
    cutoff = _now() - AI_PROVIDER_TTL_SEC
    with _conn() as conn:
        cur = conn.execute(
            "DELETE FROM bloodstone_ai_providers WHERE last_seen < ? AND source NOT IN ('local', 'coordinator')",
            (cutoff,),
        )
    return {"ok": True, "purged": int(cur.rowcount)}


def get_current_route_assignment(*, job_id: str) -> Optional[Dict[str, Any]]:
    init_ai_routing_db()
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM ai_route_assignments
            WHERE job_id = ? AND is_current = 1
            ORDER BY updated_at DESC LIMIT 1
            """,
            ((job_id or "").strip(),),
        ).fetchone()
    return dict(row) if row else None


def sync_compute_job_route(
    *,
    job_id: str,
    provider_id: str,
    route_status: str,
    score: float = 0,
    reason: str = "",
    uplink: Optional[Dict[str, Any]] = None,
    offline_mode: bool = False,
    route_json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    init_ai_routing_db()
    cjobs.init_compute_job_db()
    jid = (job_id or "").strip()
    job_status = _ROUTE_TO_JOB_STATUS.get(route_status, "pending")
    now = _now()
    upl = uplink or {}

    with _conn() as conn:
        conn.execute(
            "UPDATE ai_route_assignments SET is_current = 0 WHERE job_id = ?",
            (jid,),
        )
        conn.execute(
            """
            INSERT INTO ai_route_assignments (
                job_id, stone_address, provider_id, route_status, score, reason,
                uplink_available, offline_mode, route_json, created_at, updated_at, is_current
            ) VALUES (
                ?, COALESCE((SELECT stone_address FROM bloodstone_compute_jobs WHERE job_id=? AND is_current=1 LIMIT 1), ''),
                ?, ?, ?, ?, ?, ?, ?, ?, ?, 1
            )
            """,
            (
                jid,
                jid,
                (provider_id or "")[:64],
                route_status[:32],
                float(score),
                (reason or "")[:256],
                1 if upl.get("connected") else 0,
                1 if offline_mode else 0,
                json.dumps(route_json or {}),
                now,
                now,
            ),
        )
        conn.execute(
            """
            UPDATE bloodstone_compute_jobs
            SET provider_id = ?, status = ?, updated_at = ?
            WHERE job_id = ? AND is_current = 1
            """,
            ((provider_id or "")[:64], job_status, now, jid),
        )
    return {"ok": True, "job_id": jid, "route_status": route_status, "job_status": job_status}


def debit_compute_job(*, job_id: str, stone_address: str, flops_budget: int) -> Dict[str, Any]:
    init_ai_routing_db()
    jid = (job_id or "").strip()
    addr = (stone_address or "").strip()
    flops = max(0, int(flops_budget))
    with _conn() as conn:
        existing = conn.execute(
            "SELECT job_id FROM compute_usage_jobs WHERE job_id = ?",
            (jid,),
        ).fetchone()
        if existing:
            return {"ok": True, "duplicate": True, "job_id": jid}
        conn.execute(
            "INSERT INTO compute_usage_jobs (job_id, stone_address, flops_debited, debited_at) VALUES (?, ?, ?, ?)",
            (jid, addr, flops, _now()),
        )
    if flops > 0:
        job = cjobs.get_compute_job(job_id=jid)
        depin.record_compute_usage(
            addr,
            delta_flops=flops,
            blurt_author=str((job or {}).get("blurt_author") or ""),
        )
    return {"ok": True, "job_id": jid, "flops_debited": flops}


def dispatch_inference_job(
    *,
    job_id: str,
    provider: Dict[str, Any],
    tenant_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    job = cjobs.get_compute_job(job_id=job_id)
    if not job:
        return {"ok": False, "error": "job not found"}
    spec = _job_ai_spec(job)
    endpoints = json.loads(provider.get("endpoints_json") or "{}")
    url = str(endpoints.get("inference_url") or "").strip()
    if not url:
        return {"ok": False, "error": "no inference_url", "skipped": True}

    from chain_mesh.store import get_chunk, put_chunk

    prompt_key = spec.get("prompt_asset_key") or (
        (job.get("input_asset_keys") or [None])[0]
    )
    raw = get_chunk(str(prompt_key or "")) if prompt_key else None
    prompt_text = raw.decode("utf-8", errors="replace") if raw else ""

    try:
        url = _validate_dispatch_url(url)
    except ValueError as exc:
        sync_compute_job_route(
            job_id=job_id,
            provider_id=str(provider.get("provider_id") or ""),
            route_status="failed",
            reason=str(exc),
        )
        return {"ok": False, "error": str(exc)}

    from chain_mesh import tenant_ai_route as troute

    payload = troute.build_dispatch_payload(
        job,
        spec=tenant_spec,
        base_payload={
            "model": spec.get("model_id") or "default",
            "prompt": prompt_text,
            "max_tokens": int(spec.get("max_tokens") or 256),
            "temperature": float(spec.get("temperature") or 0.7),
            "job_id": job_id,
            "stone_address": job.get("stone_address"),
            "stream": False,
        },
    )
    if tenant_spec and tenant_spec.get("runtime") and not spec.get("runtime"):
        payload["runtime"] = tenant_spec.get("runtime")
    headers = {
        "Content-Type": "application/json",
        "X-Bloodstone-Job-Id": job_id,
        "X-Bloodstone-Stone": str(job.get("stone_address") or ""),
    }

    last_error = ""
    for attempt in range(AI_DISPATCH_RETRIES + 1):
        try:
            resp = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=AI_DISPATCH_TIMEOUT_SEC,
                allow_redirects=False,
            )
            if resp.status_code >= 400:
                last_error = f"HTTP {resp.status_code}"
                continue
            body = resp.json()
            async_status = str(
                body.get("route_status") or body.get("status") or ""
            ).strip().lower()
            if async_status == "running":
                sync_compute_job_route(
                    job_id=job_id,
                    provider_id=str(provider.get("provider_id") or ""),
                    route_status="running",
                    reason="dispatch_ack",
                )
                return {
                    "ok": True,
                    "job_id": job_id,
                    "async": True,
                    "route_status": "running",
                }
            output_key = str(body.get("output_asset_key") or "").strip()
            if not output_key:
                choices = body.get("choices") or []
                text = ""
                if choices and isinstance(choices[0], dict):
                    text = str(choices[0].get("text") or choices[0].get("message", {}).get("content") or "")
                if text:
                    import hashlib

                    output_key = hashlib.sha256(text.encode()).hexdigest()
                    put_chunk(text.encode("utf-8"), expected_hash=output_key)
            if output_key:
                with _conn() as conn:
                    row = conn.execute(
                        "SELECT job_json FROM bloodstone_compute_jobs WHERE job_id=? AND is_current=1",
                        (job_id,),
                    ).fetchone()
                    if row:
                        jb = json.loads(row["job_json"] or "{}")
                        jb["output_asset_key"] = output_key
                        jb["status"] = "completed"
                        conn.execute(
                            """
                            UPDATE bloodstone_compute_jobs
                            SET output_asset_key = ?, job_json = ?, status = 'completed', updated_at = ?
                            WHERE job_id = ? AND is_current = 1
                            """,
                            (output_key, json.dumps(jb), _now(), job_id),
                        )
                sync_compute_job_route(
                    job_id=job_id,
                    provider_id=str(provider.get("provider_id") or ""),
                    route_status="completed",
                    reason="dispatch_ok",
                )
                debit_compute_job(
                    job_id=job_id,
                    stone_address=str(job.get("stone_address") or ""),
                    flops_budget=int(job.get("flops_budget") or 0),
                )
                return {"ok": True, "job_id": job_id, "output_asset_key": output_key}
            last_error = "empty response"
        except Exception as exc:
            last_error = str(exc)
        if attempt < AI_DISPATCH_RETRIES:
            time.sleep(2)

    sync_compute_job_route(
        job_id=job_id,
        provider_id=str(provider.get("provider_id") or ""),
        route_status="failed",
        reason=last_error,
    )
    return {"ok": False, "error": last_error}


def _ingest_remote_dispatch_job(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh.store import put_chunk

    job_row = payload.get("job")
    prompt_text = str(payload.get("prompt_text") or "")
    imported = 0
    if isinstance(job_row, dict):
        imported = cjobs.import_job_rows([job_row])
    job = cjobs.get_compute_job(job_id=str(payload.get("job_id") or ""))
    if not job:
        return {"ok": False, "error": "job not found"}
    spec = _job_ai_spec(job)
    prompt_key = str(spec.get("prompt_asset_key") or "").strip()
    if prompt_text and prompt_key and len(prompt_key) == 64:
        put_chunk(prompt_text.encode("utf-8"), expected_hash=prompt_key)
    return {"ok": True, "imported": imported, "job_id": job.get("job_id")}


def _coordinator_stub_complete(*, job_id: str) -> Dict[str, Any]:
    import hashlib

    from chain_mesh.store import put_chunk

    job = cjobs.get_compute_job(job_id=job_id)
    if not job:
        return {"ok": False, "error": "job not found"}
    text = (
        f"[coordinator-stub] inference complete for {job_id} "
        f"at {_now()} on {_node_id()}"
    )
    output_key = hashlib.sha256(text.encode()).hexdigest()
    put_chunk(text.encode("utf-8"), expected_hash=output_key)
    with _conn() as conn:
        row = conn.execute(
            "SELECT job_json FROM bloodstone_compute_jobs WHERE job_id=? AND is_current=1",
            (job_id,),
        ).fetchone()
        if row:
            jb = json.loads(row["job_json"] or "{}")
            jb["output_asset_key"] = output_key
            jb["status"] = "completed"
            conn.execute(
                """
                UPDATE bloodstone_compute_jobs
                SET output_asset_key = ?, job_json = ?, status = 'completed', updated_at = ?
                WHERE job_id = ? AND is_current = 1
                """,
                (output_key, json.dumps(jb), _now(), job_id),
            )
    sync_compute_job_route(
        job_id=job_id,
        provider_id=COORDINATOR_AI_ID,
        route_status="completed",
        reason="coordinator_stub",
    )
    debit_compute_job(
        job_id=job_id,
        stone_address=str(job.get("stone_address") or ""),
        flops_budget=int(job.get("flops_budget") or 0),
    )
    return {"ok": True, "job_id": job_id, "output_asset_key": output_key, "stub": True}


def post_ai_callback_remote(
    *,
    callback_url: str,
    job_id: str,
    status: str = "completed",
    output_asset_key: str = "",
    provider_id: str = "",
    reason: str = "",
) -> Dict[str, Any]:
    url = (callback_url or "").strip()
    if not url:
        return {"ok": False, "skipped": True, "reason": "no callback_url"}
    payload = {
        "job_id": job_id,
        "status": status,
        "output_asset_key": output_asset_key,
        "provider_id": provider_id or COORDINATOR_AI_ID,
        "reason": reason,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15, allow_redirects=False)
        body: Dict[str, Any] = {}
        try:
            body = resp.json() if resp.content else {}
        except Exception:
            body = {}
        return {
            "ok": resp.status_code < 400,
            "status_code": resp.status_code,
            "callback_url": url,
            "body": body,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "callback_url": url}


def ingest_ai_callback(payload: Dict[str, Any]) -> Dict[str, Any]:
    init_ai_routing_db()
    jid = str(payload.get("job_id") or "").strip()
    if not jid:
        raise ValueError("job_id required")
    status = str(payload.get("status") or "completed").strip().lower()
    provider_id = str(payload.get("provider_id") or COORDINATOR_AI_ID)
    reason = str(payload.get("reason") or "callback")[:256]
    output_key = str(payload.get("output_asset_key") or "").strip()

    job = cjobs.get_compute_job(job_id=jid)
    if not job:
        raise ValueError("job not found")

    if status == "completed" and output_key:
        with _conn() as conn:
            row = conn.execute(
                "SELECT job_json FROM bloodstone_compute_jobs WHERE job_id=? AND is_current=1",
                (jid,),
            ).fetchone()
            if row:
                jb = json.loads(row["job_json"] or "{}")
                jb["output_asset_key"] = output_key
                jb["status"] = "completed"
                conn.execute(
                    """
                    UPDATE bloodstone_compute_jobs
                    SET output_asset_key = ?, job_json = ?, status = 'completed', updated_at = ?
                    WHERE job_id = ? AND is_current = 1
                    """,
                    (output_key, json.dumps(jb), _now(), jid),
                )
        sync_compute_job_route(
            job_id=jid,
            provider_id=provider_id,
            route_status="completed",
            reason=reason,
        )
        debit_compute_job(
            job_id=jid,
            stone_address=str(job.get("stone_address") or ""),
            flops_budget=int(job.get("flops_budget") or 0),
        )
        return {"ok": True, "job_id": jid, "route_status": "completed", "output_asset_key": output_key}

    if status == "running":
        sync_compute_job_route(
            job_id=jid,
            provider_id=provider_id,
            route_status="running",
            reason=reason,
        )
        return {"ok": True, "job_id": jid, "route_status": "running"}

    sync_compute_job_route(
        job_id=jid,
        provider_id=provider_id,
        route_status="failed",
        reason=reason or status,
    )
    with _conn() as conn:
        conn.execute(
            """
            UPDATE bloodstone_compute_jobs
            SET status = 'failed', updated_at = ?
            WHERE job_id = ? AND is_current = 1
            """,
            (_now(), jid),
        )
    return {"ok": True, "job_id": jid, "route_status": "failed"}


def coordinator_dispatch_job(
    *,
    job_id: str,
    callback_url: str = "",
    origin_node_id: str = "",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not AI_ROUTING_ENABLE:
        return {"ok": True, "skipped": True, "reason": "AI_ROUTING_ENABLE off"}

    jid = (job_id or "").strip()
    if not jid:
        raise ValueError("job_id required")

    init_ai_routing_db()
    body = dict(payload or {})
    body["job_id"] = jid
    if body.get("job") or body.get("prompt_text"):
        ingest = _ingest_remote_dispatch_job(body)
        if not ingest.get("ok"):
            return ingest

    job = cjobs.get_compute_job(job_id=jid)
    if not job:
        return {"ok": False, "error": "job not found"}
    if job.get("job_type") != "inference":
        raise ValueError("job_type must be inference")

    from chain_mesh import tenant_ai_route as troute
    from chain_mesh import tenant_submit_gate as tgate

    tenant_route = body.get("tenant_route")
    if not isinstance(tenant_route, dict) or not tenant_route:
        tenant_route = troute.resolve_job_inference_spec(job)
    gate = tgate.check_submit_allowed(
        tenant_id=str(job.get("tenant_id") or ""),
        blurt_author=str(job.get("blurt_author") or ""),
        stone_address=str(job.get("stone_address") or ""),
    )
    if not gate.get("allowed"):
        return {
            "ok": False,
            "error": gate.get("reason") or "submit gate blocked",
            "submit_gate": gate,
            "job_id": jid,
        }

    cb = (callback_url or body.get("callback_url") or "").strip()
    origin = (origin_node_id or body.get("origin_node_id") or "").strip()

    sync_compute_job_route(
        job_id=jid,
        provider_id=COORDINATOR_AI_ID,
        route_status="running",
        reason="coordinator_dispatch",
        route_json={
            "origin_node_id": origin,
            "callback_url": cb,
            "tenant_route": tenant_route,
        },
    )

    ensure_coordinator_ai_provider()
    provider = aip.get_ai_provider(provider_id=COORDINATOR_AI_ID) or {}
    dispatch: Dict[str, Any] = {"ok": False, "error": "inference unreachable", "skipped": True}
    if _inference_reachable(provider):
        dispatch = dispatch_inference_job(
            job_id=jid, provider=provider, tenant_spec=tenant_route
        )
    if dispatch.get("ok"):
        try:
            from chain_mesh import tenant_route_ledger as tledger

            tledger.record_assignment(
                job=job,
                provider=provider,
                tenant_spec=tenant_route,
                route_status=str(dispatch.get("route_status") or "completed"),
            )
        except Exception:
            pass
        if dispatch.get("async"):
            if cb:
                post_ai_callback_remote(
                    callback_url=cb,
                    job_id=jid,
                    status="running",
                    provider_id=COORDINATOR_AI_ID,
                    reason="dispatch_ack",
                )
            return {
                "ok": True,
                "job_id": jid,
                "route_status": "running",
                "provider_id": COORDINATOR_AI_ID,
                "tenant_route": tenant_route,
                "dispatch": dispatch,
                "callback": bool(cb),
            }
        if cb:
            post_ai_callback_remote(
                callback_url=cb,
                job_id=jid,
                status="completed",
                output_asset_key=str(dispatch.get("output_asset_key") or ""),
                provider_id=COORDINATOR_AI_ID,
                reason="dispatch_ok",
            )
        return {
            "ok": True,
            "job_id": jid,
            "route_status": "completed",
            "provider_id": COORDINATOR_AI_ID,
            "tenant_route": tenant_route,
            "dispatch": dispatch,
            "callback": bool(cb),
        }

    if AI_COORDINATOR_STUB:
        stub = _coordinator_stub_complete(job_id=jid)
        if stub.get("ok") and cb:
            post_ai_callback_remote(
                callback_url=cb,
                job_id=jid,
                status="completed",
                output_asset_key=str(stub.get("output_asset_key") or ""),
                provider_id=COORDINATOR_AI_ID,
                reason="coordinator_stub",
            )
        return {
            "ok": bool(stub.get("ok")),
            "job_id": jid,
            "route_status": "completed" if stub.get("ok") else "failed",
            "provider_id": COORDINATOR_AI_ID,
            "dispatch": dispatch,
            "stub": stub,
            "callback": bool(cb),
        }

    sync_compute_job_route(
        job_id=jid,
        provider_id=COORDINATOR_AI_ID,
        route_status="failed",
        reason=str(dispatch.get("error") or "dispatch_failed"),
    )
    if cb:
        post_ai_callback_remote(
            callback_url=cb,
            job_id=jid,
            status="failed",
            provider_id=COORDINATOR_AI_ID,
            reason=str(dispatch.get("error") or "dispatch_failed"),
        )
    return {
        "ok": False,
        "job_id": jid,
        "route_status": "failed",
        "provider_id": COORDINATOR_AI_ID,
        "dispatch": dispatch,
    }


def dispatch_to_coordinator(*, job_id: str) -> Dict[str, Any]:
    if not AI_COORDINATOR_DISPATCH_ENABLE:
        return {"ok": False, "skipped": True, "reason": "AI_COORDINATOR_DISPATCH_ENABLE off"}

    job = cjobs.get_compute_job(job_id=job_id)
    if not job:
        return {"ok": False, "error": "job not found"}

    from chain_mesh.store import get_chunk

    spec = _job_ai_spec(job)
    prompt_key = spec.get("prompt_asset_key") or (
        (job.get("input_asset_keys") or [None])[0]
    )
    raw = get_chunk(str(prompt_key or "")) if prompt_key else None
    prompt_text = raw.decode("utf-8", errors="replace") if raw else ""

    from chain_mesh import tenant_ai_route as troute

    tenant_spec = troute.resolve_job_inference_spec(job)
    base = _coordinator_base_url()
    url = f"{base}/api/convergence/ai/dispatch"
    payload = troute.build_dispatch_payload(
        job,
        spec=tenant_spec,
        base_payload={
            "job_id": job_id,
            "callback_url": f"{_public_callback_base()}/api/convergence/ai/callback",
            "origin_node_id": _node_id(),
            "job": job,
            "prompt_text": prompt_text,
            "tenant_route": tenant_spec,
        },
    )
    try:
        resp = requests.post(
            url,
            json=payload,
            timeout=AI_DISPATCH_TIMEOUT_SEC,
            allow_redirects=False,
        )
        body: Dict[str, Any] = {}
        try:
            body = resp.json() if resp.content else {}
        except Exception:
            body = {}
        if resp.status_code >= 400:
            return {
                "ok": False,
                "error": body.get("error") or f"HTTP {resp.status_code}",
                "status_code": resp.status_code,
                "dispatch_url": url,
            }
        route_status = str(body.get("route_status") or "running").strip().lower()
        if route_status in ("completed", "running"):
            sync_compute_job_route(
                job_id=job_id,
                provider_id=COORDINATOR_AI_ID,
                route_status=route_status,
                reason="coordinator_http_dispatch",
                route_json={"dispatch_url": url, "origin_node_id": _node_id()},
            )
        return {
            "ok": True,
            "job_id": job_id,
            "route_status": route_status,
            "dispatch_url": url,
            "coordinator": body,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "dispatch_url": url}


def process_coordinator_dispatch_queue(*, limit: int = 0) -> Dict[str, Any]:
    if not _is_coordinator_node():
        return {"ok": True, "skipped": True, "reason": "not coordinator node"}
    if not AI_COORDINATOR_DISPATCH_ENABLE:
        return {"ok": True, "skipped": True, "reason": "AI_COORDINATOR_DISPATCH_ENABLE off"}

    init_ai_routing_db()
    lim = max(1, int(limit or AI_COORDINATOR_DISPATCH_LIMIT))
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT a.job_id, a.route_json
            FROM ai_route_assignments a
            JOIN bloodstone_compute_jobs j
              ON j.job_id = a.job_id AND j.is_current = 1
            WHERE a.is_current = 1
              AND a.route_status = 'coordinator'
              AND j.status = 'pending'
              AND j.job_type = 'inference'
            ORDER BY a.updated_at ASC
            LIMIT ?
            """,
            (lim,),
        ).fetchall()

    processed = 0
    results: List[Dict[str, Any]] = []
    for row in rows:
        jid = str(row["job_id"])
        route_json: Dict[str, Any] = {}
        try:
            route_json = json.loads(row["route_json"] or "{}")
        except Exception:
            route_json = {}
        try:
            res = coordinator_dispatch_job(
                job_id=jid,
                callback_url=str(route_json.get("callback_url") or ""),
                origin_node_id=str(route_json.get("origin_node_id") or ""),
            )
            results.append(res)
            if res.get("ok"):
                processed += 1
        except Exception as exc:
            results.append({"ok": False, "job_id": jid, "error": str(exc)})
    return {"ok": True, "processed": processed, "results": results[:10]}


def route_inference_job(*, job_id: str, force: bool = False) -> Dict[str, Any]:
    if not AI_ROUTING_ENABLE:
        return {"ok": True, "skipped": True, "reason": "AI_ROUTING_ENABLE off"}

    init_ai_routing_db()
    job = cjobs.get_compute_job(job_id=job_id)
    if not job:
        raise ValueError("job not found")
    if job.get("job_type") != "inference":
        raise ValueError("job_type must be inference")

    existing = get_current_route_assignment(job_id=job_id)
    if existing and not force and existing.get("route_status") in ("assigned", "running", "completed"):
        return {"ok": True, "duplicate": True, "assignment": existing}

    quota = depin.check_compute_allowed(
        str(job.get("stone_address") or ""),
        flops_budget=int(job.get("flops_budget") or 0),
        job_id=str(job.get("job_id") or ""),
        blurt_author=str(job.get("blurt_author") or ""),
    )
    if not quota.get("allowed"):
        raise PermissionError(quota.get("reason") or "compute quota exceeded")

    uplink = uplink_available()
    spec = _job_ai_spec(job)
    prefer_offline = bool(spec.get("prefer_offline", AI_PREFER_OFFLINE))
    offline_mode = prefer_offline or not uplink.get("uplink_stable")

    from chain_mesh import tenant_ai_route as troute

    tenant_spec = troute.resolve_job_inference_spec(job)
    discover_ai_providers()
    rows = aip.list_ai_providers(limit=100).get("providers") or []
    candidates: List[Tuple[Dict[str, Any], float]] = []
    for row in rows:
        if offline_mode and row.get("provider_id") == COORDINATOR_AI_ID:
            continue
        if not offline_mode or row.get("provider_id") != COORDINATOR_AI_ID:
            sc = score_provider(row, job, offline_mode=offline_mode)
            candidates.append((row, sc))

    best = pick_best_provider(candidates)
    if best:
        provider, score = best
        pid = str(provider.get("provider_id") or "")
        sync_compute_job_route(
            job_id=job_id,
            provider_id=pid,
            route_status="assigned",
            score=score,
            reason="best_local_provider",
            uplink=uplink,
            offline_mode=offline_mode,
        )
        dispatch = dispatch_inference_job(
            job_id=job_id, provider=provider, tenant_spec=tenant_spec
        )
        try:
            from chain_mesh import tenant_route_ledger as tledger

            tledger.record_assignment(
                job=job,
                provider=provider,
                tenant_spec=tenant_spec,
                score=score,
                route_status="assigned",
            )
        except Exception:
            pass
        return {
            "ok": True,
            "job_id": job_id,
            "tenant_route": tenant_spec,
            "route_status": "assigned",
            "provider_id": pid,
            "score": score,
            "offline_mode": offline_mode,
            "dispatch": dispatch,
        }

    if uplink.get("uplink_stable"):
        sync_compute_job_route(
            job_id=job_id,
            provider_id=COORDINATOR_AI_ID,
            route_status="coordinator",
            reason="no_local_provider",
            uplink=uplink,
            offline_mode=offline_mode,
            route_json={"callback_url": f"{_public_callback_base()}/api/convergence/ai/callback"},
        )
        if _is_coordinator_node():
            dispatch = coordinator_dispatch_job(
                job_id=job_id,
                callback_url=f"{_public_callback_base()}/api/convergence/ai/callback",
                origin_node_id=_node_id(),
            )
            return {
                "ok": bool(dispatch.get("ok")),
                "job_id": job_id,
                "route_status": dispatch.get("route_status", "coordinator"),
                "provider_id": COORDINATOR_AI_ID,
                "offline_mode": offline_mode,
                "dispatch": dispatch,
            }
        dispatch = dispatch_to_coordinator(job_id=job_id)
        if dispatch.get("ok"):
            return {
                "ok": True,
                "job_id": job_id,
                "route_status": dispatch.get("route_status", "running"),
                "provider_id": COORDINATOR_AI_ID,
                "offline_mode": offline_mode,
                "dispatch": dispatch,
            }
        return {
            "ok": True,
            "job_id": job_id,
            "route_status": "coordinator",
            "provider_id": COORDINATOR_AI_ID,
            "offline_mode": offline_mode,
            "next_steps": "coordinator dispatch pending — retry upkeep or flush DTN",
            "dispatch": dispatch,
        }

    from chain_mesh import dtn_sync as dtn

    sync_compute_job_route(
        job_id=job_id,
        provider_id="",
        route_status="queued_dtn",
        reason="no_provider_offline",
        uplink=uplink,
        offline_mode=offline_mode,
    )
    raw, _fname, meta = build_ai_forward_bundle(job_id=job_id)
    queued = dtn.queue_bundle_for_forward(
        raw,
        node_id=_node_id(),
        region=_region(),
        meta=meta,
    )
    return {
        "ok": True,
        "job_id": job_id,
        "route_status": "queued_dtn",
        "queued": queued,
    }


def build_ai_forward_bundle(*, job_id: str) -> Tuple[bytes, str, Dict[str, Any]]:
    import hashlib
    import io
    import zipfile

    from chain_mesh import dtn_sync as dtn
    from chain_mesh.store import get_chunk

    job = cjobs.get_compute_job(job_id=job_id)
    if not job:
        raise ValueError("job not found")
    spec = _job_ai_spec(job)
    chunk_hashes: List[str] = list(job.get("input_asset_keys") or [])
    pk = str(spec.get("prompt_asset_key") or "")
    if pk and pk not in chunk_hashes:
        chunk_hashes.insert(0, pk)

    providers_rows = aip.list_ai_providers(region=str(job.get("region") or ""), limit=32).get("providers") or []
    route = get_current_route_assignment(job_id=job_id)
    import uuid

    meta = {
        "format": dtn.DTN_BUNDLE_FORMAT,
        "bundle_id": f"ai-{uuid.uuid4().hex[:16]}",
        "node_id": _node_id(),
        "region": _region(),
        "purpose": "ai_forward",
        "job_id": job_id,
        "ai_provider_count": len(providers_rows),
        "ai_route_count": 1 if route else 0,
        "exported_at": _now(),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("dtn-meta.json", json.dumps(meta, indent=2))
        zf.writestr("compute-jobs.json", json.dumps([job], indent=2, default=str))
        zf.writestr("ai-providers.json", json.dumps(providers_rows, indent=2, default=str))
        if route:
            zf.writestr("ai-route-assignments.json", json.dumps([route], indent=2, default=str))
        for h in chunk_hashes:
            if len(str(h)) != 64:
                continue
            data = get_chunk(h)
            if data:
                zf.writestr(f"chunks/{h}.bin", data)
    raw = buf.getvalue()
    filename = f"ai-forward-{job_id}.zip"
    meta["byte_size"] = len(raw)
    meta["sha256"] = hashlib.sha256(raw).hexdigest()
    return raw, filename, meta


def route_pending_inference_jobs(*, limit: int = 0) -> Dict[str, Any]:
    init_ai_routing_db()
    lim = max(1, int(limit or AI_AUTO_ROUTE_LIMIT))
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT job_id FROM bloodstone_compute_jobs
            WHERE is_current = 1 AND job_type = 'inference' AND status = 'pending'
            ORDER BY updated_at ASC
            LIMIT ?
            """,
            (lim,),
        ).fetchall()
    routed = 0
    results: List[Dict[str, Any]] = []
    for row in rows:
        jid = str(row["job_id"])
        current = get_current_route_assignment(job_id=jid)
        if current and current.get("route_status") in ("assigned", "running", "completed"):
            continue
        try:
            res = route_inference_job(job_id=jid)
            results.append(res)
            routed += 1
        except Exception as exc:
            results.append({"ok": False, "job_id": jid, "error": str(exc)})
    return {"ok": True, "routed": routed, "results": results[:10]}


def submit_inference_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    body_payload = dict(payload)
    body_payload["job_type"] = "inference"
    if payload.get("ai_spec"):
        body_payload["ai_spec"] = payload.get("ai_spec")
    result = cjobs.submit_payload(body_payload)
    auto_route = payload.get("auto_route", True) not in (False, "0", 0)
    route_result = None
    if auto_route and AI_ROUTING_ENABLE:
        try:
            route_result = route_inference_job(job_id=str(result.get("body", {}).get("job_id") or ""))
        except Exception as exc:
            route_result = {"ok": False, "error": str(exc)}
    result["route"] = route_result
    return result


def build_gossip_snapshots() -> List[Dict[str, Any]]:
    from chain_mesh import ai_gossip_sign as gsign

    init_ai_routing_db()
    snaps: List[Dict[str, Any]] = []
    for row in aip.list_ai_providers(limit=20).get("providers") or []:
        snaps.append(
            {
                "provider_id": row.get("provider_id"),
                "node_id": row.get("node_id"),
                "runtimes": json.loads(row.get("runtimes") or "[]"),
                "region": row.get("region"),
                "offline_capable": bool(int(row.get("offline_capable") or 0)),
                "load_ratio": float(row.get("load_ratio") or 0),
                "last_seen": int(row.get("last_seen") or 0),
            }
        )
    return gsign.sign_snapshots(snaps)


def ingest_route_assignments(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    init_ai_routing_db()
    recorded = 0
    skipped = 0
    for row in rows or []:
        if not isinstance(row, dict):
            skipped += 1
            continue
        jid = str(row.get("job_id") or "").strip()
        if not jid:
            skipped += 1
            continue
        existing = get_current_route_assignment(job_id=jid)
        ex_updated = int((existing or {}).get("updated_at") or 0)
        row_updated = int(row.get("updated_at") or 0)
        if existing and ex_updated >= row_updated:
            skipped += 1
            continue
        route_json = row.get("route_json")
        if isinstance(route_json, str):
            try:
                route_json = json.loads(route_json)
            except Exception:
                route_json = {}
        sync_compute_job_route(
            job_id=jid,
            provider_id=str(row.get("provider_id") or ""),
            route_status=str(row.get("route_status") or "pending"),
            score=float(row.get("score") or 0),
            reason=str(row.get("reason") or "dtn_import"),
            offline_mode=bool(int(row.get("offline_mode") or 0)),
            route_json=route_json if isinstance(route_json, dict) else {},
        )
        recorded += 1
    return {"ok": True, "recorded": recorded, "skipped": skipped}


def ingest_gossip_snapshots(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    from chain_mesh import ai_gossip_sign as gsign

    accepted, rejected = gsign.filter_verified_snapshots(snapshots)
    recorded = 0
    skipped = 0
    for snap in accepted:
        pid = str(snap.get("provider_id") or "").strip()
        if not pid:
            skipped += 1
            continue
        existing = aip.get_ai_provider(provider_id=pid)
        if existing:
            src = str(existing.get("source") or "")
            if src in ("local", "mdns", "lan", "coordinator"):
                ex_seen = int(existing.get("last_seen") or 0)
                snap_seen = int(snap.get("last_seen") or snap.get("signed_at") or 0)
                if ex_seen >= snap_seen:
                    skipped += 1
                    continue
        aip.register_ai_provider(provider_id=pid, source="gossip", merge=True, body=snap)
        recorded += 1
    return {
        "ok": True,
        "recorded": recorded,
        "skipped": skipped,
        "rejected": len(rejected),
        "rejections": rejected[:5],
    }


def upkeep_ai() -> Dict[str, Any]:
    if not AI_ROUTING_ENABLE:
        return {"ok": True, "skipped": True, "reason": "AI_ROUTING_ENABLE off"}

    discover = discover_ai_providers()
    probe = probe_ai_providers()
    purge = purge_stale_ai_providers()
    routed = route_pending_inference_jobs()
    coord = process_coordinator_dispatch_queue()
    result = {
        "ok": True,
        "discovered": discover.get("total"),
        "probed": probe.get("probed"),
        "purged": purge.get("purged"),
        "routed": routed.get("routed"),
        "coordinator_dispatched": coord.get("processed"),
    }
    _LAST_UPKEEP.clear()
    _LAST_UPKEEP.update(result)
    return result


def _gossip_sign_status() -> Dict[str, Any]:
    try:
        from chain_mesh import ai_gossip_sign as gsign

        return gsign.status_payload()
    except Exception:
        return {"ok": False}


def _npu_detect_status() -> Dict[str, Any]:
    try:
        from chain_mesh import ai_npu_detect as npu

        return npu.detect_npu_hardware()
    except Exception:
        return {"ok": False}


def status_payload(*, include_uplink: bool = True) -> Dict[str, Any]:
    init_ai_routing_db()
    uplink = (
        uplink_available(use_cache=True)
        if include_uplink
        else {"skipped": True, "reason": "nested_convergence_status"}
    )
    providers_count = aip.list_ai_providers(limit=1).get("count") or 0
    public = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    return {
        "ok": True,
        "format": AI_ROUTING_FORMAT,
        "enabled": AI_ROUTING_ENABLE,
        "prefer_offline": AI_PREFER_OFFLINE,
        "node_id": _node_id(),
        "region": _region(),
        "uplink": uplink,
        "providers_count": providers_count,
        "last_upkeep": dict(_LAST_UPKEEP),
        "wave": "Z",
        "coordinator_dispatch": AI_COORDINATOR_DISPATCH_ENABLE,
        "coordinator_node": _is_coordinator_node(),
        "gossip_sign": _gossip_sign_status(),
        "npu_detect": _npu_detect_status(),
        "apis": {
            "status": f"{public}/api/convergence/ai/status",
            "providers": f"{public}/api/convergence/ai/providers",
            "route": f"{public}/api/convergence/ai/route",
            "submit": f"{public}/api/convergence/ai/submit",
            "dispatch": f"{public}/api/convergence/ai/dispatch",
            "callback": f"{public}/api/convergence/ai/callback",
            "npu_status": f"{public}/api/convergence/ai/npu/status",
            "provider_health": f"{public}/api/convergence/ai/provider/health",
        },
    }