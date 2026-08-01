"""Discover STONE mainnet + all live Fork Lab child coins."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen

PUBLIC_ROOT = os.environ.get(
    "BLOODSTONE_PUBLIC_ROOT", "https://bloodstone.rocks"
).rstrip("/")

# WP2: remote runtime catalog (T+0 discoverability without local fork_lab.db)
RUNTIME_CATALOG_URL = os.environ.get(
    "MFQ_RUNTIME_CATALOG_URL",
    f"{PUBLIC_ROOT}/downloads/fork-lab-runtime-catalog.json",
)
RUNTIME_CATALOG_URLS = [
    u.strip()
    for u in os.environ.get(
        "MFQ_RUNTIME_CATALOG_URLS",
        f"{RUNTIME_CATALOG_URL},"
        f"{PUBLIC_ROOT}/api/fork-lab/runtime-catalog",
    ).split(",")
    if u.strip()
]

_HOME = Path.home()
_IS_WIN = sys.platform.startswith("win")


def _appdata() -> Path:
    if _IS_WIN:
        return Path(os.environ.get("APPDATA") or (_HOME / "AppData" / "Roaming"))
    return _HOME


def _local_appdata() -> Path:
    if _IS_WIN:
        return Path(
            os.environ.get("LOCALAPPDATA") or (_HOME / "AppData" / "Local")
        )
    return _HOME / ".local" / "share"


def _default_fork_lab_db() -> str:
    if os.environ.get("FORK_LAB_DB"):
        return os.environ["FORK_LAB_DB"]
    if _IS_WIN:
        local = (
            _local_appdata()
            / "Bloodstone"
            / "MultiForkQt"
            / "fork_lab.db"
        )
        if local.is_file():
            return str(local)
        return ""
    return "/var/lib/bloodstone/fork_lab.db"


FORK_LAB_DB = _default_fork_lab_db()


def _first_existing(*candidates: str) -> str:
    """Return first path that exists as a file; else first usable non-Linux-root candidate."""
    cleaned = []
    for c in candidates:
        if not c:
            continue
        # Never advertise Linux operator paths on Windows
        if _IS_WIN and (
            c.startswith("/root/")
            or c.startswith("/var/")
            or c.startswith("/home/")
        ):
            continue
        cleaned.append(c)
    for c in cleaned:
        if os.path.isfile(c):
            return c
    # Prefer a path the user can create on this platform
    for c in cleaned:
        if c:
            return c
    return ""


def conf_search_paths(ticker: str) -> List[str]:
    """Ordered conf candidates for a ticker on this OS."""
    t = (ticker or "").strip().upper()
    low = t.lower()
    app = _appdata()
    local = _local_appdata()
    home = _HOME
    mfq = local / "Bloodstone" / "MultiForkQt" / "rpc"
    paths: List[str] = []

    # Per-app managed confs (written by Settings → Create templates)
    paths.append(str(mfq / f"{low}.conf"))

    if t == "STONE":
        if os.environ.get("STONE_CONF"):
            paths.insert(0, os.environ["STONE_CONF"])
        paths.extend(
            [
                str(home / ".bloodstone" / "bloodstone.conf"),
                str(app / "Bloodstone" / "bloodstone.conf"),
                str(app / "Bloodstone" / "Bloodstone.conf"),
                str(app / "SpaceXpanse" / "bloodstone.conf"),
                str(app / "SpaceXpanse" / "spacexpanse.conf"),
            ]
        )
        if not _IS_WIN:
            paths.append(str(home / ".bloodstone" / "bloodstone.conf"))
    elif t == "LRGK":
        if os.environ.get("LRGK_CONF"):
            paths.insert(0, os.environ["LRGK_CONF"])
        paths.extend(
            [
                str(home / ".lrgk" / "lrgk.conf"),
                str(app / "LRGK" / "lrgk.conf"),
                str(app / ".lrgk" / "lrgk.conf"),
                str(app / "LilRaghnok" / "lrgk.conf"),
            ]
        )
        if not _IS_WIN:
            paths.append("/root/lrgk-chain/bootstrap-source/lrgk.conf")
    elif t == "AZURE":
        if os.environ.get("AZURE_CONF"):
            paths.insert(0, os.environ["AZURE_CONF"])
        paths.extend(
            [
                str(home / ".azure" / "azure.conf"),
                str(app / "AZURE" / "azure.conf"),
                str(app / ".azure" / "azure.conf"),
                str(app / "AzureGuardian" / "azure.conf"),
            ]
        )
        if not _IS_WIN:
            paths.append("/root/azure-chain/bootstrap-source/azure.conf")
    else:
        # Generic fork
        paths.extend(
            [
                str(mfq / f"{low}.conf"),
                str(home / f".{low}" / f"{low}.conf"),
                str(app / t / f"{low}.conf"),
                str(app / f".{low}" / f"{low}.conf"),
            ]
        )
        override = f"/var/lib/bloodstone/fork-rpc/{t}.conf"
        if not _IS_WIN:
            paths.append(override)

    # De-dupe preserving order
    seen = set()
    out = []
    for p in paths:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def resolve_conf(ticker: str, override: str = "") -> str:
    if override and os.path.isfile(override):
        return override
    if override and not _IS_WIN:
        # allow non-existing override so Settings can show intended path
        if override and not (
            _IS_WIN
            and (
                override.startswith("/root/")
                or override.startswith("/var/")
            )
        ):
            # still prefer existing
            pass
    if override:
        # If user set override, use it even if missing (they'll create it)
        if not (
            _IS_WIN
            and (
                override.startswith("/root/")
                or override.startswith("/var/")
                or override.startswith("/home/")
            )
        ):
            if os.path.isfile(override):
                return override
            # keep override if it looks like a Windows/local path
            return override
    return _first_existing(*conf_search_paths(ticker))


def _split_peers(*sources: Any) -> List[str]:
    """Normalize host:port seed lists from strings, lists, or env values."""
    out: List[str] = []
    seen = set()
    for src in sources:
        if src is None or src == "":
            continue
        items: List[str] = []
        if isinstance(src, (list, tuple, set)):
            items = [str(x) for x in src]
        else:
            # space / comma / semicolon separated
            raw = str(src).replace(",", " ").replace(";", " ")
            items = raw.split()
        for item in items:
            peer = item.strip()
            if not peer or peer in seen:
                continue
            seen.add(peer)
            out.append(peer)
    return out


def _default_public_peers(ticker: str) -> List[str]:
    """Official seed peers used for conf addnode= (all of them, not just one)."""
    t = ticker.upper()
    env_multi = os.environ.get(f"{t}_PUBLIC_PEERS", "").strip()
    env_one = os.environ.get(f"{t}_PUBLIC_PEER", "").strip()
    if env_multi or env_one:
        return _split_peers(env_multi, env_one)
    # Official mainnet / fork seeds (same endpoints bloodstone-qt / ops conf use)
    if t == "STONE":
        return ["64.188.22.190:17333", "192.119.82.145:17333"]
    if t == "LRGK":
        return ["64.188.22.190:33685"]
    if t == "AZURE":
        return ["64.188.22.190:29825"]
    return []


# Default RPC ports when conf missing (local daemons)
DEFAULT_RPC: Dict[str, Dict[str, Any]] = {
    "STONE": {
        "rpc_port": int(os.environ.get("STONE_RPC_PORT", "18332")),
        "p2p_port": int(os.environ.get("STONE_P2P_PORT", "17333")),
        "rpc_host": os.environ.get("STONE_RPC_HOST", "127.0.0.1"),
        "public_peers": _default_public_peers("STONE"),
        "public_peer": (_default_public_peers("STONE") or [""])[0],
        "name": "Bloodstone",
        "is_parent": True,
        "wallet_prefix": "webuser",
        "datadir_name": ".bloodstone",
        "description": "Bloodstone mainnet (STONE)",
    },
    "LRGK": {
        "rpc_port": 53685,
        "p2p_port": 33685,
        "rpc_host": os.environ.get("LRGK_RPC_HOST", "127.0.0.1"),
        "public_peers": _default_public_peers("LRGK"),
        "public_peer": (_default_public_peers("LRGK") or [""])[0],
        "name": "Lil Raghnok Coin",
        "is_parent": False,
        "wallet_prefix": "lrgkuser",
        "datadir_name": ".lrgk",
        "description": "Fork Lab sister chain",
    },
    "AZURE": {
        # Local MFQ default — NOT seed 49825 (Hyper-V excluded / seed clash).
        # Public seed node still uses 49825; MFQ wallets use a private port.
        "rpc_port": int(os.environ.get("AZURE_RPC_PORT", "18445")),
        "p2p_port": int(os.environ.get("AZURE_P2P_PORT", "29835")),
        "rpc_host": os.environ.get("AZURE_RPC_HOST", "127.0.0.1"),
        "public_peers": _default_public_peers("AZURE"),
        "public_peer": (_default_public_peers("AZURE") or [""])[0],
        "name": "Azure Guardian Coin",
        "is_parent": False,
        "wallet_prefix": "azureuser",
        "datadir_name": ".azure",
        "description": "Fork Lab sister chain",
    },
}


# Public seed P2P ports (server-side). Never treat these as "local MFQ listen"
# ports, and never invent seed peers from a local-only p2p_port (e.g. AZURE 29835).
_SEED_P2P_BY_TICKER = {
    "STONE": 17333,
    "AZURE": 29825,
    "LRGK": 33685,
}


def resolve_public_peers(
    ticker: str,
    *,
    meta: Optional[Dict[str, Any]] = None,
    coin: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Collect every seed peer for a coin (builtins, env, manifest, catalog)."""
    t = ticker.upper()
    known = DEFAULT_RPC.get(t) or {}
    meta = meta or {}
    coin = coin or {}
    peers = _split_peers(
        known.get("public_peers"),
        known.get("public_peer"),
        meta.get("public_peers"),
        meta.get("public_peer"),
        coin.get("public_peers"),
        coin.get("public_peer"),
    )
    if peers:
        return peers
    # Fallback only when no explicit seed list: seed host + *seed* P2P port
    # (not local MFQ listen port — that produced 64.188.22.190:29835).
    seed_p2p = int(_SEED_P2P_BY_TICKER.get(t) or 0)
    if not seed_p2p:
        seed_p2p = int(
            # Prefer explicit seed fields if present
            meta.get("seed_p2p_port")
            or coin.get("seed_p2p_port")
            or 0
        )
    if seed_p2p > 0:
        return [f"64.188.22.190:{seed_p2p}"]
    return []

