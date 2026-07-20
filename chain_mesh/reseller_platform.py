"""Bulk reseller + public referrer platform (backend policy).

Implements Megadrive product rules:
- Bulk providers: backend + branded frontend, stake STONE, discount 5%→15%
- Min tenants / revenue before payouts (anti-gaming)
- Referrers: 2.5%–5% by stake/volume, dashboard + links, no wholesale purchase UI
- End users: SSO-ready identity, resource calculator, usage projections
- Payment addresses from public network config (single auditable source)

STONE stake attestation uses Bloodstone chain balances when RPC available.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Optional, Tuple

from chain_mesh import db as mesh_db

# --- Bulk provider economics ---
BULK_DISCOUNT_START_PCT = float(os.environ.get("RESELLER_BULK_DISCOUNT_START", "5"))
BULK_DISCOUNT_MAX_PCT = float(os.environ.get("RESELLER_BULK_DISCOUNT_MAX", "15"))
BULK_MIN_TENANTS_FOR_PAYOUT = int(os.environ.get("RESELLER_MIN_TENANTS", "10"))
BULK_MIN_REVENUE_USDT = Decimal(os.environ.get("RESELLER_MIN_REVENUE_USDT", "100"))
BULK_STAKE_MIN_STONE = Decimal(os.environ.get("RESELLER_STAKE_MIN_STONE", "10000"))

# Referrer economics (not resellers)
REF_BPS_MIN = int(os.environ.get("RESELLER_REF_BPS_MIN", "250"))  # 2.5%
REF_BPS_MAX = int(os.environ.get("RESELLER_REF_BPS_MAX", "500"))  # 5%
REF_STAKE_FOR_MAX = Decimal(os.environ.get("RESELLER_REF_STAKE_FOR_MAX", "50000"))

# EVM payment router (trustless) — set after deploy
EVM_ROUTER = os.environ.get("BLOODSTONE_REVENUE_ROUTER", "").strip()
EVM_USDT = os.environ.get(
    "EVM_USDT_TOKEN", "0xdAC17F958D2ee523a2206206994597C13D831ec7"
).strip()
EVM_USDC = os.environ.get(
    "EVM_USDC_TOKEN", "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
).strip()
EVM_CHAIN_ID = int(os.environ.get("EVM_CHAIN_ID", "1"))

PUBLIC_ROOT = os.environ.get(
    "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
).rstrip("/")


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def _d(v) -> Decimal:
    return Decimal(str(v))


def _q(v: Decimal) -> Decimal:
    return _d(v).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)


def init_reseller_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS reseller_orgs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'bulk',  -- bulk | referrer
                owner_email TEXT NOT NULL DEFAULT '',
                owner_oauth_sub TEXT NOT NULL DEFAULT '',
                brand_json TEXT NOT NULL DEFAULT '{}',
                custom_domain TEXT NOT NULL DEFAULT '',
                stone_address TEXT NOT NULL DEFAULT '',
                stake_stone TEXT NOT NULL DEFAULT '0',
                usdt_wallet TEXT NOT NULL DEFAULT '',
                usdc_wallet TEXT NOT NULL DEFAULT '',
                fx_mode TEXT NOT NULL DEFAULT 'manual', -- manual | api
                fx_rate TEXT NOT NULL DEFAULT '1',
                fx_api_url TEXT NOT NULL DEFAULT '',
                payment_gateways_json TEXT NOT NULL DEFAULT '{}',
                discount_pct REAL NOT NULL DEFAULT 5,
                active INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reseller_tenants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER NOT NULL,
                external_user_key TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                display_name TEXT NOT NULL DEFAULT '',
                oauth_provider TEXT NOT NULL DEFAULT '',
                oauth_sub TEXT NOT NULL DEFAULT '',
                stone_address TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                UNIQUE(org_id, external_user_key)
            );
            CREATE TABLE IF NOT EXISTS reseller_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER NOT NULL,
                tenant_id INTEGER NOT NULL DEFAULT 0,
                product TEXT NOT NULL,
                units REAL NOT NULL DEFAULT 0,
                period TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reseller_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER NOT NULL,
                tenant_id INTEGER NOT NULL DEFAULT 0,
                product TEXT NOT NULL,
                units REAL NOT NULL,
                currency TEXT NOT NULL,
                amount TEXT NOT NULL,
                discount_pct REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                payment_ref TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reseller_referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_id INTEGER NOT NULL,
                code TEXT NOT NULL UNIQUE,
                clicks INTEGER NOT NULL DEFAULT 0,
                conversions INTEGER NOT NULL DEFAULT 0,
                earned_usdt TEXT NOT NULL DEFAULT '0',
                created_at INTEGER NOT NULL
            );
            """
        )


# ---------------------------------------------------------------------------
# Public auditable payment config (single source for all apps)
# ---------------------------------------------------------------------------

