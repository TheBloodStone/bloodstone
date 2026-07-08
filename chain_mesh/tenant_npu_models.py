"""Wave W/X — per-tenant NPU model bindings + probe validation."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db

NPU_FORMAT = "bloodstone_tenant_npu/v1"
VALID_RUNTIMES = frozenset({"onnx", "tflite"})


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def _default_tenant() -> str:
    return (os.environ.get("DTN_DEFAULT_TENANT") or "bloodstone").strip()[:64] or "bloodstone"


def _normalize_author(value: str = "") -> str:
    return (value or "").lstrip("@").lower().strip()[:64]


def init_tenant_npu_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tenant_npu_bindings (
                tenant_id TEXT NOT NULL,
                blurt_author TEXT NOT NULL,
                runtime TEXT NOT NULL,
                model_path TEXT NOT NULL DEFAULT '',
                hardware_kind TEXT NOT NULL DEFAULT 'cpu',
                preferred INTEGER NOT NULL DEFAULT 1,
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (tenant_id, blurt_author, runtime)
            );
            CREATE INDEX IF NOT EXISTS idx_tenant_npu_author
                ON tenant_npu_bindings(blurt_author, preferred DESC);
            """
        )


def bind_npu_model(
    *,
    tenant_id: str = "",
    blurt_author: str = "",
    runtime: str = "",
    model_path: str = "",
    hardware_kind: str = "",
    preferred: bool = True,
) -> Dict[str, Any]:
    init_tenant_npu_db()
    tid = (tenant_id or _default_tenant()).strip()[:64] or _default_tenant()
    author = _normalize_author(blurt_author)
    if not author:
        raise ValueError("blurt_author required")
    rt = (runtime or "").strip().lower()
    if rt not in VALID_RUNTIMES:
        raise ValueError(f"runtime must be one of: {sorted(VALID_RUNTIMES)}")
    path = (model_path or "").strip()
    hw = (hardware_kind or "cpu").strip().lower()[:32]
    now = _now()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO tenant_npu_bindings (
                tenant_id, blurt_author, runtime, model_path, hardware_kind,
                preferred, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tenant_id, blurt_author, runtime) DO UPDATE SET
                model_path = CASE WHEN excluded.model_path != ''
                    THEN excluded.model_path ELSE model_path END,
                hardware_kind = excluded.hardware_kind,
                preferred = excluded.preferred,
                updated_at = excluded.updated_at
            """,
            (tid, author, rt, path, hw, 1 if preferred else 0, now),
        )
    return {
        "ok": True,
        "format": NPU_FORMAT,
        "tenant_id": tid,
        "blurt_author": author,
        "runtime": rt,
        "model_path": path,
        "hardware_kind": hw,
    }


def list_npu_models(
    *,
    tenant_id: str = "",
    blurt_author: str = "",
) -> List[Dict[str, Any]]:
    init_tenant_npu_db()
    tid = (tenant_id or _default_tenant()).strip()[:64] or _default_tenant()
    author = _normalize_author(blurt_author)
    with _conn() as conn:
        if author:
            rows = conn.execute(
                """
                SELECT * FROM tenant_npu_bindings
                WHERE tenant_id = ? AND blurt_author = ?
                ORDER BY preferred DESC, updated_at DESC
                """,
                (tid, author),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM tenant_npu_bindings
                WHERE tenant_id = ?
                ORDER BY updated_at DESC
                LIMIT 50
                """,
                (tid,),
            ).fetchall()
    return [dict(r) for r in rows]


def resolve_inference_spec(
    *,
    blurt_author: str = "",
    tenant_id: str = "",
    runtime_hint: str = "",
) -> Dict[str, Any]:
    init_tenant_npu_db()
    tid = (tenant_id or _default_tenant()).strip()[:64] or _default_tenant()
    author = _normalize_author(blurt_author)
    models = list_npu_models(tenant_id=tid, blurt_author=author) if author else []
    hint = (runtime_hint or "").strip().lower()
    chosen: Optional[Dict[str, Any]] = None
    if hint:
        for row in models:
            if str(row.get("runtime") or "") == hint:
                chosen = row
                break
    if not chosen and models:
        chosen = models[0]
    if not chosen:
        try:
            from chain_mesh import ai_npu_detect as npu

            detected = npu.detect_npu_hardware()
            hw = detected.get("hardware") or {}
            kind = str(hw.get("kind") or "cpu").lower()
            runtimes = [
                str(r).strip().lower()
                for r in (detected.get("runtimes") or [])
                if str(r).strip()
            ]
            rt = runtimes[0] if runtimes else "cpu-inference"
            if rt in VALID_RUNTIMES:
                return {
                    "ok": True,
                    "runtime": rt,
                    "model_path": "",
                    "hardware_kind": kind,
                    "source": "npu_detect",
                }
        except Exception:
            pass
        return {"ok": True, "runtime": "cpu-inference", "model_path": "", "source": "default"}
    return {
        "ok": True,
        "runtime": str(chosen.get("runtime") or ""),
        "model_path": str(chosen.get("model_path") or ""),
        "hardware_kind": str(chosen.get("hardware_kind") or "cpu"),
        "source": "tenant_binding",
        "tenant_id": tid,
        "blurt_author": author,
    }


def npu_models_for_manifest(
    *,
    tenant_id: str = "",
    blurt_author: str = "",
) -> List[Dict[str, Any]]:
    rows = list_npu_models(tenant_id=tenant_id, blurt_author=blurt_author)
    return [
        {
            "runtime": str(r.get("runtime") or ""),
            "model_path": str(r.get("model_path") or ""),
            "hardware_kind": str(r.get("hardware_kind") or "cpu"),
        }
        for r in rows
    ]


def probe_model(*, runtime: str = "", model_path: str = "") -> Dict[str, Any]:
    rt = (runtime or "").strip().lower()
    path = (model_path or "").strip()
    if rt not in VALID_RUNTIMES:
        return {"ok": False, "error": f"runtime must be one of: {sorted(VALID_RUNTIMES)}"}
    if not path:
        return {"ok": False, "error": "model_path required"}
    if not os.path.isfile(path):
        return {"ok": False, "error": "model file not found", "model_path": path}
    loadable = False
    detail = ""
    if rt == "onnx":
        try:
            import onnxruntime as ort

            session = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
            loadable = True
            detail = f"inputs={len(session.get_inputs())}"
        except Exception as exc:
            detail = str(exc)
    elif rt == "tflite":
        try:
            try:
                from tflite_runtime.interpreter import Interpreter
            except ImportError:
                from tensorflow.lite import Interpreter  # type: ignore

            interpreter = Interpreter(model_path=path)
            interpreter.allocate_tensors()
            loadable = True
            detail = f"inputs={len(interpreter.get_input_details())}"
        except Exception as exc:
            detail = str(exc)
    return {
        "ok": loadable,
        "runtime": rt,
        "model_path": path,
        "loadable": loadable,
        "detail": detail,
    }


def status_payload() -> Dict[str, Any]:
    init_tenant_npu_db()
    with _conn() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM tenant_npu_bindings").fetchone()["c"]
    public = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    return {
        "ok": True,
        "format": NPU_FORMAT,
        "bindings_count": int(count),
        "valid_runtimes": sorted(VALID_RUNTIMES),
        "apis": {
            "bind": f"{public}/api/convergence/tenant/npu/bind",
            "status": f"{public}/api/convergence/tenant/npu/status",
            "resolve": f"{public}/api/convergence/tenant/npu/resolve",
            "probe": f"{public}/api/convergence/tenant/npu/probe",
        },
    }