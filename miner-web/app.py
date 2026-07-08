#!/usr/bin/env python3
"""Bloodstone web mining dashboard."""

import base64
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from functools import wraps

sys.path.insert(0, "/root")
import bloodstone_time

from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

import bloodstone_branding
import bloodstone_beta_codes
import bloodstone_downloads
import faucet_settings
import installer_branding
import pool_payout_settings
import mining_config
import server_services
import ssh_keys
import merge_mining_info
import node_rpc
import wallet_oauth_settings
from mining_config import MULTI_ALGO_FORK_HEIGHT, YESPOWER_FORK_HEIGHT
from prefix_redirect import prefixed_path, safe_redirect_target  # noqa: E402
from stratum_status import (
    all_pools_status,
    pool_connection_info,
    pools_status_light,
    pools_status_light_fast,
)

SECRETS_PATH = os.environ.get("MINER_WEB_SECRETS", "/root/bloodstone-miner-web/secrets.conf")
CHAIN_OVERVIEW_DISK_CACHE = os.environ.get(
    "CHAIN_OVERVIEW_DISK_CACHE", "/var/lib/bloodstone/chain-overview.json"
)
RECENT_BLOCKS = 15

_POOL_DASH_CACHE_LOCK = threading.Lock()
_POOL_DASH_CACHE: dict = {}
_POOL_DASH_CACHE_LOADER_LOCKS: dict = {}


def _loader_lock(key: str) -> threading.Lock:
    with _POOL_DASH_CACHE_LOCK:
        lock = _POOL_DASH_CACHE_LOADER_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _POOL_DASH_CACHE_LOADER_LOCKS[key] = lock
        return lock


def _cached_value(key: str, ttl_sec: float, loader, *, blocking: bool = True):
    now = time.time()
    with _POOL_DASH_CACHE_LOCK:
        entry = _POOL_DASH_CACHE.get(key)
        if entry and now - entry[0] < ttl_sec:
            return entry[1]
        stale = entry[1] if entry else None

    lock = _loader_lock(key)
    if not lock.acquire(blocking=False):
        if stale is not None:
            return stale
        if not blocking:
            return None
        lock.acquire()

    try:
        with _POOL_DASH_CACHE_LOCK:
            entry = _POOL_DASH_CACHE.get(key)
            if entry and time.time() - entry[0] < ttl_sec:
                return entry[1]
        try:
            data = loader()
        except Exception:
            if stale is not None:
                return stale
            raise
        with _POOL_DASH_CACHE_LOCK:
            _POOL_DASH_CACHE[key] = (time.time(), data)
        return data
    finally:
        lock.release()


def _cached_pool_dashboard(ttl_sec: float, loader):
    return _cached_value("dashboard", ttl_sec, loader)


def _cache_ttl(env_key: str, default: str) -> float:
    return float(os.environ.get(env_key, default))


def _read_chain_overview_disk_cache():
    try:
        with open(CHAIN_OVERVIEW_DISK_CACHE, encoding="utf-8") as fh:
            payload = json.load(fh)
        data = payload.get("data")
        if isinstance(data, dict) and int(data.get("height") or 0) > 0:
            return data
    except Exception:
        pass
    return None


def _write_chain_overview_disk_cache(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(CHAIN_OVERVIEW_DISK_CACHE), exist_ok=True)
        tmp_path = f"{CHAIN_OVERVIEW_DISK_CACHE}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump({"at": time.time(), "data": data}, fh)
        os.replace(tmp_path, CHAIN_OVERVIEW_DISK_CACHE)
    except Exception:
        pass


def _overview_fallback() -> dict:
    disk = _read_chain_overview_disk_cache()
    if disk:
        return disk
    # Jun 2026 relaunch: all algos active from block 1 — don't show "not active yet" while cache loads.
    yespower_live = YESPOWER_FORK_HEIGHT <= 1
    all_algos_live = yespower_live and MULTI_ALGO_FORK_HEIGHT <= 1
    return {
        "info": {"blocks": 0},
        "mining": {"pooledtx": 0, "difficulty": {}},
        "height": 0,
        "all_algos_active": all_algos_live,
        "yespower_active": yespower_live,
        "yespower_fork_height": YESPOWER_FORK_HEIGHT,
        "multi_algo_fork_height": MULTI_ALGO_FORK_HEIGHT,
        "blocks_until_yespower": 0,
        "next_yespower_height": YESPOWER_FORK_HEIGHT if yespower_live else None,
        "blocks_until_yespower_slot": 0,
        "payout_address": "",
    }


def _pools_fallback() -> dict:
    try:
        from stratum_status import pools_status_light_fast

        return pools_status_light_fast()
    except Exception:
        pools = {}
        for key in mining_config.POOLS:
            pools[key] = {
                **pool_connection_info(key),
                "healthy": False,
                "workers": 0,
                "browser_workers": 0,
                "listening": False,
                "process": {"running": False, "processes": [], "count": 0},
            }
        return pools


def ensure_pool_display(pool_key: str, pool: dict) -> dict:
    """Guarantee stratum URL fields even when serving a stale cache fallback."""
    base = pool_connection_info(pool_key)
    out = {**base, **(pool or {})}
    for field in (
        "url",
        "url_tls",
        "example_cmd",
        "share_difficulty",
        "miner_hint",
        "name",
        "algo",
        "port",
        "tls_port",
        "connection_note",
    ):
        if not out.get(field) and base.get(field) is not None:
            out[field] = base[field]
    if not out.get("stratum_host"):
        out["stratum_host"] = base.get("stratum_host")
    if "{ip}" in str(out.get("example_cmd", "")):
        out["example_cmd"] = base["example_cmd"]
    out.setdefault("key", pool_key)
    return out


_WARMING_KEYS: set = set()


def _warm_cached_value(key: str, ttl_sec: float, loader) -> None:
    with _POOL_DASH_CACHE_LOCK:
        if key in _WARMING_KEYS:
            return
        _WARMING_KEYS.add(key)

    def _run() -> None:
        try:
            _cached_value(key, ttl_sec, loader, blocking=True)
        except Exception:
            pass
        finally:
            with _POOL_DASH_CACHE_LOCK:
                _WARMING_KEYS.discard(key)

    threading.Thread(target=_run, daemon=True, name=f"warm-{key}").start()


def _try_cached_value(key: str, ttl_sec: float, loader, fallback):
    now = time.time()
    with _POOL_DASH_CACHE_LOCK:
        entry = _POOL_DASH_CACHE.get(key)
        if entry and now - entry[0] < ttl_sec:
            return entry[1]
    _warm_cached_value(key, ttl_sec, loader)
    return fallback


def _load_chain_overview():
    data = chain_overview()
    _write_chain_overview_disk_cache(data)
    return data


def cached_chain_overview():
    ttl = _cache_ttl("MINER_CHAIN_OVERVIEW_CACHE_SEC", "45")
    overview = _cached_value("chain_overview", ttl, _load_chain_overview, blocking=True)
    if overview:
        return overview
    return _overview_fallback()


def cached_recent_blocks(limit=RECENT_BLOCKS):
    def loader():
        return recent_blocks(limit)

    return _cached_value(
        f"recent_blocks_{limit}",
        _cache_ttl("MINER_RECENT_BLOCKS_CACHE_SEC", "60"),
        loader,
    )


def cached_pools_status():
    return _cached_value(
        "pools_status",
        _cache_ttl("MINER_POOLS_STATUS_CACHE_SEC", "90"),
        all_pools_status,
    )


def cached_pools_status_light():
    return _try_cached_value(
        "pools_status_light",
        _cache_ttl("MINER_POOLS_STATUS_LIGHT_CACHE_SEC", "30"),
        pools_status_light_fast,
        _pools_fallback(),
    )


def _refresh_pools_status_full() -> None:
    """Background refresh with subprocess probes (admin-grade detail)."""
    _warm_cached_value(
        "pools_status_full",
        _cache_ttl("MINER_POOLS_STATUS_CACHE_SEC", "90"),
        pools_status_light,
    )


def _pool_accounting_fallback() -> dict:
    return {"error": "loading", "round_miners": []}


def cached_pool_accounting(pool_key: str) -> dict:
    from stratum_status import (
        neoscrypt_pool_accounting,
        sha256_pool_accounting,
        yespower_pool_accounting,
    )

    loaders = {
        "yespower": yespower_pool_accounting,
        "neoscrypt": neoscrypt_pool_accounting,
        "sha256d": sha256_pool_accounting,
    }
    loader = loaders.get(pool_key)
    if not loader:
        return {}
    return _try_cached_value(
        f"pool_acct_{pool_key}",
        _cache_ttl("MINER_POOL_ACCOUNTING_CACHE_SEC", "60"),
        loader,
        _pool_accounting_fallback(),
    )


def cached_admin_service_sections():
    return _try_cached_value(
        "admin_service_sections",
        _cache_ttl("MINER_ADMIN_SERVICES_CACHE_SEC", "30"),
        server_services.admin_service_sections,
        [],
    )

app = Flask(__name__)
# Chain mesh uploads POST base64 chunks (batch JSON can exceed nginx's 1 MiB default).
app.config["MAX_CONTENT_LENGTH"] = int(
    os.environ.get("BLOODSTONE_MAX_UPLOAD_BYTES", str(16 * 1024 * 1024))
)

from prefix_middleware import apply_prefix  # noqa: E402

apply_prefix(app)

PUBLIC_BASE_URL = os.environ.get(
    "BLOODSTONE_PUBLIC_URL", "https://rodcoinwallet.duckdns.org/mining"
)