def payment_config_payload() -> Dict[str, Any]:
    """Hardcoded-into-app alternative: apps always fetch this."""
    from chain_mesh import usdt_monetization as mon
    from chain_mesh import founder_alignment as align

    team = mon.parse_team_splits()
    founder = align.usdt_founder_streams()
    return {
        "ok": True,
        "updated": _now(),
        "public": True,
        "auditable": True,
        "note": (
            "Single point of truth for payment addresses. Frontends and reseller "
            "apps MUST read this API — not hardcode forever. EVM router holds no keys "
            "after lock+renounce; splits are on-chain."
        ),
        "evm": {
            "chain_id": EVM_CHAIN_ID,
            "revenue_router": EVM_ROUTER or None,
            "usdt": EVM_USDT,
            "usdc": EVM_USDC,
            "router_status": "configured" if EVM_ROUTER else "pending_deploy",
            "trust_model": "no_held_keys_after_renounce",
        },
        "stone_treasuries": _stone_treasuries(),
        "team_split_pct": team,
        "founder": {
            "trail_pct": founder["trail"]["pct_of_gross_usdt"],
            "active_pct": founder["active_participation"]["pct_of_gross_usdt"],
            "trail_wallet": founder["trail"]["wallet"],
            "active_wallet": founder["active_participation"]["wallet"],
        },
        "referral": {
            "bps_min": REF_BPS_MIN,
            "bps_max": REF_BPS_MAX,
            "note": "Referrers (not resellers) capped 2.5%–5% by stake/volume",
        },
        "bulk_provider": {
            "discount_start_pct": BULK_DISCOUNT_START_PCT,
            "discount_max_pct": BULK_DISCOUNT_MAX_PCT,
            "min_tenants_for_payout": BULK_MIN_TENANTS_FOR_PAYOUT,
            "min_revenue_usdt": str(BULK_MIN_REVENUE_USDT),
            "stake_min_stone": str(BULK_STAKE_MIN_STONE),
            "stake_note": "Variable by Bloodstone governance",
            "network_pay_methods": ["STONE", "USDT", "USDC"],
        },
        "sso_providers": ["google", "github", "linkedin"],
        "apis": {
            "payment_config": f"{PUBLIC_ROOT}/api/network/payment-config",
            "rates_usdt": f"{PUBLIC_ROOT}/api/data-sales/usdt/quote",
            "rates_stone": f"{PUBLIC_ROOT}/api/data-sales",
            "calculator": f"{PUBLIC_ROOT}/reseller/api/calculator",
            "reseller_app": f"{PUBLIC_ROOT}/reseller/",
        },
    }


def _stone_treasuries() -> Dict[str, str]:
    try:
        from chain_mesh import stone_data_payments as sdp

        return sdp.treasuries()
    except Exception:
        return {
            "storage": os.environ.get("DATA_SALES_TREASURY_STORAGE", ""),
            "bandwidth": os.environ.get("DATA_SALES_TREASURY_BANDWIDTH", ""),
            "compute": os.environ.get("DATA_SALES_TREASURY_COMPUTE", ""),
        }


# ---------------------------------------------------------------------------
# Discount / referral bps policy
# ---------------------------------------------------------------------------

def bulk_discount_pct(*, unique_tenants: int, revenue_usdt: Decimal, stake_stone: Decimal) -> Dict[str, Any]:
    """5% start → up to 15% with growth; payout eligibility gated."""
    stake_ok = stake_stone >= BULK_STAKE_MIN_STONE
    # Linear-ish growth: tenants and revenue push discount up
    t_factor = min(1.0, unique_tenants / 50.0)
    r_factor = min(1.0, float(revenue_usdt / max(BULK_MIN_REVENUE_USDT * 10, Decimal("1"))))
    growth = max(t_factor, r_factor)
    discount = BULK_DISCOUNT_START_PCT + (BULK_DISCOUNT_MAX_PCT - BULK_DISCOUNT_START_PCT) * growth
    payout_eligible = (
        stake_ok
        and unique_tenants >= BULK_MIN_TENANTS_FOR_PAYOUT
        and revenue_usdt >= BULK_MIN_REVENUE_USDT
    )
    return {
        "discount_pct": round(discount, 2),
        "payout_eligible": payout_eligible,
        "stake_ok": stake_ok,
        "stake_min_stone": str(BULK_STAKE_MIN_STONE),
        "min_tenants": BULK_MIN_TENANTS_FOR_PAYOUT,
        "min_revenue_usdt": str(BULK_MIN_REVENUE_USDT),
        "unique_tenants": unique_tenants,
        "revenue_usdt": str(revenue_usdt),
        "reason": (
            "ok"
            if payout_eligible
            else "Need stake + ≥"
            f"{BULK_MIN_TENANTS_FOR_PAYOUT} unique tenants + ≥{BULK_MIN_REVENUE_USDT} USDT revenue"
        ),
    }


