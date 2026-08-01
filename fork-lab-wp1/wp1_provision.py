"""Provision coins/<TICKER>/ into bloodstone-fork-registry (WP1).

Also: seed-registry stub, runtime catalog row, MFQ daemon-pack queue entry.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wp1_db import connect, init, row_to_dict  # noqa: E402

REG = Path(os.environ.get("FORK_LAB_REGISTRY", "/root/bloodstone-fork-registry"))
CATALOG_PATH = Path(
    os.environ.get(
        "FORK_LAB_RUNTIME_CATALOG",
        "/var/www/bloodstone/downloads/fork-lab-runtime-catalog.json",
    )
)
MFQ_QUEUE = Path(
    os.environ.get(
        "FORK_LAB_MFQ_QUEUE",
        "/var/lib/bloodstone/fork_lab_mfq_queue.jsonl",
    )
)
SEED_STUB = Path(
    os.environ.get(
        "FORK_LAB_SEED_STUB",
        "/var/lib/bloodstone/fork_lab_seed_registry_stub.json",
    )
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def derive_network_params(seed: str) -> dict:
    """Deterministic salt/magic/ports from burn seed (txid preferred, else draft_id)."""
    material = f"bloodstone/fork-lab/netparams/v1|{seed}".encode()
    h = hashlib.sha256(material).digest()
    salt = h.hex()
    magic = "0x" + h[:4].hex()
    # Safe high port band 20000–44999; rpc = p2p+1
    p2p = 20000 + (int.from_bytes(h[4:6], "big") % 25000)
    rpc = p2p + 1
    if rpc > 65534:
        rpc = p2p - 1
    return {
        "network_salt": salt,
        "magic_hint": magic,
        "p2p_port": p2p,
        "rpc_port": rpc,
        "derive_seed": seed,
        "derive_scheme": "bloodstone/fork-lab/netparams/v1",
    }


def _burn_txs(draft_id: str) -> list:
    with connect() as c:
        rows = c.execute(
            """
            SELECT txid, vout, amount, confs, seen_at
              FROM burn_credits WHERE draft_id=? ORDER BY seen_at, vout
            """,
            (draft_id,),
        ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "txid": r["txid"],
                "vout": r["vout"],
                "amount_stone": str(r["amount"]),
                "confs": r["confs"],
                "seen_at": r["seen_at"],
            }
        )
    return out


def _update_runtime_catalog(entry: dict) -> None:
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cat = {
        "schema": "bloodstone/fork-lab-runtime-catalog/v1",
        "updated_utc": _utc(),
        "coins": [],
    }
    if CATALOG_PATH.is_file():
        try:
            cat = json.loads(CATALOG_PATH.read_text())
        except Exception:
            pass
    coins = [c for c in (cat.get("coins") or []) if c.get("ticker") != entry["ticker"]]
    coins.append(entry)
    coins.sort(key=lambda x: x.get("ticker") or "")
    cat["coins"] = coins
    cat["updated_utc"] = _utc()
    cat["count"] = len(coins)
    CATALOG_PATH.write_text(json.dumps(cat, indent=2) + "\n")


def _append_mfq_queue(entry: dict) -> None:
    MFQ_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with MFQ_QUEUE.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def _update_seed_stub(entry: dict) -> None:
    SEED_STUB.parent.mkdir(parents=True, exist_ok=True)
    stub = {
        "schema": "bloodstone/fork-lab-seed-registry-stub/v1",
        "note": (
            "Stub until coin operators publish real seeds. "
            "MFQ/edge clients should prefer live ecosystem seed registry for STONE."
        ),
        "updated_utc": _utc(),
        "coins": {},
    }
    if SEED_STUB.is_file():
        try:
            stub = json.loads(SEED_STUB.read_text())
        except Exception:
            pass
    coins = stub.get("coins") or {}
    coins[entry["ticker"]] = {
        "ticker": entry["ticker"],
        "draft_id": entry["draft_id"],
        "seeds": entry.get("seeds") or [],
        "status": "awaiting_operator_seeds",
        "updated_utc": _utc(),
    }
    stub["coins"] = coins
    stub["updated_utc"] = _utc()
    SEED_STUB.write_text(json.dumps(stub, indent=2) + "\n")
    # Mirror under downloads for operators
    pub = Path("/var/www/bloodstone/downloads/fork-lab-seed-registry-stub.json")
    try:
        pub.parent.mkdir(parents=True, exist_ok=True)
        pub.write_text(json.dumps(stub, indent=2) + "\n")
    except Exception:
        pass


def provision(draft_id: str) -> dict:
    init()
    with connect() as c:
        d = c.execute("SELECT * FROM drafts WHERE draft_id=?", (draft_id,)).fetchone()
    if not d:
        return {"ok": False, "error": "unknown draft"}
    d = row_to_dict(d)
    if d["status"] not in ("funded", "provisioning"):
        return {"ok": False, "error": f"draft status {d['status']} — need funded"}

    # Mark provisioning
    with connect() as c:
        c.execute(
            "UPDATE drafts SET status='provisioning' WHERE draft_id=? AND status='funded'",
            (draft_id,),
        )

    t = d["ticker"]
    coin_dir = REG / "coins" / t
    coin_dir.mkdir(parents=True, exist_ok=True)
    conf_dir = coin_dir / "conf"
    conf_dir.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    burn_txs = _burn_txs(draft_id)
    seed = (burn_txs[0]["txid"] if burn_txs else draft_id)
    net = derive_network_params(seed)

    payment = {
        "schema": "bloodstone/fork-lab-payment/v2",
        "draft_id": draft_id,
        "ticker": t,
        "burn_address": d["burn_address"],
        "amount_stone_required": str(d["fee_stone"]),
        "amount_stone_total": str(d.get("confirmed_total") or d["fee_stone"]),
        "burn_txs": burn_txs,
        "creator_address": d["creator_address"],
        "threshold_met_at": d.get("funded_at") or now,
        "created_utc": _utc(),
        "status": "threshold_met",
        "policy": "orphan_on_expiry_no_refund",
    }
    # PAYMENT.json immutable once written
    pay_path = coin_dir / "PAYMENT.json"
    if pay_path.is_file():
        try:
            existing = json.loads(pay_path.read_text())
            payment = existing  # never rewrite
        except Exception:
            pay_path.write_text(json.dumps(payment, indent=2) + "\n")
    else:
        pay_path.write_text(json.dumps(payment, indent=2) + "\n")

    coin = {
        "schema": "bloodstone/fork-lab-coin/v1",
        "ticker": t,
        "name": d["name"],
        "status": "live",
        "draft_id": draft_id,
        "creator_address": d["creator_address"],
        "burn_address": d["burn_address"],
        "fee_stone": d["fee_stone"],
        "network_salt": net["network_salt"],
        "magic": net["magic_hint"],
        "p2p_port": net["p2p_port"],
        "rpc_port": net["rpc_port"],
        "auxpow_parent": "STONE-SHA256d",
        "block_time_s": 90,
        "reward": "100",
        "premine": {"amount": "0", "address": "", "vesting": ""},
        "quasar_enabled": False,
        "algos": ["neoscrypt", "yespower", "sha256d"],
        "open_source": True,
        "launch": "burn-triggered",
        "provisioned_at": now,
        "provisioned_utc": _utc(),
        "derive": net,
        "note": "Provisioned by WP1 burn-triggered pipeline. Operator supplies seeds + binaries.",
    }
    (coin_dir / "COIN.json").write_text(json.dumps(coin, indent=2) + "\n")
    # Keep identity.json for earlier consumers
    (coin_dir / "identity.json").write_text(
        json.dumps(
            {
                "schema": "bloodstone/fork-lab-coin/v1",
                "ticker": t,
                "name": d["name"],
                "status": "live",
                "draft_id": draft_id,
                "creator_address": d["creator_address"],
                "burn_address": d["burn_address"],
                "fee_stone": d["fee_stone"],
                "provisioned_at": now,
                "open_source": True,
                "launch": "burn-triggered",
            },
            indent=2,
        )
        + "\n"
    )
    (coin_dir / "README.md").write_text(
        f"# {t}\n\n"
        f"Live via burn-triggered launch. Draft `{draft_id}`.\n\n"
        f"- Burn address: `{d['burn_address']}`\n"
        f"- Frozen fee: {d['fee_stone']} STONE\n"
        f"- P2P port: {net['p2p_port']} · RPC: {net['rpc_port']}\n"
        f"- Magic: `{net['magic_hint']}`\n\n"
        "PAYMENT.json is immutable. Operator publishes seeds when nodes are up.\n"
    )
    conf_example = (
        f"# {t} example conf (operator fills datadir / rpc creds)\n"
        f"server=1\n"
        f"txindex=1\n"
        f"port={net['p2p_port']}\n"
        f"rpcport={net['rpc_port']}\n"
        f"# addnode=…\n"
    )
    (conf_dir / f"{t.lower()}.conf.example").write_text(conf_example)

    catalog_entry = {
        "ticker": t,
        "name": d["name"],
        "status": "live",
        "draft_id": draft_id,
        "burn_address": d["burn_address"],
        "p2p_port": net["p2p_port"],
        "rpc_port": net["rpc_port"],
        "magic": net["magic_hint"],
        "network_salt": net["network_salt"],
        "auxpow_parent": "STONE-SHA256d",
        "algos": ["neoscrypt", "yespower", "sha256d"],
        "daemon_pack": f"{t}-win64.zip",
        "daemon_pack_status": "queued",
        "registry_path": f"coins/{t}/",
        "payment": f"coins/{t}/PAYMENT.json",
        "coin": f"coins/{t}/COIN.json",
        "listed_utc": _utc(),
    }
    _update_runtime_catalog(catalog_entry)
    _append_mfq_queue(
        {
            "event": "daemon_pack_needed",
            "ticker": t,
            "draft_id": draft_id,
            "queued_utc": _utc(),
            "artifact": f"{t}-win64.zip",
            "note": "T+0 queue entry — build pack when binaries exist; MFQ installer train ~24h",
        }
    )
    _update_seed_stub(
        {
            "ticker": t,
            "draft_id": draft_id,
            "seeds": [],
        }
    )

    with connect() as c:
        detail = {}
        try:
            detail = json.loads(d.get("detail_json") or "{}")
        except Exception:
            detail = {}
        detail["net"] = net
        detail["provisioned_utc"] = _utc()
        c.execute(
            """
            UPDATE drafts SET status='live', provisioned_at=?, detail_json=?
             WHERE draft_id=?
            """,
            (now, json.dumps(detail), draft_id),
        )

    return {
        "ok": True,
        "ticker": t,
        "path": str(coin_dir),
        "coin": coin,
        "payment": payment,
        "catalog_entry": catalog_entry,
        "runtime_catalog": str(CATALOG_PATH),
        "mfq_queue": str(MFQ_QUEUE),
        "seed_stub": str(SEED_STUB),
    }
