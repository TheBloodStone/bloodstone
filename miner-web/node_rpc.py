"""Bloodstone node RPC helpers."""

import os

import requests

CONF_PATH = os.environ.get("BLOODSTONE_CONF", "/root/.bloodstone/bloodstone.conf")


def load_kv(path):
    values = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                values[key.strip()] = val.strip()
    return values


def rpc_url(wallet=None):
    values = load_kv(CONF_PATH)
    user = values.get("rpcuser", "bloodstone")
    password = values.get("rpcpassword", "")
    port = values.get("rpcport", "18332")
    host = os.environ.get("RPC_HOST", "127.0.0.1")
    url = f"http://{user}:{password}@{host}:{port}/"
    if wallet:
        url += f"wallet/{wallet}"
    return url


def rpc(method, params=None, wallet=None):
    payload = {
        "jsonrpc": "1.0",
        "id": "miner-web",
        "method": method,
        "params": params or [],
    }
    timeout = float(os.environ.get("MINER_RPC_TIMEOUT_SEC", "12"))
    resp = requests.post(
        rpc_url(wallet),
        json=payload,
        headers={"content-type": "text/plain;"},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        err = data["error"]
        raise RuntimeError(err.get("message", str(err)))
    return data["result"]


def default_payout_address():
    try:
        received = rpc("listreceivedbyaddress", [0, True, True], wallet="mine")
        if received:
            return received[0]["address"]
    except RuntimeError:
        pass
    try:
        return rpc("getnewaddress", ["mining-dashboard"], wallet="mine")
    except RuntimeError:
        return None