def read_secrets_file():
    values = {}
    if os.path.isfile(SECRETS_PATH):
        with open(SECRETS_PATH, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                values[key.strip()] = val.strip()
    return values


def load_secrets():
    values = read_secrets_file()
    app.secret_key = values.get("secret_key") or os.urandom(32).hex()
    app.config["MASTER_CREATOR_CODE_HASH"] = values.get("master_creator_code_hash") or ""
    mesh_token = (
        values.get("chain_mesh_publish_token")
        or os.environ.get("CHAIN_MESH_PUBLISH_TOKEN", "")
    ).strip()
    if mesh_token:
        os.environ["CHAIN_MESH_PUBLISH_TOKEN"] = mesh_token
    app.config["CHAIN_MESH_PUBLISH_TOKEN"] = mesh_token
    return values.get("admin_password_hash")


def _write_secrets_file(values: dict) -> None:
    lines = [f"secret_key={values['secret_key']}\n"]
    if values.get("admin_password_hash"):
        lines.append(f"admin_password_hash={values['admin_password_hash']}\n")
    if values.get("master_creator_code_hash"):
        lines.append(
            f"master_creator_code_hash={values['master_creator_code_hash']}\n"
        )
    if values.get("chain_mesh_publish_token"):
        lines.append(
            f"chain_mesh_publish_token={values['chain_mesh_publish_token']}\n"
        )
    with open(SECRETS_PATH, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
    os.chmod(SECRETS_PATH, 0o600)


def ensure_mesh_publish_token() -> str:
    """Ensure a server-side publish token exists (never exposed on public pages)."""
    token = (app.config.get("CHAIN_MESH_PUBLISH_TOKEN") or "").strip()
    if token:
        return token
    values = read_secrets_file()
    token = (values.get("chain_mesh_publish_token") or "").strip()
    if not token:
        token = secrets.token_hex(32)
        if "secret_key" not in values:
            values["secret_key"] = app.secret_key or secrets.token_hex(32)
        values["chain_mesh_publish_token"] = token
        _write_secrets_file(values)
    os.environ["CHAIN_MESH_PUBLISH_TOKEN"] = token
    app.config["CHAIN_MESH_PUBLISH_TOKEN"] = token
    return token


def save_admin_password_hash(password_hash: str) -> None:
    values = read_secrets_file()
    if "secret_key" not in values:
        values["secret_key"] = secrets.token_hex(32)
    values["admin_password_hash"] = password_hash
    _write_secrets_file(values)
    app.config["ADMIN_PASSWORD_HASH"] = password_hash
    app.secret_key = values["secret_key"]


def save_master_creator_code_hash(code_hash: str) -> None:
    values = read_secrets_file()
    if "secret_key" not in values:
        values["secret_key"] = secrets.token_hex(32)
    values["master_creator_code_hash"] = code_hash
    _write_secrets_file(values)
    app.config["MASTER_CREATOR_CODE_HASH"] = code_hash
    app.secret_key = values["secret_key"]


def ensure_master_creator_configured() -> bool:
    if app.config.get("MASTER_CREATOR_CODE_HASH"):
        return True
    preset = os.environ.get("MASTER_CREATOR_CODE", "").strip()
    if preset:
        save_master_creator_code_hash(generate_password_hash(preset))
        return True
    code = f"MASTER-CREATOR-{secrets.token_hex(4).upper()}"
    save_master_creator_code_hash(generate_password_hash(code))
    session["master_creator_code_show_once"] = code
    return True


def master_creator_active() -> bool:
    return bool(session.get("master_creator"))


def verify_master_creator_code(code: str) -> bool:
    ensure_master_creator_configured()
    code_hash = app.config.get("MASTER_CREATOR_CODE_HASH") or ""
    return bool(code) and check_password_hash(code_hash, code)


def master_creator_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not master_creator_active():
            flash("Master Creator access code required for fleet admin edits.", "error")
            return redirect(url_for("admin"))
        return view(*args, **kwargs)

    return wrapped


app.config["ADMIN_PASSWORD_HASH"] = load_secrets()
ensure_mesh_publish_token()


def fmt_time(ts):
    if not ts:
        return "—"
    return bloodstone_time.format_pacific(ts)


def short_hash(value, left=10, right=8):
    s = str(value or "")
    if len(s) <= left + right + 3:
        return s
    return f"{s[:left]}…{s[-right:]}"


def recent_blocks(limit=RECENT_BLOCKS):
    tip = node_rpc.rpc("getblockcount")
    blocks = []
    for height in range(tip, max(-1, tip - limit), -1):
        block_hash = node_rpc.rpc("getblockhash", [height])
        block = node_rpc.rpc("getblock", [block_hash, 1])
        powdata = merge_mining_info.enrich_powdata(block.get("powdata"))
        blocks.append(
            {
                "height": block["height"],
                "hash": block["hash"],
                "time": block["time"],
                "time_fmt": fmt_time(block["time"]),
                "nTx": block.get("nTx", 0),
                "powdata": powdata,
            }
        )
    return blocks, tip


def next_yespower_height(tip: int):
    """Next block height that accepts yespower (every block after fork)."""
    if tip + 1 < YESPOWER_FORK_HEIGHT:
        return None
    return tip + 1


def chain_overview():
    info = node_rpc.rpc("getblockchaininfo")
    mining = node_rpc.rpc("getmininginfo")
    height = info["blocks"]
    yh = next_yespower_height(height)
    all_algos_active = height >= YESPOWER_FORK_HEIGHT and height + 1 >= MULTI_ALGO_FORK_HEIGHT
    return {
        "info": info,
        "mining": mining,
        "height": height,
        "all_algos_active": all_algos_active,
        "yespower_active": height >= YESPOWER_FORK_HEIGHT,
        "yespower_fork_height": YESPOWER_FORK_HEIGHT,
        "multi_algo_fork_height": MULTI_ALGO_FORK_HEIGHT,
        "blocks_until_yespower": max(0, YESPOWER_FORK_HEIGHT - height),
        "next_yespower_height": yh,
        "blocks_until_yespower_slot": max(0, (yh - height - 1) if yh else 0),
        "payout_address": node_rpc.default_payout_address(),
    }


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not app.config.get("ADMIN_PASSWORD_HASH"):
            flash("Admin actions disabled (no password configured).", "error")
            return redirect(url_for("index"))
        if not session.get("admin"):
            query = request.query_string.decode() if request.query_string else None
            return redirect(
                url_for("admin_login", next=prefixed_path(request.path, query))
            )
        return view(*args, **kwargs)

    return wrapped


def admin_api_required(view):
    """JSON API guard — returns 403 instead of redirecting to login."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not app.config.get("ADMIN_PASSWORD_HASH"):
            return jsonify({"ok": False, "error": "admin disabled"}), 503
        if not session.get("admin"):
            return jsonify({"ok": False, "error": "admin login required"}), 403
        return view(*args, **kwargs)

    return wrapped


def _mesh_publish_token_from_request(payload=None) -> str:
    payload = payload if payload is not None else (request.get_json(silent=True) or {})
    header_token = (request.headers.get("X-Chain-Mesh-Publish-Token") or "").strip()
    body_token = str((payload or {}).get("publish_token") or "").strip()
    return header_token or body_token


def _verify_mesh_publish_token(payload=None) -> bool:
    expected = ensure_mesh_publish_token()
    supplied = _mesh_publish_token_from_request(payload)
    return bool(supplied) and supplied == expected


def _service_url(service: str, port: int) -> str:
    if request.script_root:
        public_root = os.environ.get(
            "BLOODSTONE_PUBLIC_ROOT", "https://rodcoinwallet.duckdns.org"
        )
        return f"{public_root}/{service}/"
    return f"http://{mining_config.VPS_IP}:{port}/"


@app.template_filter("hashrate")
def hashrate_filter(hps):
    return format_hashrate(hps)


@app.context_processor
def inject_globals():
    public_root = (
        os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org").rstrip("/")
        if request.script_root
        else f"http://{mining_config.VPS_IP}:8887"
    )
    pools = mining_config.POOLS
    return {
        "format_hashrate": format_hashrate,
        "vps_ip": mining_config.VPS_IP,
        "stratum_host": mining_config.VPS_IP,
        "stratum_hosts": mining_config.stratum_hosts(),
        "stratum_client_hosts": mining_config.stratum_client_hosts(),
        "cpu_stratum_host": mining_config.get_cpu_stratum_host(),
        "stratum_ports": {
            "neoscrypt": pools["neoscrypt"]["port"],
            "yespower": pools["yespower"]["port"],
            "rod_neoscrypt": pools["rod_neoscrypt"]["port"],
        },
        "explorer_url": _service_url("explorer", 8888),
        "wallet_url": _service_url("wallet", 8889),
        "faucet_url": _service_url("faucet", 8895),
        "portal_url": public_root,
        "url_prefix": request.script_root or "",
        **bloodstone_branding.header_brand_context(public_root, "⛏"),
        "run_locally": bloodstone_downloads.run_locally_context(public_root),
    }


_ADDR_LEGACY = re.compile(r"^S[1-9A-HJ-NP-Za-km-z]{25,34}$")
_ADDR_BECH32 = re.compile(r"^stone1[0-9a-z]{20,}$", re.I)
_PLACEHOLDER_ADDR = re.compile(
    r"^YOUR[_\s]*(STONE|ROD)[_\s]*(ADDRESS|WALLET)?$", re.I
)


def _is_placeholder_address(addr: str) -> bool:
    s = (addr or "").strip()
    if not s:
        return True
    if s.lower() in ("x", "solo"):
        return True
    compact = re.sub(r"[\s_]+", "_", s)
    if _PLACEHOLDER_ADDR.match(compact):
        return True
    if re.match(r"^your[_\s]*(stone|rod)", compact, re.I):
        return True
    return False


def _is_valid_stone_address(addr: str) -> bool:
    s = (addr or "").strip()
    if not s or _is_placeholder_address(s):
        return False
    return bool(_ADDR_LEGACY.match(s) or _ADDR_BECH32.match(s))


def _payout_from_request(default: str) -> str:
    address = (request.args.get("address") or "").strip()
    if _is_valid_stone_address(address):
        return address
    if _is_valid_stone_address(default):
        return default
    return ""


def _network_diff_label(mining: dict, algo: str) -> str:
    diff = mining.get("difficulty", {}).get(algo, 0)
    return f"{float(diff):.6g}" if diff else "—"


def format_hashrate(hps) -> str:
    """Human-readable network hashrate (matches browser miner formatting)."""
    if hps is None:
        return "—"
    try:
        rate = float(hps)
    except (TypeError, ValueError):
        return "—"
    if rate < 0:
        return "—"
    if rate >= 1e12:
        return f"{rate / 1e12:.2f} TH/s"
    if rate >= 1e9:
        return f"{rate / 1e9:.2f} GH/s"
    if rate >= 1e6:
        return f"{rate / 1e6:.2f} MH/s"
    if rate >= 1e3:
        return f"{rate / 1e3:.2f} kH/s"
    if rate >= 1:
        return f"{rate:.2f} H/s"
    if rate > 0:
        return f"{rate:.4f} H/s"
    return "0 H/s"


def network_hashrates(mining: dict) -> dict:
    """Per-algo network hash rate plus combined total from getmininginfo."""
    raw = mining.get("networkhashps") or {}
    algos = (
        ("sha256d", "SHA256d"),
        ("neoscrypt", "Neoscrypt-Xaya"),
        ("yespower", "Yespower"),
    )
    per_algo = {}
    total = 0.0
    for key, label in algos:
        val = float(raw.get(key, 0) or 0)
        per_algo[key] = {
            "label": label,
            "hps": val,
            "formatted": format_hashrate(val),
        }
        total += val
    return {
        "per_algo": per_algo,
        "total_hps": total,
        "total_formatted": format_hashrate(total),
    }


def _default_mining_mode() -> str:
    mode = (request.args.get("mode") or "pool").strip().lower()
    return mode if mode in ("pool", "solo") else "pool"


def _solo_example_cmd(pool_key: str, payout: str) -> str:
    cfg = mining_config.POOLS[pool_key]
    fmt = {
        "ip": mining_config.stratum_client_host_for_pool(pool_key),
        "port": cfg["port"],
        "tls_port": cfg.get("tls_port", cfg["port"]),
    }
    cmd = cfg["example_cmd"].format(**fmt)
    cmd = cmd.replace("YOUR_ROD_ADDRESS", payout or "YOUR_ROD_ADDRESS")
    cmd = cmd.replace("YOUR_STONE_ADDRESS", payout)
    if "-p x" in cmd:
        return cmd.replace("-p x", "-p solo")
    return f"{cmd} -p solo"


@app.route("/mine")
def mine():
    overview = cached_chain_overview()
    default_payout = overview.get("payout_address") or ""
    import pool_db as _pool_db

    if _pool_db._is_pool_operator_address(default_payout):
        default_payout = ""
    payout = _payout_from_request(default_payout)
    reward = (request.args.get("reward") or "").strip().lower()
    rod_node_synced = None
    if reward == "rod":
        try:
            import pool_db as _pool_db

            rod_earn = (_pool_db.get_unified_pool_dashboard().get("rod_earn") or {})
            rod_node_synced = bool(rod_earn.get("rod_node_synced"))
        except Exception:
            rod_node_synced = False
    is_android_app = request.args.get("app", "").strip().lower() == "android"
    template = "mine_android.html" if is_android_app else "mine.html"
    from stratum_status import pool_connection_info

    pools_neoscrypt = pool_connection_info("neoscrypt")
    pools_yespower = pool_connection_info("yespower")
    return render_template(
        template,
        overview=overview,
        payout_address=payout,
        pools_neoscrypt=pools_neoscrypt,
        pools_yespower=pools_yespower,
        pools_yespower_share_diff=mining_config.POOLS["yespower"]["share_difficulty"],
        pools_yespower_network_diff=_network_diff_label(overview["mining"], "yespower"),
        default_mining_mode=_default_mining_mode(),
        default_reward_target="rod" if reward == "rod" else "stone",
        rod_node_synced=rod_node_synced,
    )


_DASHBOARD_FALLBACK: dict = {
    "_loading": True,
    "totals": {"pending_stone": 0.0, "paid_stone": 0.0, "miners_with_balance": 0},
    "per_algo": {},
    "next_block": None,
}


def pool_dashboard_data(address: str = "") -> dict:
    import pool_db

    try:
        # Never block API workers on dashboard rebuild — disk cache + warmer refresh async.
        data = dict(pool_db.get_unified_pool_dashboard(allow_build=False))
        if data.get("_loading"):
            pool_db._read_dashboard_disk_cache()
            data = dict(pool_db.get_unified_pool_dashboard(allow_build=False))
        if address:
            data["miner_balance"] = pool_db.get_miner_balance(address)
            rod_wallet = pool_db.get_miner_rod_wallet(address)
            data["miner_rod_wallet"] = {
                "stone_address": address,
                "rod_address": rod_wallet,
                "registered": bool(rod_wallet),
            }
            data["dual_stats"] = pool_db.get_dual_chain_stats(address, window_sec=86400)
            next_block = data.get("next_block") or {}
            per_algo_miners = pool_db.miners_from_dashboard_next_block(next_block)
            if per_algo_miners:
                data["miner_next_block"] = pool_db.miner_next_block_shares(
                    address,
                    per_algo_miners=per_algo_miners,
                    distributable_stone=next_block.get("distributable_stone"),
                )
            else:
                data["miner_next_block"] = pool_db._miner_pool_estimate_fast(
                    address,
                    distributable_stone=next_block.get("distributable_stone"),
                )
        data = pool_db.enrich_dashboard_live_fields(data)
        rod = data.get("rod_earn")
        if isinstance(rod, dict):
            rod = dict(rod)
            rod["dual_chain_stats_24h"] = pool_db.get_dual_chain_stats(window_sec=86400)
            rod["dual_submit_active"] = bool(
                rod.get("dual_submit_configured")
                and (
                    int(rod.get("registered_wallets") or 0) > 0
                    or rod.get("rod_pool_wallet_set")
                )
            )
            data["rod_earn"] = rod
        return data
    except Exception as exc:
        return {"error": str(exc)}


@app.route("/manifest.webmanifest")
def web_manifest():
    public_root = (
        os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org").rstrip("/")
        if request.script_root
        else f"http://{mining_config.VPS_IP}:8892"
    )
    icon = f"{public_root}/branding/installer-icon.png"
    return jsonify(
        {
            "name": "Bloodstone Miner",
            "short_name": "STONE Miner",
            "description": "Mine STONE on your phone — local CPU, pool payouts",
            "start_url": f"{request.script_root or ''}/mine?source=pwa",
            "scope": f"{request.script_root or ''}/",
            "display": "standalone",
            "background_color": "#0d0f14",
            "theme_color": "#d4a017",
            "icons": [
                {
                    "src": icon,
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any maskable",
                }
            ],
        }
    )


@app.route("/miners")
def connected_miners_page():
    """Minimal live list of stratum-connected miners."""
    return render_template("connected_miners.html")


@app.route("/miners/map")
def miners_geo_map_page():
    """Full-screen world map of connected miner and LAN node public IPs."""
    return render_template("miners_geo_map.html")


@app.route("/api/miners/geo-map")
def api_miners_geo_map():
    """Geolocated connected miner / LAN node markers for the world map."""
    import miners_geo_map as mgm

    return jsonify(mgm.geo_map_payload())


@app.route("/api/miners/connected")
def api_connected_miners():
    import connected_miners as cm

    include_internal = request.args.get("all") == "1"
    worker_q = (request.args.get("worker") or "").strip()
    payload = cm.connected_miners_payload(include_internal=include_internal)
    if worker_q:
        needle = worker_q.lower()
        payload["miners"] = [
            row
            for row in payload["miners"]
            if needle in str(row.get("worker") or "").lower()
        ]
        payload["count"] = len(payload["miners"])
        payload["query"] = worker_q
        match = cm.find_worker(worker_q)
        payload["worker_connected"] = bool(
            match and match.get("status") == "connected"
        )
    return jsonify(payload)


@app.route("/network-data")
def network_data():
    """Portal for browsing and receiving data on the chain mesh."""
    return render_template("network_data.html")


@app.route("/network-chat")
def network_chat_page():
    """Old-school network chat — lobby + buddy DMs over BSM3 mesh packets."""
    return render_template("network_chat.html")


@app.route("/network/blurt-mesh-traffic")
def blurt_mesh_traffic_page():
    """Public Blurt ↔ Bloodstone mesh bandwidth totals."""
    return render_template("blurt_mesh_traffic.html")


@app.route("/api/chain-mesh/partner/blurt/traffic")
def api_blurt_mesh_traffic():
    """Public JSON: Blurt partner mesh traffic by week, month, and year."""
    import chain_mesh.blurt_traffic as bt

    return jsonify(bt.public_payload())


@app.route("/mesh-search")
def mesh_search_page():
    """Full-screen mesh file search (like /miners/map)."""
    return render_template("mesh_search.html")


@app.route("/")
def index():
    try:
        overview = cached_chain_overview()
        pools = cached_pools_status_light()
        _refresh_pools_status_full()
        blocks, tip = _cached_value(
            f"recent_blocks_{RECENT_BLOCKS}",
            _cache_ttl("MINER_RECENT_BLOCKS_CACHE_SEC", "60"),
            lambda: recent_blocks(RECENT_BLOCKS),
            blocking=True,
        )
        lookup_addr = (request.args.get("address") or "").strip()
        pool_dashboard = pool_dashboard_data(lookup_addr)
    except Exception as exc:
        return (
            render_template(
                "error.html",
                message=f"Bloodstone node is offline or busy. Try again in a moment. ({exc})",
            ),
            503,
        )
    payout = overview["payout_address"] or "YOUR_STONE_ADDRESS"
    for key, pool in list(pools.items()):
        pools[key] = ensure_pool_display(key, pool)
        pool = pools[key]
        pool["example_user"] = payout
        pool["example_cmd"] = pool["example_cmd"].replace("YOUR_STONE_ADDRESS", payout)
    return render_template(
        "index.html",
        overview=overview,
        network_hashrates=network_hashrates(overview["mining"]),
        pools=pools,
        blocks=blocks,
        tip=tip,
        short_hash=short_hash,
        pool_dashboard=pool_dashboard,
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


@app.route("/pool/<pool_key>")
def pool_detail(pool_key):
    if pool_key not in mining_config.POOLS:
        return render_template("error.html", message="Unknown pool"), 404
    overview = cached_chain_overview()
    from stratum_status import (
        neoscrypt_pool_miner_status,
        yespower_block_finder_status,
    )

    pools_light = cached_pools_status_light()
    pool = ensure_pool_display(
        pool_key, dict(pools_light.get(pool_key) or _pools_fallback().get(pool_key, {}))
    )
    if pool_key == "yespower":
        pool["pool_accounting"] = cached_pool_accounting("yespower")
        pool["block_finder"] = _try_cached_value(
            "block_finder_yespower",
            _cache_ttl("MINER_BLOCK_FINDER_CACHE_SEC", "60"),
            yespower_block_finder_status,
            {},
        )
    elif pool_key == "neoscrypt":
        pool["pool_accounting"] = cached_pool_accounting("neoscrypt")
        pool["pool_miner"] = _try_cached_value(
            "pool_miner_neoscrypt",
            _cache_ttl("MINER_POOL_MINER_CACHE_SEC", "60"),
            neoscrypt_pool_miner_status,
            {"active": False},
        )
    elif pool_key == "sha256d":
        pool["pool_accounting"] = cached_pool_accounting("sha256d")
    example_user = (
        "YOUR_ROD_ADDRESS"
        if pool_key == "rod_neoscrypt"
        else (overview["payout_address"] or "YOUR_STONE_ADDRESS")
    )
    payout = overview["payout_address"] or "YOUR_STONE_ADDRESS"
    pool["example_user"] = example_user
    pool["example_cmd"] = pool["example_cmd"].replace(
        "YOUR_ROD_ADDRESS" if pool_key == "rod_neoscrypt" else "YOUR_STONE_ADDRESS",
        example_user,
    )
    cfg = mining_config.POOLS[pool_key]
    show_pool_modes = pool_key in ("neoscrypt", "yespower", "sha256d", "rod_neoscrypt")
    show_web_miner = pool_key in ("neoscrypt", "yespower", "rod_neoscrypt")
    default_payout = "" if pool_key == "rod_neoscrypt" else (overview.get("payout_address") or "")
    import pool_db as _pool_db

    if _pool_db._is_pool_operator_address(default_payout):
        default_payout = ""
    payout = "" if pool_key == "rod_neoscrypt" else _payout_from_request(default_payout)
    mining = overview["mining"]
    return render_template(
        "pool.html",
        pool=pool,
        cfg=cfg,
        overview=overview,
        show_pool_modes=show_pool_modes,
        show_web_miner=show_web_miner,
        default_algo=cfg["algo"] if show_web_miner else None,
        payout_address=payout,
        panel_title=f"Browser mine · {cfg['name']}" if show_web_miner else None,
        pools_yespower_share_diff=mining_config.POOLS["yespower"]["share_difficulty"],
        pools_yespower_network_diff=_network_diff_label(mining, "yespower"),
        network_difficulty=_network_diff_label(mining, cfg["algo"]),
        solo_example_cmd=_solo_example_cmd(pool_key, payout) if show_pool_modes else None,
        default_mining_mode=_default_mining_mode(),
        default_reward_target="rod" if pool_key == "rod_neoscrypt" else "stone",
    )


@app.route("/api/status")
def api_status():
    ttl = _cache_ttl("MINER_CHAIN_OVERVIEW_CACHE_SEC", "45")
    overview = _cached_value("chain_overview", ttl, _load_chain_overview, blocking=False)
    if not overview:
        overview = _overview_fallback()
    pools = cached_pools_status_light()
    rates = network_hashrates(overview["mining"])
    return jsonify(
        {
            "height": overview["height"],
            "difficulty": overview["mining"].get("difficulty", {}),
            "networkhashps": overview["mining"].get("networkhashps", {}),
            "network_hashrates": {
                key: {
                    "hps": entry["hps"],
                    "formatted": entry["formatted"],
                }
                for key, entry in rates["per_algo"].items()
            },
            "network_hashrate_total": {
                "hps": rates["total_hps"],
                "formatted": rates["total_formatted"],
            },
            "yespower_active": overview["yespower_active"],
            "pools": pools,
        }
    )


DIFF1_TARGET = 0x00000000FFFF0000000000000000000000000000000000000000000000000000


def _expected_hashes(difficulty: float) -> int:
    if difficulty <= 0:
        return 0
    block_target = int(DIFF1_TARGET / difficulty)
    if block_target <= 0:
        return 0
    return (1 << 256) // block_target


@app.route("/api/pool/yespower")
def api_yespower_pool():
    import pool_db
    from stratum_status import yespower_pool_accounting

    address = (request.args.get("address") or "").strip()
    payload = yespower_pool_accounting()
    if address:
        payload["balance"] = pool_db.get_miner_balance(address)
    return jsonify(payload)


@app.route("/api/pool/yespower/balance")
def api_yespower_pool_balance():
    import pool_db

    address = (request.args.get("address") or "").strip()
    if not address:
        return jsonify({"error": "address required"}), 400
    return jsonify({"address": address, **pool_db.get_miner_balance(address)})


@app.route("/api/pool/neoscrypt")
def api_neoscrypt_pool():
    from stratum_status import neoscrypt_pool_accounting

    import pool_db

    address = (request.args.get("address") or "").strip()
    payload = neoscrypt_pool_accounting()
    if address:
        payload["balance"] = pool_db.get_miner_balance(address)
    return jsonify(payload)


@app.route("/api/node/sync")
def api_node_sync():
    import bloodstone_broadcast as bb

    status = bb.sync_status()
    ready, reason = bb.ensure_network_ready()
    return jsonify({"ready": ready, "reason": reason, **status})


@app.route("/api/pool/neoscrypt/balance")
def api_neoscrypt_pool_balance():
    import pool_db

    address = (request.args.get("address") or "").strip()
    if not address:
        return jsonify({"error": "address required"}), 400
    return jsonify({"address": address, **pool_db.get_miner_balance(address)})


@app.route("/api/pool/sha256d")
def api_sha256_pool():
    from stratum_status import sha256_pool_accounting

    import pool_db
    import pool_sha256_miner as sm

    import mining_config

    address = (request.args.get("address") or "").strip()
    payload = sha256_pool_accounting()
    payload["rod_block_diff"] = sm.sha256_rod_block_diff_status(
        pool_share_difficulty=float(
            mining_config.POOLS["sha256d"]["share_difficulty"]
        )
    )
    if address:
        payload["balance"] = pool_db.get_miner_balance(address)
    return jsonify(payload)


@app.route("/api/pool/sha256d/rod-block-diff", methods=["GET", "POST"])
def api_sha256_rod_block_diff():
    """Toggle pool-wide ROD merge block difficulty for SHA256 stratum."""
    import mining_config
    import pool_sha256_miner as sm

    mining_config.reload_pools()
    pool_diff = float(mining_config.POOLS["sha256d"]["share_difficulty"])
    if request.method == "POST":
        if not session.get("admin"):
            return jsonify({"error": "admin login required"}), 403
        payload = request.get_json(silent=True) or {}
        enabled = payload.get("enabled")
        if enabled is None and "rod_block_diff_mode" in payload:
            enabled = str(payload.get("rod_block_diff_mode", "")).strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
        try:
            if enabled is not None:
                sm.set_rod_block_diff_mode(bool(enabled))
            if payload.get("asic_diff_min") is not None:
                sm.set_asic_diff_min(float(payload["asic_diff_min"]))
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
    return jsonify(sm.sha256_rod_block_diff_status(pool_share_difficulty=pool_diff))


@app.route("/api/pool/sha256d/balance")
def api_sha256_pool_balance():
    import pool_db

    address = (request.args.get("address") or "").strip()
    if not address:
        return jsonify({"error": "address required"}), 400
    return jsonify({"address": address, **pool_db.get_miner_balance(address)})


@app.route("/api/pool/dashboard")
def api_pool_dashboard():
    """Unified pool dashboard including next-block share percentages."""
    address = (request.args.get("address") or "").strip()
    return jsonify(pool_dashboard_data(address))


def _request_client_ip() -> str:
    forwarded = (request.headers.get("X-Forwarded-For") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return (request.remote_addr or "").strip()


def _beta_token_from_request() -> str:
    return (
        request.headers.get("X-Bloodstone-Beta-Token")
        or request.args.get("beta_token")
        or ""
    ).strip()


def _lan_ip_from_request() -> str:
    return (
        request.headers.get("X-Bloodstone-Lan-Ip")
        or request.args.get("lan_ip")
        or ""
    ).strip()


def _update_release_channel_from_request() -> str:
    channel = (request.args.get("channel") or "").strip()
    return bloodstone_beta_codes.resolve_release_channel(
        beta_token=_beta_token_from_request(),
        channel=channel,
    )


@app.route("/api/android-miner/update")
@app.route("/mining/api/android-miner/update")
def api_android_miner_update():
    public_root = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    channel = _update_release_channel_from_request()
    return jsonify(
        bloodstone_downloads.android_miner_update_manifest(
            public_root,
            release_channel=channel,
            lan_ip=_lan_ip_from_request(),
        )
    )


@app.route("/api/beta/redeem", methods=["POST"])
@app.route("/mining/api/beta/redeem", methods=["POST"])
def api_beta_redeem():
    payload = request.get_json(silent=True) or {}
    code = (payload.get("code") or request.form.get("code") or "").strip()
    device_id = (payload.get("device_id") or "").strip()
    lan_ip = (payload.get("lan_ip") or "").strip()
    result = bloodstone_beta_codes.redeem_code(
        code,
        device_id=device_id,
        client_ip=_request_client_ip(),
        lan_ip=lan_ip,
    )
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@app.route("/api/beta/status")
@app.route("/mining/api/beta/status")
def api_beta_status():
    token = _beta_token_from_request()
    lan_ip = _lan_ip_from_request()
    active = bloodstone_beta_codes.verify_access_token(token) if token else False
    lan_key = bloodstone_beta_codes.lan_key_from_ip(lan_ip) if lan_ip else None
    lan_release = (
        bloodstone_beta_codes.get_lan_validated_release(lan_key) if lan_key else None
    )
    return jsonify(
        {
            "ok": True,
            "beta_active": active,
            "release_channel": "beta" if active else "stable",
            "lan_key": lan_key,
            "lan_validated": bool(lan_release),
            "lan_apk_version": (lan_release or {}).get("apk_version"),
            "lan_web_bundle_version": (lan_release or {}).get("web_bundle_version"),
        }
    )


@app.route("/api/beta/validate-lan", methods=["POST"])
@app.route("/mining/api/beta/validate-lan", methods=["POST"])
def api_beta_validate_lan():
    payload = request.get_json(silent=True) or {}
    token = _beta_token_from_request() or str(payload.get("beta_token") or "").strip()
    lan_ip = str(payload.get("lan_ip") or _lan_ip_from_request() or "").strip()
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
@app.route("/mining/api/desktop-miner/update")
def api_desktop_miner_update():
    public_root = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    channel = _update_release_channel_from_request()
    return jsonify(
        bloodstone_downloads.desktop_miner_update_manifest(
            public_root, release_channel=channel
        )
    )


@app.route("/api/node-patch/update")
def api_node_patch_update():
    """Live node hot-patch manifest (bloodstoned stays up; like APK web-bundle OTA)."""
    public_root = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    return jsonify(bloodstone_downloads.node_patch_update_manifest(public_root))


@app.route("/mining/api/node-patch/update")
def api_node_patch_update_prefixed():
    return api_node_patch_update()


@app.route("/api/pool/miner-estimate")
def api_pool_miner_estimate():
    """Lightweight payout estimate for browser miner (avoids full dashboard rebuild)."""
    address = (request.args.get("address") or "").strip()
    if not _is_valid_stone_address(address):
        return jsonify({"error": "valid STONE address required"}), 400
    import pool_db

    return jsonify(pool_db.get_miner_pool_estimate(address))


@app.route("/api/pool/miner-asic-earnings")
def api_pool_miner_asic_earnings():
    """Hourly ASIC cross-subsidy earnings for a phone/browser pool miner."""
    import pool_db

    address = (request.args.get("address") or "").strip()
    hours = request.args.get("hours", "24")
    try:
        window_hours = int(hours)
    except (TypeError, ValueError):
        window_hours = 24
    payload = pool_db.get_miner_asic_subsidy_earnings_series(
        address, window_hours=window_hours
    )
    if not payload.get("ok"):
        return jsonify(payload), 400
    return jsonify(payload)


@app.route("/api/pool/rescan-hashrates", methods=["POST", "GET"])
def api_rescan_hashrates():
    """Invalidate caches and return fresh per-miner/worker hashrate samples."""
    import pool_db as pdb
    import pool_bitaxe as pbx
    import pool_sv2_live as psv2

    psv2.refresh_sv2_hashrate_cache(force=True)
    pbx.refresh_bitaxe_cache(force=True)
    pdb.invalidate_dashboard_cache()
    window = int(request.args.get("window", pdb.MINER_HASHRATE_WINDOW_SEC))
    return jsonify(
        {
            "ok": True,
            "window_sec": window,
            "miners": pdb.get_miner_hashrates(window),
            "workers": pdb.get_worker_hashrates(window),
            "bitaxe": pbx.public_device_stats(),
        }
    )


@app.route("/api/pool/bitaxe")
def api_pool_bitaxe():
    """Live Bitaxe device stats (direct HTTP poll)."""
    import pool_bitaxe as pbx

    force = request.args.get("refresh", "").lower() in ("1", "true", "yes")
    if force:
        pbx.refresh_bitaxe_cache(force=True)
    return jsonify(pbx.public_device_stats())


@app.route("/api/pool/bitaxe/report", methods=["POST"])
def api_pool_bitaxe_report():
    """Ingest Bitaxe stats from a LAN forwarder (curl /api/system/info → POST here)."""
    import pool_bitaxe as pbx

    payload = request.get_json(silent=True) or {}
    reporter_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    if reporter_ip and "," in reporter_ip:
        reporter_ip = reporter_ip.split(",")[0].strip()
    try:
        return jsonify(pbx.ingest_device_report(payload, reporter_ip=reporter_ip))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/mining/api/pool/bitaxe/report", methods=["POST"])
def api_pool_bitaxe_report_mining_prefix():
    return api_pool_bitaxe_report()


@app.route("/api/pool/lan-forwarder/devices")
def api_pool_lan_forwarder_devices():
    """Device list for LAN hashrate forwarder (Gamma Bitaxe + Luck CGMiner, etc.)."""
    import os

    from flask import send_file

    path = os.environ.get(
        "BLOODSTONE_LAN_MINER_DEVICES_FILE", "/root/lan-miner-devices.json"
    )
    if not os.path.isfile(path):
        path = os.environ.get(
            "BLOODSTONE_BITAXE_DEVICES_FILE", "/root/bitaxe-devices.json"
        )
    if not os.path.isfile(path):
        return jsonify({"ok": False, "error": "no device config", "devices": []}), 404
    if request.args.get("format") == "json":
        with open(path, encoding="utf-8") as fh:
            devices = json.load(fh)
        return jsonify({"ok": True, "devices": devices})
    return send_file(path, mimetype="application/json", max_age=120)


@app.route("/mining/api/pool/lan-forwarder/devices")
def api_pool_lan_forwarder_devices_mining_prefix():
    return api_pool_lan_forwarder_devices()


@app.route("/api/pool/lan-forwarder/status")
def api_pool_lan_forwarder_status():
    """Whether any home LAN forwarder is actively POSTing miner stats."""
    import pool_bitaxe as pbx

    forwarders = pbx.list_lan_forwarders()
    stats = pbx.public_device_stats()
    return jsonify(
        {
            "ok": True,
            "active_forwarders": forwarders,
            "forwarder_count": len(forwarders),
            "lan_reported_devices": stats.get("lan_reported_devices", 0),
            "needs_lan_forwarder_count": stats.get("needs_lan_forwarder_count", 0),
            "devices": stats.get("devices") or [],
        }
    )


@app.route("/mining/api/pool/lan-forwarder/status")
def api_pool_lan_forwarder_status_mining_prefix():
    return api_pool_lan_forwarder_status()


@app.route("/api/pool/subsidy-schedule")
def api_pool_subsidy_schedule():
    """Live block reward, halving era, and schedule preview for pool estimates."""
    import pool_block_subsidy as pbs

    return jsonify(pbs.public_status())


@app.route("/mining/api/pool/subsidy-schedule")
def api_pool_subsidy_schedule_mining_prefix():
    return api_pool_subsidy_schedule()


@app.route("/api/pool/mobile-contribution", methods=["POST"])
def api_pool_mobile_contribution():
    """Credit browser/Android presence for ASIC cross-subsidy (connection, hashrate, YES)."""
    import pool_mobile_contrib as pmc

    payload = request.get_json(silent=True) or {}
    address = (payload.get("address") or "").strip()
    algo = (payload.get("algo") or "").strip().lower()
    if not address:
        return jsonify({"error": "address required"}), 400
    if not _is_valid_stone_address(address):
        return jsonify({"error": "valid STONE payout address required"}), 400
    import pool_algos as palgos

    algo = palgos.normalize_algo(algo)
    if algo not in palgos.CPU_POOL_ALGOS:
        return jsonify({"error": "algo must be neoscrypt-xaya or yespower"}), 400

    try:
        hashrate = float(payload.get("hashrate") or 0)
    except (TypeError, ValueError):
        hashrate = 0.0
    try:
        yes_count = int(payload.get("yes_count") or 0)
    except (TypeError, ValueError):
        yes_count = 0
    try:
        connected_sec = float(payload.get("connected_sec") or 0)
    except (TypeError, ValueError):
        connected_sec = 0.0

    miner_kind = (payload.get("miner_kind") or "browser").strip().lower()
    if miner_kind not in ("browser", "android", "ios", "asic", "lan", "cgminer"):
        miner_kind = "browser"

    transport = (payload.get("transport") or "websocket").strip().lower()
    device_id = (payload.get("device_id") or "").strip()
    device_model = (payload.get("device_model") or "").strip()

    try:
        share_id = pmc.record_mobile_contribution(
            algo,
            address,
            worker=str(payload.get("worker") or address),
            job_height=payload.get("job_height"),
            hashrate=max(0.0, hashrate),
            yes_count=max(0, yes_count),
            connected_sec=max(0.0, connected_sec),
            miner_kind=miner_kind,
            peer_ip=(request.headers.get("X-Real-IP") or request.remote_addr or ""),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    fleet = None
    try:
        import pool_device_fleet as pdf

        peer_ip = (request.headers.get("X-Real-IP") or request.remote_addr or "").split(",")[0].strip()
        fleet_id = device_id or pdf.synthetic_device_id(
            address=address,
            worker=str(payload.get("worker") or address),
            miner_kind=miner_kind,
            peer_ip=peer_ip,
        )
        fleet = pdf.upsert_fleet_device(
            device_id=fleet_id,
            address=address,
            worker=str(payload.get("worker") or address),
            algo=algo,
            miner_kind=miner_kind,
            transport=transport,
            hashrate=max(0.0, hashrate),
            model=device_model,
        )
    except (ValueError, Exception):
        fleet = None

    return jsonify(
        {
            "ok": True,
            "share_id": int(share_id or 0),
            "weight": pmc.mobile_contribution_weight(
                hashrate=hashrate,
                yes_count=yes_count,
                connected_sec=connected_sec,
            ),
            "fleet": fleet,
        }
    )


@app.route("/api/pool/device-fleet")
def api_pool_device_fleet():
    """Public stats for the decentralized device pool relieving VPS load."""
    import pool_device_fleet as pdf

    return jsonify(pdf.fleet_public_stats())


@app.route("/mining/rentals")
@app.route("/rentals")
def rentals_page():
    """Hash rate rental marketplace — rent pool work for mesh data creation."""
    import pool_hashrate_rental as phr
    from stratum_status import pool_connection_info

    pools = {}
    for key in ("neoscrypt", "yespower", "sha256d"):
        if key in mining_config.POOLS:
            pools[key] = pool_connection_info(key)
    return render_template(
        "rentals.html",
        rental_algos=sorted(phr.RENTAL_ALGOS),
        rental_pools=pools,
        min_duration_hours=phr.MIN_DURATION_HOURS,
        min_target_hashrate=phr.MIN_TARGET_HASHRATE,
    )


def _rental_order_response(order: dict) -> dict:
    import pool_hashrate_rental as phr

    out = phr.public_order(order)
    if out:
        out["stratum"] = phr.stratum_connection_for_order(out)
    return out


@app.route("/api/pool/rentals", methods=["GET", "POST"])
@app.route("/mining/api/pool/rentals", methods=["GET", "POST"])
def api_pool_rentals():
    """List or create hash rate rental orders."""
    import pool_hashrate_rental as phr

    if request.method == "GET":
        status = (request.args.get("status") or "").strip() or None
        renter = (request.args.get("renter_wallet") or "").strip() or None
        try:
            limit = int(request.args.get("limit") or 50)
        except (TypeError, ValueError):
            limit = 50
        orders = [
            _rental_order_response(o)
            for o in phr.list_orders(status=status, renter_wallet=renter, limit=limit)
        ]
        return jsonify({"ok": True, "orders": orders})

    payload = request.get_json(silent=True) or {}
    try:
        result = phr.create_order(
            algo=str(payload.get("algo") or ""),
            target_hashrate=float(payload.get("target_hashrate") or 0),
            duration_hours=float(payload.get("duration_hours") or 0),
            renter_wallet=str(payload.get("renter_wallet") or ""),
            max_price_eth=float(payload.get("max_price_eth") or 0),
            renter_eth=str(payload.get("renter_eth") or ""),
            mesh_key_prefix=str(payload.get("mesh_key_prefix") or ""),
            notes=str(payload.get("notes") or ""),
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    order = result.get("order") or {}
    if order:
        order["stratum"] = phr.stratum_connection_for_order(order)
    return jsonify(result)


@app.route("/api/pool/rentals/<order_id>", methods=["GET"])
@app.route("/mining/api/pool/rentals/<order_id>", methods=["GET"])
def api_pool_rental_detail(order_id):
    import pool_hashrate_rental as phr

    order = phr.get_order(order_id)
    if not order:
        return jsonify({"ok": False, "error": "order not found"}), 404
    meter = phr.order_meter(order_id)
    out = _rental_order_response(order)
    return jsonify({"ok": True, "order": out, "meter": meter})


@app.route("/api/pool/rentals/<order_id>/accept", methods=["POST"])
@app.route("/mining/api/pool/rentals/<order_id>/accept", methods=["POST"])
def api_pool_rental_accept(order_id):
    import pool_hashrate_rental as phr

    payload = request.get_json(silent=True) or {}
    try:
        result = phr.accept_order(
            order_id, seller_wallet=str(payload.get("seller_wallet") or "")
        )
    except (TypeError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    order = (result.get("order") or {})
    if order:
        result["order"] = _rental_order_response(order)
    return jsonify(result)


@app.route("/api/pool/rentals/<order_id>/cancel", methods=["POST"])
@app.route("/mining/api/pool/rentals/<order_id>/cancel", methods=["POST"])
def api_pool_rental_cancel(order_id):
    import pool_hashrate_rental as phr

    payload = request.get_json(silent=True) or {}
    try:
        result = phr.cancel_order(
            order_id, renter_token=str(payload.get("renter_token") or "")
        )
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except (TypeError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    order = (result.get("order") or {})
    if order:
        result["order"] = _rental_order_response(order)
    return jsonify(result)


@app.route("/api/chain-mesh/rental/upload", methods=["POST"])
def api_chain_mesh_rental_upload():
    """Renter chunk upload — spends rental compute credits."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    header_token = (request.headers.get("X-Rental-Token") or "").strip()
    if header_token and not payload.get("renter_token"):
        payload = {**payload, "renter_token": header_token}
    try:
        return jsonify(cm.rental_upload_batch(payload))
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/chain-mesh/rental/publish-asset", methods=["POST"])
def api_chain_mesh_rental_publish_asset():
    """Renter manifest publish under assets/rental/<order_id>/."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    header_token = (request.headers.get("X-Rental-Token") or "").strip()
    if header_token and not payload.get("renter_token"):
        payload = {**payload, "renter_token": header_token}
    try:
        return jsonify(cm.rental_publish_asset_payload(payload))
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/network/nodes")
def api_network_nodes():
    """Connected node counts across P2P, mesh, fleet, and LAN registry."""
    import network_nodes as nn

    return jsonify(nn.network_nodes_payload())


@app.route("/api/network/lan-nodes")
@app.route("/mining/api/network/lan-nodes")
def api_network_lan_nodes():
    """LAN Android/local nodes with blocks-behind vs VPS chain tip."""
    import network_nodes as nn

    lookback = request.args.get("lookback_sec", type=int) or 86400
    active = request.args.get("active_sec", type=int)
    include_inactive = request.args.get("include_stale", "").lower() in (
        "1",
        "true",
        "yes",
    )
    return jsonify(
        nn.lan_nodes_lag_payload(
            lookback_sec=lookback,
            active_sec=active,
            include_inactive=include_inactive,
        )
    )


@app.route("/api/admin/lan-nodes")
@admin_api_required
def api_admin_lan_nodes():
    """Admin JSON — same payload as public LAN lag endpoint."""
    import network_nodes as nn

    lookback = request.args.get("lookback_sec", type=int) or 86400
    active = request.args.get("active_sec", type=int)
    return jsonify(
        nn.lan_nodes_lag_payload(
            lookback_sec=lookback,
            active_sec=active,
            include_inactive=True,
        )
    )


@app.route("/api/pool/lan-devices")
@app.route("/mining/api/pool/lan-devices")
def api_pool_lan_devices():
    """Active LAN-reported miners with live hashrate (forwarded from household Wi‑Fi)."""
    import network_nodes as nn

    stats = nn._lan_device_stats()
    return jsonify({"ok": True, **stats})


@app.route("/api/chain-mesh/manifest")
def api_chain_mesh_manifest():
    """Current blockchain chunk manifest for decentralized storage peers."""
    import chain_mesh.api as cm

    return jsonify(cm.manifest_payload())


@app.route("/api/chain-mesh/chunk/<chunk_hash>")
def api_chain_mesh_chunk(chunk_hash):
    """Download one content-addressed block chunk."""
    import chain_mesh.api as cm

    payload = cm.chunk_payload(chunk_hash)
    if not payload:
        return jsonify({"error": "chunk not found"}), 404
    return jsonify(payload)


@app.route("/api/chain-mesh/chunk/<chunk_hash>", methods=["PUT", "POST"])
def api_chain_mesh_chunk_upload(chunk_hash):
    """Upload a chunk replica from a storage peer."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    raw_b64 = payload.get("data_b64") or payload.get("data")
    if not raw_b64 and request.data:
        raw_b64 = request.data.decode("utf-8", errors="ignore")
    if not raw_b64:
        return jsonify({"error": "data_b64 required"}), 400
    try:
        import base64

        data = base64.b64decode(raw_b64, validate=True)
    except Exception:
        return jsonify({"error": "invalid base64"}), 400
    try:
        return jsonify(cm.upload_chunk(chunk_hash, data))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/chain-mesh/upload", methods=["POST"])
def api_chain_mesh_upload_batch():
    """Batch upload chunks from browser/Android storage peers (replication only)."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.upload_batch(payload))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/chain-mesh/publish-upload", methods=["POST"])
@admin_api_required
def api_chain_mesh_publish_upload_batch():
    """Admin-only chunk upload used before publishing a new mesh asset."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    if not _verify_mesh_publish_token(payload):
        return jsonify({"ok": False, "error": "invalid publish token"}), 403
    try:
        return jsonify(cm.upload_batch(payload))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/chain-mesh/partner/upload", methods=["POST"])
def api_chain_mesh_partner_upload_batch():
    """Partner chunk upload (publish token only — no admin session)."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    header_token = (request.headers.get("X-Chain-Mesh-Publish-Token") or "").strip()
    if header_token and not payload.get("publish_token"):
        payload = {**payload, "publish_token": header_token}
    if not _verify_mesh_publish_token(payload):
        return jsonify({"ok": False, "error": "invalid publish token"}), 403
    try:
        result = cm.upload_batch(payload)
        import chain_mesh.blurt_traffic as bt

        bt.record_partner_upload(payload)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/chain-mesh/v2/system")
@app.route("/mining/api/chain-mesh/v2/system")
def api_chain_mesh_v2_system():
    """Chain Mesh v2.0-Lite architecture status (Megadrive RFC)."""
    import chain_mesh.api as cm

    return jsonify(cm.mesh_v2_system_payload())


@app.route("/api/chain-mesh/v2/manifest")
@app.route("/mining/api/chain-mesh/v2/manifest")
def api_chain_mesh_v2_manifest():
    """Resolve manifest: Blurt custom_json registry first, coordinator catalog fallback."""
    import chain_mesh.api as cm

    asset_key = (request.args.get("asset_key") or request.args.get("key") or "").strip()
    if not asset_key:
        return jsonify({"ok": False, "error": "asset_key required"}), 400
    return jsonify(cm.mesh_v2_manifest_payload(asset_key))


@app.route("/api/chain-mesh/v2/verify", methods=["GET", "POST"])
@app.route("/mining/api/chain-mesh/v2/verify", methods=["GET", "POST"])
def api_chain_mesh_v2_verify():
    """Trustless retrieval self-check — verify all chunks match manifest on coordinator."""
    import chain_mesh.api as cm

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        asset_key = str(data.get("asset_key") or data.get("key") or "").strip()
    else:
        asset_key = (request.args.get("asset_key") or request.args.get("key") or "").strip()
    if not asset_key:
        return jsonify({"ok": False, "error": "asset_key required"}), 400
    return jsonify(cm.mesh_v2_trustless_verify_payload(asset_key))


@app.route("/api/chain-mesh/v2/flow")
@app.route("/mining/api/chain-mesh/v2/flow")
def api_chain_mesh_v2_flow():
    """Publishing flow diagram for Blurt v2.0-Lite integration."""
    import chain_mesh.api as cm

    return jsonify(cm.mesh_v2_publish_flow_payload())


@app.route("/api/chain-mesh/v2/providers", methods=["GET", "POST"])
@app.route("/mining/api/chain-mesh/v2/providers", methods=["GET", "POST"])
def api_chain_mesh_v2_providers():
    """List or register mesh storage/bootstrap provider nodes."""
    import chain_mesh.api as cm

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify(cm.mesh_v2_register_provider_payload(payload))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
    tenant = (request.args.get("tenant") or "").strip()
    role = (request.args.get("role") or "").strip()
    return jsonify(cm.mesh_v2_list_providers_payload(tenant=tenant, role=role))


@app.route("/api/convergence/status")
@app.route("/mining/api/convergence/status")
def api_convergence_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_status_payload())


@app.route("/api/convergence/storage/quota")
@app.route("/mining/api/convergence/storage/quota")
def api_convergence_storage_quota():
    import chain_mesh.api as cm

    stone = (request.args.get("stone_address") or request.args.get("address") or "").strip()
    if not stone:
        return jsonify({"ok": False, "error": "stone_address required"}), 400
    return jsonify(cm.convergence_storage_quota_payload(stone))


@app.route("/api/convergence/storage/sync", methods=["POST"])
@app.route("/mining/api/convergence/storage/sync", methods=["POST"])
def api_convergence_storage_sync():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_storage_sync_payload())


@app.route("/api/convergence/blog/manifest", methods=["GET", "POST"])
@app.route("/mining/api/convergence/blog/manifest", methods=["GET", "POST"])
def api_convergence_blog_manifest():
    import chain_mesh.api as cm

    if request.method == "GET":
        payload = {
            "post_id": request.args.get("post_id") or "",
            "author": request.args.get("author") or "",
            "asset_keys": [k.strip() for k in (request.args.get("asset_keys") or "").split(",") if k.strip()],
            "title": request.args.get("title") or "",
            "permlink": request.args.get("permlink") or "",
            "filename": request.args.get("filename") or "",
            "mime_type": request.args.get("mime_type") or "",
        }
    else:
        payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_blog_manifest_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/convergence/blog/publish-flow", methods=["POST"])
@app.route("/mining/api/convergence/blog/publish-flow", methods=["POST"])
def api_convergence_blog_publish_flow():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    return jsonify(cm.convergence_blog_publish_flow_payload(payload))


@app.route("/api/convergence/condenser/embed")
@app.route("/mining/api/convergence/condenser/embed")
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
@app.route("/mining/api/convergence/condenser/offline/status")
def api_convergence_condenser_offline_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_condenser_offline_status_payload())


@app.route("/api/convergence/condenser/offline/feed")
@app.route("/mining/api/convergence/condenser/offline/feed")
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
@app.route("/mining/api/convergence/condenser/offline/post")
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
@app.route("/mining/api/convergence/condenser/offline/index", methods=["POST"])
def api_convergence_condenser_offline_index():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    sync_blurt = payload.get("sync_blurt", True) not in (False, "0", 0)
    return jsonify(cm.convergence_condenser_offline_index_payload(sync_blurt=bool(sync_blurt)))


@app.route("/convergence/offline")
@app.route("/mining/convergence/offline")
def convergence_offline_feed_page():
    from chain_mesh import condenser_offline as coff

    return coff.feed_page_html()


@app.route("/convergence/offline/<author>/<post_id>")
@app.route("/mining/convergence/offline/<author>/<post_id>")
def convergence_offline_post_page(author: str, post_id: str):
    from chain_mesh import condenser_offline as coff

    return coff.post_page_html(author=author, post_id=post_id)


@app.route("/convergence/embed/<author>/<post_id>")
@app.route("/mining/convergence/embed/<author>/<post_id>")
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
    from flask import Response

    return Response(result.get("page_html") or "", mimetype="text/html")


@app.route("/api/convergence/provenance/anchor", methods=["GET", "POST"])
@app.route("/mining/api/convergence/provenance/anchor", methods=["GET", "POST"])
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
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/convergence/provenance/verify")
@app.route("/mining/api/convergence/provenance/verify")
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
@app.route("/mining/api/convergence/provenance/sync", methods=["POST"])
def api_convergence_provenance_sync():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_provenance_sync_payload())


@app.route("/api/convergence/agent/register", methods=["GET", "POST"])
@app.route("/mining/api/convergence/agent/register", methods=["GET", "POST"])
def api_convergence_agent_register():
    import chain_mesh.api as cm

    if request.method == "GET":
        payload = {
            "blurt_author": request.args.get("blurt_author") or request.args.get("author") or "",
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
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/convergence/agent/verify")
@app.route("/mining/api/convergence/agent/verify")
def api_convergence_agent_verify():
    import chain_mesh.api as cm

    return jsonify(
        cm.convergence_agent_verify_payload(
            agent_id=(request.args.get("agent_id") or "").strip(),
            blurt_author=(request.args.get("blurt_author") or request.args.get("author") or "").strip(),
        )
    )


@app.route("/api/convergence/agent/sync", methods=["POST"])
@app.route("/mining/api/convergence/agent/sync", methods=["POST"])
def api_convergence_agent_sync():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_agent_sync_payload())


@app.route("/api/convergence/agent/publish-flow", methods=["POST"])
@app.route("/mining/api/convergence/agent/publish-flow", methods=["POST"])
def api_convergence_agent_publish_flow():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_agent_publish_flow_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/convergence/compute/quota")
@app.route("/mining/api/convergence/compute/quota")
def api_convergence_compute_quota():
    import chain_mesh.api as cm

    stone = (request.args.get("stone_address") or request.args.get("address") or "").strip()
    if not stone:
        return jsonify({"ok": False, "error": "stone_address required"}), 400
    return jsonify(cm.convergence_compute_quota_payload(stone))


@app.route("/api/convergence/compute/job/status")
@app.route("/mining/api/convergence/compute/job/status")
def api_convergence_compute_job_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_compute_job_status_payload())


@app.route("/api/convergence/compute/jobs")
@app.route("/mining/api/convergence/compute/jobs")
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
@app.route("/mining/api/convergence/compute/job/submit", methods=["POST"])
def api_convergence_compute_job_submit():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_compute_job_submit_payload(payload))
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/convergence/compute/job/verify")
@app.route("/mining/api/convergence/compute/job/verify")
def api_convergence_compute_job_verify():
    import chain_mesh.api as cm

    return jsonify(
        cm.convergence_compute_job_verify_payload(
            job_id=(request.args.get("job_id") or "").strip(),
            stone_address=(request.args.get("stone_address") or "").strip(),
        )
    )


@app.route("/api/convergence/compute/job/sync", methods=["POST"])
@app.route("/mining/api/convergence/compute/job/sync", methods=["POST"])
def api_convergence_compute_job_sync():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_compute_job_sync_payload())


@app.route("/api/convergence/bandwidth/quota")
@app.route("/mining/api/convergence/bandwidth/quota")
def api_convergence_bandwidth_quota():
    import chain_mesh.api as cm

    stone = (request.args.get("stone_address") or request.args.get("address") or "").strip()
    if not stone:
        return jsonify({"ok": False, "error": "stone_address required"}), 400
    return jsonify(cm.convergence_bandwidth_quota_payload(stone))


@app.route("/api/convergence/depin/quota")
@app.route("/mining/api/convergence/depin/quota")
def api_convergence_depin_quota():
    import chain_mesh.api as cm

    stone = (request.args.get("stone_address") or request.args.get("address") or "").strip()
    if not stone:
        return jsonify({"ok": False, "error": "stone_address required"}), 400
    return jsonify(cm.convergence_depin_quota_payload(stone))


@app.route("/api/convergence/depin/sync", methods=["POST"])
@app.route("/mining/api/convergence/depin/sync", methods=["POST"])
def api_convergence_depin_sync():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_depin_sync_payload())


@app.route("/api/convergence/dtn/status")
@app.route("/mining/api/convergence/dtn/status")
def api_convergence_dtn_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_dtn_status_payload())


@app.route("/api/convergence/dtn/export", methods=["GET", "POST"])
@app.route("/mining/api/convergence/dtn/export", methods=["GET", "POST"])
def api_convergence_dtn_export():
    import chain_mesh.api as cm

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
    else:
        payload = {
            "node_id": request.args.get("node_id") or "",
            "region": request.args.get("region") or "",
            "stone_address": request.args.get("stone_address") or "",
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
            )
        )
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/convergence/dtn/export/download")
@app.route("/mining/api/convergence/dtn/export/download")
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
        )
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return Response(
        blob,
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/api/convergence/dtn/import", methods=["POST"])
@app.route("/mining/api/convergence/dtn/import", methods=["POST"])
def api_convergence_dtn_import():
    import chain_mesh.api as cm

    upload = request.files.get("bundle_file")
    if upload:
        try:
            from chain_mesh.dtn_sync import import_dtn_bundle

            return jsonify(import_dtn_bundle(upload.read()))
        except (ValueError, TypeError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_dtn_import_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/convergence/dtn/forward/pending")
@app.route("/mining/api/convergence/dtn/forward/pending")
def api_convergence_dtn_forward_pending():
    import chain_mesh.api as cm

    try:
        limit = int(request.args.get("limit") or 20)
    except (TypeError, ValueError):
        limit = 20
    return jsonify(cm.convergence_dtn_forward_pending_payload(limit=limit))


@app.route("/api/convergence/dtn/forward/submit", methods=["POST"])
@app.route("/mining/api/convergence/dtn/forward/submit", methods=["POST"])
def api_convergence_dtn_forward_submit():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_dtn_forward_submit_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/convergence/dtn/forward/flush", methods=["POST"])
@app.route("/mining/api/convergence/dtn/forward/flush", methods=["POST"])
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
@app.route("/mining/api/convergence/dtn/flush-window")
def api_convergence_dtn_flush_window():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_dtn_flush_window_payload())


@app.route("/api/convergence/dtn/compact", methods=["POST"])
@app.route("/mining/api/convergence/dtn/compact", methods=["POST"])
def api_convergence_dtn_compact():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_dtn_compact_payload())


@app.route("/api/convergence/dtn/upkeep", methods=["POST"])
@app.route("/mining/api/convergence/dtn/upkeep", methods=["POST"])
def api_convergence_dtn_upkeep():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    force = payload.get("force") in (True, "1", 1) or request.args.get("force") in ("1", "true", "yes")
    return jsonify(cm.convergence_dtn_upkeep_payload(force_flush=bool(force)))


@app.route("/api/convergence/dtn/peers")
@app.route("/mining/api/convergence/dtn/peers")
def api_convergence_dtn_peers():
    import chain_mesh.api as cm

    try:
        limit = int(request.args.get("limit") or 30)
    except (TypeError, ValueError):
        limit = 30
    return jsonify(cm.convergence_dtn_peers_payload(limit=limit))


@app.route("/api/convergence/dtn/peers/discover", methods=["POST"])
@app.route("/mining/api/convergence/dtn/peers/discover", methods=["POST"])
def api_convergence_dtn_peers_discover():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_dtn_peers_discover_payload())


@app.route("/api/convergence/dtn/peers/register", methods=["POST"])
@app.route("/mining/api/convergence/dtn/peers/register", methods=["POST"])
def api_convergence_dtn_peers_register():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_dtn_peer_register_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/convergence/dtn/replication/heal", methods=["POST"])
@app.route("/mining/api/convergence/dtn/replication/heal", methods=["POST"])
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
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/convergence/dtn/mdns/status")
@app.route("/mining/api/convergence/dtn/mdns/status")
def api_convergence_dtn_mdns_status():
    import chain_mesh.api as cm

    include = request.args.get("browse") in ("1", "true", "yes")
    return jsonify(cm.convergence_dtn_mdns_status_payload(include_browse=include))


@app.route("/api/convergence/dtn/mdns/register", methods=["POST"])
@app.route("/mining/api/convergence/dtn/mdns/register", methods=["POST"])
def api_convergence_dtn_mdns_register():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_dtn_mdns_register_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/convergence/dtn/mdns/browse", methods=["POST"])
@app.route("/mining/api/convergence/dtn/mdns/browse", methods=["POST"])
def api_convergence_dtn_mdns_browse():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    register = payload.get("register", True) not in (False, "0", 0)
    return jsonify(cm.convergence_dtn_mdns_browse_payload(register=register))


@app.route("/api/convergence/dtn/replication/status")
@app.route("/mining/api/convergence/dtn/replication/status")
def api_convergence_dtn_replication_status():
    import chain_mesh.api as cm

    return jsonify(
        cm.convergence_dtn_replication_status_payload(
            region=(request.args.get("region") or "").strip()
        )
    )


@app.route("/api/convergence/dtn/replication/check", methods=["POST"])
@app.route("/mining/api/convergence/dtn/replication/check", methods=["POST"])
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
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/convergence/dtn/alerts")
@app.route("/mining/api/convergence/dtn/alerts")
def api_convergence_dtn_alerts():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_dtn_alerts_payload())


@app.route("/api/convergence/dtn/tls/status")
@app.route("/mining/api/convergence/dtn/tls/status")
def api_convergence_dtn_tls_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_dtn_tls_status_payload())


@app.route("/api/convergence/dtn/gossip/status")
@app.route("/mining/api/convergence/dtn/gossip/status")
def api_convergence_dtn_gossip_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_dtn_gossip_status_payload())


@app.route("/api/convergence/dtn/gossip/exchange", methods=["POST"])
@app.route("/mining/api/convergence/dtn/gossip/exchange", methods=["POST"])
def api_convergence_dtn_gossip_exchange():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.convergence_dtn_gossip_exchange_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/convergence/dtn/gossip/round", methods=["POST"])
@app.route("/mining/api/convergence/dtn/gossip/round", methods=["POST"])
def api_convergence_dtn_gossip_round():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        limit = int(payload.get("limit") or request.args.get("limit") or 0)
    except (TypeError, ValueError):
        limit = 0
    return jsonify(cm.convergence_dtn_gossip_round_payload(limit=limit))


@app.route("/api/convergence/dtn/starlink/status")
@app.route("/mining/api/convergence/dtn/starlink/status")
def api_convergence_dtn_starlink_status():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_dtn_starlink_status_payload())


@app.route("/api/convergence/dtn/starlink/probe", methods=["GET", "POST"])
@app.route("/mining/api/convergence/dtn/starlink/probe", methods=["GET", "POST"])
def api_convergence_dtn_starlink_probe():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    url = str(payload.get("url") or request.args.get("url") or "").strip()
    return jsonify(cm.convergence_dtn_starlink_probe_payload(url=url))


@app.route("/api/convergence/dtn/starlink/handoff", methods=["POST"])
@app.route("/mining/api/convergence/dtn/starlink/handoff", methods=["POST"])
def api_convergence_dtn_starlink_handoff():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    force = payload.get("force") in (True, "1", 1) or request.args.get("force") in ("1", "true", "yes")
    try:
        limit = int(payload.get("limit") or request.args.get("limit") or 0)
    except (TypeError, ValueError):
        limit = 0
    return jsonify(cm.convergence_dtn_starlink_handoff_payload(force=bool(force), limit=limit))


@app.route("/api/convergence/spatial/manifest", methods=["GET", "POST"])
@app.route("/mining/api/convergence/spatial/manifest", methods=["GET", "POST"])
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
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/convergence/spatial/embed")
@app.route("/mining/api/convergence/spatial/embed")
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
@app.route("/mining/convergence/spatial/<author>/<scene_id>")
def convergence_spatial_page(author: str, scene_id: str):
    import chain_mesh.api as cm
    from flask import Response

    result = cm.convergence_spatial_embed_payload(
        {"scene_id": scene_id, "author": author, "title": request.args.get("title") or ""}
    )
    if not result.get("ok"):
        return result.get("error", "spatial embed failed"), 404
    return Response(result.get("page_html") or "", mimetype="text/html")


@app.route("/api/convergence/spatial/overlay")
@app.route("/mining/api/convergence/spatial/overlay")
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
@app.route("/mining/api/convergence/spatial/sync", methods=["POST"])
def api_convergence_spatial_sync():
    import chain_mesh.api as cm

    return jsonify(cm.convergence_spatial_sync_payload())


@app.route("/api/chain-mesh/v2/blurt/sync", methods=["POST"])
@admin_api_required
def api_chain_mesh_v2_blurt_sync():
    """Admin: index chain_mesh_anchor custom_json ops from configured Blurt accounts."""
    import chain_mesh.api as cm

    return jsonify(cm.mesh_v2_sync_blurt_registry_payload())


@app.route("/network/blurt-mesh-v2")
def blurt_mesh_v2_page():
    """Operator page — v2.0-Lite trustless storage system overview."""
    return render_template("blurt_mesh_v2.html")


@app.route("/api/chain-mesh/partner/publish-asset", methods=["POST"])
def api_chain_mesh_partner_publish_asset():
    """Partner manifest publish — token only, keys must be under assets/blurt/."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    header_token = (request.headers.get("X-Chain-Mesh-Publish-Token") or "").strip()
    if header_token and not payload.get("publish_token"):
        payload = {**payload, "publish_token": header_token}
    if not _verify_mesh_publish_token(payload):
        return jsonify({"ok": False, "error": "invalid publish token"}), 403
    try:
        return jsonify(cm.partner_publish_asset_payload(payload))
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/chain-mesh/peer", methods=["POST"])
def api_chain_mesh_peer_register():
    """Register which chunk hashes a device is holding."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify({"ok": True, **cm.register_peer(payload)})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/chain-mesh/status")
def api_chain_mesh_status():
    """Coordinator + peer replication stats."""
    import chain_mesh.api as cm

    return jsonify(cm.status_payload())


@app.route("/api/chain-mesh/time-capsule/status")
def api_chain_mesh_time_capsule_status():
    """Time Capsule archive + prune status."""
    import chain_mesh.api as cm

    return jsonify(cm.time_capsule_status_payload())


@app.route("/api/chain-mesh/time-capsule/archive", methods=["POST"])
@admin_api_required
def api_chain_mesh_time_capsule_archive():
    """Archive block files to Time Capsule mesh (admin)."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    if not _verify_mesh_publish_token(payload):
        return jsonify({"ok": False, "error": "invalid publish token"}), 403
    force = bool(payload.get("force"))
    return jsonify(cm.time_capsule_archive_payload(force=force))


@app.route("/api/chain-mesh/time-capsule/prune", methods=["POST"])
@admin_api_required
def api_chain_mesh_time_capsule_prune():
    """Enable local prune after capsule is complete (admin, explicit confirm)."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    if not _verify_mesh_publish_token(payload):
        return jsonify({"ok": False, "error": "invalid publish token"}), 403
    if not payload.get("confirm"):
        return jsonify({"ok": False, "error": "confirm=true required"}), 400
    return jsonify(cm.time_capsule_prune_payload(confirm=True))


@app.route("/api/chain-mesh/backup/manifest")
def api_chain_mesh_backup_manifest():
    """Time Capsule backup metadata (size, chunk count, completeness)."""
    import chain_mesh.api as cm

    return jsonify(cm.mesh_backup_manifest_payload())


@app.route("/api/chain-mesh/backup/download")
def api_chain_mesh_backup_download():
    """Download full Time Capsule archive as zip (manifest + chunk files)."""
    import chain_mesh.api as cm

    from io import BytesIO

    from flask import send_file

    try:
        blob, filename = cm.mesh_backup_build_zip()
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "no manifest published"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503
    return send_file(
        BytesIO(blob),
        mimetype="application/zip",
        as_attachment=True,
        download_name=filename,
        max_age=120,
    )


@app.route("/api/chain-mesh/backup/import", methods=["POST"])
def api_chain_mesh_backup_import():
    """Restore mesh chunks from a user backup (JSON body or zip upload)."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    upload = request.files.get("backup_file")
    if upload and upload.filename:
        try:
            from chain_mesh.backup import import_backup_bytes

            raw = upload.read()
            return jsonify(import_backup_bytes(raw))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500
    try:
        return jsonify(cm.mesh_backup_import_payload(payload))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/chain-mesh/assets")
def api_chain_mesh_assets():
    """Catalog of mesh-published assets (APKs, docs, archives)."""
    import chain_mesh.api as cm

    limit = request.args.get("limit", 50, type=int)
    return jsonify(cm.assets_catalog(limit=limit))


@app.route("/api/chain-mesh/writable-keys")
def api_chain_mesh_writable_keys():
    """Mesh asset keys that can be overwritten by publishing a new revision."""
    import chain_mesh.api as cm

    limit = request.args.get("limit", 200, type=int)
    prefix = request.args.get("prefix", "")
    return jsonify(cm.writable_keys(limit=limit, prefix=prefix))


@app.route("/api/chain-mesh/search")
def api_chain_mesh_search():
    """Search mesh catalog; download endpoints fetch only each file's chunks."""
    import chain_mesh.api as cm

    return jsonify(
        cm.mesh_search_payload(
            query=request.args.get("q", "") or request.args.get("query", ""),
            prefix=request.args.get("prefix", ""),
            mime=request.args.get("mime", ""),
            limit=request.args.get("limit", 50, type=int),
            offset=request.args.get("offset", 0, type=int),
        )
    )


@app.route("/api/chain-mesh/asset/<path:asset_key>", methods=["GET", "PATCH", "PUT"])
def api_chain_mesh_asset(asset_key):
    """Asset manifest (GET) or metadata update (PATCH/PUT)."""
    import chain_mesh.api as cm

    if request.method in ("PATCH", "PUT"):
        if not session.get("admin"):
            return jsonify({"ok": False, "error": "admin login required"}), 403
        payload = request.get_json(silent=True) or {}
        header_token = (request.headers.get("X-Chain-Mesh-Publish-Token") or "").strip()
        if header_token and not payload.get("publish_token"):
            payload = {**payload, "publish_token": header_token}
        if not _verify_mesh_publish_token(payload):
            return jsonify({"ok": False, "error": "invalid publish token"}), 403
        try:
            return jsonify(cm.update_asset_metadata_payload(payload, asset_key=asset_key))
        except PermissionError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 403
        except (ValueError, TypeError, KeyError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    payload = cm.asset_manifest(asset_key)
    if not payload.get("ok"):
        return jsonify(payload), 404
    return jsonify(payload)


@app.route("/api/chain-mesh/lookup")
def api_chain_mesh_lookup_query():
    """Resolve mesh file chunk list by asset_key, BSM1 txid, or merkle_root."""
    import chain_mesh.api as cm

    public_root = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    payload = cm.mesh_lookup_query_payload(
        asset_key=request.args.get("key", "") or request.args.get("asset_key", ""),
        txid=request.args.get("txid", "") or request.args.get("anchor_txid", ""),
        merkle_root=request.args.get("merkle_root", "") or request.args.get("merkle", ""),
        range_header=request.headers.get("Range", ""),
        range_query=request.args.get("range", ""),
        public_root=public_root,
    )
    if not payload.get("ok"):
        code = 416 if "range" in str(payload.get("error", "")).lower() else 404
        return jsonify(payload), code
    return jsonify(payload)


@app.route("/api/chain-mesh/asset/<path:asset_key>/lookup")
def api_chain_mesh_asset_lookup(asset_key):
    """Compact chunk lookup for a mesh asset (fetch only these chunks to reconstruct)."""
    import chain_mesh.api as cm

    public_root = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    payload = cm.asset_lookup_payload(
        asset_key,
        range_header=request.headers.get("Range", ""),
        range_query=request.args.get("range", ""),
        public_root=public_root,
    )
    if not payload.get("ok"):
        code = 416 if "range" in str(payload.get("error", "")).lower() else 404
        return jsonify(payload), code
    return jsonify(payload)


@app.route("/api/chain-mesh/asset/<path:asset_key>/versions")
def api_chain_mesh_asset_versions(asset_key):
    import chain_mesh.api as cm

    limit = request.args.get("limit", 20, type=int)
    payload = cm.asset_versions(asset_key, limit=limit)
    if not payload.get("ok"):
        return jsonify(payload), 404
    return jsonify(payload)


@app.route("/api/chain-mesh/asset/<path:asset_key>/preview")
def api_chain_mesh_asset_preview(asset_key):
    import chain_mesh.api as cm
    import chain_mesh.blurt_traffic as bt

    payload = cm.asset_preview(asset_key)
    if not payload.get("ok"):
        return jsonify(payload), 404
    if bt.is_blurt_asset_key(asset_key):
        preview_bytes = 0
        if payload.get("preview_kind") == "image" and payload.get("data_b64"):
            preview_bytes = len(base64.b64decode(payload["data_b64"]))
        elif payload.get("preview_kind") == "text" and payload.get("text"):
            preview_bytes = len(str(payload["text"]).encode("utf-8"))
        if preview_bytes > 0:
            bt.record_outbound(preview_bytes)
    return jsonify(payload)


@app.route("/api/chain-mesh/asset/<path:asset_key>/download", methods=["GET", "HEAD"])
def api_chain_mesh_asset_download(asset_key):
    """Reconstruct and download a mesh-published file (HTTP Range for VOD streaming)."""
    import chain_mesh.assets as mesh_assets

    from flask import Response

    try:
        asset = mesh_assets.asset_manifest_payload(asset_key)
        if not asset.get("ok"):
            return jsonify(asset), 404
        filename = mesh_assets.asset_download_filename(asset_key)
        mime = asset.get("mime_type") or "application/octet-stream"
        file_size = int(asset.get("file_size") or 0)
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "asset not found"}), 404
    except (ValueError, OSError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    if file_size <= 0:
        return jsonify({"ok": False, "error": "empty asset"}), 404

    inline = request.args.get("inline", "").lower() in ("1", "true", "yes")
    force_attachment = request.args.get("attachment", "").lower() in ("1", "true", "yes")
    if force_attachment:
        inline = False
    elif not inline and mesh_assets.is_streamable_mime(mime):
        inline = True

    disposition = "inline" if inline else "attachment"
    base_headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": mime,
        "Content-Disposition": f'{disposition}; filename="{filename}"',
        "Cache-Control": "public, max-age=60",
    }

    range_header = request.headers.get("Range", "")
    byte_range = None
    if range_header:
        try:
            byte_range = mesh_assets.parse_bytes_range(range_header, file_size)
        except ValueError:
            return Response(
                status=416,
                headers={
                    **base_headers,
                    "Content-Range": f"bytes */{file_size}",
                },
            )

    if request.method == "HEAD":
        if byte_range:
            start, end = byte_range
            return Response(
                status=206,
                headers={
                    **base_headers,
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Length": str(end - start + 1),
                },
            )
        return Response(
            status=200,
            headers={**base_headers, "Content-Length": str(file_size)},
        )

    try:
        import chain_mesh.blurt_traffic as bt

        track_blurt = bt.is_blurt_asset_key(asset_key)
        if byte_range:
            start, end = byte_range
            blob = mesh_assets.reconstruct_asset_byte_range(asset_key, start, end)
            if track_blurt and len(blob) > 0:
                bt.record_outbound(len(blob))
            return Response(
                blob,
                status=206,
                headers={
                    **base_headers,
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Length": str(len(blob)),
                },
            )
        blob = mesh_assets.reconstruct_asset_bytes(asset_key)
        if track_blurt and len(blob) > 0:
            bt.record_outbound(len(blob))
        return Response(
            blob,
            status=200,
            headers={**base_headers, "Content-Length": str(len(blob))},
        )
    except FileNotFoundError:
        return jsonify({"ok": False, "error": "asset not found"}), 404
    except (ValueError, OSError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/chain-mesh/publish-asset", methods=["POST"])
@admin_api_required
def api_chain_mesh_publish_asset():
    """Publish a mesh asset from admin-uploaded chunks (manifest + BSM1 anchor)."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    header_token = (request.headers.get("X-Chain-Mesh-Publish-Token") or "").strip()
    if header_token and not payload.get("publish_token"):
        payload = {**payload, "publish_token": header_token}
    if not _verify_mesh_publish_token(payload):
        return jsonify({"ok": False, "error": "invalid publish token"}), 403
    try:
        return jsonify(cm.publish_asset_payload(payload))
    except PermissionError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 403
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/chain-mesh/transfer/protocol")
def api_chain_mesh_transfer_protocol():
    """BSM2 mesh transfer protocol status and description."""
    import chain_mesh.api as cm

    return jsonify(cm.transfer_protocol_payload())


@app.route("/api/chain-mesh/transfer", methods=["POST"])
def api_chain_mesh_transfer_create():
    """Create a BSM2 file transfer (chunks must already be on mesh)."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.transfer_create_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/chain-mesh/transfer/<transfer_id>")
def api_chain_mesh_transfer_get(transfer_id):
    """Fetch BSM2 transfer manifest and replication status."""
    import chain_mesh.api as cm

    result = cm.transfer_get_payload(transfer_id)
    if not result.get("ok"):
        return jsonify(result), 404
    return jsonify(result)


@app.route("/api/chain-mesh/transfer/<transfer_id>/claim", methods=["POST"])
def api_chain_mesh_transfer_claim(transfer_id):
    """Recipient claims a ready transfer."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    result = cm.transfer_claim_payload(transfer_id, payload)
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)


@app.route("/api/chain-mesh/transfer/attest", methods=["POST"])
def api_chain_mesh_transfer_attest():
    """Miner hash-power attestation for relaying a transfer chunk."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.transfer_attest_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/chain-mesh/transfer/inbox/<recipient>")
