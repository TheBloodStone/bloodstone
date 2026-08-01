"""Provision coins/<TICKER>/ into bloodstone-fork-registry (WP1)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wp1_db import connect, init  # noqa: E402

REG = Path(os.environ.get("FORK_LAB_REGISTRY", "/root/bloodstone-fork-registry"))


def provision(draft_id: str) -> dict:
    init()
    with connect() as c:
        d = c.execute("SELECT * FROM drafts WHERE draft_id=?", (draft_id,)).fetchone()
    if not d:
        return {"ok": False, "error": "unknown draft"}
    if d["status"] not in ("funded", "provisioning"):
        return {"ok": False, "error": f"draft status {d['status']} — need funded"}
    t = d["ticker"]
    coin_dir = REG / "coins" / t
    coin_dir.mkdir(parents=True, exist_ok=True)
    now = int(time.time())
    identity = {
        "schema": "bloodstone/fork-lab-coin/v1",
        "ticker": t,
        "name": d["name"],
        "status": "live",
        "draft_id": draft_id,
        "creator_address": d["creator_address"],
        "burn_address": d["burn_address"],
        "fee_stone": d["fee_stone"],
        "confirmed_total": d["confirmed_total"] if "confirmed_total" in d.keys() else None,
        "provisioned_at": now,
        "open_source": True,
        "launch": "burn-triggered",
        "note": "Provisioned by WP1 burn-triggered pipeline (automated launch).",
    }
    payment = {
        "schema": "bloodstone/fork-lab-payment/v2",
        "draft_id": draft_id,
        "burn_address": d["burn_address"],
        "amount_stone_required": d["fee_stone"],
        "amount_stone_confirmed": d["confirmed_total"] if "confirmed_total" in d.keys() else None,
        "status": "threshold_met",
        "policy": "orphan_on_expiry_no_refund",
    }
    (coin_dir / "identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    (coin_dir / "PAYMENT.json").write_text(json.dumps(payment, indent=2) + "\n")
    (coin_dir / "README.md").write_text(
        f"# {t}\n\nLive via burn-triggered launch. Draft `{draft_id}`.\n"
        f"Burn address: `{d['burn_address']}` · fee frozen: {d['fee_stone']} STONE.\n"
    )
    with connect() as c:
        c.execute(
            "UPDATE drafts SET status='live', provisioned_at=? WHERE draft_id=?",
            (now, draft_id),
        )
    return {"ok": True, "ticker": t, "path": str(coin_dir), "identity": identity}
