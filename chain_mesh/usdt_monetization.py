"""USDT-first resource monetization (Megadrive / STONE team model).

Public & corporate customers bill in **USDT** (EVM first).
Each receipt is accounted as:

  1. Core team split (USDT) — contracted role shares
  2. Remainder → buy STONE at published rate (fixed early-adopter, later float)
  3. STONE distributed to network resource providers
  4. Providers with attested STONE holdings unlock tiered bonus % (hold-to-earn)

This sits *alongside* native STONE treasury rails (early network settlement).
USDT is the commercial front door; STONE is the provider incentive layer.
"""

from __future__ import annotations

from chain_mesh.security import public_error
import json
import os
import time
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Optional, Tuple

from chain_mesh import db as mesh_db

# ---------------------------------------------------------------------------
# USDT commercial rates (billable to public / corporate)
# ---------------------------------------------------------------------------
USDT_PER_GIB_STORAGE = Decimal(os.environ.get("MONETIZE_USDT_PER_GIB", "0.05"))
USDT_PER_100MIB_BANDWIDTH = Decimal(
    os.environ.get("MONETIZE_USDT_PER_100MIB", "0.02")
)
USDT_PER_GFLOP_COMPUTE = Decimal(os.environ.get("MONETIZE_USDT_PER_GFLOP", "0.01"))
USDT_UPKEEP_PER_GIB_MONTH = Decimal(
    os.environ.get("MONETIZE_USDT_UPKEEP_PER_GIB_MONTH", "0.005")
)

# Central commercial treasury — EVM USDT (Ethereum mainnet ERC-20 by default).
USDT_TREASURY_EVM = (
    os.environ.get("MONETIZE_USDT_TREASURY_EVM")
    or os.environ.get("ETH_USDT_TREASURY")
    or os.environ.get("USDT_HOT_ADDRESS")
    or ""
).strip()
USDT_CHAIN = os.environ.get("MONETIZE_USDT_CHAIN", "erc20").strip().lower()
USDT_NETWORK_LABEL = os.environ.get(
    "MONETIZE_USDT_NETWORK_LABEL", "Ethereum ERC-20 USDT"
)

# STONE/USDT rate: fixed early (favourable to adopters), later float via exchange API.
# rate = USDT per 1 STONE (same convention as wallet swap STONE_TO_USDT_RATE).
RATE_MODE = (os.environ.get("MONETIZE_STONE_USDT_RATE_MODE", "fixed") or "fixed").strip().lower()
# Default 0.0001 USDT/STONE → 10_000 STONE per USDT (early-adopter friendly).
FIXED_USDT_PER_STONE = Decimal(
    os.environ.get(
        "MONETIZE_STONE_USDT_RATE",
        os.environ.get("SWAP_STONE_USDT_RATE", "0.0001"),
    )
)
FLOAT_API_URL = os.environ.get("MONETIZE_STONE_PRICE_API", "").strip()

# Team split of *gross USDT* (percentages must sum ≤ 100; remainder → provider STONE pool).
# Format: role:pct:wallet,role:pct:wallet
# Example: ops:15:0x..,core:20:0x..,stone:10:0x..
_DEFAULT_TEAM = "ops:15:,core:20:,bd:10:,stone:10:"
TEAM_SPLIT_RAW = os.environ.get("MONETIZE_TEAM_SPLIT", _DEFAULT_TEAM)

# Provider hold-to-earn tiers: min_stone:bonus_pct
# Example: 0:0,1000:5,10000:10,50000:15
_DEFAULT_TIERS = "0:0,1000:5,10000:10,50000:15"
PROVIDER_TIERS_RAW = os.environ.get("MONETIZE_PROVIDER_TIERS", _DEFAULT_TIERS)

BYTES_PER_GIB = 1024 * 1024 * 1024
BYTES_PER_100MIB = 100 * 1024 * 1024
FLOPS_PER_GFLOP = 1_000_000_000


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


def parse_team_splits() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for part in (TEAM_SPLIT_RAW or "").split(","):
        part = part.strip()
        if not part:
            continue
        bits = part.split(":")
        if len(bits) < 2:
            continue
        role = bits[0].strip() or "role"
        try:
            pct = float(bits[1])
        except ValueError:
            continue
        wallet = bits[2].strip() if len(bits) > 2 else ""
        if pct <= 0:
            continue
        rows.append(
            {
                "role": role,
                "share_pct": pct,
                "usdt_wallet": wallet,
                "stone_wallet": wallet,  # same field may hold S… or 0x…; ops set appropriately
                "note": "contracted core team share — same % on USDT and STONE revenue",
            }
        )
    return rows


