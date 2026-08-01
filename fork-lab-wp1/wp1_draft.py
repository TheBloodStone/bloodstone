"""Open a draft: freeze fee from §3c curve, issue WP0 burn address, set 48h open-min."""
from __future__ import annotations

import json
import re
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, "/root")
sys.path.insert(0, "/root/bloodstone-docs")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fork_lab_burn import derive_burn_address  # noqa: E402
from wp1_db import connect, init, row_to_dict  # noqa: E402

DRAFT_DAYS = 90
OPEN_MIN_FRAC = 0.10
OPEN_MIN_SEC = 48 * 3600  # 48h skin-in or ticker frees


def _fmt_stone(n: float) -> str:
    """Human fee amounts (avoid 1e+06 in UI strings)."""
    try:
        x = float(n)
    except (TypeError, ValueError):
        return str(n)
    if abs(x - round(x)) < 1e-9:
        return f"{int(round(x)):,}"
    return f"{x:,.8f}".rstrip("0").rstrip(".")


def _ticker_ok(t: str) -> bool:
    t = t.upper()
    return bool(re.fullmatch(r"[A-Z][A-Z0-9]{1,9}", t)) and t not in {
        "STONE",
        "BTC",
        "USDT",
        "ETH",
    }


def freeze_fee(*, fee_override: float | None = None) -> dict:
    """Freeze current §3c requirement (or explicit override for tests).

    Freezing is the caller's job at draft time — this captures the live curve
    snapshot so later decay cannot change an open draft's bill.
    """
    freeze = {
        "schema": "bloodstone/fork-lab-fee-freeze/v1",
        "frozen_at": int(time.time()),
        "source": "override" if fee_override is not None else "fee_curve",
    }
    if fee_override is not None:
        fee = float(fee_override)
        freeze["requirement_stone"] = fee
        freeze["note"] = "explicit fee override (CLI/test)"
        return fee, freeze

    try:
        from fork_lab_fee_curve import current_requirement

        cr = current_requirement()
        fee = float(cr.get("requirement_stone") or cr.get("start") or 1_000_000)
        freeze.update(
            {
                "requirement_stone": fee,
                "enabled": bool(cr.get("enabled")),
                "start": cr.get("start"),
                "floor": cr.get("floor"),
                "decay": cr.get("decay"),
                "step_blocks": cr.get("step_blocks"),
                "stone_height": (cr.get("live") or {}).get("height")
                or cr.get("stone_height"),
                "stone_diff_sha256d": (cr.get("live") or {})
                .get("difficulty", {})
                .get("sha256d")
                or cr.get("stone_diff_sha256d"),
                "effective_steps": cr.get("effective_steps"),
                "held_by_difficulty_gate": cr.get("held_by_difficulty_gate"),
                "formula": cr.get("formula")
                or "max(FLOOR, START * DECAY**effective_steps)",
            }
        )
        return fee, freeze
    except Exception as exc:
        # Safe fallback: START from env / RFQ default
        import os

        fee = float(os.environ.get("FORK_LAB_FEE_START", "1000000"))
        freeze.update(
            {
                "requirement_stone": fee,
                "source": "fallback_start",
                "error": str(exc)[:200],
                "note": "fee_curve unavailable; froze FORK_LAB_FEE_START",
            }
        )
        return fee, freeze


