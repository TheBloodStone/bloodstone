"""Monthly STONE upkeep for retained / old mesh storage data.

Initial storage purchase (1 STONE / GiB) buys write quota. Keeping data online
requires a recurring upkeep fee so providers can sustain disk, power, and
replication — without this, prepaid credits alone underfund long-lived archives.

Upkeep is assessed on **bytes currently stored** (usage), not unused prepaid
quota. First grace period after credit purchase is free (default 30 days).
"""

from __future__ import annotations

import os
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db
from chain_mesh import storage_credits as storage

BYTES_PER_GIB = 1024 * 1024 * 1024
MONTH_SEC = 30 * 86400

# Monthly keep-alive: STONE per GiB of stored data per 30-day period.
STONE_PER_GIB_MONTH = Decimal(
    os.environ.get("DATA_SALES_UPKEEP_STONE_PER_GIB_MONTH", "0.1")
)
# Days after first storage credit before upkeep starts.
GRACE_DAYS = int(os.environ.get("DATA_SALES_UPKEEP_GRACE_DAYS", "30"))
# Soft enforcement: when overdue, publish/check can warn or block.
ENFORCE = os.environ.get("DATA_SALES_UPKEEP_ENFORCE", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)
# Minimum billable stored size once past grace (avoid dust).
MIN_BILLABLE_BYTES = int(
    os.environ.get("DATA_SALES_UPKEEP_MIN_BYTES", str(1024 * 1024))
)  # 1 MiB


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def init_upkeep_db() -> None:
    storage.init_storage_credits_db()
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS storage_upkeep_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stone_address TEXT NOT NULL,
                period_start INTEGER NOT NULL,
                period_end INTEGER NOT NULL,
                bytes_assessed INTEGER NOT NULL DEFAULT 0,
                stone_amount TEXT NOT NULL DEFAULT '0',
                gib_months REAL NOT NULL DEFAULT 0,
                payment_ref TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'stone',
                memo TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_storage_upkeep_addr
                ON storage_upkeep_ledger(stone_address, period_end DESC);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_storage_upkeep_ref
                ON storage_upkeep_ledger(payment_ref)
                WHERE payment_ref != '';
            CREATE TABLE IF NOT EXISTS storage_upkeep_status (
                stone_address TEXT PRIMARY KEY,
                last_period_end INTEGER NOT NULL DEFAULT 0,
                last_paid_at INTEGER NOT NULL DEFAULT 0,
                grace_until INTEGER NOT NULL DEFAULT 0,
                total_stone_paid TEXT NOT NULL DEFAULT '0',
                updated_at INTEGER NOT NULL
            );
            """
        )


def rates() -> Dict[str, Any]:
    per = float(STONE_PER_GIB_MONTH)
    per_tib = per * 1024  # GiB → TiB month
    return {
        "product": "storage_upkeep",
        "currency": "STONE",
        "stone_per_gib_month": per,
        "display_rate": f"{STONE_PER_GIB_MONTH:g} STONE",
        "unit": "1 GiB · month",
        "stone_per_tib_month": per_tib,
        "display_tib": f"{per_tib:g} STONE / TiB · month",
        "grace_days": GRACE_DAYS,
        "assessed_on": "bytes currently stored (usage), not unused prepaid quota",
        "treasury": "storage",  # same treasury as storage purchases
        "enforce": ENFORCE,
        "note": (
            "Initial purchase pays for write quota. Monthly upkeep keeps old data "
            "online for providers (disk, power, replication). Pay storage treasury "
            "and claim product=upkeep, or run the coordinator upkeep cycle."
        ),
        "example": (
            f"Store 10 GiB past grace → {10 * per:g} STONE / month upkeep"
        ),
    }


def _first_credit_at(stone_address: str) -> int:
    addr = (stone_address or "").strip()
    if not addr:
        return 0
    try:
        with _conn() as conn:
            row = conn.execute(
                """
                SELECT MIN(created_at) AS t FROM storage_credit_ledger
                WHERE stone_address = ?
                """,
                (addr,),
            ).fetchone()
            return int(row["t"] or 0) if row else 0
    except Exception:
        return 0


def _status_row(stone_address: str) -> Dict[str, Any]:
    init_upkeep_db()
    addr = (stone_address or "").strip()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM storage_upkeep_status WHERE stone_address = ?",
            (addr,),
        ).fetchone()
    if not row:
        first = _first_credit_at(addr)
        grace_until = (first + GRACE_DAYS * 86400) if first else 0
        return {
            "stone_address": addr,
            "last_period_end": 0,
            "last_paid_at": 0,
            "grace_until": grace_until,
            "total_stone_paid": "0",
        }
    return {
        "stone_address": addr,
        "last_period_end": int(row["last_period_end"] or 0),
        "last_paid_at": int(row["last_paid_at"] or 0),
        "grace_until": int(row["grace_until"] or 0),
        "total_stone_paid": str(row["total_stone_paid"] or "0"),
    }


def _ensure_grace(stone_address: str) -> int:
    """Set grace_until from first credit if missing."""
    init_upkeep_db()
    addr = (stone_address or "").strip()
    st = _status_row(addr)
    if st["grace_until"]:
        return int(st["grace_until"])
    first = _first_credit_at(addr)
    if not first:
        return 0
    grace_until = first + GRACE_DAYS * 86400
    now = _now()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO storage_upkeep_status (
                stone_address, last_period_end, last_paid_at, grace_until,
                total_stone_paid, updated_at
            ) VALUES (?, 0, 0, ?, '0', ?)
            ON CONFLICT(stone_address) DO UPDATE SET
                grace_until = CASE
                    WHEN storage_upkeep_status.grace_until = 0
                    THEN excluded.grace_until
                    ELSE storage_upkeep_status.grace_until
                END,
                updated_at = excluded.updated_at
            """,
            (addr, grace_until, now),
        )
    return grace_until


