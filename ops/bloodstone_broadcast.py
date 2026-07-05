"""Ensure wallet sends and node P2P relay transactions to the network."""

import json
import logging
import os
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import base64

LOG = logging.getLogger("bloodstone-broadcast")

RPC_URL = os.environ.get(
    "BLOODSTONE_RPC_URL",
    "http://bloodstone:a250b99cd8798d396087d0cbd87ab1721cb6f9ba53f6ba06adf77074e6886aff@127.0.0.1:18332/",
)
MAX_PEER_LAG = int(os.environ.get("BLOODSTONE_MAX_PEER_LAG", "3"))
BROADCAST_RETRIES = int(os.environ.get("BLOODSTONE_BROADCAST_RETRIES", "3"))


def rpc(method: str, params=None, wallet: Optional[str] = None, timeout: int = 120):
    parsed = urlparse(RPC_URL)
    endpoint = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
    path = parsed.path or "/"
    if wallet:
        path = path.rstrip("/") + f"/wallet/{wallet}"
    creds = ""
    if parsed.username:
        creds = base64.b64encode(
            f"{parsed.username}:{parsed.password}".encode()
        ).decode()
    payload = json.dumps(
        {"jsonrpc": "1.0", "id": "broadcast", "method": method, "params": params or []}
    ).encode()
    req = urllib.request.Request(
        endpoint + path,
        data=payload,
        headers={
            "content-type": "text/plain",
            "authorization": f"Basic {creds}" if creds else "",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode())
    if body.get("error"):
        raise RuntimeError(body["error"])
    return body["result"]


def txid_from_send_result(result: Any) -> str:
    if isinstance(result, dict):
        txid = result.get("txid")
        if txid:
            return str(txid)
        raise RuntimeError(f"sendtoaddress returned no txid: {result!r}")
    if result is None:
        raise RuntimeError("sendtoaddress returned empty result")
    return str(result)


def tx_in_mempool(txid: str) -> bool:
    try:
        mempool = rpc("getrawmempool", [False])
        return txid in mempool
    except RuntimeError:
        return False


def relay_transaction(txid: str, wallet: Optional[str] = None) -> bool:
    """Re-broadcast a wallet transaction via sendrawtransaction."""
    try:
        raw = rpc("getrawtransaction", [txid, False], wallet=wallet)
        rpc("sendrawtransaction", [raw])
        return True
    except RuntimeError as exc:
        msg = str(exc).lower()
        if "already in chain" in msg or "txn-already-in-mempool" in msg:
            return True
        if "already known" in msg:
            return True
        LOG.warning("relay failed for %s: %s", txid, exc)
        return False


def ensure_tx_broadcasted(txid: str, wallet: Optional[str] = None) -> bool:
    if tx_in_mempool(txid):
        return True
    for attempt in range(BROADCAST_RETRIES):
        if relay_transaction(txid, wallet=wallet):
            time.sleep(0.5)
            if tx_in_mempool(txid):
                return True
        time.sleep(1.0 * (attempt + 1))
    try:
        rpc("gettransaction", [txid], wallet=wallet)
        return True
    except RuntimeError:
        return False


def send_to_address_broadcast(
    address: str,
    amount: float,
    wallet: Optional[str] = None,
    comment: str = "",
    fee_rate: int = 100,
) -> str:
    """Send STONE and verify the transaction is relayed to peers."""
    params = [
        address,
        amount,
        comment or "",
        "",
        False,
        True,
        None,
        "unset",
        False,
        fee_rate,
        True,
    ]
    result = rpc("sendtoaddress", params, wallet=wallet)
    txid = txid_from_send_result(result)
    if not ensure_tx_broadcasted(txid, wallet=wallet):
        raise RuntimeError(
            f"Transaction {txid} was created but not found in mempool after relay attempts"
        )
    LOG.info("broadcast ok tx=%s wallet=%s amount=%s", txid, wallet or "default", amount)
    return txid


def sync_status() -> Dict[str, Any]:
    """Compare local chain tip to connected peers."""
    info = rpc("getblockchaininfo")
    local = int(info.get("blocks", 0))
    headers = int(info.get("headers", 0))
    peers: List[Dict] = []
    try:
        peers = rpc("getpeerinfo") or []
    except RuntimeError:
        peers = []
    peer_heights = [
        int(p.get("synced_blocks") or p.get("startingheight") or 0) for p in peers
    ]
    max_peer = max(peer_heights) if peer_heights else 0
    lag = max(0, local - max_peer)
    return {
        "local_height": local,
        "headers": headers,
        "peer_count": len(peers),
        "max_peer_height": max_peer,
        "peer_lag": lag,
        "synced_with_peers": lag <= MAX_PEER_LAG and len(peers) > 0,
        "verificationprogress": float(info.get("verificationprogress", 0)),
        "initialblockdownload": bool(info.get("initialblockdownload", False)),
        "warnings": info.get("warnings") or "",
    }


def rescan_loaded_wallets(start_height: Optional[int] = None) -> List[str]:
    """Rescan all loaded wallets so they match the node chain."""
    wallets = rpc("listwallets") or []
    done = []
    for name in wallets:
        try:
            if start_height is not None:
                rpc("rescanblockchain", [int(start_height)], wallet=name)
            else:
                rpc("rescanblockchain", [], wallet=name)
            done.append(name)
            LOG.info("rescanned wallet %s from %s", name, start_height)
        except RuntimeError as exc:
            LOG.warning("rescan failed for %s: %s", name, exc)
    return done


def ensure_network_ready(min_peers: int = 1) -> Tuple[bool, str]:
    status = sync_status()
    if status["initialblockdownload"]:
        return False, "node still in initial block download"
    if status["peer_count"] < min_peers:
        return False, f"only {status['peer_count']} peer(s) connected"
    if not status["synced_with_peers"]:
        return (
            False,
            f"local tip {status['local_height']} is {status['peer_lag']} blocks ahead of peers",
        )
    return True, "ok"