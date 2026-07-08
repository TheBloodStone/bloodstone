"""Wave X — tenant NPU-aware AI provider scoring and dispatch hints."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

ROUTE_FORMAT = "bloodstone_tenant_ai_route/v1"
TENANT_ROUTE_ENABLE = os.environ.get("TENANT_AI_ROUTE_ENABLE", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)


def _default_tenant() -> str:
    return (os.environ.get("DTN_DEFAULT_TENANT") or "bloodstone").strip()[:64] or "bloodstone"


def _normalize_author(value: str = "") -> str:
    return (value or "").lstrip("@").lower().strip()[:64]


def resolve_job_inference_spec(job: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import tenant_npu_models as tnpu

    author = _normalize_author(str(job.get("blurt_author") or ""))
    tid = str(job.get("tenant_id") or _default_tenant()).strip()[:64] or _default_tenant()
    ai_spec = job.get("ai_spec")
    if isinstance(ai_spec, str):
        try:
            ai_spec = json.loads(ai_spec)
        except json.JSONDecodeError:
            ai_spec = {}
    if not isinstance(ai_spec, dict):
        ai_spec = {}
    runtime_hint = str(ai_spec.get("runtime") or "")
    tenant_spec = (
        tnpu.resolve_inference_spec(
            blurt_author=author,
            tenant_id=tid,
            runtime_hint=runtime_hint,
        )
        if author
        else {"ok": True, "runtime": runtime_hint or "cpu-inference", "source": "job_only"}
    )
    merged_runtime = runtime_hint or str(tenant_spec.get("runtime") or "cpu-inference")
    return {
        "ok": True,
        "format": ROUTE_FORMAT,
        "tenant_id": tid,
        "blurt_author": author,
        "runtime": merged_runtime,
        "model_path": str(tenant_spec.get("model_path") or ""),
        "hardware_kind": str(tenant_spec.get("hardware_kind") or "cpu"),
        "source": tenant_spec.get("source") or "merged",
        "ai_spec": ai_spec,
    }


def tenant_route_bonus(
    provider: Dict[str, Any],
    *,
    spec: Dict[str, Any],
) -> float:
    if not TENANT_ROUTE_ENABLE:
        return 0.0
    runtime = str(spec.get("runtime") or "").lower()
    if not runtime or runtime == "cpu-inference":
        return 0.0
    runtimes = json.loads(provider.get("runtimes") or "[]")
    bonus = 0.0
    if runtime in [str(r).lower() for r in runtimes]:
        bonus += 55.0
    hardware = json.loads(provider.get("hardware_json") or "{}")
    hw_kind = str(spec.get("hardware_kind") or "").lower()
    provider_kind = str(hardware.get("kind") or hardware.get("hardware_kind") or "").lower()
    if hw_kind and provider_kind and hw_kind in provider_kind:
        bonus += 35.0
    models = json.loads(provider.get("models_json") or "[]")
    model_path = str(spec.get("model_path") or "")
    if model_path and any(str(m.get("path") or "") == model_path for m in models):
        bonus += 25.0
    return bonus


def build_dispatch_payload(
    job: Dict[str, Any],
    *,
    spec: Optional[Dict[str, Any]] = None,
    base_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    resolved = spec or resolve_job_inference_spec(job)
    payload = dict(base_payload or {})
    author = _normalize_author(str(job.get("blurt_author") or resolved.get("blurt_author") or ""))
    tid = str(job.get("tenant_id") or resolved.get("tenant_id") or _default_tenant())
    payload.setdefault("blurt_author", author)
    payload.setdefault("tenant_id", tid)
    payload.setdefault("runtime", resolved.get("runtime") or payload.get("runtime"))
    if resolved.get("model_path"):
        payload.setdefault("model", os.path.basename(str(resolved["model_path"])))
    return payload


def route_status_for_job(job: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import tenant_submit_gate as tgate

    author = _normalize_author(str(job.get("blurt_author") or ""))
    tid = str(job.get("tenant_id") or _default_tenant())
    spec = resolve_job_inference_spec(job)
    gate = tgate.check_submit_allowed(
        tenant_id=tid,
        blurt_author=author,
        stone_address=str(job.get("stone_address") or ""),
    )
    return {
        "ok": True,
        "format": ROUTE_FORMAT,
        "enabled": TENANT_ROUTE_ENABLE,
        "inference_spec": spec,
        "submit_gate": gate,
    }


def status_payload() -> Dict[str, Any]:
    public = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    return {
        "ok": True,
        "format": ROUTE_FORMAT,
        "enabled": TENANT_ROUTE_ENABLE,
        "default_tenant": _default_tenant(),
        "apis": {
            "status": f"{public}/api/convergence/tenant/ai/route/status",
            "resolve": f"{public}/api/convergence/tenant/ai/route/resolve",
        },
    }