def parse_provider_tiers() -> List[Dict[str, Any]]:
    tiers: List[Dict[str, Any]] = []
    for part in (PROVIDER_TIERS_RAW or "").split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        mn, bp = part.split(":", 1)
        try:
            tiers.append(
                {
                    "min_stone_held": float(mn),
                    "bonus_pct": float(bp),
                }
            )
        except ValueError:
            continue
    tiers.sort(key=lambda t: t["min_stone_held"])
    if not tiers:
        tiers = [{"min_stone_held": 0, "bonus_pct": 0}]
    return tiers


def usdt_per_stone() -> Decimal:
    """USDT received per 1 STONE sold into the provider pool (or market mid)."""
    if RATE_MODE == "float" and FLOAT_API_URL:
        try:
            import urllib.request

            with urllib.request.urlopen(FLOAT_API_URL, timeout=8) as resp:
                body = json.loads(resp.read().decode())
            # Accept { "usdt_per_stone": n } or { "price": n }
            price = body.get("usdt_per_stone") or body.get("price") or body.get("USDT_PER_STONE")
            if price is not None:
                return _d(price)
        except Exception:
            pass
    return FIXED_USDT_PER_STONE


def stone_per_usdt() -> Decimal:
    rate = usdt_per_stone()
    if rate <= 0:
        return Decimal("0")
    return _q_stone(Decimal("1") / rate)


