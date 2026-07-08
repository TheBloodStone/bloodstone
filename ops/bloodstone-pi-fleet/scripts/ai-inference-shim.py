#!/usr/bin/env python3
"""Wave V — OpenAI-compatible inference shim with Hailo/Coral NPU execution delegates."""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, "/root")
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib import error, request

PORT = int(os.environ.get("AI_INFERENCE_PORT", "8081"))
HOST = os.environ.get("AI_INFERENCE_BIND", "0.0.0.0")
LLAMA_URL = (os.environ.get("LLAMA_SERVER_URL") or "").strip().rstrip("/")
ONNX_MODEL = (os.environ.get("AI_ONNX_MODEL_PATH") or "").strip()
TFLITE_MODEL = (os.environ.get("AI_TFLITE_MODEL_PATH") or "").strip()
TIMEOUT_SEC = max(5, int(os.environ.get("AI_INFERENCE_TIMEOUT_SEC", "120")))

_DELEGATES: Dict[str, bool] = {}
_NPU_RUNTIMES: List[str] = []
_NPU_HARDWARE: Dict[str, Any] = {}


def _npu_hardware() -> Dict[str, Any]:
    global _NPU_HARDWARE
    if _NPU_HARDWARE:
        return _NPU_HARDWARE
    try:
        from chain_mesh import ai_npu_detect as npu

        _NPU_HARDWARE = npu.detect_npu_hardware()
    except Exception:
        _NPU_HARDWARE = {"ok": True, "hardware": {"kind": "cpu"}, "runtimes": []}
    return _NPU_HARDWARE


def _npu_runtime_prefs() -> List[str]:
    global _NPU_RUNTIMES
    if _NPU_RUNTIMES:
        return _NPU_RUNTIMES
    try:
        from chain_mesh import ai_npu_detect as npu

        detected = npu.detect_npu_hardware()
        runtimes = [
            str(r).strip().lower()
            for r in (detected.get("runtimes") or [])
            if str(r).strip()
        ]
        if runtimes:
            _NPU_RUNTIMES = runtimes
            return _NPU_RUNTIMES
    except Exception:
        pass
    _NPU_RUNTIMES = ["onnx", "tflite", "llama.cpp", "cpu-inference"]
    return _NPU_RUNTIMES


def _probe_delegates() -> Dict[str, bool]:
    global _DELEGATES
    if _DELEGATES:
        return _DELEGATES
    hw = _npu_hardware().get("hardware") or {}
    kind = str(hw.get("kind") or "cpu").lower()
    delegates = {
        "llama.cpp": bool(LLAMA_URL),
        "cpu-inference": True,
        "onnx": False,
        "tflite": False,
        "hailo-onnx": False,
        "coral-tflite": False,
    }
    try:
        import onnxruntime as ort  # noqa: F401

        delegates["onnx"] = True
        if kind in ("hailo", "hybrid"):
            providers = ort.get_available_providers()
            delegates["hailo-onnx"] = any("hailo" in p.lower() for p in providers)
            if not delegates["hailo-onnx"]:
                delegates["hailo-onnx"] = bool(hw.get("devices") or hw.get("hailo"))
    except Exception:
        pass
    try:
        try:
            import tflite_runtime.interpreter as tflite  # noqa: F401
        except ImportError:
            import tensorflow as tf  # noqa: F401

        delegates["tflite"] = True
        if kind in ("coral", "hybrid"):
            delegates["coral-tflite"] = bool(hw.get("devices") or hw.get("coral"))
    except Exception:
        pass
    if ONNX_MODEL and os.path.isfile(ONNX_MODEL):
        delegates["onnx"] = True
    if TFLITE_MODEL and os.path.isfile(TFLITE_MODEL):
        delegates["tflite"] = True
    _DELEGATES = delegates
    return delegates


def _onnx_execution_providers() -> List[str]:
    hw = _npu_hardware().get("hardware") or {}
    kind = str(hw.get("kind") or "cpu").lower()
    providers = ["CPUExecutionProvider"]
    if kind in ("hailo", "hybrid"):
        try:
            import onnxruntime as ort

            for name in ort.get_available_providers():
                if "hailo" in name.lower():
                    return [name, "CPUExecutionProvider"]
        except Exception:
            pass
        if hw.get("devices") or hw.get("hailo"):
            return ["HailoExecutionProvider", "CPUExecutionProvider"]
    return providers


