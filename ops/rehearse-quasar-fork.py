#!/usr/bin/env python3
"""Persist QUASAR Phase 4 fork rehearsal status (cron/upkeep)."""

import os
import sys

sys.path.insert(0, "/root")

import bloodstone_quasar_fork as bqf


def _rpc():
    import requests

    conf = os.environ.get("BLOODSTONE_CONF", "/root/.bloodstone/bloodstone.conf")
    vals = {}
    with open(conf, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip()
    url = (
        f"http://{vals.get('rpcuser', 'bloodstone')}:{vals.get('rpcpassword', '')}"
        f"@127.0.0.1:{vals.get('rpcport', '18332')}/"
    )

    def call(method, params=None):
        r = requests.post(
            url,
            json={"jsonrpc": "1.0", "id": "fork-rehearsal", "method": method, "params": params or []},
            timeout=180,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(data["error"])
        return data["result"]

    return call


def main() -> int:
    rpc = _rpc()
    result = bqf.persist_rehearsal_status(rpc)
    sig = result.get("signaling") or {}
    ready = (result.get("readiness") or {}).get("ready")
    print(
        "rehearsal",
        "state=" + str(sig.get("state")),
        "signaling=" + str(sig.get("signaling_blocks")) + "/" + str(sig.get("threshold_blocks")),
        "ready=" + str(ready),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())