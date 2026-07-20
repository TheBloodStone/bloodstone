"""Founder / long-term alignment structure (STONE + USDT trail + referral).

Three pillars for structuring a founding member (e.g. STONE role):

1) **STONE long-term alignment**
   - Conservative initial alignment grant
   - Monthly tranches for continued valuable participation
   - Not a dump: earn-out style, participation-gated

2) **USDT revenue**
   - **Founding-member trail** — perpetual residual % of commercial USDT
     (survives retirement; rewards organic attraction / elevated project state)
   - **Active participation stream** — separate % while actively contributing
     (stops or reduces when inactive)

3) **Community referral program**
   - Global sales force: team + external promoters share one referral rail
   - Codes credit a % of referred commercial USDT (first N months / first payment)

These sit *on top of* the base team split / provider pool model in usdt_monetization.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import time
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db

# ---------------------------------------------------------------------------
# 1) STONE long-term alignment (conservative)
# ---------------------------------------------------------------------------
# Initial alignment grant (STONE) — small relative to network, not treasury dump
STONE_INITIAL_ALIGNMENT = Decimal(
    os.environ.get("FOUNDER_STONE_INITIAL", "50000")
)
# Monthly tranche (STONE) while participation is active
STONE_MONTHLY_TRANCHE = Decimal(
    os.environ.get("FOUNDER_STONE_MONTHLY_TRANCHE", "5000")
)
# Max months of tranches (earn-out horizon)
STONE_TRANCHE_MONTHS = int(os.environ.get("FOUNDER_STONE_TRANCHE_MONTHS", "24"))
# Optional hard cap on total alignment STONE (initial + sum of tranches)
STONE_ALIGNMENT_CAP = Decimal(
    os.environ.get(
        "FOUNDER_STONE_ALIGNMENT_CAP",
        str(STONE_INITIAL_ALIGNMENT + STONE_MONTHLY_TRANCHE * STONE_TRANCHE_MONTHS),
    )
)
# Beneficiary STONE address for alignment grants
STONE_BENEFICIARY = (
    os.environ.get("FOUNDER_STONE_ADDRESS")
    or os.environ.get("MONETIZE_STONE_ROLE_ADDRESS")
    or ""
).strip()

# ---------------------------------------------------------------------------
# 2) USDT: trail (perpetual) + active participation
# ---------------------------------------------------------------------------
# Trail: perpetual % of gross commercial USDT — survives retirement
USDT_TRAIL_PCT = Decimal(os.environ.get("FOUNDER_USDT_TRAIL_PCT", "2"))
# Active stream: additional % of gross while marked active
USDT_ACTIVE_PCT = Decimal(os.environ.get("FOUNDER_USDT_ACTIVE_PCT", "5"))
# EVM USDT wallets
USDT_TRAIL_WALLET = (
    os.environ.get("FOUNDER_USDT_TRAIL_WALLET")
    or os.environ.get("FOUNDER_USDT_WALLET")
    or ""
).strip()
USDT_ACTIVE_WALLET = (
    os.environ.get("FOUNDER_USDT_ACTIVE_WALLET")
    or USDT_TRAIL_WALLET
    or ""
).strip()
# Participation flag: 1 = active stream applies this period
PARTICIPATION_ACTIVE = os.environ.get("FOUNDER_PARTICIPATION_ACTIVE", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# ---------------------------------------------------------------------------
# 3) Community referral program
# ---------------------------------------------------------------------------
# % of referred customer's commercial USDT that goes to referrer
REFERRAL_PCT = Decimal(os.environ.get("REFERRAL_USDT_PCT", "5"))
# How long referral earns on a referred customer (months from first payment)
REFERRAL_MONTHS = int(os.environ.get("REFERRAL_EARN_MONTHS", "12"))
# Cap: referral + trail + active + team base must leave room for providers
# (enforced at allocation time by residual math)

_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{4,32}$")


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def _d(v) -> Decimal:
    return Decimal(str(v))


def _q_usdt(v: Decimal) -> Decimal:
    return _d(v).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)


def _q_stone(v: Decimal) -> Decimal:
    return _d(v).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)


def init_alignment_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS founder_stone_tranches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period_label TEXT NOT NULL DEFAULT '',
                stone_amount TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'monthly',
                participation_ok INTEGER NOT NULL DEFAULT 1,
                note TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'scheduled',
                paid_txid TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                paid_at INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS founder_usdt_trails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_ref TEXT NOT NULL DEFAULT '',
                usdt_gross TEXT NOT NULL,
                trail_usdt TEXT NOT NULL,
                active_usdt TEXT NOT NULL DEFAULT '0',
                trail_wallet TEXT NOT NULL DEFAULT '',
                active_wallet TEXT NOT NULL DEFAULT '',
                participation_active INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS community_referral_codes (
                code TEXT PRIMARY KEY,
                owner_label TEXT NOT NULL DEFAULT '',
                owner_stone_address TEXT NOT NULL DEFAULT '',
                owner_usdt_wallet TEXT NOT NULL DEFAULT '',
                channel TEXT NOT NULL DEFAULT 'community',
                active INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS community_referral_earnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                payment_ref TEXT NOT NULL DEFAULT '',
                usdt_gross TEXT NOT NULL,
                referral_usdt TEXT NOT NULL,
                referred_customer TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_referral_earn_code
                ON community_referral_earnings(code, created_at DESC);
            """
        )