def referral_bps(*, stake_stone: Decimal, volume_usdt: Decimal) -> Dict[str, Any]:
    """2.5%–5% for pure referrers by stake + volume."""
    stake_f = min(1.0, float(stake_stone / max(REF_STAKE_FOR_MAX, Decimal("1"))))
    vol_f = min(1.0, float(volume_usdt / Decimal("10000")))
    score = max(stake_f, vol_f * 0.5 + stake_f * 0.5)
    bps = int(REF_BPS_MIN + (REF_BPS_MAX - REF_BPS_MIN) * score)
    bps = max(REF_BPS_MIN, min(REF_BPS_MAX, bps))
    return {
        "referral_bps": bps,
        "referral_pct": bps / 100.0,
        "cap_note": "Referrers do not resell; capped 2.5%–5%",
        "stake_stone": str(stake_stone),
        "volume_usdt": str(volume_usdt),
    }


# ---------------------------------------------------------------------------
# Resource calculator + usage projections
# ---------------------------------------------------------------------------

def calculator(
    *,
    storage_gib: float = 0,
    bandwidth_100mib: float = 0,
    compute_gflop: float = 0,
    upkeep_gib: float = 0,
    months: int = 1,
    discount_pct: float = 0,
    fx_rate: float = 1.0,
    local_currency: str = "USD",
) -> Dict[str, Any]:
    """Sliders/manual inputs → USDT + local currency + optional usage projection."""
    from chain_mesh import usdt_monetization as mon

    months = max(1, int(months))
    lines = []
    total = Decimal("0")

    def add(product: str, units: float, unit_price: Decimal, label: str):
        nonlocal total
        if units <= 0:
            return
        sub = _q(_d(units) * unit_price * months)
        total += sub
        lines.append(
            {
                "product": product,
                "units": units,
                "unit_price_usdt": str(unit_price),
                "months": months,
                "subtotal_usdt": str(sub),
                "label": label,
            }
        )

    add("storage", storage_gib, mon.USDT_PER_GIB_STORAGE, "Storage GiB")
    add("bandwidth", bandwidth_100mib, mon.USDT_PER_100MIB_BANDWIDTH, "Bandwidth ×100 MiB")
    add("compute", compute_gflop, mon.USDT_PER_GFLOP_COMPUTE, "Compute GFLOP")
    add("upkeep", upkeep_gib, mon.USDT_UPKEEP_PER_GIB_MONTH, "Upkeep GiB·month")

    disc = _q(total * _d(discount_pct) / Decimal("100"))
    net = _q(total - disc)
    local = _q(net * _d(fx_rate))

    return {
        "ok": True,
        "lines": lines,
        "subtotal_usdt": str(total),
        "discount_pct": discount_pct,
        "discount_usdt": str(disc),
        "total_usdt": str(net),
        "fx_rate": fx_rate,
        "local_currency": local_currency,
        "total_local": str(local),
        "payment_config": f"{PUBLIC_ROOT}/api/network/payment-config",
        "note": "End-user calculator for forward-planning purchases",
    }


def project_usage(
    *,
    current_storage_gib: float,
    current_bandwidth_100mib_month: float,
    current_compute_gflop_month: float,
    growth_pct_month: float = 10,
    months_ahead: int = 3,
) -> Dict[str, Any]:
    """Simple projection for users and bulk providers."""
    g = 1.0 + max(0.0, growth_pct_month) / 100.0
    series = []
    s, b, c = current_storage_gib, current_bandwidth_100mib_month, current_compute_gflop_month
    for m in range(1, max(1, months_ahead) + 1):
        s *= g
        b *= g
        c *= g
        calc = calculator(
            storage_gib=0,  # storage often prepaid capacity
            bandwidth_100mib=b,
            compute_gflop=c,
            upkeep_gib=s,
            months=1,
        )
        series.append(
            {
                "month_offset": m,
                "storage_gib": round(s, 3),
                "bandwidth_100mib": round(b, 3),
                "compute_gflop": round(c, 3),
                "est_monthly_usdt": calc["total_usdt"],
            }
        )
    return {
        "ok": True,
        "growth_pct_month": growth_pct_month,
        "projection": series,
        "note": "Indicative only — for purchase planning",
    }


# ---------------------------------------------------------------------------
# Org CRUD (bulk / referrer)
# ---------------------------------------------------------------------------