_CACHE: Dict[str, Any] = {"at": 0.0, "coins": []}
# Fork Lab catalogue rarely changes — default 1 hour (was 20s).
_CACHE_TTL = float(os.environ.get("MFQ_CATALOG_TTL", "3600"))


def _icon_for(ticker: str, icon_url: str = "") -> str:
    if icon_url:
        return icon_url
    return f"{PUBLIC_ROOT}/downloads/fork-icons/{ticker.lower()}.png"


def _builtin_coin(ticker: str) -> Dict[str, Any]:
    t = ticker.upper()
    meta = DEFAULT_RPC.get(t) or {
        "rpc_port": 0,
        "p2p_port": 0,
        "rpc_host": "127.0.0.1",
        "public_peer": "",
        "public_peers": [],
        "name": t,
        "is_parent": False,
        "wallet_prefix": f"{t.lower()}user",
        "datadir_name": f".{t.lower()}",
        "description": "",
    }
    conf = resolve_conf(t)
    peers = resolve_public_peers(t, meta=meta)
    return {
        "ticker": t,
        "name": meta["name"],
        "fork_id": "mainnet" if t == "STONE" else "",
        "status": "live",
        "p2p_port": int(meta.get("p2p_port") or 0),
        "rpc_port": int(meta.get("rpc_port") or 0),
        "rpc_host": str(meta.get("rpc_host") or "127.0.0.1"),
        "conf": conf,
        "datadir_name": meta.get("datadir_name") or f".{t.lower()}",
        "public_peers": peers,
        "public_peer": peers[0] if peers else "",
        "icon_url": _icon_for(t),
        "description": meta.get("description") or "",
        "is_parent": bool(meta.get("is_parent")),
        "wallet_prefix": meta.get("wallet_prefix") or f"{t.lower()}user",
        "source": "builtin",
        "has_conf": bool(conf and os.path.isfile(conf)),
        "conf_candidates": conf_search_paths(t),
    }


