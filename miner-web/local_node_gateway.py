"""Secure RPC relay for Android local nodes when upstream VPS bloodstoned is needed."""

import os
from typing import Any, Dict, List, Optional

import node_rpc

_ALLOWED_METHODS = frozenset(
    {
        "getblockchaininfo",
        "getblockcount",
        "getbestblockhash",
        "getblockhash",
        "getblock",
        "getblockheader",
        "getrawtransaction",
        "gettxout",
        "getchaintips",
        "getmininginfo",
        "getnetworkinfo",
        "getpeerinfo",
        "getconnectioncount",
        "creatework",
        "submitblock",
        "getblocktemplate",
        "submitheader",
        "validateaddress",
        "estimatesmartfee",
        # Mobile on-device wallets (keys stay on phone; only UTXO scan + broadcast here)
        "scantxoutset",
        "sendrawtransaction",
        "decoderawtransaction",
        "createrawtransaction",
    }
)


def relay_rpc(method: str, params: Optional[List[Any]] = None) -> Any:
    name = (method or "").strip().lower()
    if name not in _ALLOWED_METHODS:
        raise ValueError(f"method not allowed: {method}")
    return node_rpc.rpc(name, params or [])


def relay_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    method = str(payload.get("method") or "").strip()
    params = payload.get("params") or []
    if not isinstance(params, list):
        raise ValueError("params must be a list")
    result = relay_rpc(method, params)
    return {
        "jsonrpc": "1.0",
        "id": payload.get("id"),
        "result": result,
        "error": None,
    }