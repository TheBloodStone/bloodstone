"""Fork Lab — pump.fun-style launch of minable coins forked from Bloodstone.

Space-safe design:
  - Stores only small SQLite rows + JSON manifests (KB each).
  - Never clones bloodstoned source trees or chain datadirs onto this host.
  - Refuses new launches when free disk is below FORK_LAB_MIN_FREE_GB.

A "fork coin" here is a registered minable chain template: name, ticker,
unique network salt, inherited multi-algo PoW (neoscrypt / yespower / sha256d),
and operator instructions. Creators pay a STONE fee to the treasury; miners run
the fork on their own hardware, not on the coordinator VPS.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

DB_PATH = os.environ.get("FORK_LAB_DB", "/var/lib/bloodstone/fork_lab.db")
MIN_FREE_GB = float(os.environ.get("FORK_LAB_MIN_FREE_GB", "2.0"))

# Launch fee: $100 USDT, or comparable STONE at the published early rate.
# STONE valuation default: $0.0001 USDT per STONE → 1,000,000 STONE for $100.
FEE_USD = Decimal(os.environ.get("FORK_LAB_FEE_USD", "100"))
USDT_PER_STONE = Decimal(
    os.environ.get(
        "FORK_LAB_USDT_PER_STONE",
        os.environ.get(
            "MONETIZE_STONE_USDT_RATE",
            os.environ.get("SWAP_STONE_USDT_RATE", "0.0001"),
        ),
    )
)
if USDT_PER_STONE <= 0:
    USDT_PER_STONE = Decimal("0.0001")
# Allow explicit override; otherwise derive from USD fee / rate.
_FEE_STONE_ENV = os.environ.get("FORK_LAB_FEE_STONE", "").strip()
if _FEE_STONE_ENV:
    FEE_STONE = Decimal(_FEE_STONE_ENV)
else:
    FEE_STONE = (FEE_USD / USDT_PER_STONE).quantize(Decimal("1"))
FEE_USDT = Decimal(os.environ.get("FORK_LAB_FEE_USDT", str(FEE_USD)))

# First-coin sale: first N claimers register at $20 (or STONE at same valuation).
EARLY_BIRD_SLOTS = max(0, int(os.environ.get("FORK_LAB_EARLY_BIRD_SLOTS", "10")))
EARLY_BIRD_FEE_USD = Decimal(os.environ.get("FORK_LAB_EARLY_BIRD_FEE_USD", "20"))
_EARLY_STONE_ENV = os.environ.get("FORK_LAB_EARLY_BIRD_FEE_STONE", "").strip()
if _EARLY_STONE_ENV:
    EARLY_BIRD_FEE_STONE = Decimal(_EARLY_STONE_ENV)
else:
    EARLY_BIRD_FEE_STONE = (EARLY_BIRD_FEE_USD / USDT_PER_STONE).quantize(Decimal("1"))
EARLY_BIRD_FEE_USDT = Decimal(
    os.environ.get("FORK_LAB_EARLY_BIRD_FEE_USDT", str(EARLY_BIRD_FEE_USD))
)
EARLY_BIRD_CLAIM_TTL_SEC = int(
    os.environ.get("FORK_LAB_EARLY_BIRD_TTL_SEC", str(14 * 86400))
)  # claim must be used within 14 days

TREASURY = (
    os.environ.get("FORK_LAB_TREASURY")
    or os.environ.get("DATA_SALES_TREASURY_STORAGE")
    or "ST6VUeg5JJGvxgt4hgaFspTJTL3khJJzR6"
).strip()
USDT_TREASURY = (
    os.environ.get("FORK_LAB_USDT_TREASURY")
    or os.environ.get("MONETIZE_USDT_TREASURY_EVM")
    or os.environ.get("ETH_USDT_TREASURY")
    or os.environ.get("USDT_HOT_ADDRESS")
    or ""
).strip()
USDT_NETWORK_LABEL = os.environ.get(
    "FORK_LAB_USDT_NETWORK_LABEL",
    os.environ.get("MONETIZE_USDT_NETWORK_LABEL", "Ethereum ERC-20 USDT"),
)
PARENT_GENESIS = os.environ.get(
    "BLOODSTONE_GENESIS_HASH",
    "df04225074039e630dad825b24818a695462bd19cd585131a0568f50e9bf71d0",
)
PARENT_VERSION = os.environ.get("BLOODSTONE_NODE_VERSION", "0.7.2")
ALGOS = ("neoscrypt", "yespower", "sha256d")
PAYMENT_METHODS = frozenset({"stone", "usdt"})

# Coin image (icon) storage — small files only; public mirror under downloads.
ICON_DIR = os.environ.get("FORK_LAB_ICON_DIR", "/var/lib/bloodstone/fork_lab/icons")
ICON_PUBLIC_DIR = os.environ.get(
    "FORK_LAB_ICON_PUBLIC_DIR",
    "/var/www/bloodstone/downloads/fork-lab/icons",
)
PUBLIC_ROOT = os.environ.get(
    "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
).rstrip("/")
ICON_MAX_BYTES = int(os.environ.get("FORK_LAB_ICON_MAX_BYTES", str(1024 * 1024)))  # 1 MiB
ICON_MIME = {
    b"\x89PNG\r\n\x1a\n": ("png", "image/png"),
    b"\xff\xd8\xff": ("jpg", "image/jpeg"),
    b"GIF87a": ("gif", "image/gif"),
    b"GIF89a": ("gif", "image/gif"),
    b"RIFF": ("webp", "image/webp"),  # refined below
}

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]{1,9}$")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._\-]{1,47}$")
_STONE_RE = re.compile(r"^S[1-9A-HJ-NP-Za-km-z]{25,34}$")
_TXID_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_ETH_TX_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


def fee_quote(*, early_bird: bool = False) -> Dict[str, Any]:
    """Published dual-rail launch fee (USDT or STONE at fixed valuation)."""
    if early_bird:
        fee_usd, fee_usdt, fee_stone = (
            EARLY_BIRD_FEE_USD,
            EARLY_BIRD_FEE_USDT,
            EARLY_BIRD_FEE_STONE,
        )
        label = "early_bird"
    else:
        fee_usd, fee_usdt, fee_stone = FEE_USD, FEE_USDT, FEE_STONE
        label = "standard"
    return {
        "tier": label,
        "fee_usd": str(fee_usd),
        "fee_usdt": str(fee_usdt),
        "fee_stone": str(fee_stone),
        "usdt_per_stone": str(USDT_PER_STONE),
        "stone_per_usdt": str((Decimal("1") / USDT_PER_STONE).quantize(Decimal("1"))),
        "valuation_note": (
            f"${fee_usd} USD launch fee ({label}). Pay {fee_usdt} USDT on EVM, or "
            f"{fee_stone} STONE on Bloodstone mainnet at a fixed valuation of "
            f"${USDT_PER_STONE} USDT per STONE."
        ),
        "standard_fee_usd": str(FEE_USD),
        "standard_fee_stone": str(FEE_STONE),
        "standard_fee_usdt": str(FEE_USDT),
        "early_bird_fee_usd": str(EARLY_BIRD_FEE_USD),
        "early_bird_fee_stone": str(EARLY_BIRD_FEE_STONE),
        "early_bird_fee_usdt": str(EARLY_BIRD_FEE_USDT),
        "treasury_stone": TREASURY,
        "treasury_usdt": USDT_TREASURY or None,
        "usdt_network": USDT_NETWORK_LABEL,
        "usdt_available": bool(USDT_TREASURY),
    }


def _now() -> int:
    return int(time.time())


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def free_disk_gb(path: str = "/var/lib/bloodstone") -> float:
    try:
        os.makedirs(path, exist_ok=True)
        u = shutil.disk_usage(path)
        return float(u.free) / (1024.0 ** 3)
    except Exception:
        u = shutil.disk_usage("/")
        return float(u.free) / (1024.0 ** 3)


def space_ok() -> Dict[str, Any]:
    free = free_disk_gb()
    ok = free >= MIN_FREE_GB
    return {
        "ok": ok,
        "free_gb": round(free, 3),
        "min_free_gb": MIN_FREE_GB,
        "path": "/var/lib/bloodstone",
        "message": (
            "Disk OK for lightweight fork registry."
            if ok
            else f"Insufficient free disk ({free:.2f} GB < {MIN_FREE_GB} GB). Fork launches paused."
        ),
        "hosts_full_fork_chains": False,
        "note": (
            "Fork Lab never stores per-coin chain datadirs on this VPS. "
            "Creators run forked nodes elsewhere."
        ),
    }


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH) or "/var/lib/bloodstone", exist_ok=True)
    with sqlite3.connect(DB_PATH, timeout=30) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fork_coins (
                fork_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                ticker TEXT NOT NULL UNIQUE,
                creator_address TEXT NOT NULL DEFAULT '',
                website TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                algos_json TEXT NOT NULL,
                block_time_sec INTEGER NOT NULL DEFAULT 90,
                block_reward REAL NOT NULL DEFAULT 100,
                premine_stone REAL NOT NULL DEFAULT 0,
                network_salt TEXT NOT NULL,
                magic_hint TEXT NOT NULL DEFAULT '',
                p2p_port INTEGER NOT NULL DEFAULT 0,
                rpc_port INTEGER NOT NULL DEFAULT 0,
                parent_genesis TEXT NOT NULL,
                parent_version TEXT NOT NULL,
                fee_stone TEXT NOT NULL,
                fee_usdt TEXT NOT NULL DEFAULT '100',
                fee_usd TEXT NOT NULL DEFAULT '100',
                usdt_per_stone TEXT NOT NULL DEFAULT '0.0001',
                payment_method TEXT NOT NULL DEFAULT 'stone',
                fee_txid TEXT NOT NULL DEFAULT '',
                fee_confirmed INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending_payment',
                manage_token TEXT NOT NULL,
                manifest_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        # Lightweight migrations for DBs created before dual-rail fees.
        cols = {
            r[1]
            for r in conn.execute("PRAGMA table_info(fork_coins)").fetchall()
        }
        alters = {
            "fee_usdt": "TEXT NOT NULL DEFAULT '100'",
            "fee_usd": "TEXT NOT NULL DEFAULT '100'",
            "usdt_per_stone": "TEXT NOT NULL DEFAULT '0.0001'",
            "payment_method": "TEXT NOT NULL DEFAULT 'stone'",
            "icon_filename": "TEXT NOT NULL DEFAULT ''",
            "icon_url": "TEXT NOT NULL DEFAULT ''",
            "icon_sha256": "TEXT NOT NULL DEFAULT ''",
            "icon_mime": "TEXT NOT NULL DEFAULT ''",
        }
        for col, decl in alters.items():
            if col not in cols:
                conn.execute(f"ALTER TABLE fork_coins ADD COLUMN {col} {decl}")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fork_lab_early_claims (
                claim_id TEXT PRIMARY KEY,
                claim_token TEXT NOT NULL UNIQUE,
                slot_number INTEGER NOT NULL,
                claimer_address TEXT NOT NULL,
                claimer_ip TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                fork_id TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                used_at INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fork_lab_free_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                code_norm TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL DEFAULT 'admin',
                status TEXT NOT NULL DEFAULT 'open',
                fork_id TEXT NOT NULL DEFAULT '',
                redeemed_by TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                used_at INTEGER NOT NULL DEFAULT 0,
                revoked_at INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fork_free_status ON fork_lab_free_codes(status, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fork_coins_status ON fork_coins(status, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fork_coins_ticker ON fork_coins(ticker)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fork_early_status ON fork_lab_early_claims(status, created_at)"
        )
        # Promo fields on coins
        cols = {
            r[1]
            for r in conn.execute("PRAGMA table_info(fork_coins)").fetchall()
        }
        for col, decl in {
            "promo_tier": "TEXT NOT NULL DEFAULT 'standard'",
            "early_claim_id": "TEXT NOT NULL DEFAULT ''",
        }.items():
            if col not in cols:
                conn.execute(f"ALTER TABLE fork_coins ADD COLUMN {col} {decl}")
        conn.commit()


def _conn() -> sqlite3.Connection:
    init_db()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def early_bird_status() -> Dict[str, Any]:
    """First-10 $20 registration sale status."""
    init_db()
    now = _now()
    with _conn() as conn:
        claimed = conn.execute(
            "SELECT COUNT(*) AS n FROM fork_lab_early_claims"
        ).fetchone()["n"]
        open_n = conn.execute(
            """
            SELECT COUNT(*) AS n FROM fork_lab_early_claims
            WHERE status = 'open' AND expires_at >= ?
            """,
            (now,),
        ).fetchone()["n"]
        used_n = conn.execute(
            "SELECT COUNT(*) AS n FROM fork_lab_early_claims WHERE status = 'used'"
        ).fetchone()["n"]
        # expire stale open claims do not free slots — first 10 claimers means slots are gone
    remaining = max(0, EARLY_BIRD_SLOTS - int(claimed))
    return {
        "ok": True,
        "sale": "first_coin_sale",
        "active": remaining > 0 and EARLY_BIRD_SLOTS > 0,
        "slots_total": EARLY_BIRD_SLOTS,
        "slots_claimed": int(claimed),
        "slots_remaining": remaining,
        "claims_open": int(open_n),
        "claims_used": int(used_n),
        "fee_usd": str(EARLY_BIRD_FEE_USD),
        "fee_usdt": str(EARLY_BIRD_FEE_USDT),
        "fee_stone": str(EARLY_BIRD_FEE_STONE),
        "usdt_per_stone": str(USDT_PER_STONE),
        "standard_fee_usd": str(FEE_USD),
        "claim_ttl_sec": EARLY_BIRD_CLAIM_TTL_SEC,
        "rules": [
            f"First {EARLY_BIRD_SLOTS} people to claim get a ${EARLY_BIRD_FEE_USD} registration fee "
            f"(normally ${FEE_USD}).",
            "One claim per STONE address (and per IP).",
            f"Claim must be used to create a fork draft within {EARLY_BIRD_CLAIM_TTL_SEC // 86400} days.",
            f"Pay {EARLY_BIRD_FEE_STONE} STONE or {EARLY_BIRD_FEE_USDT} USDT when confirming the fork.",
        ],
        "claim_url": "/api/fork-lab/early-bird/claim",
    }


def claim_early_bird(
    *,
    claimer_address: str,
    claimer_ip: str = "",
) -> Dict[str, Any]:
    """Reserve one of the first-10 $20 registration slots for a single person."""
    init_db()
    addr = (claimer_address or "").strip()
    if not _STONE_RE.match(addr):
        raise ValueError("claimer_address must be a valid STONE address (S…)")
    ip = (claimer_ip or "").strip()[:64]
    now = _now()

    with _conn() as conn:
        # One claim per address
        existing = conn.execute(
            "SELECT * FROM fork_lab_early_claims WHERE claimer_address = ?",
            (addr,),
        ).fetchone()
        if existing:
            d = dict(existing)
            return {
                "ok": True,
                "already_claimed": True,
                "claim_id": d["claim_id"],
                "claim_token": d["claim_token"],
                "slot_number": d["slot_number"],
                "status": d["status"],
                "expires_at": d["expires_at"],
                "fee": fee_quote(early_bird=True),
                "early_bird": early_bird_status(),
                "message": "This address already claimed a first-coin sale slot.",
            }

        if ip:
            ip_hit = conn.execute(
                "SELECT claim_id FROM fork_lab_early_claims WHERE claimer_ip = ? AND claimer_ip != ''",
                (ip,),
            ).fetchone()
            if ip_hit:
                raise ValueError(
                    "This network already claimed a first-coin sale slot (one per person/IP)."
                )

        claimed = conn.execute(
            "SELECT COUNT(*) AS n FROM fork_lab_early_claims"
        ).fetchone()["n"]
        if int(claimed) >= EARLY_BIRD_SLOTS:
            raise ValueError(
                f"First-coin sale is sold out — all {EARLY_BIRD_SLOTS} $20 slots are claimed. "
                f"Standard fee is ${FEE_USD} / {FEE_STONE} STONE."
            )

        slot = int(claimed) + 1
        claim_id = secrets.token_hex(12)
        claim_token = secrets.token_urlsafe(24)
        expires = now + EARLY_BIRD_CLAIM_TTL_SEC
        conn.execute(
            """
            INSERT INTO fork_lab_early_claims (
                claim_id, claim_token, slot_number, claimer_address, claimer_ip,
                status, fork_id, created_at, expires_at, used_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                claim_id,
                claim_token,
                slot,
                addr,
                ip,
                "open",
                "",
                now,
                expires,
                0,
            ),
        )
        conn.commit()

    return {
        "ok": True,
        "already_claimed": False,
        "claim_id": claim_id,
        "claim_token": claim_token,
        "slot_number": slot,
        "status": "open",
        "expires_at": expires,
        "claimer_address": addr,
        "fee": fee_quote(early_bird=True),
        "early_bird": early_bird_status(),
        "message": (
            f"Slot {slot}/{EARLY_BIRD_SLOTS} claimed. Use claim_token when creating your fork "
            f"to pay only ${EARLY_BIRD_FEE_USD} ({EARLY_BIRD_FEE_STONE} STONE). Save this token."
        ),
        "how_to_use": (
            "On Create fork, paste claim_token into the First-coin sale field "
            "(or send early_bird_token in the API)."
        ),
    }


