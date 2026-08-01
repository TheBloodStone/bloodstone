"""Open a draft: freeze fee, issue WP0 burn address."""
from __future__ import annotations
import json, re, sys, time, uuid
from pathlib import Path
sys.path.insert(0, "/root")
sys.path.insert(0, "/root/bloodstone-docs")
from fork_lab_burn import derive_burn_address
from wp1_db import connect, init

# Fee: use floor as default until live curve wired in CLI env
DEFAULT_FEE = float(__import__("os").environ.get("FORK_LAB_FEE_START", "1000000"))
DRAFT_DAYS = 90
OPEN_MIN_FRAC = 0.10

def _ticker_ok(t: str) -> bool:
    t = t.upper()
    return bool(re.fullmatch(r"[A-Z][A-Z0-9]{1,9}", t)) and t not in {"STONE", "BTC", "USDT"}

def draft_open(*, ticker: str, name: str, creator: str, fee: float | None = None) -> dict:
    init()
    t = ticker.upper().strip()
    if not _ticker_ok(t):
        return {"ok": False, "error": "invalid ticker"}
    if not (creator or "").startswith("S") and not (creator or "").startswith("stone1"):
        return {"ok": False, "error": "creator must be STONE address (S… or stone1…)"}
    fee = float(fee if fee is not None else DEFAULT_FEE)
    open_min = fee * OPEN_MIN_FRAC
    draft_id = f"d-{t.lower()}-{uuid.uuid4().hex[:12]}"
    burn = derive_burn_address(draft_id=draft_id)
    now = int(time.time())
    exp = now + DRAFT_DAYS * 86400
    with connect() as c:
        # soft-reserve ticker while open/provisioning
        row = c.execute(
            "SELECT draft_id, status FROM drafts WHERE upper(ticker)=? AND status IN ('open','funded','provisioning','live')",
            (t,),
        ).fetchone()
        if row:
            return {"ok": False, "error": f"ticker reserved by {row['draft_id']} ({row['status']})"}
        c.execute(
            """INSERT INTO drafts(draft_id,ticker,name,creator_address,fee_stone,open_min_stone,
               burn_address,status,created_at,expires_at,detail_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                draft_id, t, name.strip()[:80], creator.strip(), fee, open_min,
                burn["address"], "open", now, exp,
                json.dumps({"burn": burn, "scheme": burn.get("scheme")}),
            ),
        )
    return {
        "ok": True,
        "draft_id": draft_id,
        "ticker": t,
        "name": name.strip()[:80],
        "fee_stone_frozen": fee,
        "open_min_stone": open_min,
        "burn_address": burn["address"],
        "expires_at": exp,
        "message": (
            f"Send {fee:g} STONE total to {burn['address']} within 90 days "
            f"(≥ {open_min:g} within 48h). Irreversible burn. No refund."
        ),
    }