def _normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    ticker = str(raw.get("ticker") or "").strip().upper()
    conf = str(raw.get("conf") or "")
    # Scrub Linux-only confs if they somehow appear on Windows
    if _IS_WIN and conf.startswith(("/root/", "/var/", "/home/")):
        conf = resolve_conf(ticker)
    peers = resolve_public_peers(ticker, coin=raw)
    return {
        "ticker": ticker,
        "name": str(raw.get("name") or ticker),
        "fork_id": str(raw.get("fork_id") or ""),
        "status": str(raw.get("status") or "live"),
        "p2p_port": int(raw.get("p2p_port") or 0),
        "rpc_port": int(raw.get("rpc_port") or 0),
        "rpc_host": str(raw.get("rpc_host") or "127.0.0.1"),
        "conf": conf,
        "datadir_name": str(raw.get("datadir_name") or f".{ticker.lower()}"),
        "public_peers": peers,
        "public_peer": peers[0] if peers else str(raw.get("public_peer") or ""),
        "icon_url": _icon_for(ticker, str(raw.get("icon_url") or "")),
        "description": str(raw.get("description") or "")[:400],
        "is_parent": bool(raw.get("is_parent")),
        "wallet_prefix": str(raw.get("wallet_prefix") or f"{ticker.lower()}user"),
        "source": str(raw.get("source") or "fork_lab"),
        "has_conf": bool(conf and os.path.isfile(conf)),
        "conf_candidates": list(raw.get("conf_candidates") or conf_search_paths(ticker)),
    }


