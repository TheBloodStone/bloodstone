"""Manual reconciliation — RFQ Decision #13 / §3.

If the watcher misses confirmed burns, the creator submits draft_id and/or
burn txids. Idempotent on the draft/address: one live coin per draft, ever.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wp1_db import connect, init, row_to_dict  # noqa: E402
from wp1_watcher import MIN_CONFS, _rpc, _scan_address, expire_orphans  # noqa: E402

_TXID_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _credit_utxos(draft_id: str, utxos: list, now: int) -> int:
    n = 0
    with connect() as c:
        for u in utxos:
            if not u.get("txid"):
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
                    draft_id,
                    u["txid"],
                    int(u.get("vout") or 0),
                    float(u.get("amount") or 0),
                    int(u.get("confs") or 0),
                    now,
                ),
            )
            n += 1
        total = sum(
            float(r["amount"])
            for r in c.execute(
                "SELECT amount, confs FROM burn_credits WHERE draft_id=?",
                (draft_id,),
            )
            if int(r["confs"] or 0) >= MIN_CONFS
        )
        # Prefer chain scan total when available (source of truth)
        c.execute(
            "UPDATE drafts SET confirmed_total=? WHERE draft_id=?",
            (total, draft_id),
        )
    return n


def _apply_status(d: dict, total: float, now: int) -> str:
    """Apply open-min / funded transitions from confirmed total."""
    fee = float(d["fee_stone"])
    open_min = float(d["open_min_stone"])
    status = d["status"]
    if status in ("live", "expired", "lapsed"):
        return status

    if total >= open_min:
        with connect() as c:
            if not d.get("open_min_met_at"):
                c.execute(
                    "UPDATE drafts SET open_min_met_at=? WHERE draft_id=?",
                    (now, d["draft_id"]),
                )
            if status == "open":
                c.execute(
                    "UPDATE drafts SET status='funding' WHERE draft_id=? AND status='open'",
                    (d["draft_id"],),
                )
                status = "funding"

    if total >= fee and total > 0:
        with connect() as c:
            c.execute(
                """
                UPDATE drafts SET status='funded', funded_at=?, confirmed_total=?
                 WHERE draft_id=? AND status IN ('open','funding','funded')
                """,
                (now, total, d["draft_id"]),
            )
        status = "funded"
    elif total >= open_min and status == "open":
        status = "funding"

    with connect() as c:
        c.execute(
            "UPDATE drafts SET confirmed_total=? WHERE draft_id=?",
            (total, d["draft_id"]),
        )
    return status


def _lookup_txid_to_address(txid: str, burn_address: str) -> list:
    """Return UTXO-like rows if txid pays burn_address."""
    try:
        raw = _rpc("getrawtransaction", [txid, True])
    except Exception as exc:
        raise RuntimeError(f"txid lookup failed: {exc}") from exc
    if not raw:
        raise RuntimeError("txid not found on node")
    confs = int(raw.get("confirmations") or 0)
    rows = []
    for i, vout in enumerate(raw.get("vout") or []):
        spk = vout.get("scriptPubKey") or {}
        addrs = spk.get("addresses") or []
        if spk.get("address"):
            addrs = list(addrs) + [spk["address"]]
        if burn_address in addrs:
            rows.append(
                {
                    "txid": txid,
                    "vout": i,
                    "amount": float(vout.get("value") or 0),
                    "confs": confs,
                }
            )
    return rows


def reconcile(
    *,
    draft_id: str = "",
    burn_address: str = "",
    txids: list | None = None,
    auto_provision: bool | None = None,
) -> dict:
    """Reconcile a draft by address scan and/or explicit burn txids.

    Public-safe: knowledge of draft_id (or burn address) is the capability.
    """
    init()
    expire_orphans()
    now = int(time.time())
    txids = [t.strip() for t in (txids or []) if t and str(t).strip()]

    with connect() as c:
        row = None
        if draft_id:
            row = c.execute(
                "SELECT * FROM drafts WHERE draft_id=?", (draft_id.strip(),)
            ).fetchone()
        elif burn_address:
            row = c.execute(
                "SELECT * FROM drafts WHERE burn_address=?",
                (burn_address.strip(),),
            ).fetchone()
        if not row:
            return {"ok": False, "error": "unknown draft (need draft_id or burn_address)"}
        d = row_to_dict(row)

    if d["status"] in ("live",):
        return {
            "ok": True,
            "already_live": True,
            "draft_id": d["draft_id"],
            "ticker": d["ticker"],
            "status": d["status"],
            "message": "Draft already live — reconciliation is a no-op (idempotent).",
        }

    if d["status"] in ("expired", "lapsed"):
        return {
            "ok": False,
            "error": f"draft is {d['status']} — ticker free; burns stay orphaned",
            "draft_id": d["draft_id"],
            "status": d["status"],
        }

    credited = 0
    scan_total = None
    scan_err = None
    txid_notes = []

    # 1) Explicit txids first
    for txid in txids:
        if not _TXID_RE.match(txid):
            txid_notes.append({"txid": txid, "ok": False, "error": "invalid txid format"})
            continue
        try:
            rows = _lookup_txid_to_address(txid, d["burn_address"])
            if not rows:
                txid_notes.append(
                    {
                        "txid": txid,
                        "ok": False,
                        "error": "txid does not pay this draft burn address",
                    }
                )
                continue
            credited += _credit_utxos(d["draft_id"], rows, now)
            txid_notes.append(
                {
                    "txid": txid,
                    "ok": True,
                    "outputs": len(rows),
                    "amount": sum(r["amount"] for r in rows),
                    "confs": rows[0]["confs"],
                }
            )
        except Exception as exc:
            txid_notes.append({"txid": txid, "ok": False, "error": str(exc)[:200]})

    # 2) Full address scan (watcher path)
    try:
        scan_total, utxos = _scan_address(d["burn_address"])
        credited += _credit_utxos(d["draft_id"], utxos, now)
    except Exception as exc:
        scan_err = str(exc)[:200]
        # Fall back to credits-only total
        with connect() as c:
            scan_total = sum(
                float(r["amount"])
                for r in c.execute(
                    "SELECT amount, confs FROM burn_credits WHERE draft_id=?",
                    (d["draft_id"],),
                )
                if int(r["confs"] or 0) >= MIN_CONFS
            )

    total = float(scan_total or 0)
    status = _apply_status(d, total, now)

    provision_out = None
    do_auto = (
        auto_provision
        if auto_provision is not None
        else str(os.environ.get("FORK_LAB_WP1_AUTO_PROVISION", "0")).lower()
        in ("1", "true", "yes", "on")
    )
    if status == "funded" and do_auto:
        try:
            from wp1_provision import provision

            provision_out = provision(d["draft_id"])
            if provision_out.get("ok"):
                status = "live"
        except Exception as exc:
            provision_out = {"ok": False, "error": str(exc)[:200]}

    with connect() as c:
        d2 = row_to_dict(
            c.execute(
                "SELECT * FROM drafts WHERE draft_id=?", (d["draft_id"],)
            ).fetchone()
        )

    return {
        "ok": True,
        "draft_id": d["draft_id"],
        "ticker": d["ticker"],
        "burn_address": d["burn_address"],
        "status": d2.get("status") or status,
        "confirmed_total": float(d2.get("confirmed_total") or total),
        "fee_stone": d["fee_stone"],
        "remaining": max(0.0, float(d["fee_stone"]) - float(d2.get("confirmed_total") or total)),
        "credits_upserted": credited,
        "txid_notes": txid_notes,
        "scan_error": scan_err,
        "min_confs": MIN_CONFS,
        "provision": provision_out,
        "message": (
            f"Reconciled {d['ticker']}: {float(d2.get('confirmed_total') or total):g} / "
            f"{d['fee_stone']} STONE confirmed toward burn address. Status: "
            f"{d2.get('status') or status}."
        ),
        "disclosure": (
            f"{float(d2.get('confirmed_total') or total):g} of {d['fee_stone']} STONE burned "
            f"toward {d['ticker']}. This is permanent. Burns cannot be refunded."
        ),
    }