def quote_upkeep(stone_address: str, *, at: Optional[int] = None) -> Dict[str, Any]:
    """Quote STONE due for the next upkeep period for stored bytes."""
    init_upkeep_db()
    addr = (stone_address or "").strip()
    now = int(at or _now())
    q = storage.quota_summary(addr)
    used = int(q.get("bytes_used") or 0)
    grace_until = _ensure_grace(addr)
    st = _status_row(addr)
    last_end = int(st.get("last_period_end") or 0)

    in_grace = bool(grace_until and now < grace_until)
    # Period start: after grace, or after last paid period
    period_start = max(grace_until, last_end)
    if period_start <= 0 and not in_grace:
        period_start = now  # first assessment

    period_end = period_start + MONTH_SEC if period_start else now + MONTH_SEC
    due_now = (not in_grace) and used >= MIN_BILLABLE_BYTES and now >= period_start
    # If already paid through a future period_end, not due
    if last_end and now < last_end:
        due_now = False
        period_end = last_end

    gib = used / float(BYTES_PER_GIB)
    stone_due = (
        (Decimal(str(gib)) * STONE_PER_GIB_MONTH).quantize(Decimal("0.00000001"))
        if due_now
        else Decimal("0")
    )
    # Always show full-month price for current usage (planning)
    stone_month = (Decimal(str(gib)) * STONE_PER_GIB_MONTH).quantize(
        Decimal("0.00000001")
    )

    return {
        "ok": True,
        "stone_address": addr,
        "bytes_stored": used,
        "gib_stored": round(gib, 6),
        "in_grace": in_grace,
        "grace_until": grace_until,
        "grace_days": GRACE_DAYS,
        "last_period_end": last_end,
        "period_start": period_start,
        "period_end": period_end,
        "due_now": due_now,
        "stone_due": str(stone_due),
        "stone_per_month_at_current_usage": str(stone_month),
        "rate": rates(),
        "enforce": ENFORCE,
        "status": "grace"
        if in_grace
        else ("paid_ahead" if last_end and now < last_end else ("due" if due_now else "ok")),
    }