def _from_fork_lab() -> List[Dict[str, Any]]:
    if not os.path.isfile(FORK_LAB_DB):
        return []
    try:
        con = sqlite3.connect(FORK_LAB_DB, timeout=8)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """
            SELECT fork_id, name, ticker, status, p2p_port, rpc_port,
                   icon_url, description, website
            FROM fork_coins
            WHERE lower(status) = 'live'
            ORDER BY created_at ASC
            """
        ).fetchall()
        con.close()
    except Exception:
        return []

    out: List[Dict[str, Any]] = []
    for row in rows:
        ticker = str(row["ticker"] or "").strip().upper()
        if not ticker or ticker == "STONE":
            continue
        known = DEFAULT_RPC.get(ticker) or {}
        peers = list(known.get("public_peers") or [])
        if not peers and known.get("public_peer"):
            peers = [str(known.get("public_peer"))]
        if not peers and row["p2p_port"]:
            peers = [f"64.188.22.190:{int(row['p2p_port'])}"]
        conf = resolve_conf(ticker)
        out.append(
            _normalize(
                {
                    "ticker": ticker,
                    "name": row["name"] or known.get("name") or ticker,
                    "fork_id": row["fork_id"] or "",
                    "status": row["status"] or "live",
                    "p2p_port": row["p2p_port"] or known.get("p2p_port") or 0,
                    "rpc_port": row["rpc_port"]
                    or known.get("rpc_port")
                    or 0,
                    "rpc_host": known.get("rpc_host") or "127.0.0.1",
                    "conf": conf,
                    "datadir_name": known.get("datadir_name")
                    or f".{ticker.lower()}",
                    "public_peers": peers,
                    "public_peer": peers[0] if peers else "",
                    "icon_url": row["icon_url"]
                    or _icon_for(ticker),
                    "description": row["description"]
                    or known.get("description")
                    or "",
                    "is_parent": False,
                    "wallet_prefix": known.get("wallet_prefix")
                    or f"{ticker.lower()}user",
                    "source": "fork_lab",
                    "conf_candidates": conf_search_paths(ticker),
                }
            )
        )
    return out


