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
import bloodstone_beta_codes
import bloodstone_http_auth as http_auth
import bloodstone_downloads
import bloodstone_quasar
import bloodstone_rich_list
import pool_db
import pool_device_fleet
import pool_payout_settings

try:
    from chain_mesh import __version__ as CONVERGENCE_VERSION
except ImportError:  # pragma: no cover
    CONVERGENCE_VERSION = "0.36.0-beta"

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
EXCHANGE_NODE_PKG = f"bloodstone-exchange-node-{NODE_VERSION}-linux-x86_64.tar.gz"
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


def _safe_err(exc, public="request failed"):
    try:
        from chain_mesh.security import public_error
        return public_error(exc, public=public)
    except Exception:
        if isinstance(exc, (ValueError, PermissionError, TypeError)):
            return str(exc)[:200]
        return public


def _api_error(exc, status=None, *, public="request failed"):
    if status is None:
        if isinstance(exc, PermissionError):
            status = 403
        elif isinstance(exc, (ValueError, TypeError, KeyError)):
            status = 400
        else:
            status = 500
    return jsonify({"ok": False, "error": _safe_err(exc, public=public)}), status


app = Flask(__name__)
print(
    f"Bloodstone portal v{CONVERGENCE_VERSION} "
    f"(bloodstone-pi-fleet-convergence-{CONVERGENCE_VERSION}) starting...",
    flush=True,
)


@app.before_request
def _guard_convergence_writes():
    return http_auth.guard_convergence_post()


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
            value = stale if stale is not None else {"error": _safe_err(exc)}
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


def _mask_rpc_secrets(text):
    """M-02: never log RPC user:password@ URLs."""
    import re

    return re.sub(r"(://[^:/?#\s]+):([^@/\s]+)@", r"\1:***@", str(text or ""))


