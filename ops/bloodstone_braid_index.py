"""QUASAR Phase 3 — persistent epoch braid index (indexes/braid/)."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import bloodstone_quasar as bq

INDEX_ROOT = os.environ.get(
    "QUASAR_BRAID_INDEX_DIR",
    os.path.join(os.environ.get("BLOODSTONE_DATADIR", "/root/.bloodstone"), "indexes", "braid"),
)
STATE_FILE = os.path.join(INDEX_ROOT, "state.json")
EPOCHS_DIR = os.path.join(INDEX_ROOT, "epochs")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_dirs() -> None:
    os.makedirs(EPOCHS_DIR, exist_ok=True)


def load_state() -> Dict[str, Any]:
    _ensure_dirs()
    if not os.path.isfile(STATE_FILE):
        return {
            "version": 1,
            "epoch_blocks": bq.EPOCH_BLOCKS,
            "last_height": 0,
            "last_epoch_index": -1,
            "updated_utc": None,
        }
    with open(STATE_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def save_state(state: Dict[str, Any]) -> None:
    _ensure_dirs()
    state["updated_utc"] = _utc_now()
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
        fh.write("\n")


def _epoch_path(epoch_index: int) -> str:
    return os.path.join(EPOCHS_DIR, f"epoch-{epoch_index:08d}.json")


def write_epoch_record(epoch_index: int, record: Dict[str, Any]) -> None:
    _ensure_dirs()
    path = _epoch_path(epoch_index)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
        fh.write("\n")


def read_epoch_record(epoch_index: int) -> Optional[Dict[str, Any]]:
    path = _epoch_path(epoch_index)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def sync_index(rpc: Callable, *, max_blocks: int = 500) -> Dict[str, Any]:
    """Incrementally extend braid index from node RPC."""
    state = load_state()
    tip = int(rpc("getblockcount"))
    start = int(state.get("last_height") or 0)
    if start > 0:
        start += 1
    else:
        start = max(0, tip - max_blocks + 1)

    scanned = 0
    epoch_blocks = int(state.get("epoch_blocks") or bq.EPOCH_BLOCKS)
    current_epoch = start // epoch_blocks if epoch_blocks else 0
    bucket_blocks: List[Dict[str, Any]] = []

    for height in range(start, tip + 1):
        block_hash = rpc("getblockhash", [height])
        block = rpc("getblock", [block_hash, 1])
        bucket_blocks.append(
            {
                "height": block["height"],
                "hash": block["hash"],
                "time": block.get("time"),
                "powdata": block.get("powdata") or {},
            }
        )
        scanned += 1
        epoch_index = height // epoch_blocks
        epoch_end = (epoch_index + 1) * epoch_blocks - 1
        if height >= epoch_end or height == tip:
            summary = bq.summarize_epoch(bucket_blocks)
            summary["epoch_index"] = epoch_index
            summary["indexed_at"] = _utc_now()
            write_epoch_record(epoch_index, summary)
            bucket_blocks = []
            current_epoch = epoch_index

    state["last_height"] = tip
    state["last_epoch_index"] = current_epoch
    state["tip_hash"] = str(rpc("getblockchaininfo").get("bestblockhash") or "")
    save_state(state)

    latest = read_epoch_record(current_epoch)
    return {
        "ok": True,
        "scanned_blocks": scanned,
        "tip_height": tip,
        "last_epoch_index": current_epoch,
        "latest_epoch": latest,
        "index_root": INDEX_ROOT,
        "state": state,
    }


def index_payload(*, epochs: int = 3) -> Dict[str, Any]:
    state = load_state()
    epoch_blocks = int(state.get("epoch_blocks") or bq.EPOCH_BLOCKS)
    last_epoch = int(state.get("last_epoch_index") or -1)
    records: List[Dict[str, Any]] = []
    for i in range(max(0, last_epoch - epochs + 1), last_epoch + 1):
        rec = read_epoch_record(i)
        if rec:
            records.append(rec)
    braid_status = records[-1]["status"] if records else "unknown"
    return {
        "ok": True,
        "version": 1,
        "phase": 3,
        "index_root": INDEX_ROOT,
        "epoch_blocks": epoch_blocks,
        "synced_height": int(state.get("last_height") or 0),
        "tip_hash": state.get("tip_hash"),
        "braid_status": braid_status,
        "epochs": records,
        "updated_utc": state.get("updated_utc"),
        "enforcement_ready": bool(records),
    }


def rpc_export() -> Dict[str, Any]:
    """Shape consumed by bloodstoned getquasarbraid RPC."""
    payload = index_payload(epochs=5)
    return {
        "ok": payload.get("ok", False),
        "phase": 3,
        "enforcement_mode": os.environ.get("QUASAR_ENFORCEMENT_MODE", "policy"),
        "epoch_blocks": payload.get("epoch_blocks"),
        "synced_height": payload.get("synced_height"),
        "tip_hash": payload.get("tip_hash"),
        "braid_status": payload.get("braid_status"),
        "current_epoch": (payload.get("epochs") or [None])[-1],
        "recent_epochs": payload.get("epochs") or [],
        "updated_utc": payload.get("updated_utc"),
    }