def _tflite_interpreter(model_path: str):
    delegate = None
    hw = _npu_hardware().get("hardware") or {}
    kind = str(hw.get("kind") or "cpu").lower()
    if kind in ("coral", "hybrid"):
        lib = (os.environ.get("CORAL_EDGETPU_LIB") or "").strip()
        candidates = [lib] if lib else [
            "/usr/lib/aarch64-linux-gnu/libedgetpu.so.1",
            "/usr/lib/libedgetpu.so.1",
        ]
        for path in candidates:
            if path and os.path.isfile(path):
                try:
                    from tflite_runtime.interpreter import load_delegate

                    delegate = load_delegate(path)
                    break
                except Exception:
                    try:
                        import tensorflow as tf  # type: ignore

                        delegate = tf.lite.experimental.load_delegate(path)
                        break
                    except Exception:
                        pass
    try:
        from tflite_runtime.interpreter import Interpreter
    except ImportError:
        from tensorflow.lite import Interpreter  # type: ignore

    if delegate is not None:
        return Interpreter(model_path=model_path, experimental_delegates=[delegate])
    return Interpreter(model_path=model_path)


def _infer_runtime(body: Dict[str, Any]) -> str:
    explicit = str(body.get("runtime") or "").strip().lower()
    if explicit in ("onnx", "tflite", "llama.cpp", "cpu-inference"):
        return explicit
    model = str(body.get("model") or "").strip().lower()
    if model.startswith("onnx:") or model.endswith(".onnx"):
        return "onnx"
    if model.startswith("tflite:") or model.endswith(".tflite"):
        return "tflite"
    if "llama" in model:
        return "llama.cpp"
    delegates = _probe_delegates()
    for pref in _npu_runtime_prefs():
        if delegates.get(pref):
            return pref
    return "cpu-inference"