def api_chain_mesh_transfer_inbox(recipient):
    """List transfers addressed to a STONE wallet."""
    import chain_mesh.api as cm

    status = request.args.get("status", "")
    return jsonify(cm.transfer_list_for_recipient(recipient, status=status))


@app.route("/api/network-chat/presence")
@app.route("/mining/api/network-chat/presence")
def api_network_chat_presence():
    import chain_mesh.api as cm

    public_ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()
    include_offline = request.args.get("include_offline", "").lower() in ("1", "true", "yes")
    limit = int(request.args.get("limit") or 120)
    return jsonify(
        cm.network_chat_presence_payload(
            public_ip=public_ip,
            include_offline=include_offline,
            limit=limit,
        )
    )


@app.route("/api/network-chat/heartbeat", methods=["POST"])
@app.route("/mining/api/network-chat/heartbeat", methods=["POST"])
def api_network_chat_heartbeat():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    public_ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()
    try:
        return jsonify(cm.network_chat_heartbeat_payload(payload, public_ip=public_ip))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/network-chat/lobby")
@app.route("/mining/api/network-chat/lobby")
def api_network_chat_lobby():
    import chain_mesh.api as cm

    if request.args.get("inbox", "").lower() in ("1", "true", "yes"):
        since_seq = int(request.args.get("since_seq") or 0)
        limit = int(request.args.get("limit") or 80)
        return jsonify(cm.network_chat_lobby_inbox_payload(since_seq=since_seq, limit=limit))
    return jsonify(cm.network_chat_lobby_payload())


