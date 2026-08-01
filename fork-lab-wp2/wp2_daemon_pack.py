"""WP2 T+0 daemon pack publisher.

- Process WP1 MFQ queue entries
- Publish real packs when zip already exists (STONE/LRGK/AZURE/…)
- For burn-launched coins without binaries: publish a *metadata pack* zip
  (COIN/PAYMENT/conf/README) + mfq-daemons manifest entry with
  usable_for_wallets=false until a real node build is attached
- Never claim a renamed bloodstoned as a child coin (historical bug)
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PUBLIC_ROOT = os.environ.get(
    "BLOODSTONE_PUBLIC_ROOT", "https://bloodstone.rocks"
).rstrip("/")
DAEMONS_DIR = Path(
    os.environ.get(
        "MFQ_DAEMONS_DIR", "/var/www/bloodstone/downloads/mfq-daemons"
    )
)
MANIFEST = Path(
    os.environ.get(
        "MFQ_DAEMONS_MANIFEST",
        "/var/www/bloodstone/downloads/mfq-daemons/manifest.json",
    )
)
MFQ_QUEUE = Path(
    os.environ.get(
        "FORK_LAB_MFQ_QUEUE",
        "/var/lib/bloodstone/fork_lab_mfq_queue.jsonl",
    )
)
REG = Path(os.environ.get("FORK_LAB_REGISTRY", "/root/bloodstone-fork-registry"))
CHAIN_ID_STATE = Path(
    os.environ.get(
        "FORK_LAB_AUXPOW_CHAIN_IDS",
        "/var/lib/bloodstone/fork_lab_auxpow_chain_ids.json",
    )
)

# Known wallet-usable packs (real binaries)
KNOWN_DAEMONS = {
    "STONE": {
        "daemon": "bloodstoned.exe",
        "cli": "bloodstone-cli.exe",
        "auxpow_chain_id": 1899,
        "usable_for_wallets": True,
    },
    "LRGK": {
        "daemon": "lrgkd.exe",
        "cli": "lrgk-cli.exe",
        "auxpow_chain_id": 1900,
        "usable_for_wallets": True,
    },
    "AZURE": {
        "daemon": "azured.exe",
        "cli": "azure-cli.exe",
        "auxpow_chain_id": 1901,
        "usable_for_wallets": True,
    },
}


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_manifest() -> Dict[str, Any]:
    if MANIFEST.is_file():
        try:
            return json.loads(MANIFEST.read_text())
        except Exception:
            pass
    return {
        "schema": "bloodstone/mfq-daemons/v2",
        "schema_version": "bloodstone/mfq-daemons/v2",
        "last_updated": _utc(),
        "updated": _utc()[:10],
        "notes": "WP2 managed manifest",
        "coins": {},
    }


def _save_manifest(man: Dict[str, Any]) -> None:
    DAEMONS_DIR.mkdir(parents=True, exist_ok=True)
    man["schema"] = "bloodstone/mfq-daemons/v2"
    man["schema_version"] = "bloodstone/mfq-daemons/v2"
    man["last_updated"] = _utc()
    man["updated"] = _utc()[:10]
    MANIFEST.write_text(json.dumps(man, indent=2) + "\n")


def next_auxpow_chain_id(ticker: str) -> int:
    """Allocate unique AuxPoW chain id (STONE 1899, LRGK 1900, AZURE 1901, next ≥1902)."""
    t = ticker.upper()
    if t in KNOWN_DAEMONS:
        return int(KNOWN_DAEMONS[t]["auxpow_chain_id"])
    state = {"next": 1902, "assigned": {}}
    if CHAIN_ID_STATE.is_file():
        try:
            state = json.loads(CHAIN_ID_STATE.read_text())
        except Exception:
            pass
    assigned = state.get("assigned") or {}
    if t in assigned:
        return int(assigned[t])
    # also respect manifest
    man = _load_manifest()
    used = set()
    for c in (man.get("coins") or {}).values():
        if isinstance(c, dict) and c.get("auxpow_chain_id") is not None:
            used.add(int(c["auxpow_chain_id"]))
    for v in assigned.values():
        used.add(int(v))
    used.update({1899, 1900, 1901})
    n = int(state.get("next") or 1902)
    while n in used:
        n += 1
    assigned[t] = n
    state["assigned"] = assigned
    state["next"] = n + 1
    CHAIN_ID_STATE.parent.mkdir(parents=True, exist_ok=True)
    CHAIN_ID_STATE.write_text(json.dumps(state, indent=2) + "\n")
    return n


def _coin_meta(ticker: str) -> Dict[str, Any]:
    t = ticker.upper()
    coin_path = REG / "coins" / t / "COIN.json"
    if coin_path.is_file():
        try:
            return json.loads(coin_path.read_text())
        except Exception:
            pass
    # WP1 draft detail
    try:
        import sys

        sys.path.insert(0, "/root/fork-lab-wp1")
        from wp1_db import connect, init

        init()
        with connect() as c:
            row = c.execute(
                "SELECT * FROM drafts WHERE upper(ticker)=? AND status='live'",
                (t,),
            ).fetchone()
        if row:
            detail = {}
            try:
                detail = json.loads(row["detail_json"] or "{}")
            except Exception:
                pass
            net = detail.get("net") or {}
            return {
                "ticker": t,
                "name": row["name"],
                "draft_id": row["draft_id"],
                "p2p_port": net.get("p2p_port") or 0,
                "rpc_port": net.get("rpc_port") or 0,
                "network_salt": net.get("network_salt") or "",
                "magic": net.get("magic_hint") or "",
                "creator_address": row["creator_address"],
                "burn_address": row["burn_address"],
            }
    except Exception:
        pass
    return {"ticker": t, "name": t}


def publish_metadata_pack(ticker: str, *, force: bool = False) -> Dict[str, Any]:
    """Write <TICKER>-win64.zip with registry artifacts (no fake node binary)."""
    t = ticker.upper()
    DAEMONS_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = DAEMONS_DIR / f"{t}-win64.zip"
    known = KNOWN_DAEMONS.get(t)
    # If a real wallet-usable pack already exists, do not overwrite
    if zip_path.is_file() and known and known.get("usable_for_wallets") and not force:
        return register_existing_pack(t)

    meta = _coin_meta(t)
    chain_id = next_auxpow_chain_id(t)
    pack_meta = {
        "schema": "bloodstone/mfq-daemon-pack/v1",
        "ticker": t,
        "kind": "metadata_only" if not known else "binary",
        "usable_for_wallets": bool(known and known.get("usable_for_wallets")),
        "auxpow_chain_id": chain_id,
        "p2p_port": int(meta.get("p2p_port") or 0),
        "rpc_port": int(meta.get("rpc_port") or 0),
        "built_utc": _utc(),
        "note": (
            "Metadata pack only — no node binary. Build offline with Fork Builder "
            "or attach a real win64 daemon pack. Do not rename bloodstoned."
            if not known
            else "Known binary pack"
        ),
        "offline_builder": f"{PUBLIC_ROOT}/downloads/bloodstone-fork-builder-latest.tar.gz",
        "coin_json": f"{PUBLIC_ROOT}/downloads/../"  # placeholder fixed below
    }
    # Prefer registry files
    coin_dir = REG / "coins" / t
    with tempfile.TemporaryDirectory(prefix=f"mfq-pack-{t}-") as td:
        stage = Path(td) / t
        stage.mkdir()
        if coin_dir.is_dir():
            for name in ("COIN.json", "PAYMENT.json", "README.md", "identity.json"):
                src = coin_dir / name
                if src.is_file():
                    shutil.copy2(src, stage / name)
            conf_src = coin_dir / "conf"
            if conf_src.is_dir():
                shutil.copytree(conf_src, stage / "conf", dirs_exist_ok=True)
        else:
            (stage / "COIN.json").write_text(json.dumps(meta, indent=2) + "\n")
        pack_meta["coin_json"] = f"coins/{t}/COIN.json"
        (stage / "PACK_META.json").write_text(json.dumps(pack_meta, indent=2) + "\n")
        (stage / "README-MFQ.txt").write_text(
            f"{t} MFQ daemon pack\n"
            f"kind={pack_meta['kind']}\n"
            f"usable_for_wallets={pack_meta['usable_for_wallets']}\n"
            f"auxpow_chain_id={chain_id}\n"
            f"Offline Fork Builder: {pack_meta['offline_builder']}\n"
            "Do not substitute bloodstoned.exe for a child coin.\n"
        )
        # zip
        if zip_path.is_file() and not force and known:
            pass
        else:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in stage.rglob("*"):
                    if p.is_file():
                        zf.write(p, arcname=str(p.relative_to(stage.parent)))

    return register_pack_file(
        t,
        zip_path,
        meta=meta,
        usable_for_wallets=bool(known and known.get("usable_for_wallets")),
        kind="binary" if known else "metadata_only",
        chain_id=chain_id,
        daemon=(known or {}).get("daemon") or f"{t.lower()}d.exe",
        cli=(known or {}).get("cli") or f"{t.lower()}-cli.exe",
    )


def register_existing_pack(ticker: str) -> Dict[str, Any]:
    t = ticker.upper()
    zip_path = DAEMONS_DIR / f"{t}-win64.zip"
    if not zip_path.is_file():
        return {"ok": False, "error": f"missing {zip_path}"}
    known = KNOWN_DAEMONS.get(t) or {}
    meta = _coin_meta(t)
    return register_pack_file(
        t,
        zip_path,
        meta=meta,
        usable_for_wallets=bool(known.get("usable_for_wallets", True)),
        kind="binary" if known else "binary_or_unknown",
        chain_id=int(known.get("auxpow_chain_id") or next_auxpow_chain_id(t)),
        daemon=known.get("daemon") or f"{t.lower()}d.exe",
        cli=known.get("cli") or f"{t.lower()}-cli.exe",
    )


def register_pack_file(
    ticker: str,
    zip_path: Path,
    *,
    meta: Dict[str, Any],
    usable_for_wallets: bool,
    kind: str,
    chain_id: int,
    daemon: str,
    cli: str,
) -> Dict[str, Any]:
    t = ticker.upper()
    sha = _sha256_file(zip_path)
    sha_path = Path(str(zip_path) + ".sha256")
    sha_path.write_text(f"{sha}  {zip_path.name}\n")
    url = f"{PUBLIC_ROOT}/downloads/mfq-daemons/{zip_path.name}"
    man = _load_manifest()
    coins = man.setdefault("coins", {})
    prev = coins.get(t) or {}
    entry = {
        "ticker": t,
        "name": meta.get("name") or prev.get("name") or t,
        "version": prev.get("version") or meta.get("version") or "0.0.1-wp2",
        "auxpow_chain_id": chain_id,
        "url": url,
        "download_url": url,
        "sha256": sha,
        "sha256_url": f"{url}.sha256",
        "daemon": daemon,
        "cli": cli,
        "rpc_port": int(meta.get("rpc_port") or prev.get("rpc_port") or 0),
        "p2p_port": int(meta.get("p2p_port") or prev.get("p2p_port") or 0),
        "platform": "win64",
        "identity": f"fork-lab-{t.lower()}",
        "usable_for_wallets": usable_for_wallets,
        "daemon_pack_status": "published" if usable_for_wallets else "metadata_only",
        "kind": kind,
        "public_peers": prev.get("public_peers") or meta.get("public_peers") or [],
        "public_peer": prev.get("public_peer") or "",
        "provenance": {
            "source_repo": "https://github.com/Bloodstone-Team/bloodstone",
            "source_path": f"bloodstone-fork-registry/coins/{t}",
            "source_commit": prev.get("provenance", {}).get("source_commit")
            or "WP2_CATALOG",
            "build_script": "fork-lab-wp2/wp2_daemon_pack.py publish",
            "built_utc": _utc(),
        },
        "draft_id": meta.get("draft_id") or prev.get("draft_id") or "",
        "offline_builder": f"{PUBLIC_ROOT}/downloads/bloodstone-fork-builder-latest.tar.gz",
    }
    # Preserve STONE/LRGK/AZURE richer fields
    if t in KNOWN_DAEMONS and prev:
        for k in ("version", "public_peer", "public_peers", "bech32_hrp", "name"):
            if prev.get(k):
                entry[k] = prev[k]
        if prev.get("provenance"):
            entry["provenance"] = prev["provenance"]
            entry["provenance"]["built_utc"] = entry["provenance"].get("built_utc") or _utc()
    coins[t] = entry
    _save_manifest(man)

    # refresh runtime catalog
    try:
        from wp2_catalog import write_catalog

        write_catalog()
    except Exception:
        pass

    # installer train pending if not wallet-usable yet still lists coin; if usable, mark for train
    try:
        from wp2_installer_train import enqueue_coin

        enqueue_coin(t, reason="daemon_pack_publish", usable=usable_for_wallets)
    except Exception:
        pass

    return {
        "ok": True,
        "ticker": t,
        "zip": str(zip_path),
        "sha256": sha,
        "url": url,
        "usable_for_wallets": usable_for_wallets,
        "kind": kind,
        "auxpow_chain_id": chain_id,
        "manifest_entry": entry,
    }


def process_queue(*, limit: int = 50) -> Dict[str, Any]:
    """Process MFQ queue jsonl; publish packs for queued tickers."""
    results = []
    if not MFQ_QUEUE.is_file():
        # Still ensure known packs registered + catalog fresh
        for t in KNOWN_DAEMONS:
            results.append(register_existing_pack(t))
        try:
            from wp2_catalog import write_catalog

            cat = write_catalog()
        except Exception as exc:
            cat = {"ok": False, "error": str(exc)}
        return {"ok": True, "processed": results, "queue_empty": True, "catalog": cat}

    lines = MFQ_QUEUE.read_text().splitlines()
    pending = []
    for line in lines[-500:]:
        line = line.strip()
        if not line:
            continue
        try:
            pending.append(json.loads(line))
        except Exception:
            continue
    # unique tickers, most recent first
    seen = set()
    tickers: List[str] = []
    for ev in reversed(pending):
        t = str(ev.get("ticker") or "").upper()
        if not t or t in seen:
            continue
        seen.add(t)
        tickers.append(t)
        if len(tickers) >= limit:
            break
    # always refresh known
    for t in KNOWN_DAEMONS:
        if t not in seen:
            tickers.append(t)

    for t in tickers:
        zip_path = DAEMONS_DIR / f"{t}-win64.zip"
        if t in KNOWN_DAEMONS and zip_path.is_file():
            results.append(register_existing_pack(t))
        else:
            results.append(publish_metadata_pack(t))

    try:
        from wp2_catalog import write_catalog

        cat = write_catalog()
    except Exception as exc:
        cat = {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "processed": results,
        "count": len(results),
        "catalog_count": cat.get("count") if isinstance(cat, dict) else None,
    }


def publish_ticker(ticker: str, *, force_metadata: bool = False) -> Dict[str, Any]:
    t = ticker.upper()
    zip_path = DAEMONS_DIR / f"{t}-win64.zip"
    if t in KNOWN_DAEMONS and zip_path.is_file() and not force_metadata:
        return register_existing_pack(t)
    if zip_path.is_file() and not force_metadata:
        # Existing zip — register (may be metadata or real)
        meta = _coin_meta(t)
        # detect PACK_META kind if present
        usable = t in KNOWN_DAEMONS
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                has_exe = any(n.lower().endswith(".exe") for n in names)
                usable = has_exe and usable or (
                    has_exe and t not in ("",) and t in KNOWN_DAEMONS
                )
                if has_exe and t not in KNOWN_DAEMONS:
                    # Real custom build attached later
                    usable = True
        except Exception:
            pass
        return register_pack_file(
            t,
            zip_path,
            meta=meta,
            usable_for_wallets=usable,
            kind="binary" if usable else "metadata_only",
            chain_id=next_auxpow_chain_id(t),
            daemon=KNOWN_DAEMONS.get(t, {}).get("daemon") or f"{t.lower()}d.exe",
            cli=KNOWN_DAEMONS.get(t, {}).get("cli") or f"{t.lower()}-cli.exe",
        )
    return publish_metadata_pack(t, force=force_metadata)
