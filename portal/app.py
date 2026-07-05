#!/usr/bin/env python3
"""Bloodstone unified portal — landing page for all VPS services."""

import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

import requests

sys.path.insert(0, "/root")
import bloodstone_time
from flask import Flask, jsonify, render_template, request

import bloodstone_branding
import bloodstone_downloads
import bloodstone_rich_list
import pool_db
import pool_device_fleet
import pool_payout_settings

CONF_PATH = os.environ.get("BLOODSTONE_CONF", "/root/.bloodstone/bloodstone.conf")
PUBLIC_HOST = os.environ.get("BLOODSTONE_PUBLIC_HOST", "rodcoinwallet.duckdns.org")
PUBLIC_ROOT = os.environ.get("BLOODSTONE_PUBLIC_ROOT", f"https://{PUBLIC_HOST}")
VPS_IP = os.environ.get("MINER_VPS_IP", "64.188.22.190")
YESPOWER_FORK = int(os.environ.get("YESPOWER_FORK_HEIGHT", "1"))
SHA256D_ONLY_FORK = int(os.environ.get("SHA256D_ONLY_FORK_HEIGHT", "2147483647"))
MULTI_ALGO_FORK = int(os.environ.get("MULTI_ALGO_FORK_HEIGHT", "1"))
GENESIS_HASH = os.environ.get(
    "BLOODSTONE_GENESIS_HASH",
    "df04225074039e630dad825b24818a695462bd19cd585131a0568f50e9bf71d0",
)
NODE_VERSION = os.environ.get("BLOODSTONE_NODE_VERSION", "0.6.9.1")
NODE_GUI_VERSION = os.environ.get("BLOODSTONE_NODE_GUI_VERSION", "0.6.9.2")
WALLET_GUI_VERSION = os.environ.get("BLOODSTONE_WALLET_GUI_VERSION", "0.7.11")
NODE_PKG = f"bloodstone-node-{NODE_VERSION}-linux-x86_64.tar.gz"
NODE_WIN_PKG = f"bloodstone-node-{NODE_VERSION}-win64.zip"
GUI_WIN_SRC = f"bloodstone-node-gui-{NODE_GUI_VERSION}-win64-source.zip"
GUI_WIN_INSTALLER = f"bloodstone-node-gui-{NODE_GUI_VERSION}-win64.exe"
GUI_WIN_INSTALLER_ZIP = f"bloodstone-node-gui-{NODE_GUI_VERSION}-win64.zip"
WALLET_GUI_INSTALLER = f"bloodstone-wallet-node-gui-{WALLET_GUI_VERSION}-win64.exe"
WALLET_GUI_PORTABLE = f"bloodstone-wallet-node-gui-{WALLET_GUI_VERSION}-win64-portable.exe"
WALLET_GUI_SRC = f"bloodstone-wallet-node-gui-{WALLET_GUI_VERSION}-win64-source.zip"
GUI_WIN_MIRROR_HOST = os.environ.get("BLOODSTONE_DOWNLOAD_MIRROR", "rodcoinwallet.duckdns.org")
PORTAL_OVERRIDE_PATHS = [
    "/root/bloodstone-portal/portal-overrides.conf",
    "/root/bloodstone-miner-web/service-overrides.conf",
]
CONTRACT_EXPLORER_TEMPLATES = {
    "ethereum": "https://etherscan.io/address/{address}",
    "eth": "https://etherscan.io/address/{address}",
    "bsc": "https://bscscan.com/address/{address}",
    "binance": "https://bscscan.com/address/{address}",
    "polygon": "https://polygonscan.com/address/{address}",
    "matic": "https://polygonscan.com/address/{address}",
    "base": "https://basescan.org/address/{address}",
    "arbitrum": "https://arbiscan.io/address/{address}",
    "optimism": "https://optimistic.etherscan.io/address/{address}",
    "avalanche": "https://snowtrace.io/address/{address}",
    "avax": "https://snowtrace.io/address/{address}",
}