def rpc(method, params=None):
    payload = {"jsonrpc": "1.0", "id": "portal", "method": method, "params": params or []}
    try:
        resp = requests.post(
            RPC_URL,
            json=payload,
            headers={"content-type": "text/plain;"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        # Mask credentials if request library embeds URL in the exception message.
        raise RuntimeError(_mask_rpc_secrets(exc)) from None
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
    quasar_status = {}
    try:
        quasar_status = bloodstone_quasar.build_status(rpc)
    except Exception:
        quasar_status = {"ok": False, "braid_status": "unknown"}
    downloads = {
        "node_linux": download_available(NODE_PKG),
        "exchange_node_linux": download_available(EXCHANGE_NODE_PKG),
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
            "confirmations_deposit_recommended": (
                (quasar_status.get("confirmations") or {}).get(
                    "recommended_deposit", 6
                )
            ),
            "confirmations_withdrawal_recommended": (
                (quasar_status.get("confirmations") or {}).get(
                    "recommended_withdrawal", 6
                )
            ),
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
        "exchange_node": {
            "package": EXCHANGE_NODE_PKG,
            "download": download_available(EXCHANGE_NODE_PKG),
            "wallet_name": "exchange-hot",
            "datadir_example": "/var/lib/bloodstone-exchange",
            "setup_script": "setup-exchange-node.sh",
            "verify_script": "verify-exchange-node.sh",
            "required_flags": ["txindex=1", "wallet=exchange-hot"],
            "forbidden_flags": ["disablewallet=1"],
        },
        "quasar": bloodstone_quasar.exchange_quasar_fields(quasar_status, PUBLIC_ROOT),
        "listing_notes": [
            "Jun 2026 relaunch — new genesis; legacy pre-relaunch chain data is not valid.",
            "RPC is localhost-only on the pool VPS; exchanges should use ElectrumX or run their own node.",
            "CEX: download bloodstone-exchange-node-*-linux-x86_64.tar.gz — includes txindex, hot wallet, setup + verify scripts.",
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
        return {"ok": False, "error": _safe_err(exc)}


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
        return {"error": _safe_err(exc)}


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
    if not isinstance(rich_list, dict):
        rich_list = {"ok": False, "entries": [], "loading": True}
    # Template expects these keys even while the UTXO index is building.
    rich_list.setdefault("entries", [])
    rich_list.setdefault("loading", False)
    rich_list.setdefault("error", None)
    rich_list.setdefault("total_onchain_stone", None)
    rich_list.setdefault("holders_scanned", None)
    rich_list.setdefault("holders_with_balance", None)
    rich_list.setdefault("estimated_supply_stone", None)
    rich_list.setdefault("indexed_height", None)
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


@app.route("/quasar/")
def quasar_page():
    downloads_base = os.environ.get(
        "BLOODSTONE_PUBLIC_DOWNLOADS_BASE",
        f"{PUBLIC_ROOT.rstrip('/')}/downloads",
    )
    return render_template(
        "quasar.html",
        public_root=PUBLIC_ROOT,
        downloads_base=downloads_base.rstrip("/"),
        coin_icon_url=bloodstone_branding.coin_icon_url(PUBLIC_ROOT),
        updated=bloodstone_time.now_pacific(),
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


def data_sales_listing() -> dict:
    """Published data rates in STONE + setup requirements for buyers and sellers."""
    try:
        from chain_mesh import depin_credits as depin
        from chain_mesh import stone_data_payments as sdp
        from chain_mesh import storage_credits as storage

        enforce_bw = bool(depin.ENFORCE_BANDWIDTH)
        enforce_st = bool(storage.ENFORCE_QUOTA)
        enforce_cp = bool(depin.ENFORCE_COMPUTE)
        stone_rates = sdp.rates_payload()
        treasuries = stone_rates.get("treasury_addresses") or sdp.treasuries()
        treasury_storage = (treasuries.get("storage") or "").strip()
        treasury_bandwidth = (treasuries.get("bandwidth") or "").strip()
        treasury_compute = (treasuries.get("compute") or "").strip()
        # Backward-compatible single field → storage treasury.
        treasury = treasury_storage or stone_rates.get("treasury_address") or ""
        st_per_gib = float(stone_rates["storage"]["stone_per_unit"])
        bw_per_100 = float(stone_rates["bandwidth"]["stone_per_unit"])
        cp_per_gflop = float(stone_rates["compute"]["stone_per_unit"])
        upkeep_per_gib = float(
            (stone_rates.get("upkeep") or {}).get("stone_per_gib_month")
            or stone_rates["storage"].get("upkeep_stone_per_gib_month")
            or 0.1
        )
        upkeep_grace = int(
            (stone_rates.get("upkeep") or {}).get("grace_days")
            or stone_rates["storage"].get("upkeep_grace_days")
            or 30
        )
        # Optional Blurt alternate rail (legacy) — not the primary settlement.
        blurt_storage_outpost = storage.OUTPOST_ACCOUNT
        blurt_depin_outpost = depin.DEPIN_OUTPOST_ACCOUNT
        try:
            from chain_mesh import storage_upkeep as supkeep

            upkeep_network = supkeep.network_upkeep_summary()
        except Exception:
            upkeep_network = {}
    except Exception:
        enforce_bw = enforce_st = enforce_cp = False
        treasury_storage = os.environ.get("DATA_SALES_TREASURY_STORAGE", "")
        treasury_bandwidth = os.environ.get("DATA_SALES_TREASURY_BANDWIDTH", "")
        treasury_compute = os.environ.get("DATA_SALES_TREASURY_COMPUTE", "")
        treasury = treasury_storage or os.environ.get("DATA_SALES_TREASURY_ADDRESS", "")
        treasuries = {
            "storage": treasury_storage,
            "bandwidth": treasury_bandwidth,
            "compute": treasury_compute,
        }
        st_per_gib = bw_per_100 = cp_per_gflop = 1.0
        upkeep_per_gib = float(os.environ.get("DATA_SALES_UPKEEP_STONE_PER_GIB_MONTH", "0.1"))
        upkeep_grace = int(os.environ.get("DATA_SALES_UPKEEP_GRACE_DAYS", "30"))
        stone_rates = {}
        upkeep_network = {}
        blurt_storage_outpost = "bloodstone-storage"
        blurt_depin_outpost = "bloodstone-depin"

    return {
        "ok": True,
        "title": "Bloodstone data sales",
        "updated": bloodstone_time.now_pacific(),
        "public_root": PUBLIC_ROOT,
        "currency": {
            "payment_token": "USDT+STONE",
            "commercial_token": "USDT",
            "provider_token": "STONE",
            "network": "Bloodstone mainnet + EVM USDT",
            "treasury_addresses": treasuries,
            "treasury_address": treasury,
            "note": (
                "Two payment rails — USDT (EVM commercial) and direct STONE (mesh-native). "
                "Team / founder trail / active / referral percentages are the same on both. "
                "USDT residual converts to STONE for providers; STONE residual is already STONE."
            ),
        },
        "storage": {
            "product": "mesh_storage",
            "display_rate": f"{st_per_gib:g} STONE",
            "unit": "1 GiB",
            "stone_per_unit": st_per_gib,
            "treasury_address": treasury_storage,
            "blurb": (
                "Persistent chain-mesh object storage (chunked assets, BSM anchors). "
                f"Plus monthly upkeep {upkeep_per_gib:g} STONE/GiB on retained data "
                f"(first {upkeep_grace} days free)."
            ),
            "payment": (
                f"Send {st_per_gib:g}+ STONE → storage treasury → claim product=storage"
            ),
            "upkeep_stone_per_gib_month": upkeep_per_gib,
            "upkeep_display": f"{upkeep_per_gib:g} STONE / GiB · month",
            "upkeep_grace_days": upkeep_grace,
            "enforced": enforce_st,
        },
        "upkeep": {
            "product": "storage_upkeep",
            "display_rate": f"{upkeep_per_gib:g} STONE",
            "unit": "1 GiB · month",
            "stone_per_gib_month": upkeep_per_gib,
            "stone_per_tib_month": upkeep_per_gib * 1024,
            "display_tib": f"{upkeep_per_gib * 1024:g} STONE / TiB · month",
            "grace_days": upkeep_grace,
            "treasury_address": treasury_storage,
            "blurb": (
                "Monthly keep-alive for old / retained data so disk, power, and "
                "replication stay funded. Assessed on bytes currently stored, not "
                "unused prepaid quota."
            ),
            "payment": (
                f"Send upkeep STONE → storage treasury → claim product=upkeep "
                f"(quote: GET /api/data-sales/upkeep?stone_address=…)"
            ),
            "assessed_on": "bytes currently stored",
            "network": upkeep_network,
        },
        "bandwidth": {
            "product": "mesh_bandwidth",
            "display_rate": f"{bw_per_100:g} STONE",
            "unit": "100 MiB",
            "stone_per_unit": bw_per_100,
            "treasury_address": treasury_bandwidth,
            "blurb": "DTN / mesh / internet-gateway data transfer credit.",
            "payment": (
                f"Send {bw_per_100:g}+ STONE → bandwidth treasury → claim product=bandwidth"
            ),
            "enforced": enforce_bw,
        },
        "compute": {
            "product": "mesh_compute",
            "display_rate": f"{cp_per_gflop:g} STONE",
            "unit": "1 GFLOP",
            "stone_per_unit": cp_per_gflop,
            "treasury_address": treasury_compute,
            "blurb": "DePIN job credits for edge compute workers.",
            "payment": (
                f"Send {cp_per_gflop:g}+ STONE → compute treasury → claim product=compute"
            ),
            "enforced": enforce_cp,
        },
        "treasury_addresses": treasuries,
        "treasury_address": treasury,
        "claim_api": f"{PUBLIC_ROOT}/api/data-sales/claim",
        "stone_rates": stone_rates,
        "table": [
            {
                "name": "Storage (write credit)",
                "buy": f"{st_per_gib:g} STONE → 1 GiB",
                "treasury": treasury_storage,
                "get": "Prepaid mesh storage credit on your STONE address",
                "enforced": enforce_st,
            },
            {
                "name": "Storage upkeep (retention)",
                "buy": f"{upkeep_per_gib:g} STONE → 1 GiB · month",
                "treasury": treasury_storage,
                "get": (
                    f"Keeps stored data online after {upkeep_grace}-day grace; "
                    "assessed on bytes currently stored"
                ),
                "enforced": False,
            },
            {
                "name": "Bandwidth / data",
                "buy": f"{bw_per_100:g} STONE → 100 MiB",
                "treasury": treasury_bandwidth,
                "get": "Prepaid transfer credit on your STONE address",
                "enforced": enforce_bw,
            },
            {
                "name": "Compute",
                "buy": f"{cp_per_gflop:g} STONE → 1 GFLOP",
                "treasury": treasury_compute,
                "get": "Prepaid compute credit (optional job_id on claim)",
                "enforced": enforce_cp,
            },
        ],
        "provider_roles": [
            {
                "role": "Storage peer",
                "supply": "Disk for mesh chunks / asset library",
                "hardware": "Pi 4/5 + USB SSD, or always-on PC/VPS",
                "software": "Pi fleet bundle or full bloodstoned + mesh coordinator",
            },
            {
                "role": "Bandwidth / gateway",
                "supply": "Uplink for mesh HTTP gateway / DTN / LAN share",
                "hardware": "Android phone (share internet) or Pi/router with uplink",
                "software": "Bloodstone miner Android app · mesh share-internet · fleet DTN",
            },
            {
                "role": "Compute worker",
                "supply": "CPU/GPU/NPU job capacity",
                "hardware": "Pi, PC, or GPU box on fleet",
                "software": "Convergence compute agent + tenant bind",
            },
        ],
        "buyer_setup": [
            {
                "title": "Create / fund a STONE wallet",
                "detail": "Data is paid in STONE on Bloodstone mainnet. Use Core Qt, web wallet, or Android miner.",
                "link": f"{PUBLIC_ROOT}/wallet/",
                "link_label": "Open wallet",
            },
            {
                "title": "Send STONE to the product treasury",
                "detail": (
                    "Three separate wallets: storage, bandwidth, compute. "
                    f"Storage: {treasury_storage or 'see /api/data-sales'} · "
                    f"Bandwidth: {treasury_bandwidth or 'see /api/data-sales'} · "
                    f"Compute: {treasury_compute or 'see /api/data-sales'}. "
                    "Amount × published rate determines credit size."
                ),
                "link": f"{PUBLIC_ROOT}/api/data-sales",
                "link_label": "JSON rates + treasuries",
            },
            {
                "title": "Claim the payment",
                "detail": (
                    "POST /api/data-sales/claim with txid, your stone_address, and product "
                    "(storage|bandwidth|compute). Claim only credits if the tx paid that product's treasury."
                ),
                "link": f"{PUBLIC_ROOT}/api/data-sales",
                "link_label": "Claim API details",
            },
            {
                "title": "Check quota",
                "detail": "Query remaining bytes/FLOPs for your STONE address on the convergence quota endpoints.",
                "link": f"{PUBLIC_ROOT}/api/convergence/status",
                "link_label": "Convergence status",
            },
            {
                "title": "Use the mesh product",
                "detail": "Publish/fetch mesh assets, open DTN/gateway paths, or submit compute jobs against your credits.",
                "link": f"{PUBLIC_ROOT}/mining/",
                "link_label": "Mining / mesh portal",
            },
        ],
        "seller_setup": [
            {
                "title": "Run mesh-capable hardware",
                "detail": "Pi fleet (edge), Android miner with Share Internet, or a full Bloodstone node on SSD.",
                "link": f"{PUBLIC_ROOT}/downloads/",
                "link_label": "Downloads",
            },
            {
                "title": "Install with chain bootstrap (nodes)",
                "detail": "Full nodes should use the tip chain bootstrap so you are not stuck mid-sync.",
                "link": f"{PUBLIC_ROOT}/downloads/bloodstone-chain-bootstrap-latest.tar.gz",
                "link_label": "Chain bootstrap",
            },
            {
                "title": "Register provider identity",
                "detail": "Bind a STONE address; advertise storage/bandwidth/compute capabilities on the fleet.",
                "link": f"{PUBLIC_ROOT}/api/convergence/agent/register",
                "link_label": "Agent register API",
            },
            {
                "title": "Keep uplink and disk healthy",
                "detail": "Bandwidth sellers need stable NAT/firewall (TCP 17333 / LAN gateway). Storage sellers need free disk.",
                "link": f"{PUBLIC_ROOT}/downloads/#qt-fix-tools",
                "link_label": "Node fix tools",
            },
            {
                "title": "Serve demand paid in STONE",
                "detail": (
                    "Buyers pay STONE into the matching product treasury and claim credits; "
                    "stay online to deliver data/compute. Operator payouts can draw from each treasury separately."
                ),
                "link": f"{PUBLIC_ROOT}/api/data-sales",
                "link_label": "Data sales API",
            },
        ],
        "examples": [
            {
                "title": "Buy 5 GiB mesh storage",
                "body": (
                    f"1) Send {5 * st_per_gib:g} STONE → {treasury_storage or 'STORAGE_TREASURY'}\n"
                    "2) POST /api/data-sales/claim\n"
                    '   {"txid":"<txid>","stone_address":"YOUR_STONE_ADDRESS","product":"storage"}'
                ),
            },
            {
                "title": f"Pay monthly upkeep for 10 GiB retained data ({10 * upkeep_per_gib:g} STONE)",
                "body": (
                    f"1) GET /api/data-sales/upkeep?stone_address=YOUR_STONE_ADDRESS  (quote)\n"
                    f"2) Send {10 * upkeep_per_gib:g} STONE → {treasury_storage or 'STORAGE_TREASURY'}\n"
                    "3) POST /api/data-sales/claim\n"
                    '   {"txid":"<txid>","stone_address":"YOUR_STONE_ADDRESS","product":"upkeep"}'
                ),
            },
            {
                "title": "Buy 1 GiB bandwidth (10 × 100 MiB packs at default rate)",
                "body": (
                    f"1) Send {10 * bw_per_100:g} STONE → {treasury_bandwidth or 'BANDWIDTH_TREASURY'}\n"
                    "2) POST /api/data-sales/claim\n"
                    '   {"txid":"<txid>","stone_address":"YOUR_STONE_ADDRESS","product":"bandwidth"}'
                ),
            },
            {
                "title": "Buy compute credits",
                "body": (
                    f"1) Send {cp_per_gflop:g}+ STONE → {treasury_compute or 'COMPUTE_TREASURY'}\n"
                    "2) POST /api/data-sales/claim\n"
                    '   {"txid":"<txid>","stone_address":"YOUR_STONE_ADDRESS","product":"compute","job_id":"my-job-01"}'
                ),
            },
            {
                "title": "Corporate path — buy 10 GiB storage in USDT",
                "body": (
                    "1) GET /api/data-sales/usdt/quote?product=storage&units=10\n"
                    "2) Send USDT (ERC-20) → central EVM treasury from quote\n"
                    "3) POST /api/data-sales/usdt/claim\n"
                    '   {"usdt_txid":"<txid>","product":"storage","units":10,"stone_address":"YOUR_STONE_ADDRESS"}\n'
                    "4) Team USDT split books automatically; remainder → STONE provider pool"
                ),
            },
        ],
        "blurt_alternate": {
            "available": True,
            "note": (
                "Optional Blurt-native path still exists for ecosystem bridging: "
                "pay BLURT to outpost accounts with storage|bandwidth|compute memos. "
                "Commercial front door is USDT; mesh-native settlement remains STONE."
            ),
            "storage_outpost": blurt_storage_outpost,
            "depin_outpost": blurt_depin_outpost,
        },
        "checklist": [
            "STONE wallet funded (payment currency)",
            f"Storage treasury: {treasury_storage or '(configure DATA_SALES_TREASURY_STORAGE)'}",
            f"Bandwidth treasury: {treasury_bandwidth or '(configure DATA_SALES_TREASURY_BANDWIDTH)'}",
            f"Compute treasury: {treasury_compute or '(configure DATA_SALES_TREASURY_COMPUTE)'}",
            "Claim via POST /api/data-sales/claim with txid + stone_address + product",
            "For sellers: node or Pi/Android mesh stack online with seed peers",
            "Full-node sellers: tip bootstrap installed; height near network tip",
            "Firewall allows P2P 17333 (and LAN gateway ports if sharing internet)",
            "Providers: watch explorer mesh capacity meters (prepaid demand vs surplus)",
        ],
        "capacity_api": f"{PUBLIC_ROOT}/api/data-sales/capacity",
        "explorer_capacity": f"{PUBLIC_ROOT}/explorer/",
        "monetization": _monetization_for_listing(),
    }


def _monetization_for_listing() -> dict:
    """USDT-first commercial model embedded in data-sales JSON."""
    try:
        from chain_mesh import usdt_monetization as mon

        payload = mon.monetization_payload()
        payload["stats"] = mon.summary_stats()
        return payload
    except Exception as exc:
        return {"ok": False, "error": _safe_err(exc)}


@app.route("/data/")
@app.route("/data-sales/")
def data_sales_page():
    rates = data_sales_listing()
    return render_template(
        "data_sales.html",
        rates=rates,
        public_root=PUBLIC_ROOT,
        public_host=PUBLIC_HOST,
        updated=bloodstone_time.now_pacific(),
    )


@app.route("/api/data-sales")
@app.route("/api/data/rates")
def api_data_sales():
    return jsonify(data_sales_listing())


@app.route("/api/data-sales/capacity")
@app.route("/api/mesh-capacity")
def api_data_sales_capacity():
    """Prepaid credit demand vs fleet capacity (same meters as explorer)."""
    try:
        from chain_mesh import capacity_demand as cap

        return jsonify(cap.capacity_demand_payload())
    except Exception as exc:
        return _api_error(exc, 503)


@app.route("/api/data-sales/upkeep")
def api_data_sales_upkeep():
    """Quote or summarize monthly storage upkeep (retention of old data)."""
    try:
        from chain_mesh import storage_upkeep as supkeep

        addr = (request.args.get("stone_address") or request.args.get("address") or "").strip()
        if addr:
            return jsonify(supkeep.quote_upkeep(addr))
        return jsonify(supkeep.network_upkeep_summary())
    except Exception as exc:
        return _api_error(exc, 400)




@app.route("/api/network/payment-config")
def api_network_payment_config():
    """Public auditable payment addresses + reseller policy (single source of truth)."""
    try:
        from chain_mesh import reseller_platform as rp
        return jsonify(rp.payment_config_payload())
    except Exception as exc:
        return _api_error(exc, 500)


@app.route("/api/reseller/overview")
def api_reseller_overview():
    try:
        from chain_mesh import reseller_platform as rp
        return jsonify(rp.platform_overview())
    except Exception as exc:
        return _api_error(exc, 500)


@app.route("/api/data-sales/monetization")
def api_data_sales_monetization():
    """USDT-first commercial model: team split → STONE provider pool → hold tiers."""
    try:
        from chain_mesh import usdt_monetization as mon

        payload = mon.monetization_payload()
        payload["stats"] = mon.summary_stats()
        return jsonify(payload)
    except Exception as exc:
        return _api_error(exc, 500)


@app.route("/api/data-sales/alignment")
def api_data_sales_alignment():
    """Founder STONE alignment + USDT trail/active + community referral structure."""
    try:
        from chain_mesh import founder_alignment as align

        return jsonify(align.alignment_payload())
    except Exception as exc:
        return _api_error(exc, 500)


@app.route("/api/data-sales/alignment/waterfall")
def api_data_sales_alignment_waterfall():
    """Preview USDT waterfall for a gross amount (optional referral code)."""
    try:
        from chain_mesh import founder_alignment as align
        from decimal import Decimal

        usdt = Decimal(str(request.args.get("usdt") or request.args.get("gross") or "100"))
        ref = (request.args.get("ref") or request.args.get("referral_code") or "").strip()
        return jsonify({"ok": True, **align.commercial_waterfall(usdt, referral_code=ref)})
    except Exception as exc:
        return _api_error(exc, 400)


@app.route("/api/data-sales/alignment/tranche", methods=["POST"])
def api_data_sales_alignment_tranche():
    """Schedule founder STONE monthly tranche (or initial) if participation active."""
    payload = request.get_json(silent=True) or {}
    try:
        from chain_mesh import founder_alignment as align

        kind = str(payload.get("kind") or "monthly").strip().lower()
        if kind == "initial":
            return jsonify(align.schedule_initial_alignment(note=str(payload.get("note") or "")))
        return jsonify(
            align.schedule_monthly_tranche(
                period_label=str(payload.get("period_label") or ""),
                participation_ok=payload.get("participation_ok"),
                note=str(payload.get("note") or ""),
            )
        )
    except Exception as exc:
        return _api_error(exc, 400)


@app.route("/api/data-sales/referral/register", methods=["POST"])
def api_data_sales_referral_register():
    """Register a community/team referral code (global sales force)."""
    payload = request.get_json(silent=True) or {}
    try:
        from chain_mesh import founder_alignment as align

        return jsonify(
            align.register_referral_code(
                owner_label=str(payload.get("owner_label") or payload.get("name") or "promoter"),
                owner_stone_address=str(payload.get("stone_address") or ""),
                owner_usdt_wallet=str(payload.get("usdt_wallet") or ""),
                channel=str(payload.get("channel") or "community"),
                code=str(payload.get("code") or ""),
            )
        )
    except Exception as exc:
        return _api_error(exc, 400)


@app.route("/api/data-sales/usdt/quote")
def api_data_sales_usdt_quote():
    """Quote USDT for storage|upkeep|bandwidth|compute units."""
    try:
        from chain_mesh import usdt_monetization as mon

        product = (request.args.get("product") or "storage").strip()
        units = float(request.args.get("units") or request.args.get("qty") or 1)
        ref = (request.args.get("ref") or request.args.get("referral_code") or "").strip()
        return jsonify(mon.quote_resource(product, units, referral_code=ref))
    except Exception as exc:
        return _api_error(exc, 400)


@app.route("/api/data-sales/usdt/claim", methods=["POST"])
def api_data_sales_usdt_claim():
    """Record USDT commercial payment → team accounting + provider STONE pool."""
    payload = request.get_json(silent=True) or {}
    try:
        from chain_mesh import usdt_monetization as mon

        result = mon.record_usdt_payment(
            product=str(payload.get("product") or ""),
            units=float(payload.get("units") or payload.get("qty") or 1),
            usdt_gross=str(payload.get("usdt_gross")) if payload.get("usdt_gross") is not None else None,
            usdt_txid=str(payload.get("usdt_txid") or payload.get("txid") or ""),
            stone_address=str(payload.get("stone_address") or ""),
            payer_ref=str(payload.get("payer_ref") or payload.get("email") or ""),
            memo=str(payload.get("memo") or ""),
            payment_ref=str(payload.get("payment_ref") or ""),
            referral_code=str(payload.get("referral_code") or payload.get("ref") or ""),
        )
        # Optionally credit mesh quota when stone_address + product map to STONE rails
        if result.get("ok") and not result.get("duplicate"):
            stone_addr = str(payload.get("stone_address") or "").strip()
            product = str(payload.get("product") or "").strip().lower()
            units = float(payload.get("units") or 1)
            if stone_addr and product in ("storage", "bandwidth", "compute", "upkeep"):
                try:
                    result["mesh_credit"] = _credit_from_usdt_units(
                        product=product, units=units, stone_address=stone_addr, usdt_txid=str(payload.get("usdt_txid") or "")
                    )
                except Exception as credit_exc:
                    result["mesh_credit"] = {"ok": False, "error": str(credit_exc)}
        return jsonify(result)
    except Exception as exc:
        return _api_error(exc, 400)


@app.route("/api/data-sales/provider-tier")
def api_data_sales_provider_tier():
    """Hold-to-earn tier for a given attested STONE holding (or address lookup later)."""
    try:
        from chain_mesh import usdt_monetization as mon

        held = float(request.args.get("stone_held") or request.args.get("holdings") or 0)
        base = request.args.get("base_stone")
        tier = mon.provider_tier_for_holdings(held)
        out = {"ok": True, "tier": tier}
        if base is not None:
            out["distribution"] = mon.apply_provider_bonus(
                mon._d(base) if hasattr(mon, "_d") else __import__("decimal").Decimal(str(base)),
                held,
            )
        return jsonify(out)
    except Exception as exc:
        return _api_error(exc, 400)


def _credit_from_usdt_units(*, product: str, units: float, stone_address: str, usdt_txid: str) -> dict:
    """Map purchased USDT units onto existing mesh credit ledgers (1 unit = same pack as STONE rates)."""
    from chain_mesh import depin_credits as depin
    from chain_mesh import storage_credits as storage
    from chain_mesh import storage_upkeep as upkeep

    synthetic = f"usdt:{usdt_txid or 'manual'}:{product}:{units}"
    product = product.lower()
    if product == "storage":
        bytes_credit = int(units * 1024 * 1024 * 1024)
        return storage.credit_from_blurt_transfer(
            stone_address=stone_address,
            bytes_credited=bytes_credit,
            blurt_txid=synthetic,
            blurt_from="usdt-commercial",
            blurt_amount=str(units),
            memo=f"usdt-pay storage {units} GiB",
        )
    if product == "bandwidth":
        bytes_credit = int(units * 100 * 1024 * 1024)
        return depin.credit_bandwidth(
            stone_address=stone_address,
            bytes_credited=bytes_credit,
            blurt_txid=synthetic,
            blurt_from="usdt-commercial",
            blurt_amount=str(units),
            memo=f"usdt-pay bandwidth {units}×100MiB",
        )
    if product == "compute":
        flops = int(units * 1_000_000_000)
        return depin.credit_compute(
            stone_address=stone_address,
            job_id="prepaid",
            flops_credited=flops,
            blurt_txid=synthetic,
            blurt_from="usdt-commercial",
            blurt_amount=str(units),
            memo=f"usdt-pay compute {units} GFLOP",
        )
    if product == "upkeep":
        # units = GiB-months; convert to STONE-equivalent amount at 0.1 STONE/GiB-month default for ledger
        stone_amt = str(float(units) * float(os.environ.get("DATA_SALES_UPKEEP_STONE_PER_GIB_MONTH", "0.1")))
        return upkeep.record_upkeep_payment(
            stone_address=stone_address,
            stone_amount=stone_amt,
            payment_ref=synthetic,
            bytes_assessed=int(units * 1024 * 1024 * 1024),
            memo=f"usdt-pay upkeep {units} GiB·month",
            source="usdt-commercial",
        )
    raise ValueError("unsupported product for mesh credit")


@app.route("/api/data-sales/claim", methods=["POST"])
def api_data_sales_claim():
    """Claim STONE payment → mesh data credits for a STONE address."""
    payload = request.get_json(silent=True) or {}
    try:
        from chain_mesh import stone_data_payments as sdp

        result = sdp.claim_payment(
            txid=str(payload.get("txid") or ""),
            stone_address=str(payload.get("stone_address") or ""),
            product=str(payload.get("product") or ""),
            job_id=str(payload.get("job_id") or ""),
            referral_code=str(payload.get("referral_code") or payload.get("ref") or ""),
        )
        return jsonify(result)
    except Exception as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/status")
def api_convergence_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_status_payload())


@app.route("/api/convergence/condenser/embed")
def api_convergence_condenser_embed():
    import chain_mesh.api as cm

    payload = {
        "post_id": request.args.get("post_id") or request.args.get("permlink") or "",
        "author": request.args.get("author") or "",
        "title": request.args.get("title") or "",
        "permlink": request.args.get("permlink") or "",
        "asset_key": request.args.get("asset_key") or "",
        "asset_keys": [k.strip() for k in (request.args.get("asset_keys") or "").split(",") if k.strip()],
    }
    result = cm.convergence_condenser_embed_payload(payload)
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)


@app.route("/api/convergence/condenser/offline/status")
def api_convergence_condenser_offline_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_condenser_offline_status_payload())


@app.route("/api/convergence/condenser/offline/feed")
def api_convergence_condenser_offline_feed():
    import chain_mesh.api as cm

    try:
        limit = int(request.args.get("limit") or 40)
    except (TypeError, ValueError):
        limit = 40
    return jsonify(
        cm.convergence_condenser_offline_feed_payload(
            author=(request.args.get("author") or "").strip(),
            limit=limit,
        )
    )


@app.route("/api/convergence/condenser/offline/post")
def api_convergence_condenser_offline_post():
    import chain_mesh.api as cm

    result = cm.convergence_condenser_offline_post_payload(
        author=(request.args.get("author") or "").strip(),
        post_id=(request.args.get("post_id") or request.args.get("permlink") or "").strip(),
    )
    if not result.get("ok"):
        return jsonify(result), 404
    return jsonify(result)


@app.route("/api/convergence/condenser/offline/index", methods=["POST"])
def api_convergence_condenser_offline_index():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    sync_blurt = payload.get("sync_blurt", True) not in (False, "0", 0)
    return jsonify(cm.convergence_condenser_offline_index_payload(sync_blurt=bool(sync_blurt)))


@app.route("/convergence/offline")
def convergence_offline_feed_page():
    from chain_mesh import condenser_offline as coff

    return coff.feed_page_html()


@app.route("/convergence/offline/<author>/<post_id>")
def convergence_offline_post_page(author: str, post_id: str):
    from chain_mesh import condenser_offline as coff

    return coff.post_page_html(author=author, post_id=post_id)


@app.route("/convergence/embed/<author>/<post_id>")
def convergence_embed_page(author: str, post_id: str):
    import chain_mesh.api as cm

    payload = {
        "post_id": post_id,
        "author": author,
        "asset_keys": [k.strip() for k in (request.args.get("asset_keys") or "").split(",") if k.strip()],
        "title": request.args.get("title") or "",
    }
    result = cm.convergence_condenser_embed_payload(payload)
    if not result.get("ok"):
        return result.get("error", "embed failed"), 404
    return render_template("convergence_embed.html", page_html=result.get("page_html") or "")


@app.route("/api/convergence/provenance/anchor", methods=["GET", "POST"])
def api_convergence_provenance_anchor():
    import chain_mesh.api as cm

    if request.method == "GET":
        payload = {
            "author": request.args.get("author") or "",
            "asset_key": request.args.get("asset_key") or "",
            "content_sha256": request.args.get("content_sha256") or "",
            "title": request.args.get("title") or "",
            "device_id": request.args.get("device_id") or "",
            "witness_capsule_id": request.args.get("witness_capsule_id") or "",
            "provenance_id": request.args.get("provenance_id") or "",
            "filename": request.args.get("filename") or "",
        }
        captured = request.args.get("captured_at")
        if captured:
            try:
                payload["captured_at"] = int(captured)
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "invalid captured_at"}), 400
    else:
        payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_provenance_anchor_payload(payload))
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/provenance/verify")
def api_convergence_provenance_verify():
    import chain_mesh.api as cm

    return jsonify(
        cm.convergence_provenance_verify_payload(
            asset_key=(request.args.get("asset_key") or "").strip(),
            provenance_id=(request.args.get("provenance_id") or "").strip(),
            content_sha256=(request.args.get("content_sha256") or "").strip(),
        )
    )