# ---------------------------------------------------------------------------
# Pillar 1 — STONE alignment schedule
# ---------------------------------------------------------------------------

def stone_alignment_plan() -> Dict[str, Any]:
    initial = _q_stone(STONE_INITIAL_ALIGNMENT)
    monthly = _q_stone(STONE_MONTHLY_TRANCHE)
    months = max(0, STONE_TRANCHE_MONTHS)
    scheduled_tranches = monthly * months
    total_if_full = _q_stone(initial + scheduled_tranches)
    cap = _q_stone(STONE_ALIGNMENT_CAP)
    if total_if_full > cap:
        # Scale note: cap binds
        total_if_full = cap
    return {
        "beneficiary_stone_address": STONE_BENEFICIARY or None,
        "initial_alignment_stone": str(initial),
        "monthly_tranche_stone": str(monthly),
        "tranche_months": months,
        "alignment_cap_stone": str(cap),
        "total_if_full_participation_stone": str(total_if_full),
        "participation_gate": (
            "Monthly tranches only release while FOUNDER_PARTICIPATION_ACTIVE=1 "
            "(continued valuable participation). Trail USDT is independent of this flag."
        ),
        "philosophy": (
            "Conservative initial alignment + earn-out monthly tranches. "
            "Rewards long-term contribution without a large upfront dump."
        ),
        "configure": {
            "FOUNDER_STONE_INITIAL": str(initial),
            "FOUNDER_STONE_MONTHLY_TRANCHE": str(monthly),
            "FOUNDER_STONE_TRANCHE_MONTHS": months,
            "FOUNDER_STONE_ALIGNMENT_CAP": str(cap),
            "FOUNDER_STONE_ADDRESS": STONE_BENEFICIARY or "S...",
        },
    }


