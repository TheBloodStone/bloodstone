"""QUASAR Phase 4 — miner version-bit signaling tracker for braid finality fork."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

DEPLOYMENT_NAME = "quasar_braid_finality"
SIGNAL_BIT = int(os.environ.get("QUASAR_FORK_BIT", "3"))
WINDOW_BLOCKS = int(os.environ.get("QUASAR_FORK_WINDOW", "2016"))
THRESHOLD_MAINNET = int(os.environ.get("QUASAR_FORK_THRESHOLD", "1815"))
THRESHOLD_TESTNET = int(os.environ.get("QUASAR_FORK_THRESHOLD_TESTNET", "1512"))
BASE_VERSION = int(os.environ.get("QUASAR_FORK_BASE_VERSION", "0x20000000"), 0)
BIT_MASK = 1 << SIGNAL_BIT
SCAN_BLOCKS = int(os.environ.get("QUASAR_FORK_SCAN_BLOCKS", "72"))
_CACHE: Dict[str, Any] = {"ts": 0.0, "payload": None}
_CACHE_TTL = float(os.environ.get("QUASAR_SIGNALING_CACHE_SEC", "120"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _chain_threshold(chain: str) -> int:
    if chain in ("test", "testnet", "regtest", "signet"):
        return THRESHOLD_TESTNET
    return THRESHOLD_MAINNET


def block_signals(version: int) -> bool:
    return bool(int(version) & BIT_MASK)


def _deployment_from_chaininfo(info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    softforks = info.get("softforks") or {}
    dep = softforks.get(DEPLOYMENT_NAME)
    if isinstance(dep, dict):
        return dep
    bip9 = softforks.get("bip9_softforks") or {}
    dep = bip9.get(DEPLOYMENT_NAME)
    if isinstance(dep, dict):
        return dep
    return None


def scan_window(
    rpc: Callable,
    *,
    window: int = WINDOW_BLOCKS,
    scan_blocks: Optional[int] = None,
) -> Dict[str, Any]:
    """Count signaling blocks in the trailing confirmation window."""
    tip = int(rpc("getblockcount"))
    sample = max(1, min(int(scan_blocks or SCAN_BLOCKS), window))
    start = max(0, tip - sample + 1)
    signaling = 0
    samples: List[Dict[str, Any]] = []

    for height in range(start, tip + 1):
        block_hash = rpc("getblockhash", [height])
        block = rpc("getblock", [block_hash, 1])
        version = int(block.get("version") or 0)
        signaled = block_signals(version)
        if signaled:
            signaling += 1
        if height >= tip - 4:
            samples.append(
                {
                    "height": height,
                    "hash": block.get("hash"),
                    "version": version,
                    "signaling": signaled,
                }
            )

    total = tip - start + 1
    pct = (signaling / total * 100.0) if total else 0.0
    projected = int(round(signaling / total * window)) if total else 0
    return {
        "window_blocks": window,
        "scan_blocks": sample,
        "window_start_height": max(0, tip - window + 1),
        "scan_start_height": start,
        "window_end_height": tip,
        "blocks_in_window": window,
        "blocks_scanned": total,
        "signaling_blocks": signaling,
        "signaling_blocks_projected": projected,
        "signaling_percent": round(pct, 2),
        "recent_blocks": samples,
        "scan_note": (
            f"Sampled last {sample} blocks; projected {projected}/{window} if sample holds."
            if sample < window
            else None
        ),
    }


def derive_state(
    signaling_blocks: int,
    *,
    threshold: int,
    start_height: int = 0,
    tip_height: int = 0,
    timeout_height: int = 0,
    node_state: str = "",
) -> str:
    if node_state in ("active", "locked_in", "started", "failed", "defined"):
        return node_state
    if timeout_height and tip_height >= timeout_height:
        return "failed"
    if start_height and tip_height < start_height:
        return "defined"
    if signaling_blocks >= threshold:
        return "locked_in"
    if start_height and tip_height >= start_height:
        return "started"
    return "defined"


def signaling_payload(rpc: Callable, *, use_cache: bool = True) -> Dict[str, Any]:
    import time

    now = time.time()
    if use_cache and _CACHE.get("payload") and now - _CACHE["ts"] < _CACHE_TTL:
        return dict(_CACHE["payload"])

    info = rpc("getblockchaininfo")
    chain = str(info.get("chain") or "main")
    tip = int(info.get("blocks") or 0)
    threshold = _chain_threshold(chain)
    window = scan_window(rpc, window=WINDOW_BLOCKS)

    node_dep = _deployment_from_chaininfo(info)
    node_state = str((node_dep or {}).get("status") or (node_dep or {}).get("state") or "")
    start_height = int(os.environ.get("QUASAR_FORK_START_HEIGHT", "0") or 0)
    timeout_height = int(os.environ.get("QUASAR_FORK_TIMEOUT_HEIGHT", "0") or 0)
    if node_dep:
        stats = node_dep.get("statistics") or {}
        if stats:
            window = {
                "window_blocks": int(stats.get("period") or WINDOW_BLOCKS),
                "window_start_height": max(0, tip - int(stats.get("period") or WINDOW_BLOCKS) + 1),
                "window_end_height": tip,
                "blocks_in_window": int(stats.get("period") or WINDOW_BLOCKS),
                "signaling_blocks": int(stats.get("count") or 0),
                "signaling_percent": round(
                    float(stats.get("count") or 0)
                    / max(1, int(stats.get("period") or WINDOW_BLOCKS))
                    * 100.0,
                    2,
                ),
                "recent_blocks": window.get("recent_blocks") or [],
                "source": "node_softforks",
            }
        start_height = int(node_dep.get("start_height") or start_height or 0)
        timeout_height = int(node_dep.get("timeout_height") or timeout_height or 0)

    projected = int(window.get("signaling_blocks_projected") or window.get("signaling_blocks") or 0)
    state = derive_state(
        projected,
        threshold=threshold,
        start_height=start_height,
        tip_height=tip,
        timeout_height=timeout_height,
        node_state=node_state,
    )
    blocks_needed = max(0, threshold - projected)

    payload = {
        "ok": True,
        "phase": 4,
        "deployment": DEPLOYMENT_NAME,
        "chain": chain,
        "tip_height": tip,
        "version_bit": SIGNAL_BIT,
        "bit_mask": BIT_MASK,
        "base_version": BASE_VERSION,
        "recommended_miner_version": BASE_VERSION | BIT_MASK,
        "window_blocks": int(window.get("window_blocks") or WINDOW_BLOCKS),
        "threshold_blocks": threshold,
        "signaling_blocks": int(window.get("signaling_blocks") or 0),
        "signaling_blocks_projected": projected,
        "signaling_percent": window.get("signaling_percent"),
        "blocks_until_lock_in": blocks_needed,
        "state": state,
        "start_height": start_height,
        "timeout_height": timeout_height,
        "window": window,
        "node_deployment": node_dep,
        "updated_utc": _utc_now(),
        "rehearsal_ready": state in ("started", "locked_in")
        or int(window.get("signaling_blocks") or 0) > 0,
    }
    _CACHE["ts"] = now
    _CACHE["payload"] = payload
    return dict(payload)