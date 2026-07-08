"""Wave M — on-device AI routing for inference compute jobs."""

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

COORDINATOR_AI_ID = "bloodstone-coordinator-v1-ai"
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


def uplink_available() -> Dict[str, Any]:
    from chain_mesh import dtn_starlink as starlink

    probe_url = AI_UPLINK_PROBE_URL or starlink.PROBE_URL
    probe = starlink.probe_uplink(url=probe_url)
    streak = int(probe.get("probe_streak") or 0)
    connected = bool(probe.get("connected"))
    return {
        "connected": connected,
        "latency_ms": probe.get("latency_ms"),
        "probe_url": probe.get("probe_url"),
        "probe_streak": streak,
        "source": "starlink" if connected else "none",
        "uplink_stable": connected and streak >= starlink.PROBE_STREAK_REQUIRED,
    }


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
    register_local_provider(
        provider_id=COORDINATOR_AI_ID,
        node_id="coordinator-vps",
        display_name="Bloodstone Coordinator AI",
        runtimes=["cpu-inference"],
        region="global",
        offline_capable=False,
        source="coordinator",
        endpoints={},
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
    register_local_provider()
    discovered = 0

    try:
        from chain_mesh import mdns_discovery as mdns

        if os.environ.get("AI_MDNS_ENABLE", "1").strip() not in ("0", "false", "no"):
            browse = mdns.discover_mdns_ai_providers(register=True)
            discovered += int(browse.get("registered") or 0)
    except Exception:
        pass

    mesh = providers.list_providers()
    for row in mesh.get("providers") or []:
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

    total = aip.list_ai_providers(limit=200).get("count") or 0
    return {"ok": True, "discovered": discovered, "total": total}


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
        depin.record_compute_usage(addr, delta_flops=flops)
    return {"ok": True, "job_id": jid, "flops_debited": flops}


def dispatch_inference_job(*, job_id: str, provider: Dict[str, Any]) -> Dict[str, Any]:
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

    payload = {
        "model": spec.get("model_id") or "default",
        "prompt": prompt_text,
        "max_tokens": int(spec.get("max_tokens") or 256),
        "temperature": float(spec.get("temperature") or 0.7),
        "job_id": job_id,
        "stone_address": job.get("stone_address"),
        "stream": False,
    }
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
            output_key = str(body.get("output_asset_key") or "").strip()
            if not output_key:
                choices = body.get("choices") or []
                text = ""
                if choices and isinstance(choices[0], dict):
                    text = str(choices[0].get("text") or choices[0].get("message", {}).get("content") or "")
                if text:
                    import hashlib

                    output_key = hashlib.sha256(text.encode()).hexdigest()
                    put_chunk(output_key, text.encode("utf-8"))
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
    )
    if not quota.get("allowed"):
        raise PermissionError(quota.get("reason") or "compute quota exceeded")

    uplink = uplink_available()
    spec = _job_ai_spec(job)
    prefer_offline = bool(spec.get("prefer_offline", AI_PREFER_OFFLINE))
    offline_mode = prefer_offline or not uplink.get("uplink_stable")

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
        dispatch = dispatch_inference_job(job_id=job_id, provider=provider)
        return {
            "ok": True,
            "job_id": job_id,
            "route_status": "assigned",
            "provider_id": pid,
            "score": score,
            "offline_mode": offline_mode,
            "dispatch": dispatch,
        }

    if uplink.get("uplink_stable"):
        sync_compute_job_route(
            job_id=job_id,
            provider_id="bloodstone-coordinator-v1",
            route_status="coordinator",
            reason="no_local_provider",
            uplink=uplink,
            offline_mode=offline_mode,
        )
        return {
            "ok": True,
            "job_id": job_id,
            "route_status": "coordinator",
            "next_steps": "flush DTN or wait for coordinator upkeep",
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
    return snaps


def ingest_gossip_snapshots(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    recorded = 0
    for snap in snapshots or []:
        if not isinstance(snap, dict):
            continue
        pid = str(snap.get("provider_id") or "").strip()
        if not pid:
            continue
        aip.register_ai_provider(provider_id=pid, source="gossip", merge=True, body=snap)
        recorded += 1
    return {"ok": True, "recorded": recorded}


def upkeep_ai() -> Dict[str, Any]:
    if not AI_ROUTING_ENABLE:
        return {"ok": True, "skipped": True, "reason": "AI_ROUTING_ENABLE off"}

    discover = discover_ai_providers()
    probe = probe_ai_providers()
    purge = purge_stale_ai_providers()
    routed = route_pending_inference_jobs()
    result = {
        "ok": True,
        "discovered": discover.get("total"),
        "probed": probe.get("probed"),
        "purged": purge.get("purged"),
        "routed": routed.get("routed"),
    }
    _LAST_UPKEEP.clear()
    _LAST_UPKEEP.update(result)
    return result


def status_payload() -> Dict[str, Any]:
    init_ai_routing_db()
    uplink = uplink_available()
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
        "apis": {
            "status": f"{public}/api/convergence/ai/status",
            "providers": f"{public}/api/convergence/ai/providers",
            "route": f"{public}/api/convergence/ai/route",
            "submit": f"{public}/api/convergence/ai/submit",
            "provider_health": f"{public}/api/convergence/ai/provider/health",
        },
    }