def register_org(
    *,
    slug: str,
    display_name: str,
    kind: str = "bulk",
    stone_address: str = "",
    owner_email: str = "",
) -> Dict[str, Any]:
    init_reseller_db()
    slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in slug.lower())[:48]
    kind = "referrer" if kind in ("referrer", "ref") else "bulk"
    now = _now()
    disc = BULK_DISCOUNT_START_PCT if kind == "bulk" else 0
    with _conn() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO reseller_orgs (
                    slug, display_name, kind, owner_email, stone_address,
                    discount_pct, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (slug, display_name[:120], kind, owner_email[:120], stone_address[:128], disc, now),
            )
            org_id = int(cur.lastrowid)
        except Exception as exc:
            raise ValueError(f"could not register org: {exc}") from exc

        code = secrets.token_urlsafe(6).replace("-", "")[:10].upper()
        conn.execute(
            """
            INSERT INTO reseller_referrals (org_id, code, created_at)
            VALUES (?, ?, ?)
            """,
            (org_id, code, now),
        )
    return {
        "ok": True,
        "org_id": org_id,
        "slug": slug,
        "kind": kind,
        "referral_code": code,
        "storefront": f"{PUBLIC_ROOT}/reseller/s/{slug}/",
        "dashboard": f"{PUBLIC_ROOT}/reseller/dash/{slug}/",
        "referral_link": f"{PUBLIC_ROOT}/reseller/s/bloodstone/?ref={code}",
    }


def get_org(slug: str) -> Optional[Dict[str, Any]]:
    init_reseller_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM reseller_orgs WHERE slug = ? AND active = 1",
            (slug,),
        ).fetchone()
    if not row:
        return None
    org = dict(row)
    org["brand"] = json.loads(org.get("brand_json") or "{}")
    org["payment_gateways"] = json.loads(org.get("payment_gateways_json") or "{}")
    with _conn() as conn:
        tenants = conn.execute(
            "SELECT COUNT(*) AS n FROM reseller_tenants WHERE org_id = ?",
            (org["id"],),
        ).fetchone()["n"]
        ref = conn.execute(
            "SELECT * FROM reseller_referrals WHERE org_id = ? LIMIT 1",
            (org["id"],),
        ).fetchone()
    org["unique_tenants"] = int(tenants)
    org["referral"] = dict(ref) if ref else None
    stake = _d(org.get("stake_stone") or 0)
    # revenue placeholder from orders
    with _conn() as conn:
        rev = conn.execute(
            """
            SELECT COALESCE(SUM(CAST(amount AS REAL)),0) AS t FROM reseller_orders
            WHERE org_id = ? AND status = 'paid' AND currency IN ('USDT','USDC','USD')
            """,
            (org["id"],),
        ).fetchone()["t"]
    org["economics"] = bulk_discount_pct(
        unique_tenants=org["unique_tenants"],
        revenue_usdt=_d(rev or 0),
        stake_stone=stake,
    )
    org["referral_bps"] = referral_bps(stake_stone=stake, volume_usdt=_d(rev or 0))
    return org


def list_orgs(kind: str = "") -> List[Dict[str, Any]]:
    init_reseller_db()
    with _conn() as conn:
        if kind:
            rows = conn.execute(
                "SELECT slug, display_name, kind, discount_pct FROM reseller_orgs WHERE active=1 AND kind=?",
                (kind,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT slug, display_name, kind, discount_pct FROM reseller_orgs WHERE active=1"
            ).fetchall()
    return [dict(r) for r in rows]


def update_brand(slug: str, brand: Dict[str, Any]) -> Dict[str, Any]:
    """One brand: logo, colors, about — powered by Bloodstone footer always."""
    org = get_org(slug)
    if not org:
        raise ValueError("org not found")
    allowed = {
        k: brand.get(k)
        for k in ("logo_url", "primary_color", "accent_color", "about_html", "support_email")
        if brand.get(k) is not None
    }
    merged = {**(org.get("brand") or {}), **allowed}
    with _conn() as conn:
        conn.execute(
            "UPDATE reseller_orgs SET brand_json = ? WHERE id = ?",
            (json.dumps(merged), org["id"]),
        )
    return {"ok": True, "brand": merged}


def platform_overview() -> Dict[str, Any]:
    return {
        "ok": True,
        "title": "Bloodstone reseller & referral platform",
        "trust": {
            "evm_router": "BloodstoneRevenueRouter — immediate split, no held balances",
            "no_held_keys": "lockPayees + renounceOwnership after deploy",
            "payment_addresses": "GET /api/network/payment-config (public, auditable)",
        },
        "roles": {
            "end_user": "SSO login, calculator, usage projections, self-provision credits",
            "referrer": "Link + dashboard only; 2.5–5% by stake/volume; no wholesale purchase UI",
            "bulk_provider": (
                "Branded storefront + backend; stake STONE; buy network resources in STONE/USDT/USDC; "
                "5–15% discount; payouts after min tenants/revenue"
            ),
        },
        "sso": ["google", "github", "linkedin", "local flavours later"],
        "payment_config": payment_config_payload(),
        "docs": f"{PUBLIC_ROOT}/downloads/Bloodstone-Reseller-Platform.md",
    }