@app.route("/api/network-chat/lobby/send", methods=["POST"])
@app.route("/mining/api/network-chat/lobby/send", methods=["POST"])
def api_network_chat_lobby_send():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.network_chat_lobby_send_payload(payload))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/network-chat/dm/open", methods=["POST"])
@app.route("/mining/api/network-chat/dm/open", methods=["POST"])
def api_network_chat_dm_open():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.network_chat_dm_open_payload(payload))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/network-chat/channels/<participant>")
@app.route("/mining/api/network-chat/channels/<participant>")
def api_network_chat_channels(participant):
    import chain_mesh.api as cm

    limit = int(request.args.get("limit") or 40)
    try:
        return jsonify(cm.network_chat_channels_payload(participant, limit=limit))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/chain-mesh/packet/protocol")
def api_chain_mesh_packet_protocol():
    """BSM3 mesh packet protocol status."""
    import chain_mesh.api as cm

    return jsonify(cm.packet_protocol_payload())


@app.route("/api/chain-mesh/packet/channel", methods=["POST"])
def api_chain_mesh_packet_channel_open():
    """Open a BSM3 virtual LAN channel between sender and recipient."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.packet_open_channel_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/chain-mesh/packet/channel/<channel_id>")
def api_chain_mesh_packet_channel_get(channel_id):
    """BSM3 channel status."""
    import chain_mesh.api as cm

    result = cm.packet_channel_payload(channel_id)
    if not result.get("ok"):
        return jsonify(result), 404
    return jsonify(result)


@app.route("/api/chain-mesh/packet/send", methods=["POST"])
def api_chain_mesh_packet_send():
    """Send a small datagram on a BSM3 channel (≤ 1400 bytes)."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.packet_send_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/chain-mesh/packet/inbox/<recipient>")
