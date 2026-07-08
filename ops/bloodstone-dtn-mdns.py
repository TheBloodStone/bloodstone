#!/usr/bin/env python3
"""Pi node mDNS broadcaster — announces _bloodstone-dtn._tcp and browses LAN peers."""

from __future__ import annotations

import os
import signal
import sys
import time

sys.path.insert(0, "/root")

from chain_mesh import mdns_discovery as mdns

RUN = True
_ZC = None


def _stop(*_args) -> None:
    global RUN
    RUN = False


def main() -> int:
    global _ZC
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    interval = max(10, int(os.environ.get("DTN_MDNS_INTERVAL_SEC", "30")))
    reg = mdns.register_dtn_service()
    if not reg.get("ok"):
        print("dtn-mdns register failed:", reg.get("error"), file=sys.stderr)
        return 1

    _ZC = reg.get("zeroconf")
    backend = reg.get("backend")
    print(
        "dtn-mdns",
        "backend=" + str(backend),
        "node_id=" + str(reg.get("node_id")),
        "host=" + str(reg.get("host")),
        "port=" + str(reg.get("port")),
        "type=" + mdns.MDNS_DTN_SERVICE_TYPE,
    )

    while RUN:
        try:
            result = mdns.discover_mdns_dtn_peers(register=True)
            print(
                "dtn-mdns browse",
                "found=" + str(result.get("services_found", 0)),
                "registered=" + str(result.get("peers_registered", 0)),
            )
        except Exception as exc:
            print("dtn-mdns browse error:", exc, file=sys.stderr)
        for _ in range(interval):
            if not RUN:
                break
            time.sleep(1)

    if _ZC is not None:
        try:
            info = reg.get("service_info")
            if info is not None:
                _ZC.unregister_service(info)
            _ZC.close()
        except Exception:
            pass
    print("dtn-mdns stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())