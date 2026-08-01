"""Sum confirmed STONE UTXOs to draft burn addresses (WP1 watch step).

Rules (RFQ v1.5 §3b):
  - Cumulative address total only (no payer ledger)
  - Fire funded when total ≥ frozen fee and confs ≥ MIN_CONFS
  - 48h open-minimum: ≥ 10% of fee or draft lapses (ticker frees)
  - 90-day expiry: expire + orphan burns (no refund, no coin)
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wp1_db import connect, init, row_to_dict  # noqa: E402

CONF = os.environ.get("BLOODSTONE_CONF", "/root/.bloodstone/bloodstone.conf")
MIN_CONFS = int(os.environ.get("FORK_LAB_BURN_MIN_CONFS", "6"))
AUTO_PROVISION = str(
    os.environ.get("FORK_LAB_WP1_AUTO_PROVISION", "0")
).strip().lower() in ("1", "true", "yes", "on")


def _rpc(method, params=None):
    kv = {}
    for line in open(CONF):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        kv[k.strip()] = v.strip()
    url = f"http://127.0.0.1:{kv['rpcport']}/"
    payload = json.dumps(
        {"jsonrpc": "1.0", "id": "wp1", "method": method, "params": params or []}
    ).encode()
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    tok = base64.b64encode(f"{kv['rpcuser']}:{kv['rpcpassword']}".encode()).decode()
    req.add_header("Authorization", f"Basic {tok}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read())
    if body.get("error"):
        raise RuntimeError(body["error"])
    return body["result"]


def _scan_address(addr: str) -> tuple[float, list[dict]]:
    """Return (confirmed_total, utxo_rows) for a keyless burn address.

    Prefer scantxoutset (no wallet import). Enrich confs via gettxout when possible.
    Only amounts with confs ≥ MIN_CONFS count toward the threshold.
    """
    scan = _rpc("scantxoutset", ["start", [f"addr({addr})"]])
    utxos = scan.get("unspents") or []
    confirmed = 0.0
    rows = []
    tip = None
    try:
        tip = int(_rpc("getblockcount"))
    except Exception:
        tip = None

    for u in utxos:
        txid = u.get("txid") or ""
        vout = int(u.get("vout") or 0)
        amount = float(u.get("amount") or 0)
        confs = 0
        # Prefer gettxout for live confs
        try:
            txo = _rpc("gettxout", [txid, vout, True])
            if txo and tip is not None and txo.get("height"):
                confs = max(0, tip - int(txo["height"]) + 1)
            elif txo:
                confs = MIN_CONFS  # in UTXO set, height unknown — treat as confirmed
            else:
                confs = 0
        except Exception:
            # scantxoutset only sees confirmed UTXOs in most deployments
            confs = MIN_CONFS if amount > 0 else 0
        rows.append(
            {"txid": txid, "vout": vout, "amount": amount, "confs": confs}
        )
        if confs >= MIN_CONFS:
            confirmed += amount
    return confirmed, rows


def expire_orphans(now: int | None = None) -> dict:
    """Lapse 48h open-min misses and expire 90-day unfinished drafts.

    Orphan policy: STONE already sent stays burned; ticker reservation frees.
    """
    init()
    now = int(now if now is not None else time.time())
    lapsed = []
    expired = []
    with connect() as c:
        # 48h open-min: still 'open' and never met open_min by deadline
        rows = c.execute(
            """
            SELECT draft_id, ticker, open_min_stone, confirmed_total, open_min_deadline
              FROM drafts
             WHERE status = 'open'
               AND open_min_deadline > 0
               AND open_min_deadline <= ?
               AND (open_min_met_at IS NULL OR open_min_met_at = 0)
            """,
            (now,),
        ).fetchall()
        for r in rows:
            # Re-check: if confirmed_total already ≥ open_min (race), skip
            if float(r["confirmed_total"] or 0) >= float(r["open_min_stone"]):
                continue
            c.execute(
                "UPDATE drafts SET status='lapsed' WHERE draft_id=? AND status='open'",
                (r["draft_id"],),
            )
            lapsed.append(
                {
                    "draft_id": r["draft_id"],
                    "ticker": r["ticker"],
                    "reason": "open_min_48h_missed",
                }
            )

        # 90-day expiry
        rows2 = c.execute(
            """
            SELECT draft_id, ticker, confirmed_total, fee_stone
              FROM drafts
             WHERE status IN ('open','funding')
               AND expires_at <= ?
            """,
            (now,),
        ).fetchall()
        for r in rows2:
            c.execute(
                "UPDATE drafts SET status='expired' WHERE draft_id=? AND status IN ('open','funding')",
                (r["draft_id"],),
            )
            expired.append(
                {
                    "draft_id": r["draft_id"],
                    "ticker": r["ticker"],
                    "confirmed_total": r["confirmed_total"],
                    "fee_stone": r["fee_stone"],
                    "reason": "draft_window_expired_orphaned",
                }
            )
    return {"ok": True, "lapsed": lapsed, "expired": expired}


def watch_once() -> dict:
    init()
    now = int(time.time())
    # Run expiry first so we don't scan dead drafts
    expiry = expire_orphans(now)

    results = []
    with connect() as c:
        drafts = c.execute(
            """
            SELECT * FROM drafts
             WHERE status IN ('open','funding')
               AND expires_at > ?
            """,
            (now,),
        ).fetchall()

    for d in drafts:
        d = row_to_dict(d)
        addr = d["burn_address"]
        try:
            total, utxos = _scan_address(addr)
        except Exception as exc:
            results.append(
                {
                    "draft_id": d["draft_id"],
                    "ok": False,
                    "error": str(exc)[:200],
                }
            )
            continue

        # Persist credits (idempotent)
        with connect() as c:
            for u in utxos:
                if not u["txid"]:
                    continue
                c.execute(
                    """
                    INSERT INTO burn_credits(draft_id,txid,vout,amount,confs,seen_at)
                    VALUES (?,?,?,?,?,?)
                    ON CONFLICT(txid,vout) DO UPDATE SET
                      confs=excluded.confs,
                      amount=excluded.amount,
                      seen_at=excluded.seen_at
                    """,
                    (
                        d["draft_id"],
                        u["txid"],
                        u["vout"],
                        u["amount"],
                        u["confs"],
                        now,
                    ),
                )
            c.execute(
                "UPDATE drafts SET confirmed_total=? WHERE draft_id=?",
                (total, d["draft_id"]),
            )

        fee = float(d["fee_stone"])
        open_min = float(d["open_min_stone"])
        status = d["status"]
        open_min_met_at = d.get("open_min_met_at")

        if total >= open_min and not open_min_met_at:
            open_min_met_at = now
            with connect() as c:
                c.execute(
                    """
                    UPDATE drafts SET open_min_met_at=?, status=CASE
                      WHEN status='open' THEN 'funding' ELSE status END
                     WHERE draft_id=?
                    """,
                    (now, d["draft_id"]),
                )
            if status == "open":
                status = "funding"

        if total >= fee and total > 0:
            status = "funded"
            with connect() as c:
                c.execute(
                    """
                    UPDATE drafts SET status='funded', funded_at=?, confirmed_total=?
                     WHERE draft_id=? AND status IN ('open','funding')
                    """,
                    (now, total, d["draft_id"]),
                )
            if AUTO_PROVISION:
                try:
                    from wp1_provision import provision

                    prov = provision(d["draft_id"])
                except Exception as exc:
                    prov = {"ok": False, "error": str(exc)[:160]}
            else:
                prov = None
        else:
            prov = None
            if status == "open" and total > 0 and total < open_min:
                # Partial dust — stay open until open-min or 48h lapse
                pass
            elif status in ("open", "funding") and total >= open_min:
                status = "funding"
                with connect() as c:
                    c.execute(
                        "UPDATE drafts SET status='funding' WHERE draft_id=? AND status='open'",
                        (d["draft_id"],),
                    )

        # Late check: open past deadline without open-min → will be caught next expire_orphans
        results.append(
            {
                "draft_id": d["draft_id"],
                "ticker": d["ticker"],
                "burn_address": addr,
                "confirmed_total": total,
                "fee_required": fee,
                "open_min_stone": open_min,
                "remaining": max(0.0, fee - total),
                "status": status,
                "utxo_count": len(utxos),
                "min_confs": MIN_CONFS,
                "provision": prov,
                "ok": True,
            }
        )

    # Second pass: catch 48h lapses that just became due after this tick's totals
    expiry2 = expire_orphans(now)
    return {
        "ok": True,
        "checked": len(results),
        "min_confs": MIN_CONFS,
        "drafts": results,
        "expiry": {
            "lapsed": expiry["lapsed"] + expiry2["lapsed"],
            "expired": expiry["expired"] + expiry2["expired"],
        },
    }