app = Flask(__name__)


@app.context_processor
def inject_brand_icon():
    return {
        **bloodstone_branding.header_brand_context(PUBLIC_ROOT, "💎"),
        "run_locally": bloodstone_downloads.run_locally_context(PUBLIC_ROOT),
    }


_CACHE_LOCK = threading.Lock()
_CACHE: dict = {}


_CACHE_LOADERS: dict = {}
_CACHE_LOADER_LOCKS: dict = {}


def _cache_loader_lock(key: str) -> threading.Lock:
    with _CACHE_LOCK:
        lock = _CACHE_LOADER_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _CACHE_LOADER_LOCKS[key] = lock
        return lock


def _cached(key: str, ttl_sec: float, loader, fallback=None):
    """Return cached data; never block page render on a cold slow loader."""
    now = time.time()
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry and now - entry[0] < ttl_sec:
            return entry[1]
        stale = entry[1] if entry else fallback

    lock = _cache_loader_lock(key)
    if not lock.acquire(blocking=False):
        return stale if stale is not None else (fallback or {"error": "loading"})

    try:
        with _CACHE_LOCK:
            entry = _CACHE.get(key)
            if entry and time.time() - entry[0] < ttl_sec:
                return entry[1]
        try:
            value = loader()
        except Exception as exc:
            value = stale if stale is not None else {"error": str(exc)}
        with _CACHE_LOCK:
            _CACHE[key] = (time.time(), value)
        return value
    finally:
        lock.release()


def load_override_values():
    values = {}
    for path in PORTAL_OVERRIDE_PATHS:
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.split("#", 1)[0].strip()
                if not line or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and val and key not in values:
                    values[key] = val
    return values


def _setting(name, overrides, default=""):
    return os.environ.get(name) or overrides.get(name) or default


def load_contract_config():
    """Return contract metadata when BLOODSTONE_CONTRACT_ADDRESS is configured."""
    overrides = load_override_values()
    address = _setting("BLOODSTONE_CONTRACT_ADDRESS", overrides).strip()
    if not address:
        return None

    if not re.fullmatch(r"0x[a-fA-F0-9]{40}", address):
        return None

    chain = _setting("BLOODSTONE_CONTRACT_CHAIN", overrides, "Ethereum").strip() or "Ethereum"
    label = _setting("BLOODSTONE_CONTRACT_LABEL", overrides, "STONE Token Contract").strip()
    explorer_url = _setting("BLOODSTONE_CONTRACT_EXPLORER_URL", overrides).strip()
    if not explorer_url:
        template = CONTRACT_EXPLORER_TEMPLATES.get(chain.lower())
        if template:
            explorer_url = template.format(address=address)

    return {
        "address": address,
        "chain": chain,
        "label": label,
        "explorer_url": explorer_url or None,
    }


