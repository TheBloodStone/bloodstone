"""WP2 runtime catalog — merge Fork Lab live sources for MFQ / discoverability.

Sources (union by ticker):
  1. mfq-daemons/manifest.json (pack status)
  2. fork_lab.db live rows (legacy store path)
  3. WP1 live drafts (burn-triggered)
  4. bloodstone-fork-registry/coins/*/COIN.json
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PUBLIC_ROOT = os.environ.get(
    "BLOODSTONE_PUBLIC_ROOT", "https://bloodstone.rocks"
).rstrip("/")
CATALOG_PATH = Path(
    os.environ.get(
        "FORK_LAB_RUNTIME_CATALOG",
        "/var/www/bloodstone/downloads/fork-lab-runtime-catalog.json",
    )
)
FORK_LAB_DB = Path(os.environ.get("FORK_LAB_DB", "/var/lib/bloodstone/fork_lab.db"))
WP1_DB = Path(os.environ.get("FORK_LAB_WP1_DB", "/var/lib/bloodstone/fork_lab_wp1.db"))
REG = Path(os.environ.get("FORK_LAB_REGISTRY", "/root/bloodstone-fork-registry"))
MANIFEST = Path(
    os.environ.get(
        "MFQ_DAEMONS_MANIFEST",
        "/var/www/bloodstone/downloads/mfq-daemons/manifest.json",
    )
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _from_manifest() -> Dict[str, Dict[str, Any]]:
    data = _load_json(MANIFEST) or {}
    coins = data.get("coins") or {}
    out: Dict[str, Dict[str, Any]] = {}
    for t, c in coins.items():
        if not isinstance(c, dict):
            continue
        ticker = str(c.get("ticker") or t).upper()
        out[ticker] = {
            "ticker": ticker,
            "name": c.get("name") or ticker,
            "status": "live",
            "source": "mfq_manifest",
            "p2p_port": int(c.get("p2p_port") or 0),
            "rpc_port": int(c.get("rpc_port") or 0),
            "daemon_pack": f"{ticker}-win64.zip",
            "daemon_pack_url": c.get("url") or c.get("download_url") or "",
            "daemon_pack_sha256": c.get("sha256") or "",
            "daemon_pack_status": (
                "published"
                if c.get("usable_for_wallets")
                else c.get("daemon_pack_status") or "published"
            ),
            "usable_for_wallets": bool(c.get("usable_for_wallets", True)),
            "daemon": c.get("daemon") or "",
            "cli": c.get("cli") or "",
            "auxpow_chain_id": c.get("auxpow_chain_id"),
            "public_peers": c.get("public_peers")
            or ([c["public_peer"]] if c.get("public_peer") else []),
            "version": c.get("version") or "",
            "algos": c.get("algos") or ["neoscrypt", "yespower", "sha256d"],
            "auxpow_parent": "STONE-SHA256d",
        }
    return out


def _from_fork_lab_db() -> Dict[str, Dict[str, Any]]:
    if not FORK_LAB_DB.is_file():
        return {}
    try:
        con = sqlite3.connect(str(FORK_LAB_DB), timeout=10)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """
            SELECT fork_id, name, ticker, status, p2p_port, rpc_port,
                   network_salt, magic_hint, icon_url, description,
                   creator_address, fee_stone, created_at
              FROM fork_coins
             WHERE lower(status) = 'live'
             ORDER BY created_at ASC
            """
        ).fetchall()
        con.close()
    except Exception:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        t = str(r["ticker"] or "").upper()
        if not t or t == "STONE":
            continue
        out[t] = {
            "ticker": t,
            "name": r["name"] or t,
            "status": "live",
            "source": "fork_lab_db",
            "fork_id": r["fork_id"],
            "draft_id": "",
            "p2p_port": int(r["p2p_port"] or 0),
            "rpc_port": int(r["rpc_port"] or 0),
            "network_salt": r["network_salt"] or "",
            "magic": r["magic_hint"] or "",
            "icon_url": r["icon_url"] or f"{PUBLIC_ROOT}/downloads/fork-icons/{t.lower()}.png",
            "description": (r["description"] or "")[:400],
            "creator_address": r["creator_address"] or "",
            "fee_stone": r["fee_stone"],
            "daemon_pack": f"{t}-win64.zip",
            "daemon_pack_url": f"{PUBLIC_ROOT}/downloads/mfq-daemons/{t}-win64.zip",
            "daemon_pack_status": "unknown",
            "algos": ["neoscrypt", "yespower", "sha256d"],
            "auxpow_parent": "STONE-SHA256d",
            "registry_path": f"coins/{t}/",
        }
    return out


def _from_wp1() -> Dict[str, Dict[str, Any]]:
    if not WP1_DB.is_file():
        return {}
    try:
        con = sqlite3.connect(str(WP1_DB), timeout=10)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """
            SELECT draft_id, ticker, name, status, burn_address, creator_address,
                   fee_stone, confirmed_total, detail_json, funded_at, provisioned_at
              FROM drafts WHERE status = 'live'
            """
        ).fetchall()
        con.close()
    except Exception:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        t = str(r["ticker"] or "").upper()
        if not t:
            continue
        detail = {}
        try:
            detail = json.loads(r["detail_json"] or "{}")
        except Exception:
            detail = {}
        net = detail.get("net") or {}
        out[t] = {
            "ticker": t,
            "name": r["name"] or t,
            "status": "live",
            "source": "wp1_burn",
            "draft_id": r["draft_id"],
            "burn_address": r["burn_address"],
            "creator_address": r["creator_address"],
            "fee_stone": r["fee_stone"],
            "confirmed_total": r["confirmed_total"],
            "p2p_port": int(net.get("p2p_port") or 0),
            "rpc_port": int(net.get("rpc_port") or 0),
            "network_salt": net.get("network_salt") or "",
            "magic": net.get("magic_hint") or "",
            "daemon_pack": f"{t}-win64.zip",
            "daemon_pack_url": f"{PUBLIC_ROOT}/downloads/mfq-daemons/{t}-win64.zip",
            "daemon_pack_status": "queued",
            "launch": "burn-triggered",
            "algos": ["neoscrypt", "yespower", "sha256d"],
            "auxpow_parent": "STONE-SHA256d",
            "registry_path": f"coins/{t}/",
            "payment": f"coins/{t}/PAYMENT.json",
            "coin": f"coins/{t}/COIN.json",
            "provisioned_at": r["provisioned_at"],
        }
    return out


def _from_registry() -> Dict[str, Dict[str, Any]]:
    coins_dir = REG / "coins"
    if not coins_dir.is_dir():
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for d in sorted(coins_dir.iterdir()):
        if not d.is_dir():
            continue
        coin = _load_json(d / "COIN.json") or _load_json(d / "identity.json") or {}
        t = str(coin.get("ticker") or d.name).upper()
        if not t:
            continue
        out[t] = {
            "ticker": t,
            "name": coin.get("name") or t,
            "status": coin.get("status") or "live",
            "source": "registry",
            "draft_id": coin.get("draft_id") or "",
            "burn_address": coin.get("burn_address") or "",
            "creator_address": coin.get("creator_address") or "",
            "p2p_port": int(coin.get("p2p_port") or 0),
            "rpc_port": int(coin.get("rpc_port") or 0),
            "network_salt": coin.get("network_salt") or "",
            "magic": coin.get("magic") or coin.get("magic_hint") or "",
            "fee_stone": coin.get("fee_stone"),
            "algos": coin.get("algos")
            or ["neoscrypt", "yespower", "sha256d"],
            "auxpow_parent": coin.get("auxpow_parent") or "STONE-SHA256d",
            "daemon_pack": f"{t}-win64.zip",
            "daemon_pack_url": f"{PUBLIC_ROOT}/downloads/mfq-daemons/{t}-win64.zip",
            "daemon_pack_status": "unknown",
            "registry_path": f"coins/{t}/",
            "payment": f"coins/{t}/PAYMENT.json",
            "coin": f"coins/{t}/COIN.json",
            "launch": coin.get("launch") or "",
        }
    return out


def _merge_entry(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Prefer non-empty overlay fields; keep pack published status if better."""
    out = dict(base)
    for k, v in overlay.items():
        if v in (None, "", [], {}):
            continue
        if k == "daemon_pack_status":
            rank = {
                "published": 4,
                "metadata_only": 3,
                "queued": 2,
                "pending_build": 1,
                "unknown": 0,
            }
            if rank.get(str(v), 0) >= rank.get(str(out.get(k) or "unknown"), 0):
                out[k] = v
            continue
        if k == "source" and out.get("source"):
            # accumulate sources
            prev = str(out["source"])
            if str(v) not in prev.split("+"):
                out["source"] = f"{prev}+{v}"
            continue
        if k in ("p2p_port", "rpc_port") and int(out.get(k) or 0) and not int(v or 0):
            continue
        out[k] = v
    return out