def api_chain_mesh_packet_inbox(recipient):
    """Poll received BSM3 packets for a recipient address or device_id."""
    import chain_mesh.api as cm

    try:
        return jsonify(
            cm.packet_inbox_payload(
                recipient,
                channel_id=request.args.get("channel_id", ""),
                since_seq=request.args.get("since_seq", 0, type=int),
                limit=request.args.get("limit", 50, type=int),
            )
        )
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/chain-mesh/packet/relay-queue")
def api_chain_mesh_packet_relay_queue():
    """Packets assigned to this miner for hash-power relay attestation."""
    import chain_mesh.api as cm

    device_id = request.args.get("device_id", "")
    try:
        return jsonify(
            cm.packet_relay_queue_payload(
                device_id,
                limit=request.args.get("limit", 8, type=int),
            )
        )
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/chain-mesh/packet/attest", methods=["POST"])
def api_chain_mesh_packet_attest():
    """Miner hash-power attestation for relaying a BSM3 packet."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.packet_attest_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/chain-mesh/packet/stream/<recipient>")
def api_chain_mesh_packet_stream(recipient):
    """SSE stream of BSM3 packets for a recipient (replaces polling)."""
    from chain_mesh import packet_stream as pkt_stream

    timeout = request.args.get("timeout", 300, type=int)
    return Response(
        pkt_stream.sse_events(recipient, timeout_sec=max(30, min(900, timeout))),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/api/chain-mesh/packet/anchors")
def api_chain_mesh_packet_anchors():
    """On-chain BSM3 channel anchors indexed from blocks."""
    import chain_mesh.api as cm

    return jsonify(
        cm.packet_anchors_payload(
            channel_id_prefix=request.args.get("channel_id_prefix", ""),
            limit=request.args.get("limit", 50, type=int),
        )
    )


@app.route("/api/chain-mesh/packet/anchors/refresh", methods=["POST"])
@admin_api_required
def api_chain_mesh_packet_anchors_refresh():
    """Rescan recent blocks for BSM3 anchors (admin)."""
    import chain_mesh.api as cm

    lookback = request.get_json(silent=True) or {}
    return jsonify(
        cm.packet_refresh_index_payload(
            lookback=int(lookback.get("lookback") or request.args.get("lookback", 500)),
        )
    )


@app.route("/api/chain-mesh/packet/peers-for/<recipient>")
def api_chain_mesh_packet_peers_for(recipient):
    """LAN endpoints that may serve BSM3 packet inbox (household P2P)."""
    import chain_mesh.api as cm

    return jsonify(
        cm.packet_peers_for_recipient(
            recipient,
            limit=request.args.get("limit", 16, type=int),
        )
    )


@app.route("/api/chain-mesh/tunnel/ip/protocol")
def api_chain_mesh_tunnel_ip_protocol():
    """BSM4 raw IPv4 tunnel over BSM3 mesh packets."""
    import chain_mesh.api as cm

    return jsonify(cm.ip_tunnel_protocol_payload())


@app.route("/api/chain-mesh/tunnel/ip/channel", methods=["POST"])
def api_chain_mesh_tunnel_ip_channel():
    """Open BSM4 tunnel channel (BSM3 + virtual subnet metadata)."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.ip_tunnel_open_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/chain-mesh/tunnel/ip/send", methods=["POST"])
