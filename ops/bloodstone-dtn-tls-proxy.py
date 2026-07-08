#!/usr/bin/env python3
"""TLS front door for Pi DTN nodes — proxies HTTPS :8443 → local portal HTTP :8887."""

from __future__ import annotations

import http.server
import os
import socketserver
import ssl
import sys
import urllib.error
import urllib.request
from typing import Tuple

BACKEND = os.environ.get("DTN_TLS_BACKEND", "http://127.0.0.1:8887").rstrip("/")
PORT = int(os.environ.get("DTN_LAN_TLS_PORT", "8443"))
CERT = os.environ.get("DTN_TLS_CERT", "/etc/bloodstone/dtn/tls.crt")
KEY = os.environ.get("DTN_TLS_KEY", "/etc/bloodstone/dtn/tls.key")
TIMEOUT = int(os.environ.get("DTN_TLS_PROXY_TIMEOUT", "120"))


class _ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[dtn-tls-proxy] " + (fmt % args) + "\n")

    def _proxy(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        url = f"{BACKEND}{self.path}"
        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in ("host", "connection", "content-length")
        }
        if body is not None:
            headers["Content-Length"] = str(len(body))
        req = urllib.request.Request(
            url,
            data=body,
            method=self.command,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                payload = resp.read()
                self.send_response(resp.status)
                for key, value in resp.headers.items():
                    if key.lower() not in ("connection", "transfer-encoding"):
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(payload)
        except urllib.error.HTTPError as exc:
            payload = exc.read() if exc.fp else b""
            self.send_response(exc.code)
            self.send_header("Content-Type", exc.headers.get("Content-Type", "text/plain"))
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
        except Exception as exc:
            msg = str(exc).encode("utf-8", errors="replace")
            self.send_response(502)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def do_GET(self) -> None:
        self._proxy()

    def do_HEAD(self) -> None:
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()

    def do_PUT(self) -> None:
        self._proxy()


def main() -> int:
    if not os.path.isfile(CERT) or not os.path.isfile(KEY):
        print(f"dtn-tls-proxy missing cert/key: {CERT} {KEY}", file=sys.stderr)
        return 1
    with socketserver.ThreadingTCPServer(("", PORT), _ProxyHandler) as httpd:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(CERT, KEY)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        print(
            "dtn-tls-proxy",
            f"listen={PORT}",
            f"backend={BACKEND}",
            f"cert={CERT}",
        )
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())