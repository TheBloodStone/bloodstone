#!/usr/bin/env python3
"""
Household mesh internet gateway — share your internet with all LAN miners.

Run on a PC or Android-adjacent host that has real internet. Registers as
the elected BSM4 egress peer; processes IPv4 mesh packets locally.

Install: install-lan-mesh-gateway.sh
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

POOL_URL = os.environ.get("POOL_URL", "https://bloodstonewallet.mytunnel.org").rstrip("/")
DEVICE_ID = os.environ.get("MESH_GATEWAY_DEVICE_ID", "").strip().lower()
PUBLIC_IP = os.environ.get("MESH_GATEWAY_PUBLIC_IP", "").strip()
LAN_IP = os.environ.get("MESH_GATEWAY_LAN_IP", "").strip()
INTERVAL = float(os.environ.get("MESH_GATEWAY_INTERVAL", "4"))
PEER_KIND = os.environ.get("MESH_GATEWAY_PEER_KIND", "pc")


def _post(path: str, body: dict) -> dict:
    url = f"{POOL_URL}{path}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _detect_public_ip() -> str:
    if PUBLIC_IP:
        return PUBLIC_IP
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=8) as resp:
            return resp.read().decode("utf-8").strip()
    except Exception:
        return ""


def main() -> int:
    device_id = DEVICE_ID
    if not device_id:
        print("MESH_GATEWAY_DEVICE_ID required", file=sys.stderr)
        return 1

    public_ip = _detect_public_ip()
    print(f"mesh internet gateway {device_id} public_ip={public_ip or '?'}", flush=True)

    while True:
        try:
            reg = _post(
                "/api/chain-mesh/internet-gateway/register",
                {
                    "device_id": device_id,
                    "public_ip": public_ip,
                    "lan_ip": LAN_IP,
                    "peer_kind": PEER_KIND,
                    "share_internet": True,
                    "label": f"LAN gateway ({device_id[:12]})",
                },
            )
            if not reg.get("ok"):
                print("register failed:", reg, flush=True)
            else:
                batch = _post(
                    "/api/chain-mesh/internet-gateway/peer-egress",
                    {"device_id": device_id, "limit": 16},
                )
                if batch.get("processed"):
                    print(
                        f"egress processed={batch.get('processed')} "
                        f"success={batch.get('success')}",
                        flush=True,
                    )
        except urllib.error.URLError as exc:
            print("gateway loop error:", exc, flush=True)
        except Exception as exc:
            print("gateway loop error:", exc, flush=True)
        time.sleep(max(2.0, INTERVAL))


if __name__ == "__main__":
    raise SystemExit(main())