@app.route("/api/convergence/provenance/sync", methods=["POST"])
def api_convergence_provenance_sync():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_provenance_sync_payload())


@app.route("/api/convergence/agent/register", methods=["GET", "POST"])
def api_convergence_agent_register():
    import chain_mesh.api as cm

    if request.method == "GET":
        payload = {
            "blurt_account": request.args.get("blurt_account") or request.args.get("blurt_author") or request.args.get("author") or "",
            "stone_address": request.args.get("stone_address") or "",
            "agent_id": request.args.get("agent_id") or "",
            "display_name": request.args.get("display_name") or "",
            "pubkey_hint": request.args.get("pubkey_hint") or "",
            "capabilities": [
                c.strip()
                for c in (request.args.get("capabilities") or "").split(",")
                if c.strip()
            ],
        }
    else:
        payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_agent_register_payload(payload))
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/agent/verify")
def api_convergence_agent_verify():
    import chain_mesh.api as cm

    return jsonify(
        cm.convergence_agent_verify_payload(
            agent_id=(request.args.get("agent_id") or "").strip(),
            blurt_account=(request.args.get("blurt_account") or request.args.get("blurt_author") or request.args.get("author") or "").strip(),
        )
    )


@app.route("/api/convergence/agent/sync", methods=["POST"])
def api_convergence_agent_sync():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_agent_sync_payload())