def load_rpc_url():
    values = {}
    if os.path.isfile(CONF_PATH):
        with open(CONF_PATH, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                values[key.strip()] = val.strip()
    user = values.get("rpcuser", "bloodstone")
    password = values.get("rpcpassword", "")
    port = values.get("rpcport", "18332")
    host = os.environ.get("RPC_HOST", "127.0.0.1")
    return f"http://{user}:{password}@{host}:{port}/"


RPC_URL = load_rpc_url()


def rpc(method, params=None):
    payload = {"jsonrpc": "1.0", "id": "portal", "method": method, "params": params or []}
    resp = requests.post(
        RPC_URL,
        json=payload,
        headers={"content-type": "text/plain;"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return data["result"]


def port_open(port):
    try:
        out = subprocess.check_output(
            ["ss", "-H", "-tln", f"sport = :{port}"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return bool(out.strip())
    except subprocess.CalledProcessError:
        return False


def download_available(filename):
    return bloodstone_downloads.download_meta(PUBLIC_ROOT, filename)


def download_stale_vs_linux(win_meta, linux_meta):
    """True when Windows node zip predates the current Linux relaunch package."""
    if not win_meta or not linux_meta:
        return False
    return win_meta["mtime"] < linux_meta["mtime"] - 300


def _read_sha256(sidecar_path):
    if not os.path.isfile(sidecar_path):
        return None
    with open(sidecar_path, encoding="utf-8") as fh:
        line = fh.readline().strip()
    return line.split()[0] if line else None


def daemon_running():
    try:
        rpc("getblockcount")
        return True
    except Exception:
        pass
    for process in ("bloodstoned",):
        for flag in ("-x", "-f"):
            try:
                subprocess.check_output(
                    ["pgrep", flag, process],
                    stderr=subprocess.DEVNULL,
                )
                return True
            except subprocess.CalledProcessError:
                continue
    return False


def electrum_status():
    ssl_up = port_open(50002)
    tcp_up = port_open(50001)
    return {
        "ssl_host": PUBLIC_HOST,
        "ssl_port": 50002,
        "ssl_url": f"ssl://{PUBLIC_HOST}:50002",
        "tcp_host": VPS_IP,
        "tcp_port": 50001,
        "tcp_url": f"tcp://{VPS_IP}:50001",
        "listening_ssl": ssl_up,
        "listening_tcp": tcp_up,
        "ready": ssl_up and tcp_up,
    }


def exchange_listing():
    stats = chain_stats()
    electrum = electrum_status()
    downloads = {
        "node_linux": download_available(NODE_PKG),
        "node_windows": download_available(NODE_WIN_PKG),
        "node_gui_windows": download_available(GUI_WIN_INSTALLER),
        "wallet_gui_windows": download_available(WALLET_GUI_INSTALLER),
        "wallet_gui_portable": download_available(WALLET_GUI_PORTABLE),
        "downloads_index": f"{PUBLIC_ROOT}/downloads/",
    }
    return {
        "coin": {
            "name": "Bloodstone",
            "ticker": "STONE",
            "symbol": "STONE",
            "network": "mainnet",
            "decimals": 8,
            "smallest_unit": "satoshi",
            "genesis_hash": GENESIS_HASH,
            "block_reward_stone": BLOCK_REWARD_STONE,
            "block_time_seconds": 90,
            "confirmations_deposit": 6,
            "confirmations_withdrawal": 6,
            "coinbase_maturity": 100,
            "address_formats": {
                "legacy_p2pkh": "S… (base58, prefix 0x3f)",
                "bech32": "stone1…",
            },
            "algorithms": ["neoscrypt", "yespower", "sha256d"],
            "merge_mining": {"spacexpanse_rod_chain_id": 1899, "algo": "sha256d"},
        },
        "node": {
            "version": NODE_VERSION,
            "p2p_port": 17333,
            "rpc_port": 18332,
            "rpc_public": False,
            "txindex": True,
            "seed_nodes": [
                f"{VPS_IP}:17333",
                "192.119.82.145:17333",
            ],
            "synced": bool(stats.get("ok") and not stats.get("error")),
            "height": stats.get("height"),
            "connections": stats.get("connections"),
        },
        "infrastructure": {
            "public_root": PUBLIC_ROOT,
            "explorer": f"{PUBLIC_ROOT}/explorer/",
            "explorer_api": f"{PUBLIC_ROOT}/explorer/api/stats",
            "web_wallet": f"{PUBLIC_ROOT}/wallet/",
            "faucet": f"{PUBLIC_ROOT}/faucet/",
            "mining_pool": f"{PUBLIC_ROOT}/mining/",
            "support": f"{PUBLIC_ROOT}/support/",
            "downloads": downloads,
        },
        "electrum": electrum,
        "software": {
            "node_core_version": NODE_VERSION,
            "node_gui_version": NODE_GUI_VERSION,
            "wallet_gui_version": WALLET_GUI_VERSION,
            "github": "https://github.com/SpaceXpanse/rod-core-wallet",
        },
        "dex": {
            "provider": "Gleec",
            "product": "GleecDEX",
            "note": "Gleec acquired Komodo Platform (Dec 2025); GleecDEX uses Komodo atomic-swap tech.",
            "coins_repo": "https://github.com/KomodoPlatform/coins",
            "coins_repo_upstream": "https://github.com/GLEECBTC/coins",
            "legacy_apps": ["Komodo Wallet", "AtomicDEX"],
        },
        "listing_notes": [
            "Jun 2026 relaunch — new genesis; legacy pre-relaunch chain data is not valid.",
            "RPC is localhost-only on the pool VPS; exchanges should use ElectrumX or run their own node.",
            "ElectrumX SSL uses the main portal hostname (Let's Encrypt rate limit blocks electrum.* subdomain cert until later).",
            "For DEX listing: GleecDEX via Gleec (ex-Komodo); CEX listing uses /exchange/ pack above.",
        ],
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def chain_stats():
    try:
        info = rpc("getblockchaininfo")
        mining = rpc("getmininginfo")
        height = info["blocks"]
        diff = mining.get("difficulty", {})
        multi_algo = height + 1 >= MULTI_ALGO_FORK
        sha256d_only = False
        return {
            "ok": True,
            "height": height,
            "chain": info.get("chain", "main"),
            "reward": 100.0,
            "difficulty": diff,
            "yespower_active": height >= YESPOWER_FORK,
            "sha256d_only": sha256d_only,
            "multi_algo": multi_algo,
            "yespower_fork": YESPOWER_FORK,
            "sha256d_only_fork": SHA256D_ONLY_FORK,
            "multi_algo_fork": MULTI_ALGO_FORK,
            "genesis_hash": GENESIS_HASH,
            "connections": info.get("connections", 0),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


SERVICES = [
    {
        "id": "explorer",
        "icon": "🔍",
        "title": "Blockchain Explorer",
        "desc": "Search blocks, transactions, and addresses on the Bloodstone chain.",
        "path": "/explorer/",
        "ip_port": 8888,
        "badge": "Live",
    },
    {
        "id": "wallet",
        "icon": "👛",
        "title": "Web Wallet",
        "desc": "Create accounts, send STONE, and manage wallets in the browser.",
        "path": "/wallet/",
        "ip_port": 8889,
        "badge": "Live",
    },
    {
        "id": "faucet",
        "icon": "💧",
        "title": "STONE Faucet",
        "desc": "Claim test STONE for new wallets, or fund the faucet from your web wallet.",
        "path": "/faucet/",
        "ip_port": 8895,
        "badge": "Free",
    },
    {
        "id": "mining",
        "icon": "⛏",
        "title": "Mining Dashboard",
        "desc": "Unified proportional pool across neoscrypt, yespower, and SHA256d — live shares and balances.",
        "path": "/mining/",
        "ip_port": 8893,
        "badge": "Live",
    },
    {
        "id": "browser-miner",
        "icon": "🌐",
        "title": "Browser CPU Miner",
        "desc": "Mine Yespower R16 directly in your browser — no install required.",
        "path": "/mining/mine",
        "ip_port": 8893,
        "badge": "Yespower",
        "highlight": True,
    },
    {
        "id": "exchange",
        "icon": "🏦",
        "title": "Exchange listing pack",
        "desc": "Coin specs, seed nodes, ElectrumX, explorer, and wallet download links for CEX submissions.",
        "path": "/exchange/",
        "ip_port": 0,
        "badge": "Listing",
        "highlight": True,
    },
    {
        "id": "atomicdex",
        "icon": "⚛",
        "title": "GleecDEX (STONE swaps)",
        "desc": "Swap STONE via GleecDEX (Gleec acquired Komodo Dec 2025). Coin PR + ElectrumX listing in progress.",
        "path": "/atomicdex/",
        "ip_port": 0,
        "badge": "Listing",
        "highlight": True,
    },
    {
        "id": "support",
        "icon": "🎫",
        "title": "Support & Tickets",
        "desc": "Open a ticket for mining, wallet, explorer, or node help. Track replies on your ticket page.",
        "path": "/support/",
        "ip_port": 0,
        "badge": "Help",
    },
    {
        "id": "wallet-node-gui",
        "icon": "💼",
        "title": f"Wallet & Node GUI (v{WALLET_GUI_VERSION})",
        "desc": "All-in-one Windows app: local node, web wallet sign-in, VPS wallet support, RPC console, and wallet import.",
        "path": f"/downloads/{WALLET_GUI_INSTALLER}",
        "ip_port": 0,
        "badge": "New",
        "highlight": True,
    },
    {
        "id": "node-download",
        "icon": "⬇",
        "title": f"Node core (v{NODE_VERSION})",
        "desc": "Required for the Jun 2026 chain relaunch (new genesis). All three PoW algos from block 1. Delete old blocks/ + chainstate/ when upgrading.",
        "path": f"/downloads/{NODE_PKG}",
        "ip_port": 0,
        "badge": "Required",
        "highlight": True,
    },
    {
        "id": "node-gui-windows",
        "icon": "🖥",
        "title": f"Windows Node GUI (v{NODE_GUI_VERSION})",
        "desc": "Node-only graphical app. First Start Node downloads bloodstoned.exe automatically if missing.",
        "path": f"/downloads/{GUI_WIN_INSTALLER}",
        "ip_port": 0,
        "badge": "Windows",
        "highlight": True,
    },
]

POOL_WALLET = os.environ.get(
    "BLOODSTONE_POOL_WALLET",
    os.environ.get(
        "BLOODSTONE_YESPOWER_POOL_WALLET",
        "SNQ2mNsQSumv1P4QdiDqYz5sjCwdDTnbWV",
    ),
)
POOL_FEE_PCT = float(os.environ.get("BLOODSTONE_POOL_FEE_PCT", "1.0"))
BLOCK_REWARD_STONE = float(os.environ.get("BLOODSTONE_BLOCK_REWARD_STONE", "100"))
POOL_PAYOUT_LOG_PATH = os.environ.get(
    "BLOODSTONE_POOL_PAYOUT_LOG", "/var/log/bloodstone-pool-payout.log"
)
POOL_PAYOUT_INTERVAL_MIN = int(os.environ.get("BLOODSTONE_POOL_PAYOUT_INTERVAL_MIN", "30"))


def pool_payout_log_tail(limit: int = 10) -> list:
    path = POOL_PAYOUT_LOG_PATH
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = [ln.rstrip() for ln in fh.readlines() if ln.strip()]
        return lines[-limit:]
    except OSError:
        return []


def pool_dashboard_data(address: str = "", use_cache: bool = True) -> dict:
    if address:
        use_cache = False
    if use_cache:
        return _cached(
            "pool_dashboard",
            float(os.environ.get("PORTAL_POOL_CACHE_SEC", "120")),
            pool_db.get_unified_pool_dashboard,
        )
    try:
        data = pool_db.get_unified_pool_dashboard()
        if address:
            data["miner_balance"] = pool_db.get_miner_balance(address)
            next_block = data.get("next_block") or {}
            per_algo_miners = {
                algo: (entry.get("miners") or [])
                for algo, entry in (next_block.get("per_algo") or {}).items()
            }
            data["miner_next_block"] = pool_db.miner_next_block_shares(
                address,
                per_algo_miners,
                next_block.get("distributable_stone"),
            )
        return data
    except Exception as exc:
        return {"error": str(exc)}


POOLS = [
    {
        "name": "Yespower R16",
        "algo": "yespower",
        "port": 3438,
        "active": True,
        "hint": "Browser miner, cpuminer-opt",
        "share_diff": "1e-9",
    },
    {
        "name": "SHA256d (ROD merge)",
        "algo": "sha256d",
        "port": 3429,
        "active": True,
        "hint": "Bitaxe / ASIC — AuxPoW merge-mined on SpaceXpanse ROD (chain 1899)",
        "share_diff": "0.001",
    },
    {
        "name": "Neoscrypt",
        "algo": "neoscrypt",
        "port": 3437,
        "active": True,
        "hint": "sgminer / ccminer (neoscrypt-xaya)",
        "share_diff": "0.001",
    },
]


@app.route("/")
def index():
    stats = _cached(
        "chain_stats",
        float(os.environ.get("PORTAL_CHAIN_CACHE_SEC", "45")),
        chain_stats,
    )
    for svc in SERVICES:
        svc["url"] = f"{PUBLIC_ROOT}{svc['path']}"
    for pool in POOLS:
        pool["listening"] = port_open(pool["port"])
        pool["stratum_url"] = f"stratum+tcp://{VPS_IP}:{pool['port']}"
    node_download = download_available(NODE_PKG)
    node_win_download = download_available(NODE_WIN_PKG)
    gui_win_src = download_available(GUI_WIN_SRC)
    gui_win_installer = download_available(GUI_WIN_INSTALLER)
    gui_win_installer_zip = download_available(GUI_WIN_INSTALLER_ZIP)
    wallet_gui_installer = download_available(WALLET_GUI_INSTALLER)
    wallet_gui_portable = download_available(WALLET_GUI_PORTABLE)
    wallet_gui_src = download_available(WALLET_GUI_SRC)
    win_downloads_stale = download_stale_vs_linux(node_win_download, node_download)
    download_mirror = f"https://{GUI_WIN_MIRROR_HOST}"
    contract = load_contract_config()
    pool_dashboard = pool_dashboard_data(use_cache=True)
    if pool_dashboard.get("_loading"):
        pool_dashboard = {"loading": True}
    pool_payout = pool_payout_settings.load_pool_payout_settings()
    try:
        fleet_stats = pool_device_fleet.fleet_public_stats()
    except Exception:
        fleet_stats = None
    rich_list = rich_list_data(use_cache=True)
    if rich_list.get("loading") or (not rich_list.get("entries") and not rich_list.get("error")):
        bloodstone_rich_list.schedule_rich_list_refresh()
    return render_template(
        "index.html",
        services=SERVICES,
        pools=POOLS,
        pool_dashboard=pool_dashboard,
        pool_payout_log_path=POOL_PAYOUT_LOG_PATH,
        pool_payout_interval_min=POOL_PAYOUT_INTERVAL_MIN,
        pool_payout_chunk_max=pool_payout["payout_chunk_max"],
        pool_payout_log_lines=pool_payout_log_tail(),
        pool_fee_pct=POOL_FEE_PCT,
        block_reward_stone=BLOCK_REWARD_STONE,
        stats=stats,
        public_root=PUBLIC_ROOT,
        public_host=PUBLIC_HOST,
        vps_ip=VPS_IP,
        daemon_ok=bool(stats.get("ok")),
        updated=bloodstone_time.now_pacific(),
        sha256d_only_fork=SHA256D_ONLY_FORK,
        multi_algo_fork=MULTI_ALGO_FORK,
        node_version=NODE_VERSION,
        node_gui_version=NODE_GUI_VERSION,
        wallet_gui_version=WALLET_GUI_VERSION,
        node_download=node_download,
        node_win_download=node_win_download,
        gui_win_src=gui_win_src,
        gui_win_installer=gui_win_installer,
        gui_win_installer_zip=gui_win_installer_zip,
        wallet_gui_installer=wallet_gui_installer,
        wallet_gui_portable=wallet_gui_portable,
        wallet_gui_src=wallet_gui_src,
        download_mirror=download_mirror,
        win_downloads_stale=win_downloads_stale,
        genesis_hash=GENESIS_HASH,
        contract=contract,
        fleet_stats=fleet_stats,
        rich_list=rich_list,
    )


@app.route("/exchange/")
def exchange_page():
    listing = exchange_listing()
    return render_template(
        "exchange.html",
        listing=listing,
        public_root=PUBLIC_ROOT,
        public_host=PUBLIC_HOST,
        vps_ip=VPS_IP,
        updated=bloodstone_time.now_pacific(),
    )


@app.route("/api/exchange")
def api_exchange():
    return jsonify(exchange_listing())


@app.route("/atomicdex/")
def atomicdex():
    node_download = download_available(NODE_PKG)
    return render_template(
        "atomicdex.html",
        public_root=PUBLIC_ROOT,
        public_host=PUBLIC_HOST,
        vps_ip=VPS_IP,
        node_version=NODE_VERSION,
        listing_status="ElectrumX live — submit GleecDEX coin PR via KomodoPlatform/coins (GLEEC lineage)",
        updated=bloodstone_time.now_pacific(),
        node_download=node_download,
    )


@app.route("/api/pool/dashboard")
def api_pool_dashboard():
    address = (request.args.get("address") or "").strip()
    return jsonify(pool_dashboard_data(address))


def rich_list_data(limit: int = 25, use_cache: bool = True) -> dict:
    limit = max(5, min(100, int(limit)))
    if use_cache:
        return _cached(
            f"rich_list_{limit}",
            float(os.environ.get("PORTAL_RICH_LIST_CACHE_SEC", "600")),
            lambda: bloodstone_rich_list.get_rich_list(limit=limit),
            fallback={"ok": False, "entries": [], "loading": True},
        )
    return bloodstone_rich_list.get_rich_list(limit=limit)


@app.route("/api/android-miner/update")
def api_android_miner_update():
    return jsonify(bloodstone_downloads.android_miner_update_manifest(PUBLIC_ROOT))


@app.route("/api/rich-list")
def api_rich_list():
    limit = request.args.get("limit", bloodstone_rich_list.DEFAULT_LIMIT)
    refresh = (request.args.get("refresh") or "").strip() in ("1", "true", "yes")
    try:
        data = bloodstone_rich_list.get_rich_list(
            limit=int(limit),
            force_refresh=refresh,
        )
        if data.get("loading") or (not data.get("entries") and not data.get("error")):
            bloodstone_rich_list.schedule_rich_list_refresh(limit=int(limit))
        return jsonify(data)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc), "entries": []}), 503


@app.route("/api/pool/payout-log")
def api_pool_payout_log():
    limit = min(30, max(1, int(request.args.get("limit", 10))))
    pool_payout = pool_payout_settings.load_pool_payout_settings()
    return jsonify(
        {
            "path": POOL_PAYOUT_LOG_PATH,
            "interval_min": POOL_PAYOUT_INTERVAL_MIN,
            "chunk_max": pool_payout["payout_chunk_max"],
            "lines": pool_payout_log_tail(limit),
        }
    )


def _warm_portal_cache():
    def _run():
        try:
            _cached(
                "chain_stats",
                float(os.environ.get("PORTAL_CHAIN_CACHE_SEC", "45")),
                chain_stats,
            )
        except Exception:
            pass
        try:
            _cached(
                "pool_dashboard",
                float(os.environ.get("PORTAL_POOL_CACHE_SEC", "120")),
                pool_db.get_unified_pool_dashboard,
            )
        except Exception:
            pass
        try:
            bloodstone_rich_list.schedule_rich_list_refresh()
        except Exception:
            pass

    threading.Thread(
        target=_run, daemon=True, name="portal-cache-warm"
    ).start()


_warm_portal_cache()


@app.route("/health")
@app.route("/live")
def health():
    """Lightweight liveness probe for watchdogs and load balancers."""
    return jsonify({"ok": True, "service": "portal"})


@app.route("/api/status")
def api_status():
    stats = chain_stats()
    pools = [
        {"name": p["name"], "port": p["port"], "listening": port_open(p["port"])}
        for p in POOLS
    ]
    return jsonify(
        {
            "chain": stats,
            "daemon": daemon_running(),
            "pools": pools,
            "public_root": PUBLIC_ROOT,
            "vps_ip": VPS_IP,
            "contract": load_contract_config(),
        }
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8887, debug=False)