def init_monetization_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS usdt_resource_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_ref TEXT NOT NULL DEFAULT '',
                usdt_txid TEXT NOT NULL DEFAULT '',
                payer_ref TEXT NOT NULL DEFAULT '',
                stone_address TEXT NOT NULL DEFAULT '',
                product TEXT NOT NULL,
                units REAL NOT NULL DEFAULT 0,
                usdt_gross TEXT NOT NULL,
                usdt_team TEXT NOT NULL,
                usdt_provider_pool TEXT NOT NULL,
                stone_for_providers TEXT NOT NULL,
                usdt_per_stone TEXT NOT NULL,
                rate_mode TEXT NOT NULL DEFAULT 'fixed',
                team_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'recorded',
                memo TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_usdt_resource_ref
                ON usdt_resource_payments(payment_ref)
                WHERE payment_ref != '';
            CREATE INDEX IF NOT EXISTS idx_usdt_resource_product
                ON usdt_resource_payments(product, created_at DESC);

            CREATE TABLE IF NOT EXISTS usdt_team_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                share_pct REAL NOT NULL,
                usdt_amount TEXT NOT NULL,
                usdt_wallet TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            );
            -- usdt_amount column also stores STONE amounts when status=recorded_stone


            CREATE TABLE IF NOT EXISTS provider_distribution_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_id INTEGER NOT NULL,
                provider_stone_address TEXT NOT NULL,
                product TEXT NOT NULL DEFAULT '',
                base_stone TEXT NOT NULL,
                bonus_pct REAL NOT NULL DEFAULT 0,
                bonus_stone TEXT NOT NULL DEFAULT '0',
                total_stone TEXT NOT NULL,
                attested_holdings TEXT NOT NULL DEFAULT '0',
                tier_label TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_provider_dist_addr
                ON provider_distribution_ledger(provider_stone_address, created_at DESC);
            """
        )


def commercial_rates() -> Dict[str, Any]:
    """Published USDT price list for resources."""
    return {
        "currency": "USDT",
        "network": USDT_NETWORK_LABEL,
        "chain": USDT_CHAIN,
        "treasury_evm": USDT_TREASURY_EVM,
        "storage": {
            "usdt_per_unit": float(USDT_PER_GIB_STORAGE),
            "unit": "1 GiB write credit",
            "display": f"{USDT_PER_GIB_STORAGE} USDT / GiB",
        },
        "upkeep": {
            "usdt_per_unit": float(USDT_UPKEEP_PER_GIB_MONTH),
            "unit": "1 GiB · month retained",
            "display": f"{USDT_UPKEEP_PER_GIB_MONTH} USDT / GiB · month",
        },
        "bandwidth": {
            "usdt_per_unit": float(USDT_PER_100MIB_BANDWIDTH),
            "unit": "100 MiB",
            "display": f"{USDT_PER_100MIB_BANDWIDTH} USDT / 100 MiB",
        },
        "compute": {
            "usdt_per_unit": float(USDT_PER_GFLOP_COMPUTE),
            "unit": "1 GFLOP",
            "display": f"{USDT_PER_GFLOP_COMPUTE} USDT / GFLOP",
        },
        "note": (
            "Commercial billing is USDT-first (EVM). Native STONE treasury rails remain "
            "for mesh-native users; both fund the same provider capacity."
        ),
    }


def quote_resource(
    product: str, units: float = 1.0, *, referral_code: str = ""
) -> Dict[str, Any]:
    """Quote USDT for a product quantity, plus team/provider split preview."""
    product = (product or "").strip().lower()
    units = max(0.0, float(units))
    if product in ("storage", "mesh_storage"):
        unit_price = USDT_PER_GIB_STORAGE
        unit_label = "GiB"
    elif product in ("upkeep", "storage_upkeep", "retention"):
        unit_price = USDT_UPKEEP_PER_GIB_MONTH
        unit_label = "GiB·month"
        product = "upkeep"
    elif product in ("bandwidth", "data", "transfer"):
        unit_price = USDT_PER_100MIB_BANDWIDTH
        unit_label = "×100 MiB"
    elif product == "compute":
        unit_price = USDT_PER_GFLOP_COMPUTE
        unit_label = "GFLOP"
    else:
        raise ValueError("product must be storage, upkeep, bandwidth, or compute")

    gross = _q_usdt(unit_price * _d(units))
    split = allocate_usdt(gross, referral_code=referral_code)
    return {
        "ok": True,
        "product": product,
        "units": units,
        "unit_label": unit_label,
        "usdt_per_unit": float(unit_price),
        "usdt_gross": str(gross),
        "treasury_evm": USDT_TREASURY_EVM,
        "network": USDT_NETWORK_LABEL,
        "referral_code": referral_code or None,
        "split": split,
        "pay_instruction": (
            f"Send {gross} USDT ({USDT_NETWORK_LABEL}) to {USDT_TREASURY_EVM or 'TREASURY'} "
            f"then POST /api/data-sales/usdt/claim with usdt_txid + product + units + stone_address"
            + (f" + referral_code={referral_code}" if referral_code else "")
        ),
    }


def allocate_revenue(
    gross: Decimal, *, currency: str = "USDT", referral_code: str = ""
) -> Dict[str, Any]:
    """Shared waterfall for USDT *or* STONE — same percentages both rails.

    Order: referral → founder trail → founder active → team roles → provider residual.
    """
    from chain_mesh import founder_alignment as align

    unit = (currency or "USDT").strip().upper()
    if unit not in ("USDT", "STONE"):
        unit = "USDT"
    q = _q_usdt if unit == "USDT" else _q_stone

    gross = q(gross)
    water = align.commercial_waterfall(gross, referral_code=referral_code or "")
    # Waterfall keys say usdt_* but amounts are unit-agnostic decimals
    residual = q(_d(water["residual_usdt_for_team_and_providers"]))

    team = parse_team_splits()
    team_rows = []
    team_total = Decimal("0")
    for row in team:
        amt = q(residual * _d(row["share_pct"]) / Decimal("100"))
        team_total += amt
        entry = {
            **row,
            "amount": str(amt),
            "currency": unit,
            "usdt_amount": str(amt) if unit == "USDT" else None,
            "stone_amount": str(amt) if unit == "STONE" else None,
        }
        team_rows.append(entry)
    if team_total > residual and team_total > 0:
        scale = residual / team_total
        team_total = Decimal("0")
        for row in team_rows:
            amt = q(_d(row["amount"]) * scale)
            row["amount"] = str(amt)
            if unit == "USDT":
                row["usdt_amount"] = str(amt)
            else:
                row["stone_amount"] = str(amt)
            team_total += amt

    provider_residual = q(residual - team_total)
    team_pct = float((team_total / gross * 100) if gross > 0 else 0)
    provider_pct = float((provider_residual / gross * 100) if gross > 0 else 0)

    rate = usdt_per_stone()
    if unit == "USDT":
        stone_for_providers = (
            _q_stone(provider_residual / rate) if rate > 0 else Decimal("0")
        )
        provider_usdt = provider_residual
        provider_stone = stone_for_providers
    else:
        # Already STONE: provider residual is STONE for the provider pool
        provider_usdt = None
        provider_stone = provider_residual
        stone_for_providers = provider_residual

    return {
        "currency": unit,
        "gross": str(gross),
        "usdt_gross": str(gross) if unit == "USDT" else None,
        "stone_gross": str(gross) if unit == "STONE" else None,
        "waterfall": water,
        "referral": water.get("referral") or {},
        "referral_amount": water["referral"].get("referral_usdt", "0"),
        "founder_trail_amount": water["founder"].get("trail_usdt", "0"),
        "founder_active_amount": water["founder"].get("active_usdt", "0"),
        "founder_total_amount": water["founder"].get("founder_usdt_total", "0"),
        # Back-compat USDT keys
        "referral_usdt": water["referral"].get("referral_usdt", "0")
        if unit == "USDT"
        else water["referral"].get("referral_usdt", "0"),
        "founder_trail_usdt": water["founder"].get("trail_usdt", "0"),
        "founder_active_usdt": water["founder"].get("active_usdt", "0"),
        "founder_usdt_total": water["founder"].get("founder_usdt_total", "0"),
        "residual_after_founder": str(residual),
        "team": team_rows,
        "team_total": str(team_total),
        "team_usdt": str(team_total) if unit == "USDT" else None,
        "team_stone": str(team_total) if unit == "STONE" else None,
        "team_pct": round(team_pct, 4),
        "provider_pool_amount": str(provider_residual),
        "provider_pool_usdt": str(provider_usdt) if provider_usdt is not None else None,
        "provider_pool_pct": round(provider_pct, 4),
        "usdt_per_stone": str(rate),
        "stone_per_usdt": str(stone_per_usdt()),
        "stone_for_providers": str(stone_for_providers),
        "provider_stone": str(provider_stone),
        "rate_mode": RATE_MODE if RATE_MODE in ("fixed", "float") else "fixed",
        "same_pct_both_rails": True,
        "rate_note": (
            "Team/founder/referral percentages are identical for USDT and direct STONE. "
            + (
                "USDT residual converts to STONE for providers at published rate."
                if unit == "USDT"
                else "STONE residual is the provider pool (no conversion)."
            )
        ),
    }


def allocate_usdt(
    gross_usdt: Decimal, *, referral_code: str = ""
) -> Dict[str, Any]:
    """USDT commercial waterfall (same % as allocate_stone)."""
    return allocate_revenue(
        gross_usdt, currency="USDT", referral_code=referral_code
    )


def allocate_stone(
    gross_stone: Decimal, *, referral_code: str = ""
) -> Dict[str, Any]:
    """Direct STONE treasury payment waterfall — same % as USDT."""
    return allocate_revenue(
        gross_stone, currency="STONE", referral_code=referral_code
    )


def record_stone_payment(
    *,
    product: str,
    amount_stone: str,
    txid: str = "",
    stone_address: str = "",
    referral_code: str = "",
    payment_ref: str = "",
) -> Dict[str, Any]:
    """Book team/founder/referral/provider split for a direct STONE claim."""
    from chain_mesh import founder_alignment as align

    init_monetization_db()
    gross = _q_stone(_d(amount_stone))
    split = allocate_stone(gross, referral_code=referral_code)
    ref = (payment_ref or "").strip() or (
        f"stone:{txid}:{product}" if txid else f"stone:manual:{_now()}:{product}"
    )
    now = _now()

    # Reuse usdt_resource_payments table with currency marker in memo/status
    with _conn() as conn:
        existing = conn.execute(
            "SELECT id FROM usdt_resource_payments WHERE payment_ref = ?",
            (ref,),
        ).fetchone()
        if existing:
            return {
                "ok": True,
                "duplicate": True,
                "payment_id": int(existing["id"]),
                "payment_ref": ref,
                "split": split,
            }
        cur = conn.execute(
            """
            INSERT INTO usdt_resource_payments (
                payment_ref, usdt_txid, payer_ref, stone_address, product, units,
                usdt_gross, usdt_team, usdt_provider_pool, stone_for_providers,
                usdt_per_stone, rate_mode, team_json, status, memo, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'recorded_stone', ?, ?)
            """,
            (
                ref,
                (txid or "")[:128],
                "stone-rail",
                (stone_address or "")[:128],
                (product or "")[:32],
                float(split.get("stone_gross") or gross),
                # Store STONE amounts in the numeric fields for accounting (labeled in memo)
                split["gross"],
                split["team_total"],
                split["provider_pool_amount"],
                split["stone_for_providers"],
                "1",  # 1 STONE = 1 STONE on this rail
                "stone_rail",
                json.dumps(
                    {
                        "currency": "STONE",
                        "team": split["team"],
                        "referral": split.get("referral_amount"),
                        "founder_trail": split.get("founder_trail_amount"),
                        "founder_active": split.get("founder_active_amount"),
                        "same_pct_as_usdt": True,
                    }
                ),
                f"STONE rail split product={product}",
                now,
            ),
        )
        payment_id = int(cur.lastrowid)
        for row in split["team"]:
            conn.execute(
                """
                INSERT INTO usdt_team_allocations (
                    payment_id, role, share_pct, usdt_amount, usdt_wallet, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payment_id,
                    row["role"],
                    float(row["share_pct"]),
                    row.get("stone_amount") or row.get("amount") or "0",
                    row.get("stone_wallet") or row.get("usdt_wallet") or "",
                    now,
                ),
            )

    founder_book = align.record_founder_usdt_on_payment(
        payment_ref=ref, usdt_gross=str(gross)
    )
    # Tag founder book is STONE units (same %); field names remain for ledger compat
    founder_book["currency"] = "STONE"
    founder_book["note"] = "Founder trail/active applied as STONE units at same %"

    referral_book = None
    if referral_code:
        referral_book = align.record_referral_earning(
            code=referral_code,
            payment_ref=ref,
            usdt_gross=str(gross),
            referred_customer=stone_address,
        )
        if referral_book.get("ok"):
            referral_book["currency"] = "STONE"

    return {
        "ok": True,
        "payment_id": payment_id,
        "payment_ref": ref,
        "currency": "STONE",
        "product": product,
        "amount_stone": str(gross),
        "split": split,
        "founder_book": founder_book,
        "referral_book": referral_book,
    }