@app.route("/api/convergence/agent/publish-flow", methods=["POST"])
def api_convergence_agent_publish_flow():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_agent_publish_flow_payload(payload))
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/compute/quota")
def api_convergence_compute_quota():
    import chain_mesh.api as cm

    stone = (request.args.get("stone_address") or request.args.get("address") or "").strip()
    if not stone:
        return jsonify({"ok": False, "error": "stone_address required"}), 400
    return jsonify(cm.convergence_compute_quota_payload(stone))


@app.route("/api/convergence/compute/tenant/quota")
def api_convergence_compute_tenant_quota():
    import chain_mesh.api as cm

    return jsonify(
        cm.convergence_compute_tenant_quota_payload(
            tenant_id=str(request.args.get("tenant_id") or ""),
            blurt_account=str(request.args.get("blurt_account") or request.args.get("blurt_author") or request.args.get("author") or ""),
            stone_address=str(request.args.get("stone_address") or ""),
        )
    )


@app.route("/api/convergence/compute/tenant/status")
def api_convergence_compute_tenant_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_compute_tenant_status_payload())


@app.route("/api/convergence/compute/tenant/bind", methods=["POST"])
def api_convergence_compute_tenant_bind():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_compute_tenant_bind_payload(payload))
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/tenant/dashboard")
def api_convergence_tenant_dashboard():
    import chain_mesh.api as cm

    return jsonify(
        cm.convergence_tenant_dashboard_payload(
            tenant_id=str(request.args.get("tenant_id") or ""),
            blurt_account=str(request.args.get("blurt_account") or request.args.get("blurt_author") or request.args.get("author") or ""),
            stone_address=str(request.args.get("stone_address") or ""),
        )
    )


