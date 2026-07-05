"""Export/import stratum worker counts for the mining dashboard."""

import json
import os
import time
from typing import Any, Dict, List, Optional

RUN_DIR = os.environ.get("BLOODSTONE_RUN_DIR", "/var/run")
STALE_SEC = float(os.environ.get("BLOODSTONE_WORKER_STATUS_STALE_SEC", "15"))


def stratum_status_path(pool_key: str) -> str:
    return os.path.join(RUN_DIR, f"bloodstone-stratum-{pool_key}.json")


def ws_status_path() -> str:
    return os.path.join(RUN_DIR, "bloodstone-ws-workers.json")


def write_json_atomic(path: str, payload: Dict[str, Any]) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    os.replace(tmp, path)


def read_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def is_fresh(data: Optional[Dict[str, Any]], max_age: float = STALE_SEC) -> bool:
    if not data:
        return False
    ts = data.get("updated_at")
    if not isinstance(ts, (int, float)):
        return False
    return (time.time() - ts) <= max_age


def export_stratum_workers(pool_key: str, workers: List[Dict[str, Any]]) -> None:
    write_json_atomic(
        stratum_status_path(pool_key),
        {
            "pool": pool_key,
            "workers": workers,
            "authorized": len(workers),
            "updated_at": time.time(),
        },
    )


def export_ws_workers(pools: Dict[str, List[Dict[str, Any]]]) -> None:
    write_json_atomic(
        ws_status_path(),
        {
            "pools": pools,
            "total": sum(len(v) for v in pools.values()),
            "updated_at": time.time(),
        },
    )


def snapshot_authorized_clients(clients) -> List[Dict[str, Any]]:
    workers = []
    for client in clients:
        if not getattr(client, "authorized", False):
            continue
        peer = client.writer.get_extra_info("peername")
        peer_ip = peer[0] if peer else None
        workers.append(
            {
                "worker": getattr(client, "worker", "") or "",
                "address": getattr(client, "address", "") or "",
                "peer_ip": peer_ip,
                "peer_port": peer[1] if peer else None,
                "local": peer_ip in ("127.0.0.1", "::1"),
            }
        )
    return workers


async def stratum_export_loop(clients, pool_key: str, interval: float = 2.0) -> None:
    import asyncio

    while True:
        try:
            export_stratum_workers(pool_key, snapshot_authorized_clients(clients))
        except Exception:
            pass
        await asyncio.sleep(interval)