def _from_remote_catalog() -> List[Dict[str, Any]]:
    """WP2: pull live coins from public runtime catalog (works on Windows MFQ)."""
    data = None
    for url in RUNTIME_CATALOG_URLS:
        try:
            req = Request(url, headers={"User-Agent": "Bloodstone-MultiForkQt/WP2"})
            with urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and (data.get("coins") is not None):
                break
        except Exception:
            data = None
            continue
    if not isinstance(data, dict):
        return []
    out: List[Dict[str, Any]] = []
    for raw in data.get("coins") or []:
        if not isinstance(raw, dict):
            continue
        ticker = str(raw.get("ticker") or "").strip().upper()
        if not ticker or ticker == "STONE":
            continue
        # Skip non-live
        if str(raw.get("status") or "live").lower() not in ("live", "published"):
            continue
        known = DEFAULT_RPC.get(ticker) or {}
        peers = list(raw.get("public_peers") or [])
        if not peers and raw.get("public_peer"):
            peers = [str(raw.get("public_peer"))]
        if not peers and known.get("public_peers"):
            peers = list(known.get("public_peers") or [])
        if not peers and raw.get("p2p_port"):
            # Prefer seed host with catalog p2p only when no official peers
            peers = []
        conf = resolve_conf(ticker)
        desc = str(raw.get("description") or known.get("description") or "")
        if raw.get("daemon_pack_status") == "metadata_only":
            desc = (
                (desc + " " if desc else "")
                + "[daemon pack metadata only — build offline or wait for node binaries]"
            ).strip()
        out.append(
            _normalize(
                {
                    "ticker": ticker,
                    "name": raw.get("name") or known.get("name") or ticker,
                    "fork_id": raw.get("fork_id") or raw.get("draft_id") or "",
                    "status": raw.get("status") or "live",
                    "p2p_port": raw.get("p2p_port") or known.get("p2p_port") or 0,
                    "rpc_port": raw.get("rpc_port") or known.get("rpc_port") or 0,
                    "rpc_host": known.get("rpc_host") or "127.0.0.1",
                    "conf": conf,
                    "datadir_name": known.get("datadir_name") or f".{ticker.lower()}",
                    "public_peers": peers,
                    "public_peer": peers[0] if peers else "",
                    "icon_url": raw.get("icon_url") or _icon_for(ticker),
                    "description": desc[:400],
                    "is_parent": False,
                    "wallet_prefix": known.get("wallet_prefix")
                    or f"{ticker.lower()}user",
                    "source": "runtime_catalog",
                    "conf_candidates": conf_search_paths(ticker),
                    "daemon_pack_url": raw.get("daemon_pack_url") or "",
                    "daemon_pack_status": raw.get("daemon_pack_status") or "",
                    "usable_for_wallets": raw.get("usable_for_wallets"),
                }
            )
        )
    return out