def draft_open(
    *,
    ticker: str,
    name: str,
    creator: str,
    fee: float | None = None,
) -> dict:
    init()
    t = ticker.upper().strip()
    if not _ticker_ok(t):
        return {"ok": False, "error": "invalid ticker"}
    creator = (creator or "").strip()
    if not (creator.startswith("S") or creator.startswith("stone1")):
        return {"ok": False, "error": "creator must be STONE address (S… or stone1…)"}
    if not (name or "").strip():
        return {"ok": False, "error": "name required"}

    fee_val, freeze = freeze_fee(fee_override=fee)
    open_min = round(fee_val * OPEN_MIN_FRAC, 8)
    draft_id = f"d-{t.lower()}-{uuid.uuid4().hex[:12]}"
    burn = derive_burn_address(draft_id=draft_id)
    now = int(time.time())
    exp = now + DRAFT_DAYS * 86400
    open_deadline = now + OPEN_MIN_SEC

    with connect() as c:
        # Soft-reserve ticker while open / funding / funded / provisioning / live
        row = c.execute(
            """
            SELECT draft_id, status FROM drafts
             WHERE upper(ticker)=?
               AND status IN ('open','funding','funded','provisioning','live')
            """,
            (t,),
        ).fetchone()
        if row:
            return {
                "ok": False,
                "error": f"ticker reserved by {row['draft_id']} ({row['status']})",
            }
        c.execute(
            """
            INSERT INTO drafts(
              draft_id,ticker,name,creator_address,fee_stone,open_min_stone,
              burn_address,status,created_at,expires_at,open_min_deadline,
              confirmed_total,fee_freeze_json,detail_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                draft_id,
                t,
                name.strip()[:80],
                creator,
                fee_val,
                open_min,
                burn["address"],
                "open",
                now,
                exp,
                open_deadline,
                0.0,
                json.dumps(freeze),
                json.dumps(
                    {
                        "burn": burn,
                        "scheme": burn.get("scheme"),
                        "open_min_frac": OPEN_MIN_FRAC,
                        "open_min_sec": OPEN_MIN_SEC,
                        "draft_days": DRAFT_DAYS,
                    }
                ),
            ),
        )

    return {
        "ok": True,
        "draft_id": draft_id,
        "ticker": t,
        "name": name.strip()[:80],
        "creator_address": creator,
        "fee_stone_frozen": fee_val,
        "open_min_stone": open_min,
        "open_min_deadline": open_deadline,
        "open_min_hours": OPEN_MIN_SEC // 3600,
        "burn_address": burn["address"],
        "burn_scheme": burn.get("scheme"),
        "created_at": now,
        "expires_at": exp,
        "expires_days": DRAFT_DAYS,
        "status": "open",
        "fee_freeze": freeze,
        "disclosure": (
            f"Send {_fmt_stone(fee_val)} STONE total to {burn['address']} within {DRAFT_DAYS} days "
            f"(≥ {_fmt_stone(open_min)} STONE within 48h to keep the ticker). "
            "Irreversible burn. No refund. Miss the 90-day threshold and burns stay orphaned."
        ),
        "message": (
            f"Send {_fmt_stone(fee_val)} STONE total to {burn['address']} within {DRAFT_DAYS} days "
            f"(≥ {_fmt_stone(open_min)} within 48h). Irreversible burn. No refund."
        ),
    }


def get_draft(draft_id: str) -> dict:
    init()
    with connect() as c:
        row = c.execute(
            "SELECT * FROM drafts WHERE draft_id=?", (draft_id,)
        ).fetchone()
        if not row:
            return {"ok": False, "error": "unknown draft"}
        credits = [
            row_to_dict(r)
            for r in c.execute(
                "SELECT txid,vout,amount,confs,seen_at FROM burn_credits WHERE draft_id=? ORDER BY seen_at",
                (draft_id,),
            )
        ]
    d = row_to_dict(row)
    fee = float(d["fee_stone"])
    total = float(d.get("confirmed_total") or 0)
    remaining = max(0.0, fee - total)
    now = int(time.time())
    try:
        freeze = json.loads(d.get("fee_freeze_json") or "{}")
    except Exception:
        freeze = {}
    try:
        detail = json.loads(d.get("detail_json") or "{}")
    except Exception:
        detail = {}
    return {
        "ok": True,
        "draft": {
            **{k: d[k] for k in d if k not in ("fee_freeze_json", "detail_json")},
            "remaining_stone": remaining,
            "pct_funded": round(100.0 * total / fee, 2) if fee > 0 else 0,
            "seconds_to_open_min_deadline": max(
                0, int(d.get("open_min_deadline") or 0) - now
            ),
            "seconds_to_expiry": max(0, int(d.get("expires_at") or 0) - now),
            "fee_freeze": freeze,
            "detail": detail,
            "credits": credits,
            "disclosure": (
                f"{_fmt_stone(total)} of {_fmt_stone(fee)} STONE burned toward {d['ticker']}. This is permanent. "
                f"If this draft is not fully funded by unix {d['expires_at']}, this STONE is gone, "
                "the name is released, and no coin is created. Burns cannot be refunded."
            ),
        },
    }


def list_drafts(limit: int = 50, status: str | None = None) -> dict:
    init()
    limit = max(1, min(200, int(limit)))
    with connect() as c:
        if status:
            rows = c.execute(
                """
                SELECT draft_id,ticker,name,status,fee_stone,open_min_stone,
                       burn_address,confirmed_total,created_at,expires_at,
                       open_min_deadline,open_min_met_at,funded_at
                  FROM drafts WHERE status=? ORDER BY created_at DESC LIMIT ?
                """,
                (status, limit),
            ).fetchall()
        else:
            rows = c.execute(
                """
                SELECT draft_id,ticker,name,status,fee_stone,open_min_stone,
                       burn_address,confirmed_total,created_at,expires_at,
                       open_min_deadline,open_min_met_at,funded_at
                  FROM drafts ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return {"ok": True, "drafts": [row_to_dict(r) for r in rows]}
