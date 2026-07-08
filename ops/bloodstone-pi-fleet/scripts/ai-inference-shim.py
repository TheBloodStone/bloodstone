#!/usr/bin/env python3
"""Wave Q — OpenAI-compatible inference shim for llama.cpp / beta stub."""

from __future__ import annotations

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple
from urllib import error, request

PORT = int(os.environ.get("AI_INFERENCE_PORT", "8081"))
HOST = os.environ.get("AI_INFERENCE_BIND", "0.0.0.0")
LLAMA_URL = (os.environ.get("LLAMA_SERVER_URL") or "").strip().rstrip("/")
TIMEOUT_SEC = max(5, int(os.environ.get("AI_INFERENCE_TIMEOUT_SEC", "120")))


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


def _stub_completion(body: Dict[str, Any]) -> Dict[str, Any]:
    prompt = str(body.get("prompt") or "").strip()
    model = str(body.get("model") or "llama.cpp-stub")
    max_tokens = max(1, int(body.get("max_tokens") or 64))
    text = prompt[: max_tokens * 4] if prompt else "Bloodstone inference shim ready."
    if not text.endswith("."):
        text = f"{text} [stub]"
    return {
        "id": f"cmpl-bloodstone-{int(time.time())}",
        "object": "text_completion",
        "model": model,
        "choices": [{"text": text, "index": 0, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": len(prompt.split()),
            "completion_tokens": len(text.split()),
            "flops_estimated": int(os.environ.get("AI_FLOPS_PER_SEC", "500000000")),
        },
    }


class InferenceHandler(BaseHTTPRequestHandler):
    server_version = "BloodstoneInferenceShim/1.0"

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
            self._send_json(200, {"ok": True, "service": "bloodstone-ai-inference", "port": PORT})
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

        if LLAMA_URL:
            status, payload = _proxy_llama(body)
            if status == 200 and isinstance(payload, dict) and payload.get("choices"):
                self._send_json(200, payload)
                return

        self._send_json(200, _stub_completion(body))


def main() -> int:
    httpd = ThreadingHTTPServer((HOST, PORT), InferenceHandler)
    sys.stderr.write(f"[ai-inference] listening on {HOST}:{PORT} llama={LLAMA_URL or 'stub'}\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())