@app.route("/api/convergence/tenant/status")
def api_convergence_tenant_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_status_payload())


@app.route("/api/convergence/tenant/bind", methods=["POST"])
def api_convergence_tenant_bind():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_tenant_bind_payload(payload))
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/tenant/fleet/status")
def api_convergence_tenant_fleet_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_fleet_status_payload())


@app.route("/api/convergence/tenant/fleet/snapshots")
def api_convergence_tenant_fleet_snapshots():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_fleet_snapshots_payload())


@app.route("/api/convergence/tenant/fleet/sign/status")
def api_convergence_tenant_fleet_sign_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_fleet_sign_status_payload())


@app.route("/convergence/tenant")
def convergence_tenant_dashboard_page():
    import chain_mesh.api as cm

    return cm.convergence_tenant_dashboard_page_payload()


@app.route("/api/convergence/tenant/fleet/quorum/status")
def api_convergence_tenant_fleet_quorum_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_fleet_quorum_status_payload())


@app.route("/api/convergence/tenant/fleet/quorum/snapshots")
def api_convergence_tenant_fleet_quorum_snapshots():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_fleet_quorum_snapshots_payload())


@app.route("/api/convergence/tenant/broadcast", methods=["POST"])
def api_convergence_tenant_broadcast():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_tenant_broadcast_payload(payload))
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/tenant/broadcast/queue")
def api_convergence_tenant_broadcast_queue():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_broadcast_queue_payload())


@app.route("/api/convergence/tenant/broadcast/status")
def api_convergence_tenant_broadcast_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_broadcast_status_payload())


@app.route("/api/convergence/tenant/sync", methods=["POST"])
def api_convergence_tenant_sync():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_sync_payload())


@app.route("/api/convergence/tenant/submit/status")
def api_convergence_tenant_submit_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_submit_status_payload())


@app.route("/api/convergence/tenant/submit/check")
def api_convergence_tenant_submit_check():
    import chain_mesh.api as cm

    return jsonify(
        cm.convergence_tenant_submit_check_payload(
            tenant_id=str(request.args.get("tenant_id") or ""),
            blurt_account=str(request.args.get("blurt_account") or request.args.get("blurt_author") or request.args.get("author") or ""),
            stone_address=str(request.args.get("stone_address") or ""),
        )
    )


@app.route("/api/convergence/tenant/quorum/author")
def api_convergence_tenant_quorum_author():
    import chain_mesh.api as cm

    return jsonify(
        cm.convergence_tenant_quorum_author_payload(
            tenant_id=str(request.args.get("tenant_id") or ""),
            blurt_account=str(request.args.get("blurt_account") or request.args.get("blurt_author") or request.args.get("author") or ""),
        )
    )


@app.route("/api/convergence/tenant/npu/bind", methods=["POST"])
def api_convergence_tenant_npu_bind():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_tenant_npu_bind_payload(payload))
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/tenant/npu/status")
def api_convergence_tenant_npu_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_npu_status_payload())


@app.route("/api/convergence/tenant/npu/resolve")
def api_convergence_tenant_npu_resolve():
    import chain_mesh.api as cm

    return jsonify(
        cm.convergence_tenant_npu_resolve_payload(
            tenant_id=str(request.args.get("tenant_id") or ""),
            blurt_account=str(request.args.get("blurt_account") or request.args.get("blurt_author") or request.args.get("author") or ""),
            runtime=str(request.args.get("runtime") or ""),
        )
    )


@app.route("/api/convergence/tenant/npu/probe", methods=["POST"])
def api_convergence_tenant_npu_probe():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    return jsonify(cm.convergence_tenant_npu_probe_payload(payload))


@app.route("/api/convergence/tenant/ai/route/status")
def api_convergence_tenant_ai_route_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_ai_route_status_payload())


@app.route("/api/convergence/tenant/ai/route/resolve")
def api_convergence_tenant_ai_route_resolve():
    import chain_mesh.api as cm

    return jsonify(
        cm.convergence_tenant_ai_route_resolve_payload(
            tenant_id=str(request.args.get("tenant_id") or ""),
            blurt_account=str(request.args.get("blurt_account") or request.args.get("blurt_author") or request.args.get("author") or ""),
            runtime=str(request.args.get("runtime") or ""),
        )
    )


@app.route("/api/convergence/tenant/manifest/gossip/status")
def api_convergence_tenant_manifest_gossip_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_manifest_gossip_status_payload())


@app.route("/api/convergence/tenant/manifest/gossip/snapshots")
def api_convergence_tenant_manifest_gossip_snapshots():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_manifest_gossip_snapshots_payload())


@app.route("/api/convergence/tenant/route/ledger/status")
def api_convergence_tenant_route_ledger_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_route_ledger_status_payload())


@app.route("/api/convergence/tenant/route/ledger/assignments")
def api_convergence_tenant_route_ledger_assignments():
    import chain_mesh.api as cm

    return jsonify(
        cm.convergence_tenant_route_ledger_assignments_payload(
            tenant_id=str(request.args.get("tenant_id") or ""),
            blurt_account=str(request.args.get("blurt_account") or request.args.get("blurt_author") or request.args.get("author") or ""),
            limit=int(request.args.get("limit") or 20),
        )
    )


@app.route("/api/convergence/tenant/upkeep/status")
def api_convergence_tenant_upkeep_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_upkeep_status_payload())


@app.route("/api/convergence/tenant/upkeep/run", methods=["POST"])
def api_convergence_tenant_upkeep_run():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_upkeep_run_payload())


@app.route("/api/convergence/tenant/planetary/status")
def api_convergence_tenant_planetary_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_planetary_status_payload())


@app.route("/api/convergence/tenant/planetary/snapshots")
def api_convergence_tenant_planetary_snapshots():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_planetary_snapshots_payload())


@app.route("/api/convergence/tenant/sovereign/status")
def api_convergence_tenant_sovereign_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_tenant_sovereign_status_payload())


@app.route("/api/convergence/tenant/sovereign/reconcile", methods=["POST"])
def api_convergence_tenant_sovereign_reconcile():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    force = str(payload.get("force_quorum_apply") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    return jsonify(cm.convergence_tenant_sovereign_reconcile_payload(force_quorum_apply=force))


@app.route("/api/convergence/compute/job/status")
def api_convergence_compute_job_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_compute_job_status_payload())


@app.route("/api/convergence/compute/jobs")
def api_convergence_compute_jobs():
    import chain_mesh.api as cm

    limit = int(request.args.get("limit") or 30)
    return jsonify(
        cm.convergence_compute_jobs_payload(
            stone_address=(request.args.get("stone_address") or "").strip(),
            status=(request.args.get("status") or "").strip(),
            limit=limit,
        )
    )


@app.route("/api/convergence/compute/job/submit", methods=["POST"])
def api_convergence_compute_job_submit():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_compute_job_submit_payload(payload))
    except PermissionError as exc:
        return _api_error(exc, 403)
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/compute/job/verify")
def api_convergence_compute_job_verify():
    import chain_mesh.api as cm

    return jsonify(
        cm.convergence_compute_job_verify_payload(
            job_id=(request.args.get("job_id") or "").strip(),
            stone_address=(request.args.get("stone_address") or "").strip(),
        )
    )


@app.route("/api/convergence/compute/job/sync", methods=["POST"])
def api_convergence_compute_job_sync():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_compute_job_sync_payload())


@app.route("/api/convergence/bandwidth/quota")
def api_convergence_bandwidth_quota():
    import chain_mesh.api as cm

    stone = (request.args.get("stone_address") or request.args.get("address") or "").strip()
    if not stone:
        return jsonify({"ok": False, "error": "stone_address required"}), 400
    return jsonify(cm.convergence_bandwidth_quota_payload(stone))


@app.route("/api/convergence/bandwidth/tenant/quota")
def api_convergence_bandwidth_tenant_quota():
    import chain_mesh.api as cm

    return jsonify(
        cm.convergence_bandwidth_tenant_quota_payload(
            tenant_id=str(request.args.get("tenant_id") or ""),
            blurt_account=str(request.args.get("blurt_account") or request.args.get("blurt_author") or request.args.get("author") or ""),
            stone_address=str(request.args.get("stone_address") or ""),
        )
    )