def provider_tier_for_holdings(stone_held: float) -> Dict[str, Any]:
    tiers = parse_provider_tiers()
    held = max(0.0, float(stone_held))
    chosen = tiers[0]
    for t in tiers:
        if held >= float(t["min_stone_held"]):
            chosen = t
    return {
        "attested_holdings": held,
        "min_stone_held": chosen["min_stone_held"],
        "bonus_pct": chosen["bonus_pct"],
        "tier_label": f"≥{chosen['min_stone_held']:g} STONE → +{chosen['bonus_pct']:g}%",
        "all_tiers": tiers,
        "note": (
            "Hold-to-earn for resource providers: attested on-chain STONE balance "
            "unlocks higher distribution of the provider pool (not a huge jump — keep fair)."
        ),
    }


def apply_provider_bonus(base_stone: Decimal, stone_held: float) -> Dict[str, Any]:
    tier = provider_tier_for_holdings(stone_held)
    bonus_pct = _d(tier["bonus_pct"])
    bonus = _q_stone(base_stone * bonus_pct / Decimal("100"))
    total = _q_stone(base_stone + bonus)
    return {
        "base_stone": str(base_stone),
        "bonus_pct": float(bonus_pct),
        "bonus_stone": str(bonus),
        "total_stone": str(total),
        "tier": tier,
    }