def schedule_initial_alignment(*, note: str = "") -> Dict[str, Any]:
    """Book the conservative initial STONE alignment (ops then pays on-chain)."""
    init_alignment_db()
    amt = _q_stone(STONE_INITIAL_ALIGNMENT)
    now = _now()
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO founder_stone_tranches (
                period_label, stone_amount, kind, participation_ok, note, status, created_at
            ) VALUES (?, ?, 'initial', 1, ?, 'scheduled', ?)
            """,
            ("initial", str(amt), (note or "conservative initial alignment")[:500], now),
        )
        row_id = int(cur.lastrowid)
    return {"ok": True, "id": row_id, "kind": "initial", "stone_amount": str(amt), "status": "scheduled"}


def schedule_monthly_tranche(
    *,
    period_label: str = "",
    participation_ok: Optional[bool] = None,
    note: str = "",
) -> Dict[str, Any]:
    """Book one monthly STONE tranche if participation continues."""
    init_alignment_db()
    active = PARTICIPATION_ACTIVE if participation_ok is None else bool(participation_ok)
    if not active:
        return {
            "ok": False,
            "error": "participation not active — monthly tranche withheld",
            "participation_active": False,
        }
    amt = _q_stone(STONE_MONTHLY_TRANCHE)
    label = (period_label or time.strftime("%Y-%m")).strip()
    now = _now()
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO founder_stone_tranches (
                period_label, stone_amount, kind, participation_ok, note, status, created_at
            ) VALUES (?, ?, 'monthly', 1, ?, 'scheduled', ?)
            """,
            (label, str(amt), (note or "monthly participation tranche")[:500], now),
        )
        row_id = int(cur.lastrowid)
    return {
        "ok": True,
        "id": row_id,
        "kind": "monthly",
        "period_label": label,
        "stone_amount": str(amt),
        "status": "scheduled",
        "beneficiary": STONE_BENEFICIARY or None,
    }


def list_stone_tranches(limit: int = 50) -> List[Dict[str, Any]]:
    init_alignment_db()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM founder_stone_tranches
            ORDER BY id DESC LIMIT ?
            """,
            (max(1, min(200, int(limit))),),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Pillar 2 — USDT trail + active stream
# ---------------------------------------------------------------------------

def usdt_founder_streams() -> Dict[str, Any]:
    return {
        "trail": {
            "pct_of_gross_usdt": float(USDT_TRAIL_PCT),
            "perpetual": True,
            "survives_retirement": True,
            "wallet": USDT_TRAIL_WALLET or None,
            "rationale": (
                "Finance-style trail: residual on commercial revenue attracted by the "
                "project's elevated state / organic acquisition — not only direct sales."
            ),
        },
        "active_participation": {
            "pct_of_gross_usdt": float(USDT_ACTIVE_PCT),
            "perpetual": False,
            "active_now": PARTICIPATION_ACTIVE,
            "wallet": USDT_ACTIVE_WALLET or None,
            "rationale": (
                "Separate stream for ongoing project work. Reduces/stops when "
                "FOUNDER_PARTICIPATION_ACTIVE=0; trail continues."
            ),
        },
        "combined_while_active_pct": float(USDT_TRAIL_PCT + USDT_ACTIVE_PCT),
        "combined_when_retired_pct": float(USDT_TRAIL_PCT),
        "configure": {
            "FOUNDER_USDT_TRAIL_PCT": str(USDT_TRAIL_PCT),
            "FOUNDER_USDT_ACTIVE_PCT": str(USDT_ACTIVE_PCT),
            "FOUNDER_USDT_TRAIL_WALLET": USDT_TRAIL_WALLET or "0x...",
            "FOUNDER_USDT_ACTIVE_WALLET": USDT_ACTIVE_WALLET or "0x...",
            "FOUNDER_PARTICIPATION_ACTIVE": "1" if PARTICIPATION_ACTIVE else "0",
        },
    }


def allocate_founder_usdt(gross_usdt: Decimal) -> Dict[str, Any]:
    """Slice trail + active from gross commercial USDT."""
    gross = _q_usdt(gross_usdt)
    trail = _q_usdt(gross * USDT_TRAIL_PCT / Decimal("100"))
    active = (
        _q_usdt(gross * USDT_ACTIVE_PCT / Decimal("100"))
        if PARTICIPATION_ACTIVE
        else Decimal("0")
    )
    return {
        "usdt_gross": str(gross),
        "trail_usdt": str(trail),
        "trail_pct": float(USDT_TRAIL_PCT),
        "trail_wallet": USDT_TRAIL_WALLET,
        "active_usdt": str(active),
        "active_pct": float(USDT_ACTIVE_PCT) if PARTICIPATION_ACTIVE else 0.0,
        "active_wallet": USDT_ACTIVE_WALLET,
        "participation_active": PARTICIPATION_ACTIVE,
        "founder_usdt_total": str(_q_usdt(trail + active)),
    }


def record_founder_usdt_on_payment(
    *,
    payment_ref: str,
    usdt_gross: str,
) -> Dict[str, Any]:
    init_alignment_db()
    alloc = allocate_founder_usdt(_d(usdt_gross))
    now = _now()
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO founder_usdt_trails (
                payment_ref, usdt_gross, trail_usdt, active_usdt,
                trail_wallet, active_wallet, participation_active, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (payment_ref or "")[:128],
                alloc["usdt_gross"],
                alloc["trail_usdt"],
                alloc["active_usdt"],
                alloc["trail_wallet"],
                alloc["active_wallet"],
                1 if alloc["participation_active"] else 0,
                now,
            ),
        )
        row_id = int(cur.lastrowid)
    return {"ok": True, "id": row_id, **alloc}


# ---------------------------------------------------------------------------
# Pillar 3 — Community referral program
# ---------------------------------------------------------------------------

def referral_program_spec() -> Dict[str, Any]:
    return {
        "name": "Bloodstone community referral",
        "pct_of_referred_commercial_usdt": float(REFERRAL_PCT),
        "earn_months": REFERRAL_MONTHS,
        "who": "Internal team and external promoters — one global sales force",
        "how": (
            "Promoter gets a code via POST /api/data-sales/referral/register. "
            "Customer passes referral_code on USDT claim. Referrer earns "
            f"{REFERRAL_PCT}% of that customer's commercial USDT for {REFERRAL_MONTHS} months "
            "from first payment (ops may extend policy)."
        ),
        "payout": "USDT to referrer wallet and/or STONE credit — ops configurable",
        "configure": {
            "REFERRAL_USDT_PCT": str(REFERRAL_PCT),
            "REFERRAL_EARN_MONTHS": REFERRAL_MONTHS,
        },
    }


def register_referral_code(
    *,
    owner_label: str,
    owner_stone_address: str = "",
    owner_usdt_wallet: str = "",
    channel: str = "community",
    code: str = "",
) -> Dict[str, Any]:
    init_alignment_db()
    raw = (code or "").strip()
    if not raw:
        raw = secrets.token_urlsafe(6).replace("-", "")[:10].upper()
    if not _CODE_RE.match(raw):
        raise ValueError("invalid referral code format")
    label = (owner_label or "promoter").strip()[:80]
    now = _now()
    with _conn() as conn:
        existing = conn.execute(
            "SELECT code FROM community_referral_codes WHERE code = ?",
            (raw,),
        ).fetchone()
        if existing:
            raise ValueError("code already registered")
        conn.execute(
            """
            INSERT INTO community_referral_codes (
                code, owner_label, owner_stone_address, owner_usdt_wallet,
                channel, active, created_at
            ) VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (
                raw,
                label,
                (owner_stone_address or "")[:128],
                (owner_usdt_wallet or "")[:128],
                (channel or "community")[:32],
                now,
            ),
        )
    return {
        "ok": True,
        "code": raw,
        "owner_label": label,
        "share_link_hint": f"?ref={raw}",
        "claim_field": "referral_code",
    }


