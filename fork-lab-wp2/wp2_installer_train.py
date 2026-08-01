"""WP2 MFQ installer release train (T+~24h batched).

Tracks coins that should ride the next multi-fork-qt installer bundle.
Does **not** rebuild Qt per coin — only records pending pack inclusion.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PUBLIC_ROOT = os.environ.get(
    "BLOODSTONE_PUBLIC_ROOT", "https://bloodstone.rocks"
).rstrip("/")
TRAIN_PATH = Path(
    os.environ.get(
        "FORK_LAB_MFQ_INSTALLER_TRAIN",
        "/var/www/bloodstone/downloads/mfq-installer-train.json",
    )
)
MFQ_VERSION_FILE = Path(
    os.environ.get("MFQ_VERSION_FILE", "/root/bloodstone-multi-fork-qt/VERSION")
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load() -> Dict[str, Any]:
    if TRAIN_PATH.is_file():
        try:
            return json.loads(TRAIN_PATH.read_text())
        except Exception:
            pass
    ver = "0.2.33"
    if MFQ_VERSION_FILE.is_file():
        ver = MFQ_VERSION_FILE.read_text().strip() or ver
    return {
        "schema": "bloodstone/mfq-installer-train/v1",
        "updated_utc": _utc(),
        "current_mfq_version": ver,
        "next_train_target": _bump_patch(ver),
        "promise": (
            "Launch triggers catalog + daemon pack immediately; "
            "the MFQ installer train tags within ~24h."
        ),
        "pending": [],
        "shipped": [],
        "notes": "Batched installer only — never rebuild Qt per coin.",
    }


def _bump_patch(ver: str) -> str:
    parts = ver.strip().split(".")
    try:
        if len(parts) >= 3:
            parts[-1] = str(int(parts[-1]) + 1)
            return ".".join(parts)
    except ValueError:
        pass
    return ver + ".next"


def _save(data: Dict[str, Any]) -> None:
    TRAIN_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["updated_utc"] = _utc()
    TRAIN_PATH.write_text(json.dumps(data, indent=2) + "\n")


def enqueue_coin(
    ticker: str,
    *,
    reason: str = "daemon_pack_publish",
    usable: bool = False,
) -> Dict[str, Any]:
    t = ticker.upper()
    data = _load()
    pending: List[Dict[str, Any]] = list(data.get("pending") or [])
    # de-dupe
    pending = [p for p in pending if str(p.get("ticker") or "").upper() != t]
    pending.append(
        {
            "ticker": t,
            "reason": reason,
            "usable_for_wallets": bool(usable),
            "queued_utc": _utc(),
            "daemon_pack_url": f"{PUBLIC_ROOT}/downloads/mfq-daemons/{t}-win64.zip",
            "include_in_installer": True,
        }
    )
    data["pending"] = pending
    if MFQ_VERSION_FILE.is_file():
        data["current_mfq_version"] = MFQ_VERSION_FILE.read_text().strip()
        data["next_train_target"] = _bump_patch(data["current_mfq_version"])
    _save(data)
    return {"ok": True, "ticker": t, "pending_count": len(pending), "train": data}


def mark_shipped(version: str, tickers: Optional[List[str]] = None) -> Dict[str, Any]:
    data = _load()
    pending = list(data.get("pending") or [])
    shipped = list(data.get("shipped") or [])
    if tickers:
        want = {t.upper() for t in tickers}
        move = [p for p in pending if str(p.get("ticker") or "").upper() in want]
        pending = [p for p in pending if str(p.get("ticker") or "").upper() not in want]
    else:
        move = pending
        pending = []
    shipped.append(
        {
            "version": version,
            "shipped_utc": _utc(),
            "coins": [p.get("ticker") for p in move],
        }
    )
    data["pending"] = pending
    data["shipped"] = shipped[-50:]
    data["current_mfq_version"] = version
    data["next_train_target"] = _bump_patch(version)
    _save(data)
    return {"ok": True, "train": data}


def status() -> Dict[str, Any]:
    data = _load()
    data["ok"] = True
    data["path"] = str(TRAIN_PATH)
    data["public_url"] = f"{PUBLIC_ROOT}/downloads/mfq-installer-train.json"
    return data
