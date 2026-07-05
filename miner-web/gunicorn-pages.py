"""Gunicorn hooks for the HTML pages worker (port 8893)."""

import threading
import time


def post_fork(server, worker):
    """Warm per-worker caches after fork (--preload leaves workers with empty cache)."""

    def _warm() -> None:
        time.sleep(0.5)
        try:
            from app import (
                RECENT_BLOCKS,
                _cache_ttl,
                _cached_value,
                _load_chain_overview,
                recent_blocks,
            )

            _cached_value(
                "chain_overview",
                _cache_ttl("MINER_CHAIN_OVERVIEW_CACHE_SEC", "45"),
                _load_chain_overview,
                blocking=True,
            )
            _cached_value(
                f"recent_blocks_{RECENT_BLOCKS}",
                _cache_ttl("MINER_RECENT_BLOCKS_CACHE_SEC", "60"),
                lambda: recent_blocks(RECENT_BLOCKS),
                blocking=True,
            )
            from server_services import admin_service_sections

            _cached_value(
                "admin_service_sections",
                _cache_ttl("MINER_ADMIN_SERVICES_CACHE_SEC", "30"),
                admin_service_sections,
                blocking=True,
            )
            from stratum_status import pools_status_light_fast

            _cached_value(
                "pools_status_light",
                _cache_ttl("MINER_POOLS_STATUS_LIGHT_CACHE_SEC", "30"),
                pools_status_light_fast,
                blocking=True,
            )
        except Exception:
            pass

    threading.Thread(target=_warm, daemon=True, name=f"warm-{worker.pid}").start()