def api_chain_mesh_tunnel_ip_send():
    """Send raw IPv4 datagram encapsulated in BSM3 (payload_type=ipv4)."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.ip_tunnel_send_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/chain-mesh/tunnel/ip/inbox/<recipient>")
def api_chain_mesh_tunnel_ip_inbox(recipient):
    """BSM3 inbox with decoded IPv4 headers for tunnel packets."""
    import chain_mesh.api as cm

    try:
        return jsonify(
            cm.ip_tunnel_inbox_payload(
                recipient,
                channel_id=request.args.get("channel_id", ""),
                since_seq=request.args.get("since_seq", 0, type=int),
                limit=request.args.get("limit", 50, type=int),
            )
        )
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/chain-mesh/tunnel/ip/gateway/status")
def api_chain_mesh_tunnel_ip_gateway_status():
    """BSM4 internet gateway status (mesh-gateway egress)."""
    import chain_mesh.api as cm

    return jsonify(cm.ip_gateway_status_payload())


@app.route("/api/chain-mesh/internet-gateway/register", methods=["POST"])
def api_chain_mesh_internet_gateway_register():
    """Register this device as a household internet gateway (share with LAN miners)."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    if not str(payload.get("public_ip") or "").strip():
        public_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
        if public_ip and "," in public_ip:
            public_ip = public_ip.split(",")[0].strip()
        if public_ip:
            payload = {**payload, "public_ip": public_ip}
    try:
        return jsonify(cm.internet_gateway_register_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/chain-mesh/internet-gateway/unregister", methods=["POST"])
def api_chain_mesh_internet_gateway_unregister():
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.internet_gateway_unregister_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/chain-mesh/internet-gateway/elected")
def api_chain_mesh_internet_gateway_elected():
    """Best household internet gateway for BSM4 tunnel recipient."""
    import chain_mesh.api as cm

    return jsonify(
        cm.internet_gateway_elect_payload(
            public_ip=request.args.get("public_ip", ""),
            requester_device_id=request.args.get("device_id", ""),
        )
    )


@app.route("/api/chain-mesh/internet-gateway/peer-egress", methods=["POST"])
def api_chain_mesh_internet_gateway_peer_egress():
    """Process pending packets for a peer gateway (server-side egress)."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.internet_gateway_peer_egress_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/chain-mesh/internet-gateway/pending/<device_id>")
def api_chain_mesh_internet_gateway_pending(device_id):
    """Pending IPv4 packets for APK/PC peer gateway to process locally."""
    import chain_mesh.api as cm

    try:
        return jsonify(
            cm.internet_gateway_pending_payload(
                device_id=device_id,
                limit=request.args.get("limit", 12, type=int),
            )
        )
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/chain-mesh/internet-gateway/reply", methods=["POST"])
def api_chain_mesh_internet_gateway_reply():
    """Submit peer-processed egress reply (APK fetch / PC local sockets)."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.internet_gateway_reply_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/chain-mesh/tunnel/ip/gateway/egress", methods=["POST"])
def api_chain_mesh_tunnel_ip_gateway_egress():
    """Process pending IPv4 packets for mesh internet egress."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(
            cm.ip_gateway_egress_payload(
                limit=int(payload.get("limit") or request.args.get("limit", 16)),
            )
        )
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/chain-mesh/tunnel/ip/tls/client-hello")
def api_chain_mesh_tunnel_ip_tls_client_hello():
    """Build a valid TLS ClientHello (openssl -msg) for mesh handshake flight 1."""
    import chain_mesh.api as cm

    try:
        return jsonify(
            cm.ip_tls_client_hello_template_payload(
                host=request.args.get("host", ""),
                connect_host=request.args.get("connect_host", ""),
                port=request.args.get("port", 0, type=int),
                session=request.args.get("session", "1") != "0",
            )
        )
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/chain-mesh/tunnel/ip/tls/client-flight2", methods=["POST"])
def api_chain_mesh_tunnel_ip_tls_client_flight2():
    """Build TLS client flight 2 (CCS + Finished) for mesh handshake relay."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.ip_tls_client_flight2_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/chain-mesh/tunnel/ip/tls/encrypt-app-data", methods=["POST"])
def api_chain_mesh_tunnel_ip_tls_encrypt_app_data():
    """Encrypt TLS 1.3 client application_data (HTTP request) after mesh handshake."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.ip_tls_encrypt_app_data_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/chain-mesh/tunnel/ip/tls/decrypt-app-data", methods=["POST"])
def api_chain_mesh_tunnel_ip_tls_decrypt_app_data():
    """Decrypt TLS 1.3 server application_data after mesh handshake."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.ip_tls_decrypt_app_data_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/chain-mesh/submit-asset", methods=["POST"])
def api_chain_mesh_submit_asset():
    """Queue a user mesh upload for admin approval (not published until approved)."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.submit_asset_payload(payload))
    except (ValueError, TypeError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/chain-mesh/pending-submissions", methods=["GET"])
@admin_api_required
def api_chain_mesh_pending_submissions():
    """List user uploads awaiting admin review."""
    import chain_mesh.api as cm

    status = (request.args.get("status") or "pending").strip().lower()
    limit = request.args.get("limit", 50, type=int)
    return jsonify(cm.pending_submissions_payload(status=status, limit=limit))


@app.route("/api/chain-mesh/pending-submissions/<int:submission_id>", methods=["GET"])
@admin_api_required
def api_chain_mesh_pending_submission(submission_id: int):
    import chain_mesh.api as cm

    payload = cm.pending_submission_payload(submission_id)
    if not payload.get("ok"):
        return jsonify(payload), 404
    return jsonify(payload)


@app.route("/api/chain-mesh/pending-submissions/<int:submission_id>/approve", methods=["POST"])
@admin_api_required
def api_chain_mesh_approve_submission(submission_id: int):
    """Approve a queued user upload and publish it to the chain mesh."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    result = cm.approve_submission_payload(submission_id, payload=payload)
    if not result.get("ok"):
        return jsonify(result), 400 if result.get("error") else 500
    return jsonify(result)


@app.route("/api/chain-mesh/pending-submissions/<int:submission_id>/reject", methods=["POST"])
@admin_api_required
def api_chain_mesh_reject_submission(submission_id: int):
    """Reject a queued user upload."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    result = cm.reject_submission_payload(submission_id, payload=payload)
    if not result.get("ok"):
        return jsonify(result), 400 if result.get("error") else 500
    return jsonify(result)


@app.route("/api/chain-mesh/peers-for/<chunk_hash>")
def api_chain_mesh_peers_for(chunk_hash):
    """List storage peers holding a chunk (for mesh recovery)."""
    import chain_mesh.api as cm

    public_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    if public_ip and "," in public_ip:
        public_ip = public_ip.split(",")[0].strip()
    return jsonify(cm.peers_for_chunk_payload(chunk_hash, requester_public_ip=public_ip))


@app.route("/api/chain-mesh/local-node", methods=["POST"])
def api_chain_mesh_local_node_register():
    """Register a device acting as a local VPS chain extension node."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.local_node_register(payload))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/chain-mesh/job-cache", methods=["GET", "POST"])
def api_chain_mesh_job_cache():
    """Cache or fetch last stratum job for offline mining on local nodes."""
    import chain_mesh.api as cm

    if request.method == "GET":
        device_id = (request.args.get("device_id") or "").strip()
        return jsonify(cm.job_cache_fetch(device_id))
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.job_cache_store(payload))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


def _api_local_node_lan_register():
    """Phone registers LAN RPC/stratum endpoint for same-network peer discovery."""
    import chain_mesh.api as cm

    payload = request.get_json(silent=True) or {}
    public_ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()
    try:
        return jsonify(cm.lan_register(payload, public_ip=public_ip))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/local-node/lan-register", methods=["POST"])
@app.route("/mining/api/local-node/lan-register", methods=["POST"])
def api_local_node_lan_register():
    return _api_local_node_lan_register()


def _api_local_node_nearby():
    """Return LAN nodes behind the same public IP (household / site discovery)."""
    import chain_mesh.api as cm

    public_ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()
    return jsonify(cm.lan_nearby(public_ip))


@app.route("/api/local-node/nearby")
@app.route("/mining/api/local-node/nearby")
def api_local_node_nearby():
    return _api_local_node_nearby()


def _api_local_node_rpc_relay():
    """Upstream RPC relay for Android pruned/gateway local nodes."""
    import local_node_gateway as lng

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(lng.relay_payload(payload))
    except ValueError as exc:
        return jsonify({"jsonrpc": "1.0", "id": payload.get("id"), "error": {"message": str(exc)}}), 400
    except Exception as exc:
        return jsonify({"jsonrpc": "1.0", "id": payload.get("id"), "error": {"message": str(exc)}}), 502


@app.route("/api/local-node/rpc", methods=["POST"])
@app.route("/mining/api/local-node/rpc", methods=["POST"])
def api_local_node_rpc_relay():
    return _api_local_node_rpc_relay()


@app.route("/api/chain-mesh/pending-shares", methods=["GET", "POST"])
def api_chain_mesh_pending_shares():
    """Queue shares mined offline; drain when device reconnects to pool."""
    import chain_mesh.api as cm

    if request.method == "GET":
        device_id = (request.args.get("device_id") or "").strip()
        return jsonify(cm.pending_shares_fetch(device_id))
    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(cm.pending_shares_store(payload))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


def _quasar_public_ip() -> str:
    public_ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()
    return public_ip


@app.route("/api/quasar/status")
@app.route("/mining/api/quasar/status")
def api_quasar_status():
    import bloodstone_quasar_api as qapi
    import node_rpc

    try:
        return jsonify(qapi.status_payload(node_rpc.rpc))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


@app.route("/api/quasar/witness/submit", methods=["POST"])
@app.route("/mining/api/quasar/witness/submit", methods=["POST"])
def api_quasar_witness_submit():
    import bloodstone_quasar_api as qapi

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(qapi.witness_submit(payload))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/quasar/witness/capsules")
@app.route("/mining/api/quasar/witness/capsules")
def api_quasar_witness_capsules():
    import bloodstone_quasar_api as qapi

    tip_hash = (request.args.get("tip_hash") or "").strip()
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    return jsonify(qapi.witness_list(tip_hash=tip_hash, limit=limit, offset=offset))


