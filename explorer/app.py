#!/usr/bin/env python3
"""Bloodstone blockchain explorer — lightweight RPC-backed web UI."""

import os
import re
import sys
import time
from datetime import datetime, timezone

import requests

sys.path.insert(0, "/root")
import bloodstone_branding
import bloodstone_time
import merge_mining_info
import pool_db
from flask import Flask, jsonify, redirect, render_template, request, url_for

CONF_PATH = os.environ.get("BLOODSTONE_CONF", "/root/.bloodstone/bloodstone.conf")
BLOCKS_PER_PAGE = 25
NAMES_PER_PAGE = 50
ADDRESS_CACHE_TTL = 300  # seconds

HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
HEIGHT = re.compile(r"^\d+$")
LEGACY_ADDR = re.compile(r"^S[1-9A-HJ-NP-Za-km-z]{25,34}$")
BECH32_ADDR = re.compile(r"^stone1[0-9a-z]{20,}$", re.I)

_address_cache = {}

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

from prefix_middleware import apply_prefix  # noqa: E402

apply_prefix(app)


def load_rpc_config():
    values = {}
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


RPC_URL = load_rpc_config()


def rpc(method, params=None):
    payload = {
        "jsonrpc": "1.0",
        "id": "explorer",
        "method": method,
        "params": params or [],
    }
    resp = requests.post(
        RPC_URL,
        json=payload,
        headers={"content-type": "text/plain;"},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        err = data["error"]
        raise RuntimeError(err.get("message", str(err)))
    return data["result"]


def fmt_time(ts):
    if not ts:
        return "—"
    return bloodstone_time.format_pacific(ts)


def fmt_amount(val):
    if val is None:
        return "—"
    return f"{float(val):,.8f}".rstrip("0").rstrip(".")


def short_hash(value, left=10, right=8):
    if not value:
        return "—"
    s = str(value)
    if len(s) <= left + right + 3:
        return s
    return f"{s[:left]}…{s[-right:]}"


def classify_query(q):
    q = (q or "").strip()
    if not q:
        return None, None
    if HEIGHT.match(q):
        return "block", int(q)
    if HEX64.match(q):
        return "tx", q.lower()
    if LEGACY_ADDR.match(q) or BECH32_ADDR.match(q):
        return "address", q
    if q.startswith("d/") or q.startswith("D/"):
        return "name", q
    if "/" not in q and len(q) >= 1:
        return "name", f"d/{q}"
    return "search", q


def block_summary(height):
    block_hash = rpc("getblockhash", [height])
    block = rpc("getblock", [block_hash, 1])
    return {
        "height": block["height"],
        "hash": block["hash"],
        "time": block["time"],
        "time_fmt": fmt_time(block["time"]),
        "nTx": block.get("nTx", 0),
        "size": block.get("size", 0),
        "powdata": merge_mining_info.enrich_powdata(block.get("powdata")),
    }


def get_recent_blocks(limit=25):
    tip = rpc("getblockcount")
    start = max(0, tip - limit + 1)
    blocks = []
    for h in range(tip, start - 1, -1):
        blocks.append(block_summary(h))
    return blocks, tip


def resolve_block(query):
    if isinstance(query, int) or (isinstance(query, str) and query.isdigit()):
        height = int(query)
        block_hash = rpc("getblockhash", [height])
    else:
        block_hash = query
    return rpc("getblock", [block_hash, 2])


def get_address_info(address):
    now = time.time()
    cached = _address_cache.get(address)
    if cached and now - cached["ts"] < ADDRESS_CACHE_TTL:
        return cached["data"]

    validation = rpc("validateaddress", [address])
    if not validation.get("isvalid"):
        return {"valid": False, "address": address}

    balance = None
    utxos = []
    try:
        scan = rpc("scantxoutset", ["start", [f"addr({address})"]])
        balance = scan.get("total_amount", 0)
        utxos = scan.get("unspents", [])
    except RuntimeError:
        balance = None

    data = {
        "valid": True,
        "address": address,
        "scriptPubKey": validation.get("scriptPubKey"),
        "isscript": validation.get("isscript", False),
        "iswitness": validation.get("iswitness", False),
        "balance": balance,
        "utxos": utxos,
    }
    _address_cache[address] = {"ts": now, "data": data}
    return data


def _public_root():
    return os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")


@app.context_processor
def inject_helpers():
    root = _public_root()
    return {
        "fmt_time": fmt_time,
        "fmt_amount": fmt_amount,
        "short_hash": short_hash,
        "currency": "STONE",
        "public_root": root,
        "wallet_url": f"{root}/wallet/",
        "mining_url": f"{root}/mining/",
        "faucet_url": f"{root}/faucet/",
        "format_hashrate": pool_db.format_hashrate,
        **bloodstone_branding.header_brand_context(root, "◆"),
    }


@app.route("/")
def index():
    try:
        blocks, tip = get_recent_blocks(BLOCKS_PER_PAGE)
        info = rpc("getblockchaininfo")
        mining = rpc("getmininginfo")
        mempool = rpc("getrawmempool")
    except Exception as exc:
        return (
            render_template(
                "error.html",
                message=f"Bloodstone node is offline or busy. Try again in a moment. ({exc})",
            ),
            503,
        )
    return render_template(
        "index.html",
        blocks=blocks,
        tip=tip,
        info=info,
        mining=mining,
        mempool_count=len(mempool),
    )


@app.errorhandler(500)
def internal_error(exc):
    return (
        render_template(
            "error.html",
            message="An internal error occurred. The node may be restarting.",
        ),
        500,
    )


@app.route("/block/<query>")
def block_page(query):
    try:
        block = resolve_block(query)
    except RuntimeError as exc:
        return render_template("error.html", message=str(exc)), 404
    if isinstance(block.get("powdata"), dict):
        block = dict(block)
        block["powdata"] = merge_mining_info.enrich_powdata(block["powdata"])
    return render_template("block.html", block=block)


@app.route("/tx/<txid>")
def tx_page(txid):
    try:
        tx = rpc("getrawtransaction", [txid, True])
    except RuntimeError as exc:
        return render_template("error.html", message=str(exc)), 404
    mesh_anchors = []
    try:
        from chain_mesh.anchor_index import decode_tx_anchors

        mesh_anchors = decode_tx_anchors(tx)
    except Exception:
        mesh_anchors = []
    return render_template("tx.html", tx=tx, mesh_anchors=mesh_anchors)


@app.route("/mesh-anchors")
def mesh_anchors_page():
    try:
        from chain_mesh.anchor_index import ensure_fresh, list_anchors

        ensure_fresh()
        payload = list_anchors(limit=100)
    except Exception as exc:
        return render_template("error.html", message=str(exc)), 503
    return render_template(
        "mesh_anchors.html",
        anchors=payload.get("anchors") or [],
        total=payload.get("total") or 0,
        meta=payload.get("meta") or {},
    )


@app.route("/address/<path:address>")
def address_page(address):
    try:
        info = get_address_info(address)
    except RuntimeError as exc:
        return render_template("error.html", message=str(exc)), 404
    if not info.get("valid"):
        return render_template("error.html", message="Invalid address"), 404
    pool_mining = pool_db.get_miner_pool_profile(address)
    return render_template(
        "address.html", info=info, pool_mining=pool_mining
    )


def _live_pool_dashboard() -> dict:
    """Cached pool dashboard with live miner/hashrate overlay (fast API path)."""
    data = pool_db.get_unified_pool_dashboard(allow_build=False)
    if data.get("_loading"):
        pool_db._read_dashboard_disk_cache()
        data = pool_db.get_unified_pool_dashboard(allow_build=False)
    return pool_db.enrich_dashboard_live_fields(data)


def _miners_api_payload(dashboard: dict) -> dict:
    return {
        "pool_miners": dashboard.get("pool_miners") or [],
        "top_pending": dashboard.get("top_pending") or [],
        "block_find_leaderboard": dashboard.get("block_find_leaderboard") or [],
        "recent_block_finds": dashboard.get("recent_block_finds") or [],
        "bitaxe": dashboard.get("bitaxe") or {},
        "finder_bonus_stone": dashboard.get(
            "finder_bonus_stone", pool_db.BLOCK_FINDER_BONUS_STONE
        ),
        "staking_block_pct": dashboard.get("staking_block_pct", 0.0),
        "staking_contribution_stone": dashboard.get("staking_contribution_stone", 0.0),
        "hashrate_window_sec": pool_db.MINER_HASHRATE_WINDOW_SEC,
        "live_enriched_at": dashboard.get("live_enriched_at"),
    }


@app.route("/miners")
def miners_page():
    try:
        dashboard = _live_pool_dashboard()
        if dashboard.get("error"):
            raise RuntimeError(str(dashboard.get("error")))
    except Exception as exc:
        return render_template("error.html", message=str(exc)), 503
    payload = _miners_api_payload(dashboard)
    return render_template("miners.html", **payload)


@app.route("/api/pool/miners")
def api_pool_miners():
    try:
        dashboard = _live_pool_dashboard()
        if dashboard.get("error"):
            return jsonify({"error": str(dashboard.get("error"))}), 503
        return jsonify(_miners_api_payload(dashboard))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503


@app.route("/name/<path:name>")
def name_page(name):
    if not name.startswith("d/"):
        name = f"d/{name}"
    try:
        record = rpc("name_show", [name])
    except RuntimeError as exc:
        return render_template("error.html", message=str(exc)), 404
    return render_template("name.html", name=name, record=record)


@app.route("/names")
def names_page():
    start = request.args.get("start", "")
    page = max(1, int(request.args.get("page", 1)))
    try:
        names = rpc("name_scan", [start, NAMES_PER_PAGE])
    except RuntimeError as exc:
        return render_template("error.html", message=str(exc)), 500
    return render_template("names.html", names=names, start=start, page=page)


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return redirect(url_for("index"))
    kind, value = classify_query(q)
    if kind == "block":
        return redirect(url_for("block_page", query=value))
    if kind == "tx":
        return redirect(url_for("tx_page", txid=value))
    if kind == "address":
        return redirect(url_for("address_page", address=value))
    if kind == "name":
        return redirect(url_for("name_page", name=value))
    return render_template("error.html", message=f"Could not identify search query: {q}"), 400


@app.route("/api/stats")
def api_stats():
    info = rpc("getblockchaininfo")
    mining = rpc("getmininginfo")
    mempool = rpc("getrawmempool")
    return jsonify(
        {
            "height": info["blocks"],
            "bestblockhash": info["bestblockhash"],
            "difficulty": mining.get("difficulty", {}),
            "networkhashps": mining.get("networkhashps", {}),
            "mempool": len(mempool),
            "chain": info.get("chain"),
        }
    )


@app.route("/api/blocks")
def api_blocks():
    limit = min(100, max(1, int(request.args.get("limit", BLOCKS_PER_PAGE))))
    blocks, tip = get_recent_blocks(limit)
    return jsonify({"tip": tip, "blocks": blocks})


@app.route("/api/mesh-anchors")
def api_mesh_anchors():
    try:
        from chain_mesh.anchor_index import ensure_fresh, list_anchors

        ensure_fresh()
        limit = min(200, max(1, int(request.args.get("limit", 50))))
        offset = max(0, int(request.args.get("offset", 0)))
        return jsonify(list_anchors(limit=limit, offset=offset))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


@app.route("/live")
def live():
    return jsonify({"ok": True, "service": "explorer"})


@app.route("/health")
def health():
    try:
        height = rpc("getblockcount")
        return jsonify({"ok": True, "height": height})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8888, debug=False)