def record_usdt_payment(
    *,
    product: str,
    units: float,
    usdt_gross: Optional[str] = None,
    usdt_txid: str = "",
    stone_address: str = "",
    payer_ref: str = "",
    memo: str = "",
    payment_ref: str = "",
    referral_code: str = "",
) -> Dict[str, Any]:
    """Record a commercial USDT payment and book full waterfall splits."""
    from chain_mesh import founder_alignment as align

    init_monetization_db()
    quote = quote_resource(product, units, referral_code=referral_code)
    if usdt_gross is None:
        gross = _q_usdt(quote["usdt_gross"])
    else:
        gross = _q_usdt(usdt_gross)
    split = allocate_usdt(gross, referral_code=referral_code)
    ref = (payment_ref or "").strip() or (
        f"usdt:{usdt_txid}:{product}" if usdt_txid else f"usdt:manual:{_now()}:{product}"
    )
    now = _now()

    with _conn() as conn:
        if ref:
            existing = conn.execute(
                "SELECT id FROM usdt_resource_payments WHERE payment_ref = ?",
                (ref,),
            ).fetchone()
            if existing:
                return {
                    "ok": True,
                    "duplicate": True,
                    "payment_id": int(existing["id"]),
                    "payment_ref": ref,
                }

        cur = conn.execute(
            """
            INSERT INTO usdt_resource_payments (
                payment_ref, usdt_txid, payer_ref, stone_address, product, units,
                usdt_gross, usdt_team, usdt_provider_pool, stone_for_providers,
                usdt_per_stone, rate_mode, team_json, status, memo, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'recorded', ?, ?)
            """,
            (
                ref,
                (usdt_txid or "")[:128],
                (payer_ref or "")[:128],
                (stone_address or "")[:128],
                quote["product"],
                float(units),
                split["usdt_gross"],
                split["team_usdt"],
                split["provider_pool_usdt"],
                split["stone_for_providers"],
                split["usdt_per_stone"],
                split["rate_mode"],
                json.dumps(
                    {
                        "team": split["team"],
                        "referral": split.get("referral_usdt"),
                        "founder_trail": split.get("founder_trail_usdt"),
                        "founder_active": split.get("founder_active_usdt"),
                    }
                ),
                (memo or "")[:500],
                now,
            ),
        )
        payment_id = int(cur.lastrowid)
        for row in split["team"]:
            conn.execute(
                """
                INSERT INTO usdt_team_allocations (
                    payment_id, role, share_pct, usdt_amount, usdt_wallet, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payment_id,
                    row["role"],
                    float(row["share_pct"]),
                    row["usdt_amount"],
                    row.get("usdt_wallet") or "",
                    now,
                ),
            )

    founder_book = align.record_founder_usdt_on_payment(
        payment_ref=ref, usdt_gross=str(gross)
    )
    referral_book = None
    if referral_code:
        referral_book = align.record_referral_earning(
            code=referral_code,
            payment_ref=ref,
            usdt_gross=str(gross),
            referred_customer=stone_address or payer_ref,
        )

    return {
        "ok": True,
        "payment_id": payment_id,
        "payment_ref": ref,
        "product": quote["product"],
        "units": float(units),
        "usdt_txid": usdt_txid,
        "stone_address": stone_address,
        "split": split,
        "founder_book": founder_book,
        "referral_book": referral_book,
        "credit_hint": (
            "Apply mesh credits via existing STONE claim rails or ops credit for "
            f"product={quote['product']} units={units} on stone_address"
        ),
    }


def distribute_to_provider(
    *,
    payment_id: int,
    provider_stone_address: str,
    base_stone: str,
    attested_holdings: float = 0,
    product: str = "",
) -> Dict[str, Any]:
    """Allocate provider-pool STONE with hold-to-earn tier bonus."""
    init_monetization_db()
    addr = (provider_stone_address or "").strip()
    if len(addr) < 25:
        raise ValueError("provider_stone_address required")
    base = _q_stone(_d(base_stone))
    if base <= 0:
        raise ValueError("base_stone must be positive")
    applied = apply_provider_bonus(base, attested_holdings)
    now = _now()
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO provider_distribution_ledger (
                payment_id, provider_stone_address, product,
                base_stone, bonus_pct, bonus_stone, total_stone,
                attested_holdings, tier_label, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(payment_id),
                addr,
                (product or "")[:32],
                applied["base_stone"],
                float(applied["bonus_pct"]),
                applied["bonus_stone"],
                applied["total_stone"],
                str(_q_stone(_d(attested_holdings))),
                applied["tier"]["tier_label"],
                now,
            ),
        )
        dist_id = int(cur.lastrowid)
    return {"ok": True, "distribution_id": dist_id, **applied, "provider_stone_address": addr}


def monetization_payload() -> Dict[str, Any]:
    """Full commercial model for portal / data-sales / partner decks."""
    rate = usdt_per_stone()
    team = parse_team_splits()
    team_pct = sum(float(t["share_pct"]) for t in team)
    provider_pct = max(0.0, 100.0 - team_pct)
    sample = allocate_usdt(Decimal("100"))  # $100 USDT worked example

    return {
        "ok": True,
        "title": "Bloodstone resource monetization",
        "model": (
            "USDT or direct STONE → same team/founder/referral % → provider pool "
            "→ hold-to-earn tiers"
        ),
        "updated": _now(),
        "commercial": commercial_rates(),
        "rails_aligned": True,
        "flow": [
            {
                "step": 1,
                "title": "Pay in USDT (commercial) or STONE (mesh-native)",
                "detail": (
                    "Two front doors, one split policy. USDT to EVM treasury or STONE to "
                    "product treasuries — team percentages match on both rails."
                ),
            },
            {
                "step": 2,
                "title": "Same waterfall both rails",
                "detail": (
                    "Referral → founder trail → founder active → team roles "
                    f"({team_pct:g}% of residual after founder cuts) → provider residual."
                ),
            },
            {
                "step": 3,
                "title": "Provider pool",
                "detail": (
                    f"USDT residual converts to STONE @ {rate} USDT/STONE; "
                    "STONE residual stays STONE for providers."
                ),
            },
            {
                "step": 4,
                "title": "Hold-to-earn tiers",
                "detail": (
                    "Providers who attest higher on-chain STONE holdings unlock modest "
                    "distribution bonuses (+5%, +X%) — fair, not a huge jump."
                ),
            },
        ],
        "team_split": {
            "roles": team,
            "total_team_pct": team_pct,
            "provider_pool_pct": provider_pct,
            "applies_to": ["USDT", "STONE"],
            "configure": "MONETIZE_TEAM_SPLIT=role:pct:wallet (same % on USDT and STONE)",
            "how_to_slot_upside": (
                "Add your contracted role to MONETIZE_TEAM_SPLIT with share_pct and "
                "payout wallet. Same percentage applies to commercial USDT and direct "
                "STONE data sales. Optional: hold STONE as a provider for tier bonuses."
            ),
        },
        "worked_example_100_stone": allocate_stone(Decimal("100")),
        "stone_rate": {
            "mode": RATE_MODE if RATE_MODE in ("fixed", "float") else "fixed",
            "usdt_per_stone": str(rate),
            "stone_per_usdt": str(stone_per_usdt()),
            "early_adopter_note": (
                "Fixed rate is set favourable to early adopters; later MONETIZE_STONE_USDT_RATE_MODE=float "
                "with MONETIZE_STONE_PRICE_API for exchange mid."
            ),
            "price_api": FLOAT_API_URL or None,
        },
        "provider_tiers": {
            "tiers": parse_provider_tiers(),
            "example": provider_tier_for_holdings(0),
            "configure": "MONETIZE_PROVIDER_TIERS=0:0,1000:5,10000:10,50000:15",
        },
        "worked_example_100_usdt": sample,
        "native_stone_rails": {
            "still_available": True,
            "note": (
                "Mesh-native users can still pay STONE treasuries directly "
                "(/data/ STONE rates). Commercial USDT path is for public/corporate accessibility."
            ),
            "stone_data_sales": "/data/",
        },
        "founder_alignment": _founder_alignment_embed(),
        "apis": {
            "model": "/api/data-sales/monetization",
            "alignment": "/api/data-sales/alignment",
            "quote": "/api/data-sales/usdt/quote?product=storage&units=10",
            "claim": "POST /api/data-sales/usdt/claim",
            "tier": "/api/data-sales/provider-tier?stone_held=5000",
            "referral_register": "POST /api/data-sales/referral/register",
        },
    }


def _founder_alignment_embed() -> Dict[str, Any]:
    try:
        from chain_mesh import founder_alignment as align

        return align.alignment_payload()
    except Exception as exc:
        return {"ok": False, "error": public_error(exc)}


def summary_stats() -> Dict[str, Any]:
    init_monetization_db()
    try:
        with _conn() as conn:
            n = conn.execute(
                "SELECT COUNT(*) AS n FROM usdt_resource_payments"
            ).fetchone()["n"]
            gross = conn.execute(
                "SELECT COALESCE(SUM(CAST(usdt_gross AS REAL)),0) AS t FROM usdt_resource_payments"
            ).fetchone()["t"]
            team = conn.execute(
                "SELECT COALESCE(SUM(CAST(usdt_team AS REAL)),0) AS t FROM usdt_resource_payments"
            ).fetchone()["t"]
            stone = conn.execute(
                "SELECT COALESCE(SUM(CAST(stone_for_providers AS REAL)),0) AS t FROM usdt_resource_payments"
            ).fetchone()["t"]
    except Exception:
        n, gross, team, stone = 0, 0.0, 0.0, 0.0
    return {
        "payments_recorded": int(n),
        "usdt_gross_total": float(gross or 0),
        "usdt_team_total": float(team or 0),
        "stone_for_providers_total": float(stone or 0),
    }