@app.route("/api/quasar/lan-echo", methods=["POST"])
@app.route("/mining/api/quasar/lan-echo", methods=["POST"])
def api_quasar_lan_echo():
    import bloodstone_quasar_api as qapi
    import node_rpc

    payload = request.get_json(silent=True) or {}
    try:
        return jsonify(
            qapi.lan_echo_submit(payload, public_ip=_quasar_public_ip(), rpc=node_rpc.rpc)
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/quasar/lan-echo/status")
@app.route("/mining/api/quasar/lan-echo/status")
def api_quasar_lan_echo_status():
    import bloodstone_quasar_api as qapi
    import node_rpc

    public_ip = (request.args.get("public_ip") or _quasar_public_ip()).strip()
    try:
        return jsonify(qapi.lan_echo_status_payload(public_ip=public_ip, rpc=node_rpc.rpc))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


@app.route("/api/quasar/alerts")
@app.route("/mining/api/quasar/alerts")
def api_quasar_alerts():
    import bloodstone_quasar_api as qapi
    import node_rpc

    try:
        return jsonify(qapi.alerts_payload(node_rpc.rpc))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


@app.route("/api/quasar/braid-index")
@app.route("/mining/api/quasar/braid-index")
def api_quasar_braid_index():
    import bloodstone_quasar_api as qapi
    import node_rpc

    sync = (request.args.get("sync") or "").strip().lower() in ("1", "true", "yes")
    try:
        return jsonify(qapi.braid_index_payload(sync=sync, rpc=node_rpc.rpc))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


@app.route("/api/quasar/enforcement/check", methods=["POST"])
@app.route("/mining/api/quasar/enforcement/check", methods=["POST"])
def api_quasar_enforcement_check():
    import bloodstone_quasar_api as qapi
    import node_rpc

    payload = request.get_json(silent=True) or {}
    amount = float(payload.get("amount_stone") or payload.get("amount") or 0)
    try:
        return jsonify(qapi.enforcement_check(amount, node_rpc.rpc))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


@app.route("/api/quasar/activation")
@app.route("/mining/api/quasar/activation")
def api_quasar_activation():
    import bloodstone_quasar_api as qapi

    return jsonify(qapi.activation_payload())


@app.route("/api/quasar/signaling")
@app.route("/mining/api/quasar/signaling")
def api_quasar_signaling():
    import bloodstone_quasar_api as qapi
    import node_rpc

    try:
        return jsonify(qapi.signaling_payload(node_rpc.rpc))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


@app.route("/api/quasar/fork-rehearsal")
@app.route("/mining/api/quasar/fork-rehearsal")
def api_quasar_fork_rehearsal():
    import bloodstone_quasar_api as qapi
    import node_rpc

    persist = (request.args.get("persist") or "").strip().lower() in ("1", "true", "yes")
    try:
        return jsonify(qapi.fork_rehearsal_payload(node_rpc.rpc, persist=persist))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


@app.route("/api/quasar/confirmations")
@app.route("/mining/api/quasar/confirmations")
def api_quasar_confirmations():
    import bloodstone_quasar_api as qapi
    import node_rpc

    try:
        return jsonify(qapi.confirmations_payload(node_rpc.rpc))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


@app.route("/api/pool/dual-stats")
def api_pool_dual_stats():
    """Per-chain dual-mining share/block counts (24h window by default)."""
    import pool_db

    address = (request.args.get("address") or request.args.get("stone_address") or "").strip()
    window = request.args.get("window_sec", 86400, type=int)
    window = max(300, min(int(window or 86400), 7 * 86400))
    return jsonify(pool_db.get_dual_chain_stats(address, window_sec=window))


@app.route("/api/pool/rod-wallet", methods=["GET", "POST", "DELETE"])
def api_pool_rod_wallet():
    """Link a STONE mining address to a SpaceXpanse ROD core wallet."""
    import pool_db

    if request.method == "GET":
        stone = (request.args.get("stone_address") or request.args.get("address") or "").strip()
        if not stone:
            return jsonify({"error": "stone_address required"}), 400
        rod = pool_db.get_miner_rod_wallet(stone)
        return jsonify(
            {
                "stone_address": stone,
                "rod_address": rod,
                "registered": bool(rod),
            }
        )

    payload = request.get_json(silent=True) or {}
    stone = (payload.get("stone_address") or request.args.get("stone_address") or "").strip()
    if not stone:
        return jsonify({"error": "stone_address required"}), 400

    if request.method == "DELETE":
        result = pool_db.set_miner_rod_wallet(stone, "")
        return jsonify(result)

    rod = (payload.get("rod_address") or "").strip()
    result = pool_db.set_miner_rod_wallet(stone, rod)
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)


@app.route("/api/pool/balance")
def api_unified_pool_balance():
    """Pending/paid balance across all three proportional pool algos."""
    import pool_db

    address = (request.args.get("address") or "").strip()
    if not address:
        return jsonify({"error": "address required"}), 400
    balance = pool_db.get_miner_balance(address)
    return jsonify(
        {
            "address": address,
            "algos": ["neoscrypt-xaya", "yespower", "sha256d"],
            "note": "Balances are shared across all pool algos",
            **balance,
        }
    )


