#!/usr/bin/env python3
"""Bloodstone Multi-Fork Qt Wallet — entry point."""

from __future__ import annotations

import os
import sys

# Allow running from source tree without install
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Prefer offscreen only when explicitly requested (CI / headless smoke)
# QT_QPA_PLATFORM=offscreen python3 main.py --smoke


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)

    smoke = "--smoke" in argv
    if smoke:
        argv = [a for a in argv if a != "--smoke"]
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt, QTimer

    # High-DPI before QApplication
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(argv)
    app.setApplicationName("Bloodstone Multi-Fork Qt Wallet")
    app.setOrganizationName("Bloodstone")

    from bloodstone_mfq import APP_NAME, __version__
    from bloodstone_mfq.ui.mainwindow import MainWindow
    from bloodstone_mfq.catalog import list_coins
    from bloodstone_mfq.rpc import CoinRPC
    from bloodstone_mfq import settings_store as store

    if smoke:
        coins = list_coins(force=True, conf_overrides=store.conf_overrides())
        print(f"{APP_NAME} v{__version__} smoke test")
        print(f"Catalogue ({len(coins)}): " + ", ".join(c["ticker"] for c in coins))
        ok = 0
        for coin in coins:
            rpc = CoinRPC(coin)
            probe = rpc.probe(timeout=3.0)
            status = "ONLINE" if probe.get("online") else "offline"
            detail = probe.get("blocks") if probe.get("online") else probe.get("error")
            print(f"  {coin['ticker']:8} {status:8} {detail}")
            if probe.get("online"):
                ok += 1
        # Construct UI and wait for first refresh worker to finish
        win = MainWindow()
        win.show()

        def _finish_smoke():
            if win._worker is not None and win._worker.isRunning():
                # wait a bit longer for RPC probes
                return
            win.close()
            app.quit()

        poll = QTimer()
        poll.setInterval(250)
        started = {"t": 0}

        def _poll():
            started["t"] += 1
            # max ~15s
            if started["t"] > 60:
                win.close()
                app.quit()
                return
            if not win._busy and win._rows:
                win.close()
                app.quit()

        poll.timeout.connect(_poll)
        poll.start()
        # also hard cap
        QTimer.singleShot(15000, app.quit)
        app.exec_()
        poll.stop()
        if win._worker is not None and win._worker.isRunning():
            win._worker.wait(5000)
        print(f"UI ok; rows={len(win._rows)}; {ok}/{len(coins)} RPC online")
        return 0 if (ok > 0 or len(coins) > 0) else 1

    win = MainWindow()
    win.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