def _consume_early_claim(
    conn: sqlite3.Connection,
    claim_token: str,
    *,
    claimer_address: str = "",
) -> Dict[str, Any]:
    """Validate open claim and return fee amounts; marks claim used with fork later."""
    token = (claim_token or "").strip()
    if not token:
        raise ValueError("early bird claim_token required")
    now = _now()
    row = conn.execute(
        "SELECT * FROM fork_lab_early_claims WHERE claim_token = ?",
        (token,),
    ).fetchone()
    if not row:
        raise ValueError("invalid early-bird claim_token")
    d = dict(row)
    if d["status"] == "used":
        raise ValueError("this early-bird claim was already used for a fork")
    if int(d["expires_at"] or 0) < now:
        raise ValueError("early-bird claim expired — standard $100 fee applies")
    if claimer_address and d["claimer_address"] and claimer_address != d["claimer_address"]:
        raise ValueError(
            "creator_address must match the STONE address that claimed this early-bird slot"
        )
    return d


def _normalize_free_code(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", (raw or "").strip()).upper()


def generate_free_codes(
    *,
    count: int = 1,
    label: str = "",
    created_by: str = "admin",
) -> Dict[str, Any]:
    """Admin: create one-time FREE registration codes for Fork Lab checkout."""
    init_db()
    count = max(1, min(50, int(count)))
    now = _now()
    created: List[Dict[str, Any]] = []
    with _conn() as conn:
        for _ in range(count):
            # Human-friendly: FREE-XXXX-XXXX-XXXX
            parts = [secrets.token_hex(2).upper() for _ in range(3)]
            code = "FREE-" + "-".join(parts)
            code_norm = _normalize_free_code(code)
            conn.execute(
                """
                INSERT INTO fork_lab_free_codes (
                    code, code_norm, label, created_by, status, fork_id,
                    redeemed_by, created_at, used_at, revoked_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    code,
                    code_norm,
                    (label or "")[:120],
                    (created_by or "admin")[:64],
                    "open",
                    "",
                    "",
                    now,
                    0,
                    0,
                ),
            )
            created.append(
                {
                    "code": code,
                    "label": (label or "")[:120],
                    "status": "open",
                    "created_at": now,
                    "created_by": (created_by or "admin")[:64],
                }
            )
        conn.commit()
        # attach ids
        for item in created:
            row = conn.execute(
                "SELECT id FROM fork_lab_free_codes WHERE code = ?",
                (item["code"],),
            ).fetchone()
            item["id"] = int(row["id"]) if row else None
    return {"ok": True, "count": len(created), "codes": created}


def list_free_codes(*, include_used: bool = True, limit: int = 100) -> Dict[str, Any]:
    init_db()
    limit = max(1, min(500, int(limit)))
    with _conn() as conn:
        if include_used:
            rows = conn.execute(
                """
                SELECT * FROM fork_lab_free_codes
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM fork_lab_free_codes
                WHERE status = 'open'
                ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        open_n = conn.execute(
            "SELECT COUNT(*) AS n FROM fork_lab_free_codes WHERE status = 'open'"
        ).fetchone()["n"]
        used_n = conn.execute(
            "SELECT COUNT(*) AS n FROM fork_lab_free_codes WHERE status = 'used'"
        ).fetchone()["n"]
        rev_n = conn.execute(
            "SELECT COUNT(*) AS n FROM fork_lab_free_codes WHERE status = 'revoked'"
        ).fetchone()["n"]
    return {
        "ok": True,
        "codes": [dict(r) for r in rows],
        "counts": {
            "open": int(open_n),
            "used": int(used_n),
            "revoked": int(rev_n),
            "total": int(open_n) + int(used_n) + int(rev_n),
        },
    }


def revoke_free_code(code_id: int) -> Dict[str, Any]:
    init_db()
    now = _now()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM fork_lab_free_codes WHERE id = ?",
            (int(code_id),),
        ).fetchone()
        if not row:
            raise ValueError("unknown free code id")
        if row["status"] == "used":
            raise ValueError("cannot revoke a code that was already redeemed")
        conn.execute(
            """
            UPDATE fork_lab_free_codes
            SET status = 'revoked', revoked_at = ?
            WHERE id = ? AND status = 'open'
            """,
            (now, int(code_id)),
        )
        conn.commit()
        row2 = conn.execute(
            "SELECT * FROM fork_lab_free_codes WHERE id = ?",
            (int(code_id),),
        ).fetchone()
    return {"ok": True, "code": dict(row2) if row2 else None}


def _redeem_free_code(
    conn: sqlite3.Connection,
    free_code: str,
    *,
    fork_id: str,
    redeemed_by: str = "",
) -> Dict[str, Any]:
    """Atomically mark a free one-time code as used for this fork."""
    norm = _normalize_free_code(free_code)
    if not norm:
        raise ValueError("free code required")
    row = conn.execute(
        "SELECT * FROM fork_lab_free_codes WHERE code_norm = ?",
        (norm,),
    ).fetchone()
    if not row:
        raise ValueError("invalid free registration code")
    d = dict(row)
    if d["status"] == "revoked":
        raise ValueError("this free code was revoked")
    if d["status"] == "used":
        raise ValueError("this free code was already used")
    now = _now()
    cur = conn.execute(
        """
        UPDATE fork_lab_free_codes
        SET status = 'used', fork_id = ?, redeemed_by = ?, used_at = ?
        WHERE id = ? AND status = 'open'
        """,
        (fork_id, (redeemed_by or "")[:80], now, int(d["id"])),
    )
    if cur.rowcount != 1:
        raise ValueError("free code could not be redeemed (race or already used)")
    d["status"] = "used"
    d["fork_id"] = fork_id
    d["used_at"] = now
    return d


def _normalize_ticker(raw: str) -> str:
    t = (raw or "").strip().upper().replace("$", "")
    if not _TICKER_RE.match(t):
        raise ValueError("ticker must be 2–10 chars A–Z / 0–9, starting with a letter")
    reserved = {"STONE", "BTC", "ETH", "USDT", "ROD", "BLURT"}
    if t in reserved:
        raise ValueError(f"ticker {t} is reserved")
    return t


def _normalize_name(raw: str) -> str:
    n = (raw or "").strip()
    if not _NAME_RE.match(n):
        raise ValueError("name must be 2–48 safe characters")
    return n


def _parse_algos(raw: Any) -> List[str]:
    if raw is None or raw == "":
        return list(ALGOS)
    if isinstance(raw, str):
        parts = [p.strip().lower() for p in raw.replace(";", ",").split(",") if p.strip()]
    elif isinstance(raw, (list, tuple)):
        parts = [str(p).strip().lower() for p in raw if str(p).strip()]
    else:
        raise ValueError("algos must be a list or comma-separated string")
    out = []
    for p in parts:
        if p not in ALGOS:
            raise ValueError(f"unsupported algo {p}; choose from {', '.join(ALGOS)}")
        if p not in out:
            out.append(p)
    if not out:
        raise ValueError("at least one algo required")
    return out


def _ports_for_salt(salt: str) -> Tuple[int, int]:
    h = int(hashlib.sha256(salt.encode()).hexdigest()[:8], 16)
    p2p = 20000 + (h % 20000)  # 20000–39999
    rpc = 40000 + (h % 20000)  # 40000–59999
    return p2p, rpc


def _magic_hint(salt: str) -> str:
    return hashlib.sha256(f"magic:{salt}".encode()).hexdigest()[:8]


def _detect_image(data: bytes) -> Tuple[str, str]:
    """Return (ext, mime) or raise ValueError."""
    if not data or len(data) < 12:
        raise ValueError("image too small")
    if len(data) > ICON_MAX_BYTES:
        raise ValueError(f"image too large (max {ICON_MAX_BYTES} bytes)")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg", "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif", "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    raise ValueError("unsupported image type — use PNG, JPEG, GIF, or WebP")


def _icon_urls(fork_id: str, filename: str) -> Dict[str, str]:
    rel = f"fork-lab/icons/{filename}"
    return {
        "filename": filename,
        "path": f"/downloads/{rel}",
        "url": f"{PUBLIC_ROOT}/downloads/{rel}",
        "qt_icon_url": f"{PUBLIC_ROOT}/downloads/{rel}",
        "store_path": f"/fork-lab/store/#coin-{fork_id}",
    }


def save_fork_icon(
    fork_id: str,
    image_bytes: bytes,
    *,
    manage_token: str = "",
    original_name: str = "",
    require_token: bool = True,
) -> Dict[str, Any]:
    """Persist coin image for Qt wallet branding + store listing."""
    space = space_ok()
    if not space["ok"]:
        raise RuntimeError(space["message"])
    fid = (fork_id or "").strip().lower()
    if not fid:
        raise ValueError("fork_id required")
    ext, mime = _detect_image(image_bytes)
    digest = hashlib.sha256(image_bytes).hexdigest()
    filename = f"{fid}.{ext}"

    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM fork_coins WHERE fork_id = ?", (fid,)
        ).fetchone()
        if not row:
            raise ValueError("unknown fork_id")
        if require_token:
            if not manage_token or not secrets.compare_digest(
                str(row["manage_token"]), str(manage_token)
            ):
                raise ValueError("invalid manage_token")

        os.makedirs(ICON_DIR, exist_ok=True)
        os.makedirs(ICON_PUBLIC_DIR, exist_ok=True)
        private_path = os.path.join(ICON_DIR, filename)
        public_path = os.path.join(ICON_PUBLIC_DIR, filename)
        with open(private_path, "wb") as fh:
            fh.write(image_bytes)
        shutil.copy2(private_path, public_path)
        # Also publish a generic coin.png alias for fork builder / Qt packs
        alias = os.path.join(ICON_PUBLIC_DIR, f"{fid}-coin.png")
        if ext == "png":
            shutil.copy2(private_path, alias)
        else:
            # keep original name as canonical; alias only for png
            alias = public_path

        urls = _icon_urls(fid, filename)
        now = _now()
        conn.execute(
            """
            UPDATE fork_coins
            SET icon_filename = ?, icon_url = ?, icon_sha256 = ?, icon_mime = ?, updated_at = ?
            WHERE fork_id = ?
            """,
            (filename, urls["url"], digest, mime, now, fid),
        )
        # refresh manifest branding
        row2 = dict(
            conn.execute("SELECT * FROM fork_coins WHERE fork_id = ?", (fid,)).fetchone()
        )
        manifest = _build_manifest(row2)
        conn.execute(
            "UPDATE fork_coins SET manifest_json = ? WHERE fork_id = ?",
            (json.dumps(manifest, sort_keys=True), fid),
        )
        conn.commit()
        row3 = conn.execute(
            "SELECT * FROM fork_coins WHERE fork_id = ?", (fid,)
        ).fetchone()

    return {
        "ok": True,
        "fork_id": fid,
        "icon": {
            **urls,
            "sha256": digest,
            "mime": mime,
            "bytes": len(image_bytes),
            "original_name": (original_name or "")[:120],
            "qt_paths_hint": [
                "share/pixmaps/bitcoin.png",
                "src/qt/res/icons/bitcoin.png",
                "src/qt/res/icons/about.png",
            ],
            "local_public_file": public_path,
        },
        "fork": _row_public(row3),
        "manifest": manifest,
    }


