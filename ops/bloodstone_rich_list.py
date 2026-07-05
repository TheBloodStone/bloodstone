"""Bloodstone on-chain rich list — UTXO balances for portal and explorer."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set

import requests

import pool_db
from stratum_utils import is_valid_stone_address

CONF_PATH = os.environ.get("BLOODSTONE_CONF", "/root/.bloodstone/bloodstone.conf")
CACHE_DIR = os.environ.get("BLOODSTONE_RICH_LIST_CACHE_DIR", "/var/cache/bloodstone")
ADDRESS_INDEX_PATH = os.path.join(CACHE_DIR, "rich-list-address-index.json")
RICH_LIST_PATH = os.path.join(CACHE_DIR, "rich-list.json")
RICH_LIST_TTL_SEC = float(os.environ.get("BLOODSTONE_RICH_LIST_TTL_SEC", "600"))
DEFAULT_LIMIT = int(os.environ.get("BLOODSTONE_RICH_LIST_LIMIT", "25"))
SCAN_BATCH_SIZE = int(os.environ.get("BLOODSTONE_RICH_LIST_SCAN_BATCH", "250"))
BLOCK_REWARD_STONE = float(os.environ.get("BLOODSTONE_BLOCK_REWARD_STONE", "100"))

_LOCK = threading.Lock()
_BUILD_LOCK = threading.Lock()
_BUILDING = False

_ADDR_FROM_DESC = re.compile(r"^addr\(([^)#]+)\)")


def _load_rpc_url() -> str:
    values: Dict[str, str] = {}
    if os.path.isfile(CONF_PATH):
        with open(CONF_PATH, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                values[key.strip()] = val.strip()
    user = values.get("rpcuser", os.environ.get("RPC_USER", "bloodstone"))
    password = values.get("rpcpassword", os.environ.get("RPC_PASSWORD", ""))
    port = values.get("rpcport", os.environ.get("RPC_PORT", "18332"))
    host = os.environ.get("RPC_HOST", "127.0.0.1")
    return f"http://{user}:{password}@{host}:{port}/"


def rpc(method: str, params: Optional[List[Any]] = None, *, rpc_url: Optional[str] = None) -> Any:
    payload = {"jsonrpc": "1.0", "id": "rich-list", "method": method, "params": params or []}
    resp = requests.post(
        rpc_url or _load_rpc_url(),
        json=payload,
        headers={"content-type": "text/plain;"},
        timeout=180,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        err = data["error"]
        raise RuntimeError(err.get("message", str(err)))
    return data["result"]


def _read_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def _extract_addresses_from_block(block: Dict[str, Any]) -> Set[str]:
    found: Set[str] = set()
    for tx in block.get("tx", []) or []:
        for vout in tx.get("vout", []) or []:
            spk = vout.get("scriptPubKey", {}) or {}
            for addr in spk.get("addresses", []) or []:
                if is_valid_stone_address(addr):
                    found.add(addr)
            addr = spk.get("address")
            if addr and is_valid_stone_address(addr):
                found.add(addr)
    return found


def _pool_supplement_addresses() -> Set[str]:
    out: Set[str] = set()
    for addr in pool_db.pool_operator_addresses():
        if is_valid_stone_address(addr):
            out.add(addr)
    try:
        conn = pool_db._read_conn()
        try:
            for row in conn.execute("SELECT address FROM miner_balances"):
                addr = str(row["address"] or "").strip()
                if is_valid_stone_address(addr):
                    out.add(addr)
            for row in conn.execute("SELECT DISTINCT finder_address FROM block_finds"):
                addr = str(row["finder_address"] or "").strip()
                if is_valid_stone_address(addr):
                    out.add(addr)
        finally:
            conn.close()
    except Exception:
        pass
    return out


def _load_address_index() -> Dict[str, Any]:
    data = _read_json(ADDRESS_INDEX_PATH)
    if not data:
        return {"indexed_height": -1, "addresses": [], "updated_at": 0}
    addresses = data.get("addresses") or []
    if isinstance(addresses, list):
        data["addresses"] = sorted({a for a in addresses if is_valid_stone_address(str(a))})
    else:
        data["addresses"] = []
    data["indexed_height"] = int(data.get("indexed_height", -1))
    data["updated_at"] = int(data.get("updated_at", 0))
    return data


def _save_address_index(index: Dict[str, Any]) -> None:
    _write_json(
        ADDRESS_INDEX_PATH,
        {
            "indexed_height": index["indexed_height"],
            "addresses": sorted(index["addresses"]),
            "updated_at": int(time.time()),
        },
    )


def refresh_address_index(*, rpc_fn: Callable[..., Any] = rpc) -> Dict[str, Any]:
    index = _load_address_index()
    addresses: Set[str] = set(index.get("addresses") or [])
    addresses.update(_pool_supplement_addresses())

    tip = int(rpc_fn("getblockcount"))
    start_height = int(index.get("indexed_height", -1)) + 1
    if start_height < 0:
        start_height = 0

    for height in range(start_height, tip + 1):
        block_hash = rpc_fn("getblockhash", [height])
        block = rpc_fn("getblock", [block_hash, 2])
        addresses.update(_extract_addresses_from_block(block))

    index = {
        "indexed_height": tip,
        "addresses": sorted(addresses),
        "updated_at": int(time.time()),
    }
    _save_address_index(index)
    return index


def _address_from_desc(desc: str) -> str:
    match = _ADDR_FROM_DESC.match(str(desc or ""))
    return match.group(1) if match else ""


def _scan_balances(addresses: List[str], *, rpc_fn: Callable[..., Any] = rpc) -> Dict[str, float]:
    balances: Dict[str, float] = {}
    if not addresses:
        return balances

    for offset in range(0, len(addresses), SCAN_BATCH_SIZE):
        batch = addresses[offset : offset + SCAN_BATCH_SIZE]
        descriptors = [f"addr({addr})" for addr in batch]
        try:
            scan = rpc_fn("scantxoutset", ["start", descriptors])
        except Exception:
            for addr in batch:
                try:
                    one = rpc_fn("scantxoutset", ["start", [f"addr({addr})"]])
                except Exception:
                    continue
                for utxo in one.get("unspents", []) or []:
                    addr_key = _address_from_desc(utxo.get("desc", "")) or addr
                    balances[addr_key] = balances.get(addr_key, 0.0) + float(utxo.get("amount", 0) or 0)
            continue

        if not scan.get("success"):
            continue
        for utxo in scan.get("unspents", []) or []:
            addr = _address_from_desc(utxo.get("desc", ""))
            if not addr:
                continue
            balances[addr] = balances.get(addr, 0.0) + float(utxo.get("amount", 0) or 0)
    return balances


def _estimate_circulating_supply(height: int) -> float:
    return max(0.0, float(height + 1) * BLOCK_REWARD_STONE)


def build_rich_list(*, limit: int = DEFAULT_LIMIT, rpc_fn: Callable[..., Any] = rpc) -> Dict[str, Any]:
    index = refresh_address_index(rpc_fn=rpc_fn)
    addresses = index.get("addresses") or []
    balances = _scan_balances(addresses, rpc_fn=rpc_fn)

    pool_ops = set(pool_db.pool_operator_addresses())
    rows: List[Dict[str, Any]] = []
    for addr, amount in balances.items():
        if amount <= 0:
            continue
        rows.append(
            {
                "address": addr,
                "balance_stone": round(amount, 8),
                "is_pool": addr in pool_ops,
            }
        )

    rows.sort(key=lambda row: row["balance_stone"], reverse=True)
    tip = int(index.get("indexed_height", 0))
    total_onchain = round(sum(balances.values()), 8)
    nominal_supply = _estimate_circulating_supply(tip)
    supply_basis = total_onchain if total_onchain > 0 else nominal_supply
    top = []
    for rank, row in enumerate(rows[:limit], start=1):
        pct = (row["balance_stone"] / supply_basis * 100.0) if supply_basis > 0 else 0.0
        top.append(
            {
                "rank": rank,
                "address": row["address"],
                "balance_stone": row["balance_stone"],
                "pct_supply": round(pct, 4),
                "is_pool": row["is_pool"],
            }
        )

    payload = {
        "ok": True,
        "entries": top,
        "holders_scanned": len(addresses),
        "holders_with_balance": len(rows),
        "total_onchain_stone": total_onchain,
        "estimated_supply_stone": round(nominal_supply, 8),
        "supply_basis_stone": round(supply_basis, 8),
        "indexed_height": tip,
        "updated_at": int(time.time()),
        "limit": limit,
    }
    _write_json(RICH_LIST_PATH, payload)
    return payload


def get_rich_list(*, limit: int = DEFAULT_LIMIT, force_refresh: bool = False) -> Dict[str, Any]:
    limit = max(5, min(100, int(limit)))
    now = time.time()

    if not force_refresh:
        cached = _read_json(RICH_LIST_PATH)
        if cached and now - float(cached.get("updated_at", 0)) < RICH_LIST_TTL_SEC:
            cached["loading"] = False
            cached["entries"] = (cached.get("entries") or [])[:limit]
            cached["limit"] = limit
            return cached

    with _LOCK:
        if not force_refresh:
            cached = _read_json(RICH_LIST_PATH)
            if cached and now - float(cached.get("updated_at", 0)) < RICH_LIST_TTL_SEC:
                cached["loading"] = False
                cached["entries"] = (cached.get("entries") or [])[:limit]
                cached["limit"] = limit
                return cached

        stale = _read_json(RICH_LIST_PATH) or {"ok": False, "entries": [], "loading": True}
        try:
            return build_rich_list(limit=limit)
        except Exception as exc:
            stale["error"] = str(exc)
            stale["loading"] = False
            stale["ok"] = False
            return stale


def schedule_rich_list_refresh(*, limit: int = DEFAULT_LIMIT) -> None:
    global _BUILDING

    def _run() -> None:
        global _BUILDING
        if not _BUILD_LOCK.acquire(blocking=False):
            return
        _BUILDING = True
        try:
            build_rich_list(limit=limit)
        except Exception:
            pass
        finally:
            _BUILDING = False
            _BUILD_LOCK.release()

    if _BUILDING:
        return
    threading.Thread(target=_run, daemon=True, name="bloodstone-rich-list").start()