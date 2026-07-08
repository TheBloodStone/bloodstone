#!/usr/bin/env python3
"""Sync QUASAR braid index and write RPC export for bloodstoned getquasarbraid."""

import json
import os
import sys

sys.path.insert(0, "/root")

import bloodstone_braid_index as bbi


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
            json={"jsonrpc": "1.0", "id": "braid-index", "method": method, "params": params or []},
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
    result = bbi.sync_index(rpc)
    export = bbi.rpc_export()
    export_path = os.path.join(bbi.INDEX_ROOT, "rpc-export.json")
    with open(export_path, "w", encoding="utf-8") as fh:
        json.dump(export, fh, indent=2)
        fh.write("\n")
    print("synced", result.get("scanned_blocks", 0), "blocks to height", result.get("tip_height"))
    print("braid_status", export.get("braid_status"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())