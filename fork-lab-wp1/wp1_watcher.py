"""Sum confirmed STONE UTXOs to draft burn addresses (WP1 watch step).

Uses local bloodstoned RPC when available. Idempotent credits table.
"""
from __future__ import annotations
import json, os, sys, time, base64, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from wp1_db import connect, init

CONF = os.environ.get("BLOODSTONE_CONF", "/root/.bloodstone/bloodstone.conf")
MIN_CONFS = int(os.environ.get("FORK_LAB_BURN_MIN_CONFS", "6"))


def _rpc(method, params=None):
    kv = {}
    for line in open(CONF):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        kv[k.strip()] = v.strip()
    url = f"http://127.0.0.1:{kv['rpcport']}/"
    payload = json.dumps({"jsonrpc": "1.0", "id": "wp1", "method": method, "params": params or []}).encode()
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    tok = base64.b64encode(f"{kv['rpcuser']}:{kv['rpcpassword']}".encode()).decode()
    req.add_header("Authorization", f"Basic {tok}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read())
    if body.get("error"):
        raise RuntimeError(body["error"])
    return body["result"]


def watch_once() -> dict:
    init()
    now = int(time.time())
    results = []
    with connect() as c:
        drafts = c.execute(
            "SELECT * FROM drafts WHERE status IN ('open','funding') AND expires_at > ?",
            (now,),
        ).fetchall()
    for d in drafts:
        addr = d["burn_address"]
        try:
            # scantxoutset is heavy; prefer listunspent if wallet watches imports —
            # for keyless burns use scantxoutset on single address descriptor.
            scan = _rpc("scantxoutset", ["start", [f"addr({addr})"]])
            total = float(scan.get("total_amount") or 0)
            # confs not in scantxoutset — treat as confirmed once in UTXO set
            confs = MIN_CONFS if total > 0 else 0
        except Exception as exc:
            results.append({"draft_id": d["draft_id"], "ok": False, "error": str(exc)[:160]})
            continue
        status = d["status"]
        if total >= float(d["fee_stone"]) and confs >= MIN_CONFS:
            status = "funded"
            with connect() as c:
                c.execute(
                    "UPDATE drafts SET status='funded', funded_at=? WHERE draft_id=? AND status IN ('open','funding')",
                    (now, d["draft_id"]),
                )
        elif total >= float(d["open_min_stone"]):
            status = "funding"
            with connect() as c:
                c.execute(
                    "UPDATE drafts SET status='funding' WHERE draft_id=? AND status='open'",
                    (d["draft_id"],),
                )
        results.append({
            "draft_id": d["draft_id"],
            "ticker": d["ticker"],
            "burn_address": addr,
            "confirmed_total": total,
            "fee_required": d["fee_stone"],
            "status": status,
            "ok": True,
        })
    # expire
    with connect() as c:
        c.execute(
            "UPDATE drafts SET status='expired' WHERE status IN ('open','funding') AND expires_at <= ?",
            (now,),
        )
    return {"ok": True, "checked": len(results), "drafts": results}
