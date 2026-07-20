#!/usr/bin/env python3
"""Emit coordinator witness capsule + evaluate QUASAR tripwires (cron/upkeep)."""

import os
import sys

sys.path.insert(0, "/root")

import bloodstone_quasar_api as qapi


def _rpc():
    import requests

    conf = os.environ.get("BLOODSTONE_CONF", "/root/.bloodstone/bloodstone.conf")
    vals = {}
    if os.path.isfile(conf):
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
            json={"jsonrpc": "1.0", "id": "quasar-emit", "method": method, "params": params or []},
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(data["error"])
        return data["result"]

    return call


def main() -> int:
    rpc = _rpc()
    witness = qapi.emit_coordinator_witness(rpc)
    tip_review = qapi.witness_tip_review_payload(rpc, force=False)
    alerts = qapi.alerts_payload(rpc)
    print("witness", witness.get("capsule", {}).get("capsule_id", "")[:16])
    d = tip_review.get("disagreement") or {}
    r = tip_review.get("review") or {}
    print(
        "tip_review",
        "disagree=" + str(bool(d.get("disagreement"))),
        "action=" + str(r.get("action") or "n/a"),
        "reviewer=" + str(r.get("reviewer") or "n/a"),
        "review_id=" + str(tip_review.get("review_id") or "")[:16],
    )
    print("alerts", alerts.get("alert_count", 0), "active", alerts.get("active"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())