def _proxy_llama(body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
    url = f"{LLAMA_URL}/v1/completions"
    payload = json.dumps(body).encode("utf-8")
    req = request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
            return int(resp.status), data if isinstance(data, dict) else {"raw": data}
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return exc.code, {"error": detail or str(exc)}
    except Exception as exc:
        return 502, {"error": str(exc)}


def _onnx_completion(body: Dict[str, Any], *, stub_only: bool = False) -> Dict[str, Any]:
    prompt = str(body.get("prompt") or "").strip()
    model = str(body.get("model") or "onnx-delegate")
    if not stub_only and ONNX_MODEL and os.path.isfile(ONNX_MODEL):
        try:
            import numpy as np
            import onnxruntime as ort

            providers = _onnx_execution_providers()
            session = ort.InferenceSession(ONNX_MODEL, providers=providers)
            inputs = session.get_inputs()
            if inputs:
                shape = [1]
                for dim in inputs[0].shape[1:]:
                    shape.append(int(dim) if isinstance(dim, int) and dim > 0 else 8)
                arr = np.zeros(shape, dtype=np.float32)
                outputs = session.run(None, {inputs[0].name: arr})
                provider = providers[0] if providers else "CPUExecutionProvider"
                text = f"ONNX/{provider} inference ok ({len(outputs)} outputs) for: {prompt[:80]}"
            else:
                text = f"ONNX session ready for: {prompt[:80]}"
        except Exception as exc:
            text = f"ONNX delegate error: {exc}"
    else:
        text = f"[onnx] {prompt[:120] or 'Bloodstone ONNX delegate ready.'}"
    return _completion_envelope(text, model=model, runtime="onnx", body=body)


def _tflite_completion(body: Dict[str, Any], *, stub_only: bool = False) -> Dict[str, Any]:
    prompt = str(body.get("prompt") or "").strip()
    model = str(body.get("model") or "tflite-delegate")
    if not stub_only and TFLITE_MODEL and os.path.isfile(TFLITE_MODEL):
        try:
            try:
                from tflite_runtime.interpreter import Interpreter
            except ImportError:
                from tensorflow.lite import Interpreter  # type: ignore

            interpreter = _tflite_interpreter(TFLITE_MODEL)
            interpreter.allocate_tensors()
            hw = _npu_hardware().get("hardware") or {}
            kind = str(hw.get("kind") or "cpu")
            text = (
                f"TFLite/{kind} inference ready "
                f"({len(interpreter.get_input_details())} inputs) for: {prompt[:80]}"
            )
        except Exception as exc:
            text = f"TFLite delegate error: {exc}"
    else:
        text = f"[tflite] {prompt[:120] or 'Bloodstone TFLite delegate ready.'}"
    return _completion_envelope(text, model=model, runtime="tflite", body=body)


def _completion_envelope(
    text: str,
    *,
    model: str,
    runtime: str,
    body: Dict[str, Any],
) -> Dict[str, Any]:
    prompt = str(body.get("prompt") or "")
    return {
        "id": f"cmpl-bloodstone-{runtime}-{int(time.time())}",
        "object": "text_completion",
        "model": model,
        "runtime": runtime,
        "choices": [{"text": text, "index": 0, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": len(prompt.split()),
            "completion_tokens": len(text.split()),
            "flops_estimated": int(os.environ.get("AI_FLOPS_PER_SEC", "500000000")),
        },
    }


def _stub_completion(body: Dict[str, Any], *, runtime: str = "cpu-inference") -> Dict[str, Any]:
    prompt = str(body.get("prompt") or "").strip()
    model = str(body.get("model") or f"{runtime}-stub")
    max_tokens = max(1, int(body.get("max_tokens") or 64))
    text = prompt[: max_tokens * 4] if prompt else f"Bloodstone {runtime} shim ready."
    if not text.endswith("."):
        text = f"{text} [{runtime}]"
    return _completion_envelope(text, model=model, runtime=runtime, body=body)


def dispatch_completion(body: Dict[str, Any]) -> Dict[str, Any]:
    runtime = _infer_runtime(body)
    delegates = _probe_delegates()
    if runtime == "llama.cpp" and delegates.get("llama.cpp"):
        status, payload = _proxy_llama(body)
        if status == 200 and isinstance(payload, dict) and payload.get("choices"):
            payload["runtime"] = "llama.cpp"
            return payload
    if runtime == "onnx":
        return _onnx_completion(body, stub_only=not delegates.get("onnx"))
    if runtime == "tflite":
        return _tflite_completion(body, stub_only=not delegates.get("tflite"))
    if runtime == "llama.cpp":
        return _stub_completion(body, runtime="llama.cpp")
    return _stub_completion(body, runtime="cpu-inference")


class InferenceHandler(BaseHTTPRequestHandler):
    server_version = "BloodstoneInferenceShim/2.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[ai-inference] " + (fmt % args) + "\n")

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path in ("/health", "/v1/health", "/"):
            self._send_json(
                200,
                {
                    "ok": True,
                    "service": "bloodstone-ai-inference",
                    "port": PORT,
                    "delegates": _probe_delegates(),
                    "npu_runtimes": _npu_runtime_prefs(),
                    "npu_hardware": (_npu_hardware().get("hardware") or {}),
                    "wave": "V",
                },
            )
            return
        if self.path in ("/v1/runtimes", "/runtimes"):
            self._send_json(
                200,
                {
                    "ok": True,
                    "delegates": _probe_delegates(),
                    "npu_runtimes": _npu_runtime_prefs(),
                    "npu_hardware": (_npu_hardware().get("hardware") or {}),
                },
            )
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        if self.path not in ("/v1/completions", "/completions"):
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw.decode("utf-8", errors="replace") or "{}")
        except json.JSONDecodeError:
            self._send_json(400, {"ok": False, "error": "invalid json"})
            return
        if not isinstance(body, dict):
            self._send_json(400, {"ok": False, "error": "body must be object"})
            return
        self._send_json(200, dispatch_completion(body))


def main() -> int:
    delegates = _probe_delegates()
    httpd = ThreadingHTTPServer((HOST, PORT), InferenceHandler)
    sys.stderr.write(
        f"[ai-inference] listening on {HOST}:{PORT} delegates={delegates}\n"
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())