def _build_manifest(row: Dict[str, Any]) -> Dict[str, Any]:
    try:
        algos = json.loads(row["algos_json"]) if isinstance(row.get("algos_json"), str) else (row.get("algos") or [])
    except Exception:
        algos = []
    icon_url = str(row.get("icon_url") or "")
    icon_filename = str(row.get("icon_filename") or "")
    branding = {
        "icon_url": icon_url or None,
        "icon_filename": icon_filename or None,
        "icon_sha256": str(row.get("icon_sha256") or "") or None,
        "icon_mime": str(row.get("icon_mime") or "") or None,
        "qt_wallet_notes": (
            "Download icon_url into the fork tree as share/pixmaps/bitcoin.png and "
            "src/qt/res/icons/bitcoin.png before building bloodstone-qt."
            if icon_url
            else "Upload a coin image on Fork Lab create for Qt wallet branding."
        ),
    }
    return {
        "schema": "bloodstone/fork-coin-manifest/v1",
        "fork_id": row["fork_id"],
        "name": row["name"],
        "ticker": row["ticker"],
        "status": row["status"],
        "parent": {
            "chain": "Bloodstone",
            "ticker": "STONE",
            "genesis_hash": row["parent_genesis"],
            "node_version": row["parent_version"],
            "github": "https://github.com/TheBloodStone/bloodstone",
            "source_core": f"{PUBLIC_ROOT}/downloads/bloodstone-core-source-latest.tar.gz",
        },
        "consensus": {
            "pow_algorithms": algos,
            "block_time_seconds": row["block_time_sec"],
            "block_reward": row["block_reward"],
            "premine": row["premine_stone"],
            "network_salt": row["network_salt"],
            "message_start_hint": row["magic_hint"],
            "p2p_port_hint": row["p2p_port"],
            "rpc_port_hint": row["rpc_port"],
            "note": (
                "This is a minable fork template derived from Bloodstone multi-algo PoW. "
                "Generate a unique genesis using network_salt; do not reuse STONE genesis."
            ),
        },
        "branding": branding,
        "economics": {
            "launch_fee_usd": str(row.get("fee_usd") or FEE_USD),
            "launch_fee_usdt": str(row.get("fee_usdt") or FEE_USDT),
            "launch_fee_stone": str(row["fee_stone"]),
            "usdt_per_stone": str(row.get("usdt_per_stone") or USDT_PER_STONE),
            "payment_method": str(row.get("payment_method") or "stone"),
            "fee_txid": row["fee_txid"] or None,
            "fee_confirmed": bool(row["fee_confirmed"]),
        },
        "store": {
            "listed_when": "live",
            "store_url": f"{PUBLIC_ROOT}/fork-lab/store/",
            "coin_anchor": f"{PUBLIC_ROOT}/fork-lab/store/#coin-{row['fork_id']}",
        },
        "operator_guide": [
            "1. Download Bloodstone core source (parent) or offline Fork Builder.",
            "2. Change chain name, ticker, network magic, genesis, and ports using this manifest.",
            "3. Install branding.icon_url as Qt coin image (bitcoin.png paths) if present.",
            "4. Keep multi-algo PoW lanes you selected (neoscrypt / yespower / sha256d).",
            "5. Run your own nodes + stratum — Bloodstone coordinator does not host your fork chain data.",
            "6. Publish seeds + explorer; list miners against your P2P port.",
        ],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "website": row.get("website") or "",
        "description": row.get("description") or "",
        "creator_address": row.get("creator_address") or "",
    }