def get_referral_code(code: str) -> Optional[Dict[str, Any]]:
    init_alignment_db()
    c = (code or "").strip()
    if not c:
        return None
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM community_referral_codes WHERE code = ? AND active = 1",
            (c,),
        ).fetchone()
    return dict(row) if row else None


def allocate_referral_usdt(gross_usdt: Decimal, code: str = "") -> Dict[str, Any]:
    row = get_referral_code(code) if code else None
    if not row:
        return {
            "referral_usdt": "0",
            "referral_pct": 0.0,
            "code": None,
            "owner_label": None,
        }
    gross = _q_usdt(gross_usdt)
    amt = _q_usdt(gross * REFERRAL_PCT / Decimal("100"))
    return {
        "referral_usdt": str(amt),
        "referral_pct": float(REFERRAL_PCT),
        "code": row["code"],
        "owner_label": row["owner_label"],
        "owner_usdt_wallet": row.get("owner_usdt_wallet") or "",
        "owner_stone_address": row.get("owner_stone_address") or "",
        "earn_months": REFERRAL_MONTHS,
    }


def record_referral_earning(
    *,
    code: str,
    payment_ref: str,
    usdt_gross: str,
    referred_customer: str = "",
) -> Dict[str, Any]:
    init_alignment_db()
    alloc = allocate_referral_usdt(_d(usdt_gross), code)
    if not alloc.get("code"):
        return {"ok": False, "error": "unknown or inactive referral code"}
    now = _now()
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO community_referral_earnings (
                code, payment_ref, usdt_gross, referral_usdt, referred_customer, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                alloc["code"],
                (payment_ref or "")[:128],
                str(usdt_gross),
                alloc["referral_usdt"],
                (referred_customer or "")[:128],
                now,
            ),
        )
        row_id = int(cur.lastrowid)
    return {"ok": True, "id": row_id, **alloc}