@app.route("/api/convergence/bandwidth/tenant/status")
def api_convergence_bandwidth_tenant_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_bandwidth_tenant_status_payload())


@app.route("/api/convergence/bandwidth/tenant/bind", methods=["POST"])
def api_convergence_bandwidth_tenant_bind():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_bandwidth_tenant_bind_payload(payload))
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/storage/quota")
def api_convergence_storage_quota():
    import chain_mesh.api as cm

    stone = (request.args.get("stone_address") or request.args.get("address") or "").strip()
    if not stone:
        return jsonify({"ok": False, "error": "stone_address required"}), 400
    return jsonify(cm.convergence_storage_quota_payload(stone))


@app.route("/api/convergence/storage/tenant/quota")
def api_convergence_storage_tenant_quota():
    import chain_mesh.api as cm

    return jsonify(
        cm.convergence_storage_tenant_quota_payload(
            tenant_id=str(request.args.get("tenant_id") or ""),
            blurt_account=str(request.args.get("blurt_account") or request.args.get("blurt_author") or request.args.get("author") or ""),
            stone_address=str(request.args.get("stone_address") or ""),
        )
    )


@app.route("/api/convergence/storage/tenant/status")
def api_convergence_storage_tenant_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_storage_tenant_status_payload())


@app.route("/api/convergence/storage/tenant/bind", methods=["POST"])
def api_convergence_storage_tenant_bind():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_storage_tenant_bind_payload(payload))
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/depin/quota")
def api_convergence_depin_quota():
    import chain_mesh.api as cm

    stone = (request.args.get("stone_address") or request.args.get("address") or "").strip()
    if not stone:
        return jsonify({"ok": False, "error": "stone_address required"}), 400
    return jsonify(cm.convergence_depin_quota_payload(stone))


@app.route("/api/convergence/depin/sync", methods=["POST"])
def api_convergence_depin_sync():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_depin_sync_payload())


@app.route("/api/convergence/dtn/status")
def api_convergence_dtn_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_dtn_status_payload())


@app.route("/api/convergence/dtn/export", methods=["GET", "POST"])
def api_convergence_dtn_export():
    import chain_mesh.api as cm

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
    else:
        payload = {
            "node_id": request.args.get("node_id") or "",
            "region": request.args.get("region") or "",
            "stone_address": request.args.get("stone_address") or "",
            "blurt_account": request.args.get("blurt_account") or request.args.get("blurt_author") or request.args.get("author") or "",
            "tenant_id": request.args.get("tenant_id") or "",
            "include_chunks": request.args.get("include_chunks", "1") not in ("0", "false", "no"),
            "queue_forward": request.args.get("queue_forward") in ("1", "true", "yes"),
        }
        since = request.args.get("since")
        if since:
            try:
                payload["since"] = int(since)
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "invalid since"}), 400
    try:
        return jsonify(
            cm.convergence_dtn_export_payload(
                node_id=str(payload.get("node_id") or ""),
                since=payload.get("since"),
                include_chunks=bool(payload.get("include_chunks", True)),
                region=str(payload.get("region") or ""),
                queue_forward=bool(payload.get("queue_forward")),
                stone_address=str(payload.get("stone_address") or ""),
                blurt_account=str(payload.get("blurt_account") or payload.get("blurt_author") or payload.get("author") or ""),
                tenant_id=str(payload.get("tenant_id") or ""),
            )
        )
    except PermissionError as exc:
        return _api_error(exc, 403)
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/dtn/export/download")
def api_convergence_dtn_export_download():
    import chain_mesh.api as cm
    from flask import Response

    since = request.args.get("since")
    since_val = None
    if since:
        try:
            since_val = int(since)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "invalid since"}), 400
    try:
        blob, filename, _meta = cm.convergence_dtn_build_zip(
            node_id=(request.args.get("node_id") or "").strip(),
            since=since_val,
            include_chunks=request.args.get("include_chunks", "1") not in ("0", "false", "no"),
            region=(request.args.get("region") or "").strip(),
            stone_address=(request.args.get("stone_address") or "").strip(),
            blurt_account=(request.args.get("blurt_account") or request.args.get("blurt_author") or request.args.get("author") or "").strip(),
            tenant_id=(request.args.get("tenant_id") or "").strip(),
        )
    except PermissionError as exc:
        return _api_error(exc, 403)
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)
    return Response(
        blob,
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/api/convergence/dtn/import", methods=["POST"])
def api_convergence_dtn_import():
    import chain_mesh.api as cm

    upload = request.files.get("bundle_file")
    if upload:
        try:
            from chain_mesh.dtn_sync import import_dtn_bundle

            return jsonify(import_dtn_bundle(upload.read()))
        except (ValueError, TypeError) as exc:
            return _api_error(exc, 400)
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_dtn_import_payload(payload))
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/dtn/forward/pending")
def api_convergence_dtn_forward_pending():
    import chain_mesh.api as cm

    try:
        limit = int(request.args.get("limit") or 20)
    except (TypeError, ValueError):
        limit = 20
    return jsonify(cm.convergence_dtn_forward_pending_payload(limit=limit))


@app.route("/api/convergence/dtn/forward/submit", methods=["POST"])
def api_convergence_dtn_forward_submit():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_dtn_forward_submit_payload(payload))
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/dtn/forward/flush", methods=["POST"])
def api_convergence_dtn_forward_flush():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        limit = int(payload.get("limit") or request.args.get("limit") or 3)
    except (TypeError, ValueError):
        limit = 3
    force = payload.get("force") in (True, "1", 1) or request.args.get("force") in ("1", "true", "yes")
    return jsonify(
        cm.convergence_dtn_forward_flush_payload(
            upstream_url=str(payload.get("upstream_url") or request.args.get("upstream_url") or ""),
            limit=limit,
            force=bool(force),
        )
    )


@app.route("/api/convergence/dtn/flush-window")
def api_convergence_dtn_flush_window():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_dtn_flush_window_payload())


@app.route("/api/convergence/dtn/compact", methods=["POST"])
def api_convergence_dtn_compact():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_dtn_compact_payload())


@app.route("/api/convergence/dtn/upkeep", methods=["POST"])
def api_convergence_dtn_upkeep():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    force = payload.get("force") in (True, "1", 1) or request.args.get("force") in ("1", "true", "yes")
    return jsonify(cm.convergence_dtn_upkeep_payload(force_flush=bool(force)))


@app.route("/api/convergence/dtn/peers")
def api_convergence_dtn_peers():
    import chain_mesh.api as cm

    try:
        limit = int(request.args.get("limit") or 30)
    except (TypeError, ValueError):
        limit = 30
    return jsonify(cm.convergence_dtn_peers_payload(limit=limit))


@app.route("/api/convergence/dtn/peers/discover", methods=["POST"])
def api_convergence_dtn_peers_discover():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_dtn_peers_discover_payload())


@app.route("/api/convergence/dtn/peers/register", methods=["POST"])
def api_convergence_dtn_peers_register():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_dtn_peer_register_payload(payload))
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/dtn/replication/heal", methods=["POST"])
def api_convergence_dtn_replication_heal():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(
            cm.convergence_dtn_replication_heal_payload(
                region=str(payload.get("region") or request.args.get("region") or ""),
                limit=int(payload.get("limit") or request.args.get("limit") or 10),
            )
        )
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/dtn/mdns/status")
def api_convergence_dtn_mdns_status():
    import chain_mesh.api as cm

    include = request.args.get("browse") in ("1", "true", "yes")
    return jsonify(cm.convergence_dtn_mdns_status_payload(include_browse=include))


@app.route("/api/convergence/dtn/mdns/register", methods=["POST"])
def api_convergence_dtn_mdns_register():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_dtn_mdns_register_payload(payload))
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/dtn/mdns/browse", methods=["POST"])
def api_convergence_dtn_mdns_browse():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    register = payload.get("register", True) not in (False, "0", 0)
    return jsonify(cm.convergence_dtn_mdns_browse_payload(register=register))


@app.route("/api/convergence/dtn/replication/status")
def api_convergence_dtn_replication_status():
    import chain_mesh.api as cm

    return jsonify(
        cm.convergence_dtn_replication_status_payload(
            region=(request.args.get("region") or "").strip()
        )
    )


@app.route("/api/convergence/dtn/replication/check", methods=["POST"])
def api_convergence_dtn_replication_check():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(
            cm.convergence_dtn_replication_check_payload(
                region=str(payload.get("region") or ""),
                chunk_hashes=payload.get("chunk_hashes"),
                quorum_n=int(payload.get("quorum_n") or 0),
                quorum_m=int(payload.get("quorum_m") or 0),
            )
        )
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/dtn/alerts")
def api_convergence_dtn_alerts():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_dtn_alerts_payload())


@app.route("/api/convergence/dtn/tls/status")
def api_convergence_dtn_tls_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_dtn_tls_status_payload())


@app.route("/api/convergence/dtn/gossip/status")
def api_convergence_dtn_gossip_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_dtn_gossip_status_payload())