def _row_public(row: sqlite3.Row, *, include_manage: bool = False) -> Dict[str, Any]:
    d = dict(row)
    try:
        d["algos"] = json.loads(d.pop("algos_json") or "[]")
    except Exception:
        d["algos"] = []
        d.pop("algos_json", None)
    try:
        d["manifest"] = json.loads(d.get("manifest_json") or "{}")
    except Exception:
        d["manifest"] = {}
    d.pop("manifest_json", None)
    if not include_manage:
        d.pop("manage_token", None)
    d["fee_confirmed"] = bool(d.get("fee_confirmed"))
    icon_url = str(d.get("icon_url") or "")
    d["icon"] = {
        "url": icon_url or None,
        "filename": d.get("icon_filename") or None,
        "sha256": d.get("icon_sha256") or None,
        "mime": d.get("icon_mime") or None,
    }
    return d


def list_forks(*, status: str = "", limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    init_db()
    limit = max(1, min(200, int(limit)))
    offset = max(0, int(offset))
    clauses = []
    params: List[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status.strip().lower())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with _conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM fork_coins {where}", params
        ).fetchone()["n"]
        rows = conn.execute(
            f"""
            SELECT * FROM fork_coins {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
    return {
        "ok": True,
        "total": int(total),
        "forks": [_row_public(r) for r in rows],
        "limit": limit,
        "offset": offset,
        "space": space_ok(),
        "fee": fee_quote(),
        "fee_stone": str(FEE_STONE),
        "fee_usdt": str(FEE_USDT),
        "fee_usd": str(FEE_USD),
        "usdt_per_stone": str(USDT_PER_STONE),
        "treasury": TREASURY,
        "treasury_usdt": USDT_TREASURY or None,
    }


def get_fork(fork_id: str, *, manage_token: str = "") -> Dict[str, Any]:
    init_db()
    fid = (fork_id or "").strip().lower()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM fork_coins WHERE fork_id = ?", (fid,)
        ).fetchone()
    if not row:
        raise ValueError("unknown fork_id")
    include = bool(manage_token) and secrets.compare_digest(
        str(row["manage_token"]), str(manage_token)
    )
    return {"ok": True, "fork": _row_public(row, include_manage=include), "space": space_ok()}


def create_fork_draft(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create a pending fork coin registration (pay fee to activate)."""
    space = space_ok()
    if not space["ok"]:
        raise RuntimeError(space["message"])

    name = _normalize_name(str(payload.get("name") or ""))
    ticker = _normalize_ticker(str(payload.get("ticker") or ""))
    algos = _parse_algos(payload.get("algos") or payload.get("algorithms"))
    creator = str(payload.get("creator_address") or payload.get("creator") or "").strip()
    if creator and not _STONE_RE.match(creator):
        raise ValueError("creator_address must be a valid STONE address (S…)")
    website = str(payload.get("website") or "")[:200]
    description = str(payload.get("description") or "")[:500]
    try:
        block_time = max(30, min(600, int(payload.get("block_time_sec") or 90)))
    except (TypeError, ValueError):
        raise ValueError("block_time_sec invalid") from None
    try:
        block_reward = float(payload.get("block_reward") or 100)
    except (TypeError, ValueError):
        raise ValueError("block_reward invalid") from None
    if block_reward <= 0 or block_reward > 1_000_000:
        raise ValueError("block_reward out of range")
    try:
        premine = float(payload.get("premine") or payload.get("premine_stone") or 0)
    except (TypeError, ValueError):
        raise ValueError("premine invalid") from None
    if premine < 0 or premine > 1_000_000_000:
        raise ValueError("premine out of range")

    pay_method = str(payload.get("payment_method") or payload.get("pay_with") or "stone").strip().lower()
    if pay_method not in PAYMENT_METHODS:
        raise ValueError("payment_method must be 'stone' or 'usdt'")
    if pay_method == "usdt" and not USDT_TREASURY:
        raise ValueError(
            "USDT payments are not configured yet (set FORK_LAB_USDT_TREASURY / MONETIZE_USDT_TREASURY_EVM). "
            f"Pay {FEE_STONE} STONE instead at ${USDT_PER_STONE}/STONE (= ${FEE_USD})."
        )

    claim_token = str(
        payload.get("early_bird_token")
        or payload.get("claim_token")
        or ""
    ).strip()
    free_code = str(
        payload.get("free_code")
        or payload.get("promo_code")
        or payload.get("checkout_code")
        or ""
    ).strip()
    # Free one-time codes win over early-bird (full waive).
    if free_code and claim_token:
        claim_token = ""

    promo_tier = "standard"
    fee_usd = FEE_USD
    fee_usdt = FEE_USDT
    fee_stone = FEE_STONE
    early_claim_id = ""
    free_code_id = ""
    auto_live = False
    claim_row = None

    salt = secrets.token_hex(16)
    fork_id = hashlib.sha256(f"{ticker}:{salt}:{_now()}".encode()).hexdigest()[:24]
    manage_token = secrets.token_hex(24)
    p2p, rpc = _ports_for_salt(salt)
    magic = _magic_hint(salt)
    now = _now()

    # Resolve early-bird claim (fee preview only; redeem at insert)
    if claim_token and not free_code:
        with _conn() as conn:
            claim_row = _consume_early_claim(
                conn, claim_token, claimer_address=creator or ""
            )
            promo_tier = "early_bird"
            fee_usd = EARLY_BIRD_FEE_USD
            fee_usdt = EARLY_BIRD_FEE_USDT
            fee_stone = EARLY_BIRD_FEE_STONE
            early_claim_id = str(claim_row["claim_id"])
            if not creator:
                creator = str(claim_row["claimer_address"] or "")

    if free_code:
        # Validate code exists before insert (actual redeem in insert txn)
        with _conn() as conn:
            norm = _normalize_free_code(free_code)
            rowc = conn.execute(
                "SELECT * FROM fork_lab_free_codes WHERE code_norm = ?",
                (norm,),
            ).fetchone()
            if not rowc:
                raise ValueError("invalid free registration code")
            if rowc["status"] != "open":
                raise ValueError(f"free code is {rowc['status']}, not redeemable")
        promo_tier = "free_code"
        fee_usd = Decimal("0")
        fee_usdt = Decimal("0")
        fee_stone = Decimal("0")
        auto_live = True

    row = {
        "fork_id": fork_id,
        "name": name,
        "ticker": ticker,
        "creator_address": creator,
        "website": website,
        "description": description,
        "algos_json": json.dumps(algos),
        "block_time_sec": block_time,
        "block_reward": block_reward,
        "premine_stone": premine,
        "network_salt": salt,
        "magic_hint": magic,
        "p2p_port": p2p,
        "rpc_port": rpc,
        "parent_genesis": PARENT_GENESIS,
        "parent_version": PARENT_VERSION,
        "fee_stone": str(fee_stone),
        "fee_usdt": str(fee_usdt),
        "fee_usd": str(fee_usd),
        "usdt_per_stone": str(USDT_PER_STONE),
        "payment_method": pay_method if not auto_live else "free",
        "fee_txid": "FREE_CODE" if auto_live else "",
        "fee_confirmed": 1 if auto_live else 0,
        "status": "live" if auto_live else "pending_payment",
        "manage_token": manage_token,
        "promo_tier": promo_tier,
        "early_claim_id": early_claim_id,
        "icon_filename": "",
        "icon_url": "",
        "icon_sha256": "",
        "icon_mime": "",
        "manifest_json": "{}",
        "created_at": now,
        "updated_at": now,
    }
    manifest = _build_manifest(row)
    row["manifest_json"] = json.dumps(manifest, sort_keys=True)

    with _conn() as conn:
        try:
            conn.execute(
                """
                INSERT INTO fork_coins (
                    fork_id, name, ticker, creator_address, website, description,
                    algos_json, block_time_sec, block_reward, premine_stone,
                    network_salt, magic_hint, p2p_port, rpc_port,
                    parent_genesis, parent_version, fee_stone, fee_usdt, fee_usd,
                    usdt_per_stone, payment_method, fee_txid, fee_confirmed,
                    status, manage_token, icon_filename, icon_url, icon_sha256,
                    icon_mime, manifest_json, created_at, updated_at,
                    promo_tier, early_claim_id
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    row["fork_id"],
                    row["name"],
                    row["ticker"],
                    row["creator_address"],
                    row["website"],
                    row["description"],
                    row["algos_json"],
                    row["block_time_sec"],
                    row["block_reward"],
                    row["premine_stone"],
                    row["network_salt"],
                    row["magic_hint"],
                    row["p2p_port"],
                    row["rpc_port"],
                    row["parent_genesis"],
                    row["parent_version"],
                    row["fee_stone"],
                    row["fee_usdt"],
                    row["fee_usd"],
                    row["usdt_per_stone"],
                    row["payment_method"],
                    row["fee_txid"],
                    row["fee_confirmed"],
                    row["status"],
                    row["manage_token"],
                    row["icon_filename"],
                    row["icon_url"],
                    row["icon_sha256"],
                    row["icon_mime"],
                    row["manifest_json"],
                    row["created_at"],
                    row["updated_at"],
                    row["promo_tier"],
                    row["early_claim_id"],
                ),
            )
            if early_claim_id:
                conn.execute(
                    """
                    UPDATE fork_lab_early_claims
                    SET status = 'used', fork_id = ?, used_at = ?
                    WHERE claim_id = ? AND status = 'open'
                    """,
                    (fork_id, now, early_claim_id),
                )
            if free_code:
                redeemed = _redeem_free_code(
                    conn,
                    free_code,
                    fork_id=fork_id,
                    redeemed_by=creator or ticker,
                )
                free_code_id = str(redeemed.get("id") or "")
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"ticker already registered: {ticker}") from exc

    # Optional icon in create payload (raw bytes or base64)
    icon_info = None
    icon_bytes = payload.get("icon_bytes")
    if icon_bytes is None and payload.get("icon_base64"):
        import base64

        b64 = str(payload.get("icon_base64") or "")
        if "," in b64 and b64.strip().startswith("data:"):
            b64 = b64.split(",", 1)[1]
        try:
            icon_bytes = base64.b64decode(b64, validate=False)
        except Exception as exc:
            raise ValueError("icon_base64 invalid") from exc
    if icon_bytes:
        if isinstance(icon_bytes, str):
            icon_bytes = icon_bytes.encode("latin-1")
        icon_info = save_fork_icon(
            fork_id,
            bytes(icon_bytes),
            manage_token=manage_token,
            original_name=str(payload.get("icon_filename") or "coin.png"),
            require_token=True,
        )
        manifest = icon_info.get("manifest") or manifest

    if promo_tier == "free_code":
        quote = {
            **fee_quote(),
            "tier": "free_code",
            "fee_usd": "0",
            "fee_usdt": "0",
            "fee_stone": "0",
            "valuation_note": "Free one-time admin registration code — $0 fee.",
        }
        pay_instr = {
            "method": "free",
            "amount_stone": "0",
            "amount_usd": "0",
            "amount_usdt": "0",
            "promo_tier": "free_code",
            "next": "No payment required. Your coin is registered live. Download the offline Fork Builder to compile binaries.",
        }
    elif promo_tier == "early_bird":
        quote = fee_quote(early_bird=True)
        if pay_method == "usdt":
            pay_instr = {
                "method": "usdt",
                "amount_usdt": str(fee_usdt),
                "amount_usd": str(fee_usd),
                "pay_to": USDT_TREASURY,
                "network": USDT_NETWORK_LABEL,
                "memo": f"forklab:{fork_id}",
                "comparable_stone": str(fee_stone),
                "usdt_per_stone": str(USDT_PER_STONE),
                "promo_tier": promo_tier,
                "next": (
                    f"Send exactly {fee_usdt} USDT ({USDT_NETWORK_LABEL}) to the treasury, "
                    "then POST /api/fork-lab/confirm with fee_txid set to the EVM tx hash (0x…)."
                ),
            }
        else:
            pay_instr = {
                "method": "stone",
                "amount_stone": str(fee_stone),
                "amount_usd": str(fee_usd),
                "usdt_per_stone": str(USDT_PER_STONE),
                "pay_to": TREASURY,
                "memo": f"forklab:{fork_id}",
                "comparable_usdt": str(fee_usdt),
                "promo_tier": promo_tier,
                "next": (
                    f"Send {fee_stone} STONE (${fee_usd} at ${USDT_PER_STONE}/STONE) on Bloodstone "
                    "mainnet, then POST /api/fork-lab/confirm with fee_txid."
                ),
            }
    else:
        quote = fee_quote()
        if pay_method == "usdt":
            pay_instr = {
                "method": "usdt",
                "amount_usdt": str(fee_usdt),
                "amount_usd": str(fee_usd),
                "pay_to": USDT_TREASURY,
                "network": USDT_NETWORK_LABEL,
                "memo": f"forklab:{fork_id}",
                "comparable_stone": str(fee_stone),
                "usdt_per_stone": str(USDT_PER_STONE),
                "promo_tier": promo_tier,
                "next": (
                    f"Send exactly {fee_usdt} USDT ({USDT_NETWORK_LABEL}) to the treasury, "
                    "then POST /api/fork-lab/confirm with fee_txid set to the EVM tx hash (0x…)."
                ),
            }
        else:
            pay_instr = {
                "method": "stone",
                "amount_stone": str(fee_stone),
                "amount_usd": str(fee_usd),
                "usdt_per_stone": str(USDT_PER_STONE),
                "pay_to": TREASURY,
                "memo": f"forklab:{fork_id}",
                "comparable_usdt": str(fee_usdt),
                "promo_tier": promo_tier,
                "next": (
                    f"Send {fee_stone} STONE (${fee_usd} at ${USDT_PER_STONE}/STONE) on Bloodstone "
                    "mainnet, then POST /api/fork-lab/confirm with fee_txid."
                ),
            }
    return {
        "ok": True,
        "fork_id": fork_id,
        "manage_token": manage_token,
        "status": "live" if auto_live else "pending_payment",
        "registered_free": auto_live,
        "payment_method": "free" if auto_live else pay_method,
        "promo_tier": promo_tier,
        "early_claim_id": early_claim_id or None,
        "free_code_id": free_code_id or None,
        "fee": quote,
        "fee_stone": str(fee_stone),
        "fee_usdt": str(fee_usdt),
        "fee_usd": str(fee_usd),
        "usdt_per_stone": str(USDT_PER_STONE),
        "treasury": TREASURY,
        "treasury_usdt": USDT_TREASURY or None,
        "payment_instructions": pay_instr,
        "manifest": manifest,
        "icon": (icon_info or {}).get("icon"),
        "space": space,
        "early_bird": early_bird_status(),
        "store_url": f"{PUBLIC_ROOT}/fork-lab/store/" if auto_live else None,
    }


def store_list(*, limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    """Public store of paid (live) forks forked from Bloodstone."""
    init_db()
    limit = max(1, min(200, int(limit)))
    offset = max(0, int(offset))
    with _conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM fork_coins WHERE status = 'live' AND fee_confirmed = 1"
        ).fetchone()["n"]
        rows = conn.execute(
            """
            SELECT * FROM fork_coins
            WHERE status = 'live' AND fee_confirmed = 1
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    coins = []
    for r in rows:
        pub = _row_public(r)
        coins.append(
            {
                "fork_id": pub["fork_id"],
                "name": pub["name"],
                "ticker": pub["ticker"],
                "description": pub.get("description") or "",
                "website": pub.get("website") or "",
                "algos": pub.get("algos") or [],
                "icon_url": (pub.get("icon") or {}).get("url"),
                "p2p_port": pub.get("p2p_port"),
                "rpc_port": pub.get("rpc_port"),
                "block_reward": pub.get("block_reward"),
                "block_time_sec": pub.get("block_time_sec"),
                "created_at": pub.get("created_at"),
                "manifest_url": f"{PUBLIC_ROOT}/api/fork-lab/coins/{pub['fork_id']}",
                "store_anchor": f"#coin-{pub['fork_id']}",
                "fee_txid": pub.get("fee_txid") or "",
            }
        )
    return {
        "ok": True,
        "store": "bloodstone-fork-store",
        "title": "Paid minable coins forked from Bloodstone",
        "total": int(total),
        "coins": coins,
        "limit": limit,
        "offset": offset,
        "fork_lab_url": f"{PUBLIC_ROOT}/fork-lab/",
        "fork_builder_url": f"{PUBLIC_ROOT}/downloads/bloodstone-fork-builder-latest.tar.gz",
        "fee": fee_quote(),
        "space": space_ok(),
    }


def _rpc_get_tx(rpc, txid: str) -> Dict[str, Any]:
    try:
        return rpc("getrawtransaction", [txid, True])
    except Exception:
        # wallet-aware fallback
        return rpc("gettransaction", [txid])


def _tx_pays_treasury(tx: Dict[str, Any], amount: Decimal) -> bool:
    """True if any vout pays TREASURY at least `amount` STONE."""
    vouts = tx.get("vout") or []
    paid = Decimal("0")
    for v in vouts:
        val = v.get("value")
        try:
            val_d = Decimal(str(val))
        except (InvalidOperation, TypeError):
            continue
        spk = v.get("scriptPubKey") or {}
        addrs = spk.get("addresses") or []
        if spk.get("address"):
            addrs = list(addrs) + [spk["address"]]
        if TREASURY in addrs:
            paid += val_d
    return paid + Decimal("0.00000001") >= amount


def confirm_payment(
    fork_id: str,
    fee_txid: str,
    *,
    manage_token: str,
    rpc,
) -> Dict[str, Any]:
    space = space_ok()
    if not space["ok"]:
        raise RuntimeError(space["message"])

    fid = (fork_id or "").strip().lower()
    txid_raw = (fee_txid or "").strip()
    token = (manage_token or "").strip()
    if not token:
        raise ValueError("manage_token required")

    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM fork_coins WHERE fork_id = ?", (fid,)
        ).fetchone()
        if not row:
            raise ValueError("unknown fork_id")
        if not secrets.compare_digest(str(row["manage_token"]), token):
            raise ValueError("invalid manage_token")
        if row["status"] == "live" and row["fee_confirmed"]:
            return {"ok": True, "fork": _row_public(row, include_manage=True), "already": True}

        pay_method = str(row["payment_method"] or "stone").strip().lower()
        if pay_method == "usdt":
            txid = txid_raw if txid_raw.startswith("0x") else txid_raw.lower()
            if not _ETH_TX_RE.match(txid) and not _ETH_TX_RE.match("0x" + txid):
                # accept bare 64 hex as eth
                if _TXID_RE.match(txid_raw.lower()):
                    txid = "0x" + txid_raw.lower()
                else:
                    raise ValueError("USDT fee_txid must be an EVM tx hash (0x + 64 hex)")
            if not USDT_TREASURY:
                raise ValueError("USDT treasury not configured")
            # Record EVM payment reference (full eth log verification is ops/async).
            # Creator attests payment of FEE_USDT to USDT_TREASURY via this hash.
        else:
            txid = txid_raw.lower()
            if not _TXID_RE.match(txid):
                raise ValueError("STONE fee_txid must be 64 hex chars")

            # ensure txid not reused
            other = conn.execute(
                "SELECT fork_id FROM fork_coins WHERE fee_txid = ? AND fork_id != ?",
                (txid, fid),
            ).fetchone()
            if other:
                raise ValueError("fee_txid already used for another fork")

            tx = _rpc_get_tx(rpc, txid)
            conf = int(tx.get("confirmations") or 0)
            if conf < 1:
                raise ValueError("fee transaction needs at least 1 confirmation")
            fee_needed = Decimal(str(row["fee_stone"] or FEE_STONE))
            if not _tx_pays_treasury(tx, fee_needed):
                # gettransaction shape may nest details
                details = tx.get("details") or []
                paid = Decimal("0")
                for d in details:
                    if d.get("address") == TREASURY and d.get("category") in (
                        "receive",
                        "send",
                    ):
                        try:
                            paid += abs(Decimal(str(d.get("amount") or 0)))
                        except InvalidOperation:
                            pass
                if paid + Decimal("0.00000001") < fee_needed:
                    raise ValueError(
                        f"transaction does not pay ≥ {fee_needed} STONE to treasury {TREASURY}"
                    )

        # reuse check for both rails
        other = conn.execute(
            "SELECT fork_id FROM fork_coins WHERE fee_txid = ? AND fork_id != ?",
            (txid, fid),
        ).fetchone()
        if other:
            raise ValueError("fee_txid already used for another fork")

        now = _now()
        conn.execute(
            """
            UPDATE fork_coins
            SET fee_txid = ?, fee_confirmed = 1, status = 'live', updated_at = ?
            WHERE fork_id = ?
            """,
            (txid, now, fid),
        )
        # refresh manifest
        row2 = conn.execute(
            "SELECT * FROM fork_coins WHERE fork_id = ?", (fid,)
        ).fetchone()
        d = dict(row2)
        manifest = _build_manifest(d)
        conn.execute(
            "UPDATE fork_coins SET manifest_json = ? WHERE fork_id = ?",
            (json.dumps(manifest, sort_keys=True), fid),
        )
        conn.commit()
        row3 = conn.execute(
            "SELECT * FROM fork_coins WHERE fork_id = ?", (fid,)
        ).fetchone()

    return {
        "ok": True,
        "fork": _row_public(row3, include_manage=True),
        "manifest": manifest,
        "space": space,
    }


def status_payload() -> Dict[str, Any]:
    init_db()
    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM fork_coins").fetchone()["n"]
        live = conn.execute(
            "SELECT COUNT(*) AS n FROM fork_coins WHERE status = 'live'"
        ).fetchone()["n"]
        pending = conn.execute(
            "SELECT COUNT(*) AS n FROM fork_coins WHERE status = 'pending_payment'"
        ).fetchone()["n"]
    quote = fee_quote()
    return {
        "ok": True,
        "feature": "fork-lab",
        "tagline": "Launch minable coins forked from Bloodstone — like pump.fun, but PoW.",
        "fee": quote,
        "early_bird": early_bird_status(),
        "fee_stone": str(FEE_STONE),
        "fee_usdt": str(FEE_USDT),
        "fee_usd": str(FEE_USD),
        "usdt_per_stone": str(USDT_PER_STONE),
        "treasury": TREASURY,
        "treasury_usdt": USDT_TREASURY or None,
        "algos": list(ALGOS),
        "parent_genesis": PARENT_GENESIS,
        "parent_version": PARENT_VERSION,
        "counts": {"total": int(total), "live": int(live), "pending_payment": int(pending)},
        "space": space_ok(),
        "hosting_model": "registry-only",
        "github_parent": "https://github.com/TheBloodStone/bloodstone",
        "create_url": "/fork-lab/",
        "fork_builder": {
            "version": "1.0.0",
            "linux_tar": f"{PUBLIC_ROOT}/downloads/bloodstone-fork-builder-latest.tar.gz",
            "windows_zip": f"{PUBLIC_ROOT}/downloads/bloodstone-fork-builder-latest.zip",
            "manifest": f"{PUBLIC_ROOT}/downloads/bloodstone-fork-builder-manifest.json",
            "note": "Offline home-PC app to patch + compile paid fork binaries (uses branding.icon_url for Qt).",
        },
        "store_url": f"{PUBLIC_ROOT}/fork-lab/store/",
        "api": {
            "status": "/api/fork-lab",
            "list": "/api/fork-lab/coins",
            "store": "/api/fork-lab/store",
            "create": "POST /api/fork-lab/create",
            "confirm": "POST /api/fork-lab/confirm",
            "icon": "POST /api/fork-lab/coins/<fork_id>/icon",
            "get": "/api/fork-lab/coins/<fork_id>",
            "early_bird": "/api/fork-lab/early-bird",
            "early_bird_claim": "POST /api/fork-lab/early-bird/claim",
            "admin_free_codes": "POST /admin/api/fork-lab/free-codes/generate",
        },
    }