def record_upkeep_payment(
    *,
    stone_address: str,
    stone_amount: str,
    payment_ref: str,
    bytes_assessed: Optional[int] = None,
    memo: str = "",
    source: str = "stone",
    periods: int = 1,
) -> Dict[str, Any]:
    """Record STONE upkeep payment; extends paid-through period."""
    init_upkeep_db()
    addr = (stone_address or "").strip()
    if len(addr) < 25:
        raise ValueError("stone_address required")
    ref = (payment_ref or "").strip()
    amount = Decimal(str(stone_amount or "0"))
    if amount <= 0:
        raise ValueError("stone_amount must be positive")
    periods = max(1, int(periods))

    quote = quote_upkeep(addr)
    used = int(bytes_assessed if bytes_assessed is not None else quote["bytes_stored"])
    gib = used / float(BYTES_PER_GIB) if used else 0.0
    # How many months this payment covers at current usage
    month_cost = Decimal(str(gib)) * STONE_PER_GIB_MONTH if gib > 0 else STONE_PER_GIB_MONTH
    if month_cost > 0:
        covered = max(periods, int(amount / month_cost + Decimal("0.0000001")))
        covered = max(1, covered)
    else:
        covered = periods

    now = _now()
    st = _status_row(addr)
    base = max(int(st.get("last_period_end") or 0), int(quote.get("grace_until") or 0), now)
    period_start = base if base > now else now
    # If already ahead, stack on last_period_end
    if int(st.get("last_period_end") or 0) > now:
        period_start = int(st["last_period_end"])
    period_end = period_start + covered * MONTH_SEC
    gib_months = float(gib) * covered

    with _conn() as conn:
        if ref:
            existing = conn.execute(
                "SELECT id FROM storage_upkeep_ledger WHERE payment_ref = ?",
                (ref,),
            ).fetchone()
            if existing:
                return {"ok": True, "duplicate": True, "stone_address": addr, "payment_ref": ref}

        conn.execute(
            """
            INSERT INTO storage_upkeep_ledger (
                stone_address, period_start, period_end, bytes_assessed,
                stone_amount, gib_months, payment_ref, source, memo, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                addr,
                period_start,
                period_end,
                used,
                str(amount),
                gib_months,
                ref,
                source[:32],
                (memo or "")[:500],
                now,
            ),
        )
        prev_total = Decimal(str(st.get("total_stone_paid") or "0"))
        new_total = prev_total + amount
        grace_until = int(st.get("grace_until") or 0) or _ensure_grace(addr)
        conn.execute(
            """
            INSERT INTO storage_upkeep_status (
                stone_address, last_period_end, last_paid_at, grace_until,
                total_stone_paid, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(stone_address) DO UPDATE SET
                last_period_end = excluded.last_period_end,
                last_paid_at = excluded.last_paid_at,
                grace_until = CASE
                    WHEN storage_upkeep_status.grace_until = 0
                    THEN excluded.grace_until
                    ELSE storage_upkeep_status.grace_until
                END,
                total_stone_paid = excluded.total_stone_paid,
                updated_at = excluded.updated_at
            """,
            (addr, period_end, now, grace_until, str(new_total), now),
        )

    return {
        "ok": True,
        "stone_address": addr,
        "payment_ref": ref,
        "stone_amount": str(amount),
        "bytes_assessed": used,
        "periods_covered": covered,
        "period_start": period_start,
        "period_end": period_end,
        "gib_months": gib_months,
        "total_stone_paid": str(new_total),
    }


def check_storage_allowed(stone_address: str) -> Dict[str, Any]:
    """Optional gate: block new publishes when upkeep overdue and enforce is on."""
    quote = quote_upkeep(stone_address)
    if not ENFORCE:
        return {
            "ok": True,
            "allowed": True,
            "reason": "upkeep enforcement off",
            "quote": quote,
        }
    if quote.get("in_grace") or quote.get("status") in ("ok", "paid_ahead", "grace"):
        if not quote.get("due_now"):
            return {"ok": True, "allowed": True, "quote": quote}
    if quote.get("due_now"):
        return {
            "ok": True,
            "allowed": False,
            "reason": (
                f"storage upkeep due: {quote.get('stone_due')} STONE for "
                f"{quote.get('gib_stored')} GiB stored — pay storage treasury, "
                f"claim product=upkeep"
            ),
            "quote": quote,
        }
    return {"ok": True, "allowed": True, "quote": quote}


def network_upkeep_summary() -> Dict[str, Any]:
    """Aggregate stored bytes and estimated monthly upkeep revenue signal."""
    init_upkeep_db()
    try:
        with _conn() as conn:
            used = conn.execute(
                "SELECT COALESCE(SUM(bytes_used), 0) AS t FROM storage_usage"
            ).fetchone()["t"]
            paid = conn.execute(
                "SELECT COALESCE(SUM(CAST(stone_amount AS REAL)), 0) AS t FROM storage_upkeep_ledger"
            ).fetchone()["t"]
            addrs = conn.execute(
                "SELECT COUNT(DISTINCT stone_address) AS n FROM storage_usage WHERE bytes_used > 0"
            ).fetchone()["n"]
    except Exception:
        used, paid, addrs = 0, 0.0, 0
    gib = int(used) / float(BYTES_PER_GIB)
    monthly = Decimal(str(gib)) * STONE_PER_GIB_MONTH
    return {
        "ok": True,
        "bytes_stored_network": int(used),
        "gib_stored_network": round(gib, 4),
        "unique_stores": int(addrs),
        "estimated_monthly_upkeep_stone": str(
            monthly.quantize(Decimal("0.00000001"))
        ),
        "total_upkeep_stone_collected": float(paid or 0),
        "rate": rates(),
    }
