"""Gunicorn hooks for the mining API worker (port 8892)."""


def post_fork(server, worker):
    import os
    import threading
    import time

    if os.environ.get("BLOODSTONE_POOL_DASH_WARM") != "1":
        return

    def _warm() -> None:
        import logging

        log = logging.getLogger("pool-dash-warm")
        time.sleep(1.0)
        try:
            import pool_db

            pool_db.get_unified_pool_dashboard(allow_build=True)
            log.info("dashboard cache warm ok (worker %s)", worker.pid)
        except Exception as exc:
            log.warning("dashboard cache warm failed (worker %s): %s", worker.pid, exc)
        while True:
            time.sleep(max(60.0, float(pool_db.DASHBOARD_CACHE_SEC)))
            try:
                pool_db.get_unified_pool_dashboard(allow_build=True)
            except Exception as exc:
                log.warning("dashboard cache refresh failed (worker %s): %s", worker.pid, exc)

    threading.Thread(target=_warm, daemon=True, name=f"dash-warm-{worker.pid}").start()