@app.route("/api/mining/yespower-stats")
def api_yespower_stats():
    """Stats for browser miners: pool share difficulty vs chain block difficulty."""
    overview = cached_chain_overview()
    mining = overview["mining"]
    yespower_diff = float(mining.get("difficulty", {}).get("yespower", 0) or 0)
    share_diff = float(mining_config.POOLS["yespower"]["share_difficulty"])
    block_hashes = _expected_hashes(yespower_diff)
    share_hashes = _expected_hashes(share_diff)
    return jsonify(
        {
            "yespower_active": overview["yespower_active"],
            "network_difficulty": yespower_diff,
            "share_difficulty": share_diff,
            "share_easier_than_block": block_hashes / max(share_hashes, 1),
            "expected_hashes_per_block": block_hashes,
            "expected_hashes_per_share": share_hashes,
            "pool_block_miner": "active",
        }
    )


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if not app.config.get("ADMIN_PASSWORD_HASH"):
        flash("Admin login not configured.", "error")
        return redirect(url_for("index"))
    if request.method == "POST":
        password = request.form.get("password", "")
        creator_code = (request.form.get("master_creator_code") or "").strip()
        if check_password_hash(app.config["ADMIN_PASSWORD_HASH"], password):
            session["admin"] = True
            if creator_code and verify_master_creator_code(creator_code):
                session["master_creator"] = True
                flash("Master Creator access enabled for this session.", "success")
            return redirect(safe_redirect_target(request.args.get("next"), "admin"))
        flash("Incorrect admin password.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("admin", None)
    session.pop("master_creator", None)
    return redirect(url_for("index"))


@app.route("/admin/password", methods=["GET", "POST"])
@admin_required
def admin_change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not check_password_hash(app.config["ADMIN_PASSWORD_HASH"], current_password):
            flash("Current password is incorrect.", "error")
            return redirect(url_for("admin_change_password"))

        if len(new_password) < 8:
            flash("New password must be at least 8 characters.", "error")
            return redirect(url_for("admin_change_password"))

        if new_password != confirm_password:
            flash("New password and confirmation do not match.", "error")
            return redirect(url_for("admin_change_password"))

        if check_password_hash(app.config["ADMIN_PASSWORD_HASH"], new_password):
            flash("New password must be different from the current password.", "error")
            return redirect(url_for("admin_change_password"))

        save_admin_password_hash(generate_password_hash(new_password))
        flash("Admin password updated.", "success")
        return redirect(url_for("admin"))

    return render_template("admin_change_password.html")


@app.route("/admin/ssh-keys/generate", methods=["POST"])
@admin_required
def admin_ssh_generate():
    try:
        result = ssh_keys.generate_key_pair(
            request.form.get("key_name", ""),
            comment=(request.form.get("key_comment") or "").strip(),
        )
        session["ssh_key_generated"] = {
            "name": result["name"],
            "public_key": result["public_key"],
            "fingerprint": result["fingerprint"],
        }
        flash(
            f"SSH key pair '{result['name']}' created. Copy the public key below "
            f"into the other VPS authorized_keys.",
            "success",
        )
    except (ValueError, subprocess.CalledProcessError) as exc:
        flash(f"Could not generate SSH key: {exc}", "error")
    return redirect(url_for("admin"))


@app.route("/admin/ssh-keys/authorize", methods=["POST"])
@admin_required
def admin_ssh_authorize():
    try:
        row = ssh_keys.add_authorized_key(request.form.get("public_key", ""))
        flash(
            f"Authorized login key added ({row.get('fingerprint') or 'fingerprint unknown'}).",
            "success",
        )
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin"))


@app.route("/admin/ssh-keys/revoke", methods=["POST"])
@admin_required
def admin_ssh_revoke():
    try:
        ssh_keys.revoke_authorized_key(request.form.get("fingerprint", ""))
        flash("Authorized key removed from this server.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("admin"))


@app.route("/admin/ssh-keys/<name>.pub")
@admin_required
def admin_ssh_download_pub(name: str):
    try:
        pub = ssh_keys.read_public_key_file(name)
    except (ValueError, FileNotFoundError) as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin"))
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-") or "key"
    return Response(
        pub + "\n",
        mimetype="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{safe}.pub"'},
    )


def _restart_all_stratum():
    for pool_key in mining_config.POOLS:
        script = mining_config.POOLS[pool_key]["restart_script"]
        subprocess.Popen(
            ["/bin/bash", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


def _installer_icon_preview_url():
    public = os.environ.get("BLOODSTONE_PUBLIC_URL", PUBLIC_BASE_URL).rstrip("/")
    if public.endswith("/mining"):
        public = public[: -len("/mining")]
    return f"{public}/branding/installer-icon.png"


@app.route("/admin/master-creator/unlock", methods=["POST"])
@admin_required
def admin_master_creator_unlock():
    code = (request.form.get("master_creator_code") or "").strip()
    if verify_master_creator_code(code):
        session["master_creator"] = True
        flash("Master Creator access enabled.", "success")
    else:
        flash("Invalid Master Creator access code.", "error")
    return redirect(url_for("admin"))


@app.route("/admin/master-creator/logout", methods=["POST"])
@admin_required
def admin_master_creator_logout():
    session.pop("master_creator", None)
    flash("Master Creator edit access ended.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/fleet/device", methods=["POST"])
@admin_required
@master_creator_required
def admin_fleet_device_save():
    import pool_fleet_admin as pfa

    device_id = (request.form.get("device_id") or "").strip()
    if not device_id:
        flash("Device id missing.", "error")
        return redirect(url_for("admin"))
    fields = {
        key: request.form.get(key, "")
        for key in pfa.FLEET_DEVICE_FIELDS
    }
    if request.form.get("delete_device") == "1":
        if pfa.delete_fleet_device(device_id):
            flash("Fleet device removed.", "success")
        else:
            flash("Fleet device not found.", "error")
        return redirect(url_for("admin"))
    if pfa.update_fleet_device_admin(device_id, fields):
        flash("Fleet device updated.", "success")
    else:
        flash("Fleet device not found.", "error")
    return redirect(url_for("admin"))


@app.route("/admin/api/beta-codes/generate", methods=["POST"])
@admin_required
@master_creator_required
def admin_generate_beta_code():
    payload = request.get_json(silent=True) or {}
    label = (payload.get("label") or request.form.get("label") or "").strip()
    try:
        count = int(payload.get("count") or request.form.get("count") or 1)
    except (TypeError, ValueError):
        count = 1
    count = max(1, min(count, 20))
    codes = []
    for _ in range(count):
        row = bloodstone_beta_codes.generate_code(
            label=label,
            created_by="master-creator",
        )
        codes.append(row["code"])
    return jsonify({"ok": True, "count": len(codes), "codes": codes})


@app.route("/admin/api/beta-codes")
@admin_required
@master_creator_required
def admin_list_beta_codes():
    include_redeemed = (request.args.get("include_redeemed") or "1").strip() not in (
        "0",
        "false",
        "no",
    )
    rows = bloodstone_beta_codes.list_codes(include_redeemed=include_redeemed)
    return jsonify({"ok": True, "codes": rows})


@app.route("/admin/api/lan-validations")
@admin_required
@master_creator_required
def admin_list_lan_validations():
    rows = bloodstone_beta_codes.list_lan_validations()
    return jsonify({"ok": True, "validations": rows})


@app.route("/admin/fleet/settings", methods=["POST"])
@admin_required
@master_creator_required
def admin_fleet_settings_save():
    import pool_fleet_admin as pfa

    values = {}
    for key in pfa.all_field_keys():
        if key in request.form:
            values[key] = request.form.get(key, "")
    pfa.save_fleet_admin_values(values, updated_by="master-creator")
    flash("Fleet admin field overrides saved. Apply via “Save all settings” below.", "success")
    return redirect(url_for("admin"))


@app.route("/admin")
@admin_required
def admin():
    import pool_fleet_admin as pfa

    ensure_master_creator_configured()
    show_code = session.pop("master_creator_code_show_once", None)
    if show_code:
        flash(
            f"New Master Creator access code (save it now): {show_code}",
            "success",
        )

    mining_config.reload_pools()
    pools = cached_pools_status_light()
    faucet = faucet_settings.load_faucet_settings()
    pool_payout = pool_payout_settings.load_pool_payout_settings()
    overrides = mining_config.load_service_overrides()
    fleet_fields = pfa.merge_admin_context(faucet, pool_payout, overrides)
    installer_icon = installer_branding.get_icon_info()
    if installer_icon.get("configured"):
        installer_icon["preview_url"] = _installer_icon_preview_url()
    generated_key = session.pop("ssh_key_generated", None)
    import pool_db

    blocked_addresses = pool_db.list_blocked_addresses()
    x_ctx = wallet_oauth_settings.x_admin_context()
    return render_template(
        "admin.html",
        pools=pools,
        faucet=faucet,
        pool_payout=pool_payout,
        overrides=overrides,
        fleet_fields=fleet_fields,
        fleet_admin_sections=pfa.ADMIN_FIELD_SECTIONS,
        fleet_devices=pfa.list_fleet_devices_admin(include_inactive=True),
        master_creator=master_creator_active(),
        pool_keys=list(mining_config.POOLS.keys()),
        installer_icon=installer_icon,
        ssh_keys=ssh_keys.admin_snapshot(),
        ssh_key_generated=generated_key,
        service_sections=cached_admin_service_sections(),
        restart_groups=server_services.admin_restart_groups(),
        blocked_addresses=blocked_addresses,
        fmt_time=fmt_time,
        mesh_admin=True,
        **x_ctx,
    )


@app.route("/admin/faucet-abuse")
@admin_required
def admin_faucet_abuse():
    import faucet_settings

    sys.path.insert(0, "/root/bloodstone-faucet")
    sys.path.insert(0, "/root/bloodstone-wallet-web")
    import faucet_db
    import users_db

    faucet_db.init_db()
    users_db.init_db()
    limits = faucet_settings.load_faucet_settings()
    return render_template(
        "admin_faucet_abuse.html",
        limits=limits,
        registration_ips=users_db.registration_ip_stats(200),
        registration_devices=users_db.registration_device_stats(100),
        claim_ips=faucet_db.claim_ip_stats(200),
        ip_detail=None,
        ip_users=[],
        ip_claims=[],
        fmt_time=fmt_time,
    )


@app.route("/admin/faucet-abuse/ip/<path:ip>")
@admin_required
def admin_faucet_abuse_ip(ip):
    import faucet_settings

    sys.path.insert(0, "/root/bloodstone-faucet")
    sys.path.insert(0, "/root/bloodstone-wallet-web")
    import faucet_db
    import users_db

    faucet_db.init_db()
    users_db.init_db()
    limits = faucet_settings.load_faucet_settings()
    ip = (ip or "").strip()
    return render_template(
        "admin_faucet_abuse.html",
        limits=limits,
        registration_ips=users_db.registration_ip_stats(200),
        registration_devices=users_db.registration_device_stats(100),
        claim_ips=faucet_db.claim_ip_stats(200),
        ip_detail=ip,
        ip_users=users_db.users_for_ip(ip, 100),
        ip_claims=faucet_db.claims_for_ip(ip, 50),
        fmt_time=fmt_time,
    )


@app.route("/admin/mesh-publish-token")
@admin_api_required
def admin_mesh_publish_token():
    """Issue publish token to logged-in admin JS (never embedded on public pages)."""
    token = ensure_mesh_publish_token()
    return jsonify({"ok": True, "publish_token": token})


@app.route("/admin/generators")
@admin_required
def admin_generators():
    """Run white paper and release-note generator scripts."""
    return render_template("admin_generators.html")


@app.route("/admin/api/generators")
@admin_api_required
def admin_api_generators_catalog():
    import doc_generators as dg

    return jsonify(dg.catalog_payload())


@app.route("/admin/api/generators/<gen_id>/run", methods=["POST"])
@admin_api_required
def admin_api_generators_run(gen_id):
    import doc_generators as dg

    payload = request.get_json(silent=True) or {}
    result = dg.run_generator(
        gen_id,
        copy_downloads=bool(payload.get("copy_downloads", True)),
        publish_mesh=bool(payload.get("publish_mesh", False)),
        sync_worker=bool(payload.get("sync_worker", False)),
        triggered_by="admin-ui",
    )
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)


@app.route("/admin/api/node-patch/status")
@admin_api_required
def admin_node_patch_status():
    import node_live_patch as nlp

    return jsonify(nlp.admin_status())


@app.route("/admin/api/node-patch/apply", methods=["POST"])
@admin_api_required
@master_creator_required
def admin_node_patch_apply():
    import node_live_patch as nlp

    upload = request.files.get("patch_bundle")
    if not upload or not upload.filename:
        return jsonify({"ok": False, "error": "patch_bundle zip required"}), 400
    tmp_dir = os.path.join(nlp.PATCH_ROOT, "upload")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_zip = os.path.join(tmp_dir, f"upload-{int(time.time())}.zip")
    upload.save(tmp_zip)
    try:
        result = nlp.apply_patch_zip(tmp_zip)
        return jsonify(
            {
                "ok": True,
                "message": f"Applied patch {result.get('patch_version')}",
                **result,
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/admin/api/node-patch/publish", methods=["POST"])
@admin_api_required
@master_creator_required
def admin_node_patch_publish():
    import node_live_patch as nlp

    upload = request.files.get("patch_bundle")
    if not upload or not upload.filename:
        return jsonify({"ok": False, "error": "patch_bundle zip required"}), 400
    tmp_dir = os.path.join(nlp.PATCH_ROOT, "upload")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_zip = os.path.join(tmp_dir, f"publish-{int(time.time())}.zip")
    upload.save(tmp_zip)
    public_root = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    try:
        published = nlp.publish_patch_zip(tmp_zip, public_root=public_root)
        if os.path.isfile("/root/offload-bloodstone-downloads.sh"):
            subprocess.Popen(
                ["/bin/bash", "/root/offload-bloodstone-downloads.sh"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        return jsonify(
            {
                "ok": True,
                "message": f"Published patch {published.get('patch_version')}",
                **published,
            }
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/admin/api/node-patch/auto-apply", methods=["POST"])
@admin_api_required
@master_creator_required
def admin_node_patch_auto_apply():
    import node_live_patch as nlp

    public_root = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    try:
        result = nlp.maybe_auto_apply(public_root=public_root)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/admin/x-settings", methods=["POST"])
@admin_required
def admin_save_x_settings():
    """Save X OAuth credentials for the wallet web app (shared referrals DB)."""
    try:
        wallet_oauth_settings.save_x_settings(request.form)
        ctx = wallet_oauth_settings.x_admin_context()
        if ctx.get("x_oauth_ready") and ctx.get("x_oauth_probe_ok"):
            flash(
                "X sign-in settings saved. Credentials verified with X.",
                "success",
            )
        elif ctx.get("x_oauth_ready"):
            flash(
                "X settings saved, but X rejected the credentials: "
                + (ctx.get("x_oauth_probe_error") or "unknown error"),
                "error",
            )
        else:
            flash(
                "X settings saved. Add both client ID and client secret to enable sign-in.",
                "success",
            )
    except Exception as exc:
        flash(f"Could not save X settings: {exc}", "error")
    return redirect(url_for("admin"))


@app.route("/admin/settings", methods=["POST"])
@admin_required
@master_creator_required
def admin_save_settings():
    try:
        claim_amount = float(request.form.get("claim_amount", "25"))
        claim_cooldown_min_hours = int(
            float(request.form.get("claim_cooldown_min_hours", "3"))
        )
        claim_cooldown_max_hours = int(
            float(request.form.get("claim_cooldown_max_hours", "6"))
        )
        min_faucet_balance = float(request.form.get("min_faucet_balance", "0.5"))
        if (
            claim_amount <= 0
            or claim_cooldown_min_hours < 1
            or claim_cooldown_max_hours < 1
            or min_faucet_balance < 0
        ):
            raise ValueError("Invalid faucet values")

        max_accounts_per_ip = int(
            float(request.form.get("max_accounts_per_ip", "2"))
        )
        max_accounts_per_device = int(
            float(request.form.get("max_accounts_per_device", "2"))
        )
        enforce_device_binding = str(
            request.form.get("enforce_device_binding", "1")
        ).strip() not in ("0", "false", "no", "off")
        if max_accounts_per_ip < 1 or max_accounts_per_device < 1:
            raise ValueError("Account limits must be at least 1")

        faucet_settings.save_faucet_settings(
            claim_amount,
            claim_cooldown_min_hours,
            claim_cooldown_max_hours,
            min_faucet_balance,
            max_accounts_per_ip=max_accounts_per_ip,
            max_accounts_per_device=max_accounts_per_device,
            enforce_device_binding=enforce_device_binding,
        )

        payout_chunk_max = float(request.form.get("payout_chunk_max", "1000"))
        if payout_chunk_max <= 0:
            raise ValueError("Pool payout maximum must be positive")
        pool_payout_settings.save_pool_payout_settings(payout_chunk_max)

        import pool_sha256_miner as sm

        sha256_min_diff = float(
            request.form.get("sha256d_asic_diff_min", "1000000").strip()
        )
        sha256_max_diff = float(
            request.form.get("sha256d_asic_diff_max", "0").strip()
        )
        sha256_share_diff = float(
            request.form.get("sha256d_share_difficulty", "0.01").strip()
        )
        if sha256_min_diff <= 0:
            raise ValueError("SHA256 minimum difficulty must be positive")
        if sha256_max_diff < 0:
            raise ValueError("SHA256 maximum difficulty cannot be negative")
        if sha256_max_diff > 0 and sha256_max_diff < sha256_min_diff:
            raise ValueError(
                "SHA256 maximum difficulty cannot be below minimum"
            )
        if sha256_share_diff <= 0:
            raise ValueError("SHA256 share difficulty must be positive")

        neoscrypt_gpu_diff_max = float(
            request.form.get("neoscrypt_gpu_diff_max", "1000").strip()
        )
        yespower_gpu_diff_max = float(
            request.form.get("yespower_gpu_diff_max", "1000").strip()
        )
        if neoscrypt_gpu_diff_max <= 0 or yespower_gpu_diff_max <= 0:
            raise ValueError("GPU diff max must be positive")

        import pool_fleet_admin as pfa

        fleet_values = {
            key: request.form.get(key, "")
            for key in pfa.all_field_keys()
            if key in request.form
        }
        if fleet_values:
            pfa.save_fleet_admin_values(fleet_values, updated_by="master-creator")

        mining_config.save_service_overrides(
            {
                "MINER_VPS_IP": request.form.get("miner_vps_ip", mining_config.VPS_IP).strip(),
                "BLOODSTONE_STRATUM_PORT": str(
                    int(request.form.get("neoscrypt_port", "3437"))
                ),
                "BLOODSTONE_SHA256_STRATUM_PORT": str(
                    int(request.form.get("sha256d_port", "3429"))
                ),
                "BLOODSTONE_YESPOWER_STRATUM_PORT": str(
                    int(request.form.get("yespower_port", "3438"))
                ),
                "BLOODSTONE_NEOSCRYPT_SHARE_DIFFICULTY": request.form.get(
                    "neoscrypt_share_difficulty", "1e-8"
                ).strip(),
                "BLOODSTONE_SHA256_SHARE_DIFFICULTY": str(sha256_share_diff),
                "BLOODSTONE_SHA256_ASIC_DIFF_MIN": str(sha256_min_diff),
                "BLOODSTONE_SHA256_ASIC_DIFF_MAX": str(sha256_max_diff),
                "BLOODSTONE_SHA256_ROD_BLOCK_DIFF_MODE": (
                    "1"
                    if request.form.get("sha256d_rod_block_diff_mode") == "1"
                    else "0"
                ),
                "BLOODSTONE_YESPOWER_SHARE_DIFFICULTY": request.form.get(
                    "yespower_share_difficulty", "6e-8"
                ).strip(),
                "BLOODSTONE_NEOSCRYPT_GPU_SHARE_DIFFICULTY": request.form.get(
                    "neoscrypt_gpu_share_difficulty", "1e-6"
                ).strip(),
                "BLOODSTONE_YESPOWER_GPU_SHARE_DIFFICULTY": request.form.get(
                    "yespower_gpu_share_difficulty", "1e-6"
                ).strip(),
                "BLOODSTONE_NEOSCRYPT_GPU_DIFF_MAX": str(neoscrypt_gpu_diff_max),
                "BLOODSTONE_YESPOWER_GPU_DIFF_MAX": str(yespower_gpu_diff_max),
            }
        )
    except (TypeError, ValueError) as exc:
        flash(f"Settings not saved: {exc}", "error")
        return redirect(url_for("admin"))

    subprocess.Popen(
        ["systemctl", "restart", "bloodstone-faucet.service"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    if request.form.get("restart_stratum") == "1":
        _restart_all_stratum()
        flash(
            "Settings saved. Faucet restarted; all stratum pools restart triggered.",
            "success",
        )
    else:
        flash(
            "Settings saved and faucet restarted. "
            "Restart stratum pools for port/share changes to take effect.",
            "success",
        )
    return redirect(url_for("admin"))


@app.route("/admin/installer-icon", methods=["POST"])
@admin_required
def admin_upload_installer_icon():
    upload = request.files.get("installer_icon")
    if not upload or not upload.filename:
        flash("Choose a PNG file to upload.", "error")
        return redirect(url_for("admin"))
    try:
        result = installer_branding.save_uploaded_png(upload, uploaded_by="admin")
        flash(
            "Installer coin image saved and synced to GUI + Qt wallet assets "
            f"({result['width']}×{result['height']} px). "
            "Rebuild Qt wallet / Windows installers to publish a new download.",
            "success",
        )
    except ValueError as exc:
        flash(f"Installer image not saved: {exc}", "error")
    except OSError as exc:
        flash(f"Installer image not saved: {exc}", "error")
    return redirect(url_for("admin"))


@app.route("/admin/rebuild-android-apk", methods=["POST"])
@admin_required
def admin_rebuild_android_apk():
    script = "/root/build-bloodstone-miner-android-apk.sh"
    if not os.path.isfile(script):
        flash("Android APK build script not found on this VPS.", "error")
        return redirect(url_for("admin"))
    log_path = "/var/log/bloodstone-miner-android-apk-build.log"
    with open(log_path, "a", encoding="utf-8") as logfh:
        logfh.write(f"\n--- apk rebuild started {bloodstone_time.now_pacific()} ---\n")
    subprocess.Popen(
        ["/bin/bash", script],
        stdout=open(log_path, "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    flash(
        "Android APK build started in the background. "
        "Check /downloads/ in several minutes.",
        "success",
    )
    return redirect(url_for("admin"))


@app.route("/admin/rebuild-android-miner", methods=["POST"])
@admin_required
def admin_rebuild_android_miner():
    script = "/root/build-bloodstone-miner-android.sh"
    if not os.path.isfile(script):
        flash("Android miner build script not found on this VPS.", "error")
        return redirect(url_for("admin"))
    log_path = "/var/log/bloodstone-miner-android-build.log"
    with open(log_path, "a", encoding="utf-8") as logfh:
        logfh.write(f"\n--- rebuild started {bloodstone_time.now_pacific()} ---\n")
    subprocess.Popen(
        ["/bin/bash", script],
        stdout=open(log_path, "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    flash("Android miner source zip rebuild started.", "success")
    return redirect(url_for("admin"))


@app.route("/admin/rebuild-miner-desktop", methods=["POST"])
@admin_required
def admin_rebuild_miner_desktop():
    script = "/root/build-bloodstone-miner-desktop.sh"
    if not os.path.isfile(script):
        flash("Desktop miner build script not found on this VPS.", "error")
        return redirect(url_for("admin"))
    log_path = "/var/log/bloodstone-miner-desktop-build.log"
    with open(log_path, "a", encoding="utf-8") as logfh:
        logfh.write(f"\n--- rebuild started {bloodstone_time.now_pacific()} ---\n")
    subprocess.Popen(
        ["/bin/bash", script],
        stdout=open(log_path, "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    flash(
        "Desktop miner build started (Linux tarball + source zip). "
        "Check /downloads/ in several minutes.",
        "success",
    )
    return redirect(url_for("admin"))


@app.route("/admin/rebuild-miner-pack", methods=["POST"])
@admin_required
def admin_rebuild_miner_pack():
    script = "/root/build-bloodstone-miner-windows.sh"
    if not os.path.isfile(script):
        flash("Miner pack build script not found on this VPS.", "error")
        return redirect(url_for("admin"))
    log_path = "/var/log/bloodstone-miner-pack-build.log"
    with open(log_path, "a", encoding="utf-8") as logfh:
        logfh.write(f"\n--- rebuild started {bloodstone_time.now_pacific()} ---\n")
    subprocess.Popen(
        ["/bin/bash", script],
        stdout=open(log_path, "a", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    flash(
        "Windows CPU miner zip rebuild started in the background. "
        "Check /downloads/ in about a minute.",
        "success",
    )
    return redirect(url_for("admin"))


@app.route("/admin/rebuild-installers", methods=["POST"])
@admin_required
def admin_rebuild_installers():
    scripts = [
        "/root/build-bloodstone-node-gui-windows.sh",
        "/root/build-bloodstone-wallet-node-gui-windows.sh",
    ]
    started = []
    for script in scripts:
        if not os.path.isfile(script):
            continue
        subprocess.Popen(
            ["/bin/bash", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        started.append(os.path.basename(script))
    if not started:
        flash("No Windows GUI build scripts found on this VPS.", "error")
    else:
        flash(
            "Windows installer rebuild started in the background: "
            + ", ".join(started),
            "success",
        )
    return redirect(url_for("admin"))


@app.route("/admin/services/<service_id>/restart", methods=["POST"])
@admin_required
def admin_restart_service(service_id):
    try:
        unit = server_services.restart_service(service_id)
        flash(f"Restart triggered for {unit}.", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() or str(exc)
        flash(f"Restart failed for {service_id}: {detail}", "error")
    except subprocess.TimeoutExpired:
        flash(f"Restart timed out for {service_id}.", "error")
    return redirect(url_for("admin"))


@app.route("/admin/services/group/<group_id>/restart", methods=["POST"])
@admin_required
def admin_restart_service_group(group_id):
    try:
        units = server_services.restart_group(group_id)
        flash(
            f"Restart triggered for {len(units)} service(s): "
            + ", ".join(units),
            "success",
        )
    except ValueError as exc:
        flash(str(exc), "error")
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() or str(exc)
        flash(f"Group restart failed: {detail}", "error")
    except subprocess.TimeoutExpired:
        flash(f"Group restart timed out for {group_id}.", "error")
    return redirect(url_for("admin"))


@app.route("/admin/restart/<pool_key>", methods=["POST"])
@admin_required
def admin_restart(pool_key):
    if pool_key not in mining_config.POOLS:
        flash("Unknown pool.", "error")
        return redirect(url_for("admin"))
    script = mining_config.POOLS[pool_key]["restart_script"]
    try:
        subprocess.Popen(
            ["/bin/bash", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        flash(f"Restart triggered for {mining_config.POOLS[pool_key]['name']}.", "success")
    except OSError as exc:
        flash(f"Restart failed: {exc}", "error")
    return redirect(url_for("admin"))


@app.route("/live")
def live():
    """Fast liveness probe — no RPC (watchdog uses this)."""
    return jsonify({"ok": True, "service": "miner-web"})


@app.route("/health")
def health():
    return jsonify({"ok": True, "service": "miner-web"}), 200


def _start_background_cache_warmer() -> None:
    try:
        import fcntl

        lock_path = "/var/run/bloodstone-miner-cache-warm.lock"
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)
        fh = open(lock_path, "w", encoding="utf-8")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
    except Exception:
        return

    def _loop() -> None:
        time.sleep(8)
        while True:
            try:
                _cached_value(
                    "chain_overview",
                    _cache_ttl("MINER_CHAIN_OVERVIEW_CACHE_SEC", "45"),
                    _load_chain_overview,
                    blocking=True,
                )
            except Exception:
                pass
            try:
                _cached_value(
                    "pools_status_light",
                    _cache_ttl("MINER_POOLS_STATUS_LIGHT_CACHE_SEC", "30"),
                    pools_status_light,
                    blocking=True,
                )
            except Exception:
                pass
            try:
                _cached_value(
                    f"recent_blocks_{RECENT_BLOCKS}",
                    _cache_ttl("MINER_RECENT_BLOCKS_CACHE_SEC", "60"),
                    lambda: recent_blocks(RECENT_BLOCKS),
                    blocking=True,
                )
            except Exception:
                pass
            try:
                from stratum_status import (
                    neoscrypt_pool_accounting,
                    sha256_pool_accounting,
                    yespower_pool_accounting,
                )

                for pk, loader in (
                    ("yespower", yespower_pool_accounting),
                    ("neoscrypt", neoscrypt_pool_accounting),
                    ("sha256d", sha256_pool_accounting),
                ):
                    _cached_value(
                        f"pool_acct_{pk}",
                        _cache_ttl("MINER_POOL_ACCOUNTING_CACHE_SEC", "60"),
                        loader,
                        blocking=True,
                    )
            except Exception:
                pass
            time.sleep(45)

    threading.Thread(target=_loop, daemon=True, name="miner-cache-warm").start()


try:
    import pool_bitaxe as _pool_bitaxe

    _pool_bitaxe.start_poller()
except Exception:
    pass

def _start_bsm4_gateway_worker() -> None:
    """Background loop: forward mesh IPv4 frames to the real internet."""
    if os.environ.get("BSM4_GATEWAY_ENABLED", "1") != "1":
        return

    def _loop() -> None:
        time.sleep(6)
        while True:
            try:
                import chain_mesh.ip_gateway as gw

                if gw.GATEWAY_ENABLED:
                    gw.run_egress_batch()
            except Exception:
                pass
            time.sleep(max(2.0, float(os.environ.get("BSM4_GATEWAY_INTERVAL_SEC", "4"))))

    threading.Thread(target=_loop, daemon=True, name="bsm4-gateway").start()


if os.environ.get("BLOODSTONE_MINER_SKIP_WARMER") != "1":
    _start_background_cache_warmer()
    _start_bsm4_gateway_worker()
elif os.environ.get("BLOODSTONE_MINER_PAGES_ONLY") == "1":
    # Pages-only gunicorn (port 8893) — warm chain overview so algo flags are correct.
    def _pages_warm_once() -> None:
        time.sleep(2)
        try:
            _cached_value(
                "chain_overview",
                _cache_ttl("MINER_CHAIN_OVERVIEW_CACHE_SEC", "45"),
                _load_chain_overview,
                blocking=True,
            )
        except Exception:
            pass
        try:
            _cached_value(
                f"recent_blocks_{RECENT_BLOCKS}",
                _cache_ttl("MINER_RECENT_BLOCKS_CACHE_SEC", "60"),
                lambda: recent_blocks(RECENT_BLOCKS),
                blocking=True,
            )
        except Exception:
            pass

    threading.Thread(target=_pages_warm_once, daemon=True, name="pages-overview-warm").start()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8892, debug=False)