def build_catalog() -> Dict[str, Any]:
    """Merge all sources into a single runtime catalog document."""
    layers = [
        _from_registry(),
        _from_wp1(),
        _from_fork_lab_db(),
        _from_manifest(),  # pack status wins for download URLs
    ]
    merged: Dict[str, Dict[str, Any]] = {}
    for layer in layers:
        for t, entry in layer.items():
            if t in merged:
                merged[t] = _merge_entry(merged[t], entry)
            else:
                merged[t] = dict(entry)

    # Normalize public fields
    coins: List[Dict[str, Any]] = []
    for t in sorted(merged.keys(), key=lambda x: (0 if x == "STONE" else 1, x)):
        e = merged[t]
        e.setdefault("ticker", t)
        e.setdefault("status", "live")
        e.setdefault("daemon_pack", f"{t}-win64.zip")
        if not e.get("daemon_pack_url"):
            e["daemon_pack_url"] = (
                f"{PUBLIC_ROOT}/downloads/mfq-daemons/{t}-win64.zip"
            )
        # mark pack presence on disk
        zip_path = Path(
            f"/var/www/bloodstone/downloads/mfq-daemons/{t}-win64.zip"
        )
        if zip_path.is_file() and e.get("daemon_pack_status") in (
            "unknown",
            "queued",
            "pending_build",
            None,
            "",
        ):
            e["daemon_pack_status"] = (
                "published"
                if e.get("usable_for_wallets", True)
                else e.get("daemon_pack_status") or "metadata_only"
            )
            if not e.get("daemon_pack_sha256"):
                try:
                    import hashlib

                    h = hashlib.sha256(zip_path.read_bytes()).hexdigest()
                    e["daemon_pack_sha256"] = h
                except Exception:
                    pass
        e["icon_url"] = e.get("icon_url") or (
            f"{PUBLIC_ROOT}/downloads/fork-icons/{t.lower()}.png"
        )
        coins.append(e)

    return {
        "ok": True,
        "schema": "bloodstone/fork-lab-runtime-catalog/v1",
        "updated_utc": _utc(),
        "public_root": PUBLIC_ROOT,
        "mfq_daemons_base": f"{PUBLIC_ROOT}/downloads/mfq-daemons",
        "count": len(coins),
        "coins": coins,
        "note": (
            "T+0 catalog for MFQ / portal. Daemon packs may be metadata-only "
            "until real win64 binaries are built; usable_for_wallets false then."
        ),
    }


def write_catalog(path: Optional[Path] = None) -> Dict[str, Any]:
    cat = build_catalog()
    dest = Path(path or CATALOG_PATH)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(cat, indent=2) + "\n")
    # stable latest alias not needed — single path
    cat["path"] = str(dest)
    return cat


def get_catalog(*, rebuild: bool = False) -> Dict[str, Any]:
    if rebuild or not CATALOG_PATH.is_file():
        return write_catalog()
    data = _load_json(CATALOG_PATH)
    if not isinstance(data, dict):
        return write_catalog()
    # Rebuild if older than 5 minutes
    try:
        mtime = CATALOG_PATH.stat().st_mtime
        if time.time() - mtime > 300:
            return write_catalog()
    except Exception:
        pass
    data.setdefault("ok", True)
    data["path"] = str(CATALOG_PATH)
    return data