def list_coins(
    *,
    force: bool = False,
    conf_overrides: Optional[Dict[str, str]] = None,
    rpc_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Return STONE first, then every live Fork Lab coin (AZURE, LRGK, …)."""
    now = time.time()
    if (
        not force
        and _CACHE["coins"]
        and (now - float(_CACHE["at"])) < _CACHE_TTL
        and not conf_overrides
        and not rpc_overrides
    ):
        return deepcopy(_CACHE["coins"])

    by_ticker: Dict[str, Dict[str, Any]] = {}

    # Built-ins (re-resolved each call so conf files created later are seen)
    for t in ("STONE", "AZURE", "LRGK"):
        by_ticker[t] = _builtin_coin(t)

    def _merge_coin(coin: Dict[str, Any], src_label: str) -> None:
        t = coin["ticker"]
        if t in by_ticker:
            base = by_ticker[t]
            for key in (
                "name",
                "fork_id",
                "p2p_port",
                "rpc_port",
                "icon_url",
                "description",
                "public_peer",
                "public_peers",
                "status",
                "daemon_pack_url",
                "daemon_pack_status",
                "usable_for_wallets",
            ):
                if coin.get(key) not in (None, "", []):
                    base[key] = coin[key]
            peers = resolve_public_peers(t, coin=base)
            if peers:
                base["public_peers"] = peers
                base["public_peer"] = peers[0]
            if coin.get("has_conf") and not base.get("has_conf"):
                base["conf"] = coin["conf"]
                base["has_conf"] = True
            prev = str(base.get("source") or "builtin")
            if src_label not in prev:
                base["source"] = f"{prev}+{src_label}"
        else:
            by_ticker[t] = coin

    for coin in _from_fork_lab():
        _merge_coin(coin, "fork_lab")

    # WP2 remote catalog (Windows clients; burn-launched coins without local DB)
    for coin in _from_remote_catalog():
        _merge_coin(coin, "runtime_catalog")

    conf_overrides = conf_overrides or {}
    rpc_overrides = rpc_overrides or {}

    for ticker, path in conf_overrides.items():
        t = str(ticker).upper()
        if t not in by_ticker:
            continue
        if path:
            # reject Linux-only paths on Windows
            if _IS_WIN and path.startswith(("/root/", "/var/", "/home/")):
                continue
            by_ticker[t]["conf"] = path
            by_ticker[t]["has_conf"] = os.path.isfile(path)

    for ticker, ov in rpc_overrides.items():
        t = str(ticker).upper()
        if t not in by_ticker or not isinstance(ov, dict):
            continue
        if ov.get("rpc_host"):
            by_ticker[t]["rpc_host"] = str(ov["rpc_host"])
        if ov.get("rpc_port"):
            try:
                by_ticker[t]["rpc_port"] = int(ov["rpc_port"])
            except (TypeError, ValueError):
                pass
        # stash credentials for CoinRPC (not shown in public overview unnecessarily)
        if ov.get("rpc_user"):
            by_ticker[t]["rpc_user"] = str(ov["rpc_user"])
        if ov.get("rpc_password"):
            by_ticker[t]["rpc_password"] = str(ov["rpc_password"])
        if ov.get("conf"):
            p = str(ov["conf"])
            if not (
                _IS_WIN and p.startswith(("/root/", "/var/", "/home/"))
            ):
                by_ticker[t]["conf"] = p
                by_ticker[t]["has_conf"] = os.path.isfile(p)

    order_rank = {"STONE": 0, "AZURE": 1, "LRGK": 2}

    def sort_key(c: Dict[str, Any]):
        return (order_rank.get(c["ticker"], 50), c["ticker"])

    coins = sorted(by_ticker.values(), key=sort_key)
    if not conf_overrides and not rpc_overrides:
        _CACHE["at"] = now
        _CACHE["coins"] = coins
    return deepcopy(coins)


def get_coin(
    ticker: str,
    *,
    conf_overrides: Optional[Dict[str, str]] = None,
    rpc_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    t = (ticker or "").strip().upper()
    for c in list_coins(
        conf_overrides=conf_overrides, rpc_overrides=rpc_overrides
    ):
        if c["ticker"] == t:
            return c
    return None


def default_rpc_template(ticker: str) -> Dict[str, Any]:
    """Suggested values for Settings / conf template generation."""
    t = (ticker or "").upper()
    meta = DEFAULT_RPC.get(t) or {}
    port = int(meta.get("rpc_port") or 0)
    p2p = int(meta.get("p2p_port") or 0)
    return {
        "ticker": t,
        "rpc_host": "127.0.0.1",
        "rpc_port": port,
        "p2p_port": p2p,
        "rpc_user": f"{t.lower()}rpc" if t != "STONE" else "bloodstone",
        "rpc_password": "",
        "conf_path": str(
            _local_appdata()
            / "Bloodstone"
            / "MultiForkQt"
            / "rpc"
            / f"{t.lower()}.conf"
        ),
        "search_paths": conf_search_paths(t),
    }