@app.route("/api/convergence/dtn/gossip/exchange", methods=["POST"])
def api_convergence_dtn_gossip_exchange():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_dtn_gossip_exchange_payload(payload))
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/dtn/gossip/round", methods=["POST"])
def api_convergence_dtn_gossip_round():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        limit = int(payload.get("limit") or request.args.get("limit") or 0)
    except (TypeError, ValueError):
        limit = 0
    return jsonify(cm.convergence_dtn_gossip_round_payload(limit=limit))


@app.route("/api/convergence/dtn/uplink/status")
@app.route("/api/convergence/dtn/starlink/status")
def api_convergence_dtn_starlink_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_dtn_starlink_status_payload())


@app.route("/api/convergence/dtn/uplink/probe", methods=["GET", "POST"])
@app.route("/api/convergence/dtn/starlink/probe", methods=["GET", "POST"])
def api_convergence_dtn_starlink_probe():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    url = str(payload.get("url") or request.args.get("url") or "").strip()
    return jsonify(cm.convergence_dtn_starlink_probe_payload(url=url))


@app.route("/api/convergence/dtn/uplink/handoff", methods=["POST"])
@app.route("/api/convergence/dtn/starlink/handoff", methods=["POST"])
def api_convergence_dtn_starlink_handoff():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    force = payload.get("force") in (True, "1", 1) or request.args.get("force") in ("1", "true", "yes")
    try:
        limit = int(payload.get("limit") or request.args.get("limit") or 0)
    except (TypeError, ValueError):
        limit = 0
    return jsonify(cm.convergence_dtn_starlink_handoff_payload(force=bool(force), limit=limit))


@app.route("/api/convergence/dtn/planetary/status")
def api_convergence_dtn_planetary_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_dtn_planetary_status_payload())


@app.route("/api/convergence/dtn/planetary/regions")
def api_convergence_dtn_planetary_regions():
    import chain_mesh.api as cm

    try:
        limit = int(request.args.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    return jsonify(cm.convergence_dtn_planetary_regions_payload(limit=limit))


@app.route("/api/convergence/dtn/planetary/heal", methods=["POST"])
def api_convergence_dtn_planetary_heal():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    regions = payload.get("regions")
    if isinstance(regions, str):
        regions = [r.strip() for r in regions.split(",") if r.strip()]
    try:
        limit = int(payload.get("limit") or request.args.get("limit") or 0)
    except (TypeError, ValueError):
        limit = 0
    return jsonify(cm.convergence_dtn_planetary_heal_payload(limit=limit, regions=regions))


@app.route("/api/convergence/dtn/planetary/exchange", methods=["POST"])
def api_convergence_dtn_planetary_exchange():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_dtn_planetary_exchange_payload(payload))
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/dtn/planetary/round", methods=["POST"])
def api_convergence_dtn_planetary_round():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        limit = int(payload.get("limit") or request.args.get("limit") or 0)
    except (TypeError, ValueError):
        limit = 0
    return jsonify(cm.convergence_dtn_planetary_round_payload(limit=limit))


@app.route("/api/convergence/bridge/status")
def api_convergence_bridge_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_bridge_status_payload())


@app.route("/api/convergence/bridge/quote")
def api_convergence_bridge_quote():
    import chain_mesh.api as cm

    try:
        return jsonify(
            cm.convergence_bridge_quote_payload(
                direction=str(request.args.get("direction") or ""),
                amount=request.args.get("amount") or request.args.get("blurt_amount") or request.args.get("stone_amount"),
                stone_address=str(request.args.get("stone_address") or ""),
                blurt_account=str(request.args.get("blurt_account") or request.args.get("blurt_author") or request.args.get("author") or ""),
            )
        )
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/bridge/initiate", methods=["POST"])
def api_convergence_bridge_initiate():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_bridge_initiate_payload(payload))
    except (ValueError, TypeError, RuntimeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/bridge/claim", methods=["POST"])
def api_convergence_bridge_claim():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(
            cm.convergence_bridge_claim_payload(
                swap_id=str(payload.get("swap_id") or request.args.get("swap_id") or ""),
                preimage=str(payload.get("preimage") or request.args.get("preimage") or ""),
            )
        )
    except (ValueError, TypeError, RuntimeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/bridge/attest", methods=["POST"])
def api_convergence_bridge_attest():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(
            cm.convergence_bridge_attest_payload(
                swap_id=str(payload.get("swap_id") or ""),
                stone_txid=str(payload.get("stone_txid") or ""),
            )
        )
    except (ValueError, TypeError, RuntimeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/bridge/intents")
def api_convergence_bridge_intents():
    import chain_mesh.api as cm

    try:
        limit = int(request.args.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    return jsonify(
        cm.convergence_bridge_intents_payload(
            status=str(request.args.get("status") or ""),
            limit=limit,
        )
    )


@app.route("/api/convergence/bridge/sync", methods=["POST"])
def api_convergence_bridge_sync():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_bridge_sync_payload())


@app.route("/api/convergence/ai/status")
def api_convergence_ai_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_ai_status_payload())


@app.route("/api/convergence/ai/providers")
def api_convergence_ai_providers():
    import chain_mesh.api as cm

    try:
        limit = int(request.args.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    return jsonify(
        cm.convergence_ai_providers_payload(
            runtime=str(request.args.get("runtime") or ""),
            region=str(request.args.get("region") or ""),
            limit=limit,
        )
    )


@app.route("/api/convergence/ai/providers/register", methods=["POST"])
def api_convergence_ai_register():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_ai_register_payload(payload))
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/ai/route", methods=["POST"])
def api_convergence_ai_route():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    force = payload.get("force") in (True, "1", 1) or request.args.get("force") in ("1", "true", "yes")
    try:
        return jsonify(
            cm.convergence_ai_route_payload(
                job_id=str(payload.get("job_id") or request.args.get("job_id") or ""),
                force=bool(force),
            )
        )
    except (ValueError, TypeError, PermissionError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/ai/submit", methods=["POST"])
def api_convergence_ai_submit():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_ai_submit_payload(payload))
    except (ValueError, TypeError, PermissionError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/ai/discover", methods=["POST"])
def api_convergence_ai_discover():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_ai_discover_payload())


@app.route("/api/convergence/ai/provider/health")
def api_convergence_ai_provider_health():
    import chain_mesh.api as cm

    return jsonify(
        cm.convergence_ai_provider_health_payload(
            provider_id=str(request.args.get("provider_id") or "")
        )
    )


@app.route("/api/convergence/ai/dispatch", methods=["POST"])
def api_convergence_ai_dispatch():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_ai_dispatch_payload(payload))
    except (ValueError, TypeError, PermissionError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/ai/callback", methods=["POST"])
def api_convergence_ai_callback():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_ai_callback_payload(payload))
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/ai/npu/status")
def api_convergence_ai_npu_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_ai_npu_status_payload())


@app.route("/api/convergence/ai/gossip/sign/status")
def api_convergence_ai_gossip_sign_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_ai_gossip_sign_status_payload())


@app.route("/api/convergence/ai/provider/sync", methods=["POST"])
def api_convergence_ai_provider_sync():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_ai_provider_sync_payload())


@app.route("/api/convergence/ai/provider/broadcast", methods=["POST"])
def api_convergence_ai_provider_broadcast():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_ai_provider_broadcast_payload(payload))
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/ai/provider/broadcast/queue")
def api_convergence_ai_provider_broadcast_queue():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_ai_provider_broadcast_queue_payload())


@app.route("/api/convergence/spatial/manifest", methods=["GET", "POST"])
def api_convergence_spatial_manifest():
    import chain_mesh.api as cm

    if request.method == "GET":
        payload = {
            "scene_id": request.args.get("scene_id") or "",
            "author": request.args.get("author") or "",
            "post_id": request.args.get("post_id") or "",
            "title": request.args.get("title") or "",
            "filename": request.args.get("filename") or "",
            "model_format": request.args.get("model_format") or "glb",
            "placement": request.args.get("placement") or "surface",
            "provenance_id": request.args.get("provenance_id") or "",
        }
        if request.args.get("lat") and request.args.get("lon"):
            try:
                payload["geo"] = {
                    "lat": float(request.args.get("lat")),
                    "lon": float(request.args.get("lon")),
                    "alt_m": float(request.args.get("alt_m") or 0),
                    "heading_deg": float(request.args.get("heading_deg") or 0),
                }
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "invalid geo coordinates"}), 400
    else:
        payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_spatial_manifest_payload(payload))
    except (ValueError, TypeError) as exc:
        return _api_error(exc, 400)


@app.route("/api/convergence/spatial/embed")
def api_convergence_spatial_embed():
    import chain_mesh.api as cm

    payload = {
        "scene_id": request.args.get("scene_id") or "",
        "author": request.args.get("author") or "",
        "post_id": request.args.get("post_id") or "",
        "title": request.args.get("title") or "",
    }
    result = cm.convergence_spatial_embed_payload(payload)
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)


@app.route("/convergence/spatial/<author>/<scene_id>")
def convergence_spatial_page(author: str, scene_id: str):
    import chain_mesh.api as cm

    result = cm.convergence_spatial_embed_payload(
        {"scene_id": scene_id, "author": author, "title": request.args.get("title") or ""}
    )
    if not result.get("ok"):
        return result.get("error", "spatial embed failed"), 404
    return render_template("convergence_embed.html", page_html=result.get("page_html") or "")