# ---------------------------------------------------------------------------
# Combined commercial waterfall (for quotes / transparency)
# ---------------------------------------------------------------------------

def commercial_waterfall(gross_usdt: Decimal, *, referral_code: str = "") -> Dict[str, Any]:
    """
    Order of cuts on gross commercial USDT (transparent residual):

      gross
        - referral (if code)
        - founder trail (perpetual)
        - founder active (if participating)
        - remaining → base team split + provider STONE pool (usdt_monetization)
    """
    gross = _q_usdt(gross_usdt)
    ref = allocate_referral_usdt(gross, referral_code)
    ref_amt = _q_usdt(ref["referral_usdt"])
    after_ref = _q_usdt(gross - ref_amt)

    founder = allocate_founder_usdt(after_ref)
    # Trail/active taken from post-referral gross (standard trail practice)
    founder_total = _q_usdt(founder["founder_usdt_total"])
    residual = _q_usdt(after_ref - founder_total)

    return {
        "usdt_gross": str(gross),
        "referral": ref,
        "founder": founder,
        "residual_usdt_for_team_and_providers": str(residual),
        "order": [
            "1. Gross commercial USDT",
            "2. Community referral cut (if code)",
            "3. Founding-member trail (perpetual)",
            "4. Founding-member active participation (if active)",
            "5. Residual → core team roles + STONE provider pool",
        ],
        "note": (
            "Trail survives retirement. Active stream and STONE monthly tranches "
            "require continued valuable participation."
        ),
    }


def alignment_payload() -> Dict[str, Any]:
    """Full structural package for portal / partner negotiation."""
    sample = commercial_waterfall(Decimal("100"), referral_code="")
    sample_ref = commercial_waterfall(Decimal("100"), referral_code="")  # no code
    return {
        "ok": True,
        "title": "Founder alignment + referral structure",
        "updated": _now(),
        "pillars": {
            "1_stone_long_term": stone_alignment_plan(),
            "2_usdt_trail_and_active": usdt_founder_streams(),
            "3_community_referral": referral_program_spec(),
        },
        "waterfall_example_100_usdt": sample,
        "summary_for_member": {
            "stone": (
                f"Initial {STONE_INITIAL_ALIGNMENT} STONE + "
                f"{STONE_MONTHLY_TRANCHE}/month × {STONE_TRANCHE_MONTHS} months "
                f"(cap {STONE_ALIGNMENT_CAP}), gated on participation."
            ),
            "usdt": (
                f"Trail {USDT_TRAIL_PCT}% perpetual + "
                f"active {USDT_ACTIVE_PCT}% while contributing "
                f"(combined {USDT_TRAIL_PCT + USDT_ACTIVE_PCT}% when active)."
            ),
            "referral": (
                f"Anyone can promote: {REFERRAL_PCT}% of referred commercial USDT "
                f"for {REFERRAL_MONTHS} months — team and externals same program."
            ),
        },
        "apis": {
            "structure": "/api/data-sales/alignment",
            "waterfall": "/api/data-sales/alignment/waterfall?usdt=100&ref=CODE",
            "referral_register": "POST /api/data-sales/referral/register",
            "schedule_monthly": "POST /api/data-sales/alignment/tranche",
        },
    }