@app.route("/api/convergence/spatial/overlay")
def api_convergence_spatial_overlay():
    import chain_mesh.api as cm

    lat = lon = None
    if request.args.get("lat") and request.args.get("lon"):
        try:
            lat = float(request.args.get("lat"))
            lon = float(request.args.get("lon"))
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "invalid lat/lon"}), 400
    try:
        radius = float(request.args.get("radius_m") or 500)
        limit = int(request.args.get("limit") or 20)
    except (TypeError, ValueError):
        radius, limit = 500.0, 20
    return jsonify(
        cm.convergence_spatial_overlay_payload(
            lat=lat,
            lon=lon,
            radius_m=radius,
            author=(request.args.get("author") or "").strip(),
            post_id=(request.args.get("post_id") or "").strip(),
            scene_id=(request.args.get("scene_id") or "").strip(),
            limit=limit,
        )
    )


@app.route("/api/convergence/spatial/sync", methods=["POST"])
def api_convergence_spatial_sync():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_spatial_sync_payload())


@app.route("/api/quasar/status")
def api_quasar_status():
    try:
        import bloodstone_quasar_api as qapi

        return jsonify(qapi.status_payload(rpc))
    except Exception as exc:
        return _api_error(exc, 503)


@app.route("/api/quasar/witness/submit", methods=["POST"])
def api_quasar_witness_submit():
    import bloodstone_quasar_api as qapi

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(qapi.witness_submit(payload))
    except ValueError as exc:
        return _api_error(exc, 400)


@app.route("/api/quasar/witness/capsules")
def api_quasar_witness_capsules():
    import bloodstone_quasar_api as qapi

    tip_hash = (request.args.get("tip_hash") or "").strip()
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    return jsonify(qapi.witness_list(tip_hash=tip_hash, limit=limit, offset=offset))


@app.route("/api/quasar/lan-echo", methods=["POST"])
def api_quasar_lan_echo():
    import bloodstone_quasar_api as qapi

    payload = request.get_json(silent=True) or {}
    public_ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()
    try:
        return jsonify(qapi.lan_echo_submit(payload, public_ip=public_ip, rpc=rpc))
    except ValueError as exc:
        return _api_error(exc, 400)


@app.route("/api/quasar/lan-echo/status")
def api_quasar_lan_echo_status():
    import bloodstone_quasar_api as qapi

    public_ip = (request.args.get("public_ip") or "").strip()
    try:
        return jsonify(qapi.lan_echo_status_payload(public_ip=public_ip, rpc=rpc))
    except Exception as exc:
        return _api_error(exc, 503)


@app.route("/api/quasar/alerts")
def api_quasar_alerts():
    import bloodstone_quasar_api as qapi

    try:
        return jsonify(qapi.alerts_payload(rpc))
    except Exception as exc:
        return _api_error(exc, 503)


@app.route("/api/quasar/braid-index")
def api_quasar_braid_index():
    import bloodstone_quasar_api as qapi

    sync = (request.args.get("sync") or "").strip().lower() in ("1", "true", "yes")
    try:
        return jsonify(qapi.braid_index_payload(sync=sync, rpc=rpc))
    except Exception as exc:
        return _api_error(exc, 503)


@app.route("/api/quasar/enforcement/check", methods=["POST"])
def api_quasar_enforcement_check():
    import bloodstone_quasar_api as qapi

    payload = request.get_json(silent=True) or {}
    amount = float(payload.get("amount_stone") or payload.get("amount") or 0)
    try:
        return jsonify(qapi.enforcement_check(amount, rpc))
    except Exception as exc:
        return _api_error(exc, 503)


@app.route("/api/quasar/activation")
def api_quasar_activation():
    import bloodstone_quasar_api as qapi

    return jsonify(qapi.activation_payload())


@app.route("/api/quasar/signaling")
def api_quasar_signaling():
    import bloodstone_quasar_api as qapi

    try:
        return jsonify(qapi.signaling_payload(rpc))
    except Exception as exc:
        return _api_error(exc, 503)


@app.route("/api/quasar/fork-rehearsal")
def api_quasar_fork_rehearsal():
    import bloodstone_quasar_api as qapi

    persist = (request.args.get("persist") or "").strip().lower() in ("1", "true", "yes")
    try:
        return jsonify(qapi.fork_rehearsal_payload(rpc, persist=persist))
    except Exception as exc:
        return _api_error(exc, 503)


@app.route("/api/quasar/confirmations")
def api_quasar_confirmations():
    import bloodstone_quasar_api as qapi

    try:
        return jsonify(qapi.confirmations_payload(rpc))
    except Exception as exc:
        return _api_error(exc, 503)


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
    _empty = {
        "ok": False,
        "entries": [],
        "loading": True,
        "error": None,
        "total_onchain_stone": None,
        "holders_scanned": None,
        "holders_with_balance": None,
        "estimated_supply_stone": None,
        "indexed_height": None,
    }
    if use_cache:
        return _cached(
            f"rich_list_{limit}",
            float(os.environ.get("PORTAL_RICH_LIST_CACHE_SEC", "600")),
            lambda: bloodstone_rich_list.get_rich_list(limit=limit),
            fallback=_empty,
        )
    return bloodstone_rich_list.get_rich_list(limit=limit)


def _portal_request_client_ip() -> str:
    forwarded = (request.headers.get("X-Forwarded-For") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return (request.remote_addr or "").strip()


def _portal_beta_token() -> str:
    return (
        request.headers.get("X-Bloodstone-Beta-Token")
        or request.args.get("beta_token")
        or ""
    ).strip()


def _portal_lan_ip() -> str:
    return (
        request.headers.get("X-Bloodstone-Lan-Ip")
        or request.args.get("lan_ip")
        or ""
    ).strip()


def _portal_update_release_channel() -> str:
    channel = (request.args.get("channel") or "").strip()
    return bloodstone_beta_codes.resolve_release_channel(
        beta_token=_portal_beta_token(),
        channel=channel,
    )


@app.route("/api/android-miner/update")
def api_android_miner_update():
    channel = _portal_update_release_channel()
    return jsonify(
        bloodstone_downloads.android_miner_update_manifest(
            PUBLIC_ROOT,
            release_channel=channel,
            lan_ip=_portal_lan_ip(),
        )
    )


@app.route("/api/beta/redeem", methods=["POST"])
def api_beta_redeem():
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or "").strip()
    device_id = (payload.get("device_id") or "").strip()
    lan_ip = (payload.get("lan_ip") or "").strip()
    result = bloodstone_beta_codes.redeem_code(
        code,
        device_id=device_id,
        client_ip=_portal_request_client_ip(),
        lan_ip=lan_ip,
    )
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@app.route("/api/beta/status")
def api_beta_status():
    token = _portal_beta_token()
    lan_ip = _portal_lan_ip()
    token_info = (
        bloodstone_beta_codes.get_access_token_info(token) if token else None
    )
    active = bool(token_info and token_info.get("active"))
    lan_key = bloodstone_beta_codes.lan_key_from_ip(lan_ip) if lan_ip else None
    lan_release = (
        bloodstone_beta_codes.get_lan_validated_release(lan_key) if lan_key else None
    )
    return jsonify(
        {
            "ok": True,
            "beta_active": active,
            "release_channel": "beta" if active else "stable",
            "lifetime_unlock": bool(token_info and token_info.get("lifetime_unlock")),
            "code_type": (token_info or {}).get("code_type"),
            "lan_key": lan_key,
            "lan_validated": bool(lan_release),
            "lan_apk_version": (lan_release or {}).get("apk_version"),
            "lan_web_bundle_version": (lan_release or {}).get("web_bundle_version"),
        }
    )


@app.route("/api/beta/validate-lan", methods=["POST"])
def api_beta_validate_lan():
    payload = request.get_json(silent=True) or {}
    token = _portal_beta_token() or str(payload.get("beta_token") or "").strip()
    lan_ip = str(payload.get("lan_ip") or _portal_lan_ip() or "").strip()
    device_id = str(payload.get("device_id") or "").strip()
    beta_apk_version, beta_apk_filename = bloodstone_downloads._resolve_android_apk("beta")
    beta_web_version, beta_web_filename = bloodstone_downloads._resolve_android_web_bundle(
        "beta"
    )
    result = bloodstone_beta_codes.validate_lan_release(
        beta_token=token,
        lan_ip=lan_ip,
        device_id=device_id,
        apk_version=beta_apk_version,
        apk_filename=beta_apk_filename,
        web_bundle_version=beta_web_version,
        web_bundle_filename=beta_web_filename,
    )
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@app.route("/api/desktop-miner/update")
def api_desktop_miner_update():
    channel = _portal_update_release_channel()
    return jsonify(
        bloodstone_downloads.desktop_miner_update_manifest(
            PUBLIC_ROOT, release_channel=channel
        )
    )


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
        return jsonify({"ok": False, "error": _safe_err(exc), "entries": []}), 503


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
    return jsonify(
        {
            "ok": True,
            "service": "portal",
            "version": CONVERGENCE_VERSION,
            "package": f"bloodstone-pi-fleet-convergence-{CONVERGENCE_VERSION}",
        }
    )


@app.route("/version")
@app.route("/api/version")
def api_version():
    """Package / convergence stack version (single source: chain_mesh.__version__)."""
    return jsonify(
        {
            "ok": True,
            "version": CONVERGENCE_VERSION,
            "package": f"bloodstone-pi-fleet-convergence-{CONVERGENCE_VERSION}",
        }
    )


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