"""Bloodstone Coordinator Federation — roster, gates, fee schedule, seats.

Implements the design in:
  Bloodstone-Coordinator-Federation-Remediation-And-Membership-Fee.md (v1.2)
  Bloodstone-Decentralized-Coordinator-Federation-Ops-Topology.md (v1.1)

G6 open-join fee gate stays closed until ops closes G0–G4 as required.
Fee amounts are the recommended published schedule; board may reprice later.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from chain_mesh import db as mesh_db

# ---------------------------------------------------------------------------
# Fee schedule (fee_schedule_version 1) — remediation doc §5
# ---------------------------------------------------------------------------

FEE_SCHEDULE_VERSION = 1
CAPSULE_TYPE = "bloodstone/coordinator-roster/v1"
FEE_TYPE = "bloodstone/coordinator-fee-schedule/v1"

SUB_YEARLY_STONE = 400_000
BOND_BASE_STONE = 2_000_000
SUB_MONTHLY_STONE = 50_000  # optional tier; not default

ROLE_TOPUP_STONE = {
    "catalog": 1_000_000,
    "pool": 500_000,
    "electrumx": 500_000,
}

BASE_ROLES = ("witness", "status", "downloads")
ALL_ROLES = BASE_ROLES + tuple(ROLE_TOPUP_STONE.keys())

# Early fixed commercial rate (USDT monetization model) — illustrative only
USDT_PER_STONE = float(os.environ.get("MONETIZE_STONE_USDT_RATE", "0.0001"))
VPS_USD_MONTH = 20.0
GRACE_DAYS = 21
EXIT_COOLOFF_DAYS = 14

# Slash codes → fraction of locked bond
SLASH_FRACTION = {
    "S0": 0.0,
    "S1": 0.0,
    "S2": 0.10,
    "S3": 0.25,
    "S4": 1.0,
    "S5": 1.0,
    "S6": 1.0,
    "S7": 0.0,  # hold / review
}
SLASH_TREASURY_SHARE = 0.50
SLASH_BURN_SHARE = 0.50

# Quorum / failure-domain defaults (ops topology §8.0)
W_REQ = int(os.environ.get("QUASAR_WITNESS_QUORUM", "3"))
W_WIN = int(os.environ.get("QUASAR_WITNESS_WINDOW_SEC", "7200"))
C_MIN = 2
L_MAX = 6
O_MIN_V1 = 2
D_MIN_PHASE1 = 2
S_MAX = 120
E_SILENCE = 1800

WITNESS_RETENTION_DAYS = int(os.environ.get("QUASAR_WITNESS_RETENTION_DAYS", "90"))
OPEN_JOIN_ENABLED = os.environ.get("COORD_FEDERATION_OPEN_JOIN", "0") == "1"

PUBLIC_ROOT = os.environ.get(
    "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
).rstrip("/")
DOWNLOADS_DIR = os.environ.get(
    "BLOODSTONE_DOWNLOADS_DIR", "/var/www/bloodstone/downloads"
)
FEDERATION_DIR = os.environ.get(
    "COORD_FEDERATION_DIR", "/root/.bloodstone/federation"
)
ROSTER_KEY_PATH = os.path.join(FEDERATION_DIR, "roster-root.ed25519")
ROSTER_PUB_PATH = os.path.join(FEDERATION_DIR, "roster-root.ed25519.pub")
ADDRESSES_PATH = os.path.join(FEDERATION_DIR, "payment-addresses.json")
LOCAL_MEMBER_PATH = os.path.join(FEDERATION_DIR, "local-member.json")

THIS_DEVICE_ID = os.environ.get("QUASAR_COORDINATOR_DEVICE_ID", "coord-a-primary")
THIS_OPERATOR_ID = os.environ.get("COORD_FEDERATION_OPERATOR_ID", "bloodstone-ops")
THIS_REGION = os.environ.get("COORD_FEDERATION_REGION", "us-east")
THIS_BASE_URL = os.environ.get("COORD_FEDERATION_BASE_URL", PUBLIC_ROOT)
THIS_P2P = os.environ.get("COORD_FEDERATION_P2P", "64.188.22.190:17333")

GATES: Tuple[Tuple[str, str, str], ...] = (
    ("G0", "Decisions / inventory", "Phase 0"),
    ("G1", "Multi-witness unique IDs", "Phase 1"),
    ("G2", "Multi-homed status", "Phase 2"),
    ("G3", "Catalog / registry-first", "Phase 3"),
    ("G4", "Signed roster + client pin → Federation v1", "Phase 4"),
    ("G5", "Pool messaging / LAN clarity", "Phase 5"),
    ("G6", "Open join, drills, rotation, O_min policy", "Phase 6"),
)


def _now() -> int:
    return int(time.time())


def _utc_iso(ts: Optional[int] = None) -> str:
    t = ts if ts is not None else _now()
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stone_to_usd(stone: float) -> float:
    return round(float(stone) * USDT_PER_STONE, 4)


def _ensure_dirs() -> None:
    os.makedirs(FEDERATION_DIR, exist_ok=True)
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def init_federation_db() -> None:
    mesh_db.init_db()
    with mesh_db._conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS federation_gates (
                gate_id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                phase TEXT NOT NULL DEFAULT '',
                closed INTEGER NOT NULL DEFAULT 0,
                closed_at INTEGER,
                note TEXT NOT NULL DEFAULT '',
                closed_by TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS federation_operators (
                operator_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL DEFAULT '',
                entity_note TEXT NOT NULL DEFAULT '',
                contact TEXT NOT NULL DEFAULT '',
                is_founding INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS federation_seats (
                seat_id TEXT PRIMARY KEY,
                operator_id TEXT NOT NULL,
                device_id TEXT NOT NULL UNIQUE,
                mesh_key TEXT NOT NULL DEFAULT '',
                base_url TEXT NOT NULL DEFAULT '',
                p2p TEXT NOT NULL DEFAULT '',
                region TEXT NOT NULL DEFAULT '',
                asn_hint TEXT NOT NULL DEFAULT '',
                roles_json TEXT NOT NULL DEFAULT '[]',
                bond_locked_stone REAL NOT NULL DEFAULT 0,
                bond_required_stone REAL NOT NULL DEFAULT 0,
                paid_through INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                grace_until INTEGER NOT NULL DEFAULT 0,
                fee_schedule_version INTEGER NOT NULL DEFAULT 1,
                sub_txid TEXT NOT NULL DEFAULT '',
                bond_txid TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_fed_seats_status
                ON federation_seats(status, paid_through);
            CREATE TABLE IF NOT EXISTS federation_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seat_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                amount_stone REAL NOT NULL,
                txid TEXT NOT NULL DEFAULT '',
                address TEXT NOT NULL DEFAULT '',
                memo TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS federation_slash_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                seat_id TEXT NOT NULL,
                code TEXT NOT NULL,
                fraction REAL NOT NULL,
                amount_stone REAL NOT NULL,
                treasury_stone REAL NOT NULL DEFAULT 0,
                burn_stone REAL NOT NULL DEFAULT 0,
                reason TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS federation_roster_log (
                roster_version INTEGER PRIMARY KEY,
                payload_json TEXT NOT NULL,
                signature_b64 TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            );
            """
        )
        for gid, title, phase in GATES:
            conn.execute(
                """
                INSERT OR IGNORE INTO federation_gates
                    (gate_id, title, phase, closed, closed_at, note, closed_by)
                VALUES (?, ?, ?, 0, NULL, '', '')
                """,
                (gid, title, phase),
            )


# ---------------------------------------------------------------------------
# Fee schedule & claims
# ---------------------------------------------------------------------------

def fee_schedule_payload() -> Dict[str, Any]:
    topups = {
        role: {
            "additional_bond_stone": amt,
            "approx_usd": _stone_to_usd(amt),
        }
        for role, amt in ROLE_TOPUP_STONE.items()
    }
    return {
        "ok": True,
        "type": FEE_TYPE,
        "fee_schedule_version": FEE_SCHEDULE_VERSION,
        "issued_at": _utc_iso(),
        "g_start": "G6",
        "open_join_enabled": OPEN_JOIN_ENABLED and is_gate_closed("G6"),
        "phases_0_4": "known-operator invite-only",
        "usdt_per_stone_illustrative": USDT_PER_STONE,
        "pricing_method": {
            "lean_vps_usd_month": VPS_USD_MONTH,
            "sub_months_equivalent": 2,
            "bond_months_equivalent": 10,
            "formula": "round_up(months * vps_usd_month / usdt_per_stone)",
        },
        "base_seat": {
            "yearly_subscription_stone": SUB_YEARLY_STONE,
            "yearly_subscription_approx_usd": _stone_to_usd(SUB_YEARLY_STONE),
            "standing_bond_stone": BOND_BASE_STONE,
            "standing_bond_approx_usd": _stone_to_usd(BOND_BASE_STONE),
            "first_year_total_stone": SUB_YEARLY_STONE + BOND_BASE_STONE,
            "first_year_total_approx_usd": _stone_to_usd(
                SUB_YEARLY_STONE + BOND_BASE_STONE
            ),
            "base_roles": list(BASE_ROLES),
            "subscription_refundable": False,
            "bond_refundable_on_clean_exit": True,
            "burn_on_join_or_renewal": False,
        },
        "optional_monthly_subscription_stone": SUB_MONTHLY_STONE,
        "role_topups_stone": topups,
        "stacking_note": (
            "Top-ups additive to base bond; pool and electrumx are +500k each."
        ),
        "grace_days": GRACE_DAYS,
        "exit_cooloff_days": EXIT_COOLOFF_DAYS,
        "slash": {
            "codes": SLASH_FRACTION,
            "proceeds": {
                "ops_treasury_share": SLASH_TREASURY_SHARE,
                "burn_share": SLASH_BURN_SHARE,
                "note": "Applies only to slashed portion after proven offense; never on join.",
            },
        },
        "identity": {
            "rule": "1 paid package ↔ 1 operator_id ↔ 1 primary device_id",
            "extra_vps_same_operator_increases_o_min": False,
        },
        "payment_addresses": load_payment_addresses(),
        "payment_memo_format": "BSCF1|<operator_id>|<device_id>|<fee_schedule_version>",
        "docs": {
            "fee_plan_md": f"{PUBLIC_ROOT}/downloads/Bloodstone-Coordinator-Federation-Remediation-And-Membership-Fee.md",
            "ops_topology_md": f"{PUBLIC_ROOT}/downloads/Bloodstone-Decentralized-Coordinator-Federation-Ops-Topology.md",
        },
        "claim_language": claim_language_payload(),
    }


def claim_language_payload() -> Dict[str, Any]:
    return {
        "allowed": [
            "Operators may apply to join the coordinator roster by locking a STONE bond and paying a yearly STONE subscription.",
            "The fee is Sybil resistance and roster membership, not a mining reward and not consensus power.",
            "Paid seats still require unique device identity and do not by themselves prove multi-operator decentralization.",
            "The bond is refundable collateral; it is not burned on join. Only proven policy offenses can slash a portion of the bond.",
            "Optional roles (catalog / pool directory / ElectrumX listing) may require additional locked bond.",
        ],
        "forbidden_unless_o_min_d_min": [
            "Decentralized because anyone can pay STONE.",
            "N paid coordinators = N independent operators (false if one entity).",
            "Fee replaces witness quorum / braid / LAN pool.",
        ],
        "forbidden_always": [
            "Burn STONE to become a coordinator.",
            "Admission fee is destroyed.",
            "Implying slash burn is automatic on join or renewal.",
        ],
        "fee_not_multi_op": True,
        "o_min_for_multi_operator_marketing": O_MIN_V1,
        "federation_v1_gates": ["G1", "G2", "G4"],
        "storage_claim_requires": "G3",
        "open_join_marketing_requires": "G6 fee gate checklist",
    }


def bond_required_for_roles(roles: Sequence[str]) -> float:
    total = float(BOND_BASE_STONE)
    seen = set()
    for r in roles:
        key = str(r).strip().lower()
        if key in ROLE_TOPUP_STONE and key not in seen:
            total += ROLE_TOPUP_STONE[key]
            seen.add(key)
    return total


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------

def list_gates() -> List[Dict[str, Any]]:
    init_federation_db()
    with mesh_db._conn() as conn:
        rows = conn.execute(
            "SELECT * FROM federation_gates ORDER BY gate_id"
        ).fetchall()
    return [dict(r) for r in rows]


def is_gate_closed(gate_id: str) -> bool:
    init_federation_db()
    with mesh_db._conn() as conn:
        row = conn.execute(
            "SELECT closed FROM federation_gates WHERE gate_id = ?",
            (gate_id.upper(),),
        ).fetchone()
    return bool(row and int(row["closed"] or 0) == 1)


def close_gate(
    gate_id: str,
    *,
    note: str = "",
    closed_by: str = "ops",
    force: bool = False,
) -> Dict[str, Any]:
    """Close a gate. Requires previous gate closed unless force or G0."""
    init_federation_db()
    gid = gate_id.upper().strip()
    ids = [g[0] for g in GATES]
    if gid not in ids:
        return {"ok": False, "error": f"unknown gate {gid}"}
    idx = ids.index(gid)
    if idx > 0 and not force and not is_gate_closed(ids[idx - 1]):
        return {
            "ok": False,
            "error": f"close {ids[idx - 1]} before {gid}",
            "implementation_start_rule": "Phase N requires G(N-1) closed",
        }
    now = _now()
    with mesh_db._conn() as conn:
        conn.execute(
            """
            UPDATE federation_gates
            SET closed = 1, closed_at = ?, note = ?, closed_by = ?
            WHERE gate_id = ?
            """,
            (now, note[:500], closed_by[:64], gid),
        )
    return {"ok": True, "gate_id": gid, "closed_at": _utc_iso(now), "note": note}


def open_gate(gate_id: str, *, note: str = "") -> Dict[str, Any]:
    init_federation_db()
    gid = gate_id.upper().strip()
    with mesh_db._conn() as conn:
        conn.execute(
            """
            UPDATE federation_gates
            SET closed = 0, closed_at = NULL, note = ?, closed_by = ''
            WHERE gate_id = ?
            """,
            (note[:500], gid),
        )
    return {"ok": True, "gate_id": gid, "closed": False}


def federation_v1_ready() -> bool:
    return all(is_gate_closed(g) for g in ("G1", "G2", "G4"))


def gates_payload() -> Dict[str, Any]:
    gates = list_gates()
    return {
        "ok": True,
        "gates": gates,
        "federation_v1_ready": federation_v1_ready(),
        "storage_claim_ready": is_gate_closed("G3"),
        "open_join_ready": is_gate_closed("G6") and OPEN_JOIN_ENABLED,
        "implementation_start_rule": (
            "Coding/deploy for Phase N requires gate G(N-1) closed"
        ),
        "federation_v1_rule": "G1 + G2 + G4 closed",
        "claims_track_gates_not_calendar": True,
    }


# ---------------------------------------------------------------------------
# Payment addresses
# ---------------------------------------------------------------------------

def load_payment_addresses() -> Dict[str, Any]:
    if os.path.isfile(ADDRESSES_PATH):
        try:
            with open(ADDRESSES_PATH, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {
        "COORD_FEE_SUB_v1": os.environ.get("COORD_FEE_SUB_ADDRESS", ""),
        "COORD_BOND_ESCROW_v1": os.environ.get("COORD_BOND_ESCROW_ADDRESS", ""),
        "COORD_BOND_BURN_v1": os.environ.get("COORD_BOND_BURN_ADDRESS", ""),
        "status": "placeholders_until_generated",
    }


def save_payment_addresses(addrs: Dict[str, Any]) -> None:
    _ensure_dirs()
    with open(ADDRESSES_PATH, "w", encoding="utf-8") as fh:
        json.dump(addrs, fh, indent=2, sort_keys=True)
        fh.write("\n")


def ensure_payment_addresses(rpc: Callable) -> Dict[str, Any]:
    """Generate labeled receive addresses via wallet RPC if missing."""
    existing = load_payment_addresses()
    if (
        existing.get("COORD_FEE_SUB_v1")
        and existing.get("COORD_BOND_ESCROW_v1")
        and existing.get("status") != "placeholders_until_generated"
    ):
        return existing

    def _new(label: str) -> str:
        # Prefer wallet/mine path used on this VPS
        try:
            return str(rpc("getnewaddress", [label]))
        except Exception:
            return str(rpc("getnewaddress", [label, "legacy"]))

    # Wrap wallet-scoped RPC if needed
    try:
        sub = _new("coord-fee-sub-v1")
        escrow = _new("coord-bond-escrow-v1")
        burn = _new("coord-bond-burn-v1")
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "status": "rpc_failed",
            **{k: existing.get(k, "") for k in (
                "COORD_FEE_SUB_v1",
                "COORD_BOND_ESCROW_v1",
                "COORD_BOND_BURN_v1",
            )},
        }

    data = {
        "ok": True,
        "status": "live",
        "fee_schedule_version": FEE_SCHEDULE_VERSION,
        "generated_at": _utc_iso(),
        "wallet_note": (
            "Addresses live in node wallet; burn key retained until true "
            "OP_RETURN burn pipeline — slash burn is ledger-tracked at G6."
        ),
        "COORD_FEE_SUB_v1": sub,
        "COORD_BOND_ESCROW_v1": escrow,
        "COORD_BOND_BURN_v1": burn,
        "burn_on_join": False,
        "slash_burn_share": SLASH_BURN_SHARE,
    }
    save_payment_addresses(data)
    return data


# ---------------------------------------------------------------------------
# Seats / applications
# ---------------------------------------------------------------------------

def _seat_id(operator_id: str, device_id: str) -> str:
    raw = f"{operator_id}|{device_id}|{FEE_SCHEDULE_VERSION}".encode()
    return hashlib.sha256(raw).hexdigest()[:32]


def apply_for_seat(
    *,
    operator_id: str,
    device_id: str,
    base_url: str = "",
    p2p: str = "",
    region: str = "",
    asn_hint: str = "",
    roles: Optional[Sequence[str]] = None,
    contact: str = "",
    display_name: str = "",
) -> Dict[str, Any]:
    init_federation_db()
    op = str(operator_id or "").strip().lower()
    dev = str(device_id or "").strip().lower()
    if not op or not dev:
        return {"ok": False, "error": "operator_id and device_id required"}
    if len(op) < 3 or len(dev) < 3:
        return {"ok": False, "error": "operator_id/device_id too short"}

    # Open join enforcement
    if OPEN_JOIN_ENABLED:
        if not is_gate_closed("G6"):
            return {
                "ok": False,
                "error": "open join requires G6 closed",
                "g_start": "G6",
            }
    else:
        # Allow founding/local applications always; public open join off
        if op != THIS_OPERATOR_ID and not is_gate_closed("G0"):
            return {
                "ok": False,
                "error": (
                    "public open join disabled (COORD_FEDERATION_OPEN_JOIN=0); "
                    "known-operator invite only until G6"
                ),
                "open_join_enabled": False,
            }

    role_list = [str(r).lower() for r in (roles or list(BASE_ROLES))]
    for r in role_list:
        if r not in ALL_ROLES:
            return {"ok": False, "error": f"unknown role {r}"}
    bond_req = bond_required_for_roles(role_list)
    now = _now()
    sid = _seat_id(op, dev)
    addrs = load_payment_addresses()

    with mesh_db._conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO federation_operators
                (operator_id, display_name, entity_note, contact, is_founding, created_at)
            VALUES (?, ?, '', ?, 0, ?)
            """,
            (op, (display_name or op)[:120], contact[:200], now),
        )
        conn.execute(
            """
            INSERT INTO federation_seats (
                seat_id, operator_id, device_id, mesh_key, base_url, p2p, region,
                asn_hint, roles_json, bond_locked_stone, bond_required_stone,
                paid_through, status, grace_until, fee_schedule_version,
                sub_txid, bond_txid, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, 0, 'pending', 0, ?, '', '', ?, ?)
            ON CONFLICT(seat_id) DO UPDATE SET
                base_url=excluded.base_url,
                p2p=excluded.p2p,
                region=excluded.region,
                asn_hint=excluded.asn_hint,
                roles_json=excluded.roles_json,
                bond_required_stone=excluded.bond_required_stone,
                updated_at=excluded.updated_at
            """,
            (
                sid,
                op,
                dev,
                dev,
                base_url[:200],
                p2p[:120],
                region[:64],
                asn_hint[:32],
                json.dumps(role_list),
                bond_req,
                FEE_SCHEDULE_VERSION,
                now,
                now,
            ),
        )

    memo = f"BSCF1|{op}|{dev}|{FEE_SCHEDULE_VERSION}"
    return {
        "ok": True,
        "seat_id": sid,
        "status": "pending",
        "operator_id": op,
        "device_id": dev,
        "roles": role_list,
        "bond_required_stone": bond_req,
        "subscription_stone": SUB_YEARLY_STONE,
        "payment_instructions": {
            "subscription": {
                "amount_stone": SUB_YEARLY_STONE,
                "address": addrs.get("COORD_FEE_SUB_v1") or "",
            },
            "bond": {
                "amount_stone": bond_req,
                "address": addrs.get("COORD_BOND_ESCROW_v1") or "",
            },
            "memo": memo,
            "confirmations_preferred": 6,
        },
        "note": (
            "Send subscription + bond on-chain, then POST /api/coordinator/payment "
            "with txids. Open join activates only when G6 + COORD_FEDERATION_OPEN_JOIN=1."
        ),
    }


def record_payment(
    *,
    seat_id: str = "",
    operator_id: str = "",
    device_id: str = "",
    sub_txid: str = "",
    bond_txid: str = "",
    amount_sub: float = 0,
    amount_bond: float = 0,
    activate: bool = True,
) -> Dict[str, Any]:
    init_federation_db()
    now = _now()
    with mesh_db._conn() as conn:
        row = None
        if seat_id:
            row = conn.execute(
                "SELECT * FROM federation_seats WHERE seat_id = ?",
                (seat_id,),
            ).fetchone()
        elif operator_id and device_id:
            row = conn.execute(
                """
                SELECT * FROM federation_seats
                WHERE operator_id = ? AND device_id = ?
                ORDER BY updated_at DESC LIMIT 1
                """,
                (operator_id.strip().lower(), device_id.strip().lower()),
            ).fetchone()
        if not row:
            return {"ok": False, "error": "seat not found"}
        seat = dict(row)
        sid = seat["seat_id"]
        if sub_txid:
            conn.execute(
                """
                INSERT INTO federation_payments
                    (seat_id, kind, amount_stone, txid, address, memo, created_at)
                VALUES (?, 'subscription', ?, ?, '', '', ?)
                """,
                (sid, float(amount_sub or SUB_YEARLY_STONE), sub_txid.strip(), now),
            )
            conn.execute(
                "UPDATE federation_seats SET sub_txid = ?, updated_at = ? WHERE seat_id = ?",
                (sub_txid.strip(), now, sid),
            )
        if bond_txid:
            bond_amt = float(amount_bond or seat["bond_required_stone"] or BOND_BASE_STONE)
            conn.execute(
                """
                INSERT INTO federation_payments
                    (seat_id, kind, amount_stone, txid, address, memo, created_at)
                VALUES (?, 'bond', ?, ?, '', '', ?)
                """,
                (sid, bond_amt, bond_txid.strip(), now),
            )
            conn.execute(
                """
                UPDATE federation_seats
                SET bond_txid = ?, bond_locked_stone = ?, updated_at = ?
                WHERE seat_id = ?
                """,
                (bond_txid.strip(), bond_amt, now, sid),
            )

        seat = dict(
            conn.execute(
                "SELECT * FROM federation_seats WHERE seat_id = ?", (sid,)
            ).fetchone()
        )
        can_activate = bool(seat.get("sub_txid") and seat.get("bond_txid"))
        if activate and can_activate:
            # Founding / invite path: activate without open join flag
            paid_through = now + 365 * 86400
            status = "active"
            if not OPEN_JOIN_ENABLED and seat["operator_id"] != THIS_OPERATOR_ID:
                status = "pending_invite_review"
            conn.execute(
                """
                UPDATE federation_seats
                SET status = ?, paid_through = ?, updated_at = ?
                WHERE seat_id = ?
                """,
                (status, paid_through, now, sid),
            )
            seat = dict(
                conn.execute(
                    "SELECT * FROM federation_seats WHERE seat_id = ?", (sid,)
                ).fetchone()
            )

    return {"ok": True, "seat": _public_seat(seat)}


def _public_seat(seat: Dict[str, Any]) -> Dict[str, Any]:
    roles = []
    try:
        roles = json.loads(seat.get("roles_json") or "[]")
    except Exception:
        roles = []
    return {
        "seat_id": seat.get("seat_id"),
        "operator_id": seat.get("operator_id"),
        "device_id": seat.get("device_id"),
        "mesh_key": seat.get("mesh_key") or seat.get("device_id"),
        "base_url": seat.get("base_url"),
        "p2p": seat.get("p2p"),
        "region": seat.get("region"),
        "roles": roles,
        "bond_locked_stone": seat.get("bond_locked_stone"),
        "bond_required_stone": seat.get("bond_required_stone"),
        "paid_through": seat.get("paid_through"),
        "paid_through_iso": _utc_iso(int(seat["paid_through"]))
        if int(seat.get("paid_through") or 0)
        else "",
        "status": seat.get("status"),
        "fee_schedule_version": seat.get("fee_schedule_version"),
    }


def list_seats(*, status: str = "") -> Dict[str, Any]:
    init_federation_db()
    with mesh_db._conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM federation_seats WHERE status = ? ORDER BY updated_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM federation_seats ORDER BY updated_at DESC"
            ).fetchall()
    return {"ok": True, "seats": [_public_seat(dict(r)) for r in rows]}


def ensure_local_founding_seat() -> Dict[str, Any]:
    """Register COORD-A as founding active seat (grandfather — no payment required)."""
    init_federation_db()
    now = _now()
    op = THIS_OPERATOR_ID
    dev = THIS_DEVICE_ID
    sid = _seat_id(op, dev)
    with mesh_db._conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO federation_operators
                (operator_id, display_name, entity_note, contact, is_founding, created_at)
            VALUES (?, 'Bloodstone Ops', 'Founding coordinator A', '', 1, ?)
            """,
            (op, now),
        )
        conn.execute(
            """
            INSERT INTO federation_seats (
                seat_id, operator_id, device_id, mesh_key, base_url, p2p, region,
                asn_hint, roles_json, bond_locked_stone, bond_required_stone,
                paid_through, status, grace_until, fee_schedule_version,
                sub_txid, bond_txid, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, '', ?, 0, ?, ?, 'active', 0, ?,
                      'founding-grandfather', 'founding-grandfather', ?, ?)
            ON CONFLICT(seat_id) DO UPDATE SET
                base_url=excluded.base_url,
                p2p=excluded.p2p,
                device_id=excluded.device_id,
                status='active',
                paid_through=excluded.paid_through,
                updated_at=excluded.updated_at
            """,
            (
                sid,
                op,
                dev,
                dev,
                THIS_BASE_URL,
                THIS_P2P,
                THIS_REGION,
                json.dumps(list(BASE_ROLES) + ["catalog", "pool", "electrumx"]),
                0.0,  # grandfather bond waived
                now + 365 * 86400,
                FEE_SCHEDULE_VERSION,
                now,
                now,
            ),
        )
    _ensure_dirs()
    with open(LOCAL_MEMBER_PATH, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "operator_id": op,
                "device_id": dev,
                "base_url": THIS_BASE_URL,
                "p2p": THIS_P2P,
                "region": THIS_REGION,
                "founding": True,
            },
            fh,
            indent=2,
        )
        fh.write("\n")
    return {"ok": True, "seat_id": sid, "device_id": dev, "operator_id": op}


# ---------------------------------------------------------------------------
# Roster signing
# ---------------------------------------------------------------------------

def ensure_roster_keys() -> Dict[str, str]:
    _ensure_dirs()
    from nacl.signing import SigningKey

    if not os.path.isfile(ROSTER_KEY_PATH):
        sk = SigningKey.generate()
        with open(ROSTER_KEY_PATH, "wb") as fh:
            fh.write(bytes(sk))
        os.chmod(ROSTER_KEY_PATH, 0o600)
        with open(ROSTER_PUB_PATH, "w", encoding="utf-8") as fh:
            fh.write(base64.b64encode(bytes(sk.verify_key)).decode() + "\n")
    with open(ROSTER_KEY_PATH, "rb") as fh:
        sk = SigningKey(fh.read())
    pub_b64 = base64.b64encode(bytes(sk.verify_key)).decode()
    if not os.path.isfile(ROSTER_PUB_PATH):
        with open(ROSTER_PUB_PATH, "w", encoding="utf-8") as fh:
            fh.write(pub_b64 + "\n")
    return {"signing_key_id": "roster-root-2026-07", "public_key_b64": pub_b64}


_ROSTER_SIG_EXCLUDE = frozenset(
    {"signature", "signature_b64", "signing_key_id", "public_key_b64"}
)


def _canonical_roster_body(roster: Dict[str, Any]) -> bytes:
    """Sign/verify over payload only — never include signature or key metadata."""
    body = {k: v for k, v in roster.items() if k not in _ROSTER_SIG_EXCLUDE}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_roster(roster: Dict[str, Any]) -> Dict[str, Any]:
    from nacl.signing import SigningKey

    keys = ensure_roster_keys()
    with open(ROSTER_KEY_PATH, "rb") as fh:
        sk = SigningKey(fh.read())
    out = dict(roster)
    # Strip any prior sig fields so body is clean
    for k in _ROSTER_SIG_EXCLUDE:
        out.pop(k, None)
    sig = sk.sign(_canonical_roster_body(out)).signature
    out["signing_key_id"] = keys["signing_key_id"]
    out["public_key_b64"] = keys["public_key_b64"]
    out["signature_b64"] = base64.b64encode(sig).decode()
    return out


def verify_roster(roster: Dict[str, Any]) -> Dict[str, Any]:
    from nacl.signing import VerifyKey
    from nacl.exceptions import BadSignatureError

    pub_b64 = roster.get("public_key_b64") or ""
    sig_b64 = roster.get("signature_b64") or roster.get("signature") or ""
    if not pub_b64 or not sig_b64:
        return {"ok": False, "error": "missing public key or signature"}
    try:
        vk = VerifyKey(base64.b64decode(pub_b64))
        vk.verify(_canonical_roster_body(roster), base64.b64decode(sig_b64))
        return {"ok": True, "verified": True, "signing_key_id": roster.get("signing_key_id")}
    except (BadSignatureError, Exception) as exc:
        return {"ok": False, "verified": False, "error": str(exc)}


def build_roster(*, sign: bool = True) -> Dict[str, Any]:
    init_federation_db()
    ensure_local_founding_seat()
    now = _now()
    with mesh_db._conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM federation_seats
            WHERE status IN ('active', 'grace')
            ORDER BY operator_id, device_id
            """
        ).fetchall()
        prev = conn.execute(
            "SELECT roster_version FROM federation_roster_log ORDER BY roster_version DESC LIMIT 1"
        ).fetchone()
    version = int(prev["roster_version"] if prev else 0) + 1
    members = []
    operator_ids = set()
    for r in rows:
        seat = _public_seat(dict(r))
        # grace check
        pt = int(r["paid_through"] or 0)
        if pt and pt < now:
            grace_end = pt + GRACE_DAYS * 86400
            if now <= grace_end:
                seat["status"] = "grace"
            else:
                continue
        operator_ids.add(seat["operator_id"])
        members.append(
            {
                "id": seat["device_id"],
                "operator_id": seat["operator_id"],
                "base_url": seat["base_url"] or PUBLIC_ROOT,
                "p2p": seat["p2p"],
                "roles": seat["roles"],
                "region": seat["region"],
                "paid_through": seat["paid_through_iso"],
                "status": seat["status"],
            }
        )
    # Always include local member if empty seats somehow
    if not members:
        members.append(
            {
                "id": THIS_DEVICE_ID,
                "operator_id": THIS_OPERATOR_ID,
                "base_url": THIS_BASE_URL,
                "p2p": THIS_P2P,
                "roles": list(BASE_ROLES),
                "region": THIS_REGION,
                "status": "active",
            }
        )
        operator_ids.add(THIS_OPERATOR_ID)

    roster: Dict[str, Any] = {
        "type": CAPSULE_TYPE,
        "roster_version": version,
        "fee_schedule_version": FEE_SCHEDULE_VERSION,
        "issued_at": _utc_iso(now),
        "not_before": _utc_iso(now),
        "not_after": _utc_iso(now + 90 * 86400),
        "quorum_hint": W_REQ,
        "o_min": O_MIN_V1,
        "operator_count": len(operator_ids),
        "multi_operator_claim_ok": len(operator_ids) >= O_MIN_V1,
        "federation_v1_ready": federation_v1_ready(),
        "members": members,
        "prev_roster_hash": "",
    }
    if prev:
        with mesh_db._conn() as conn:
            prow = conn.execute(
                "SELECT payload_json FROM federation_roster_log WHERE roster_version = ?",
                (int(prev["roster_version"]),),
            ).fetchone()
        if prow:
            roster["prev_roster_hash"] = hashlib.sha256(
                prow["payload_json"].encode()
            ).hexdigest()

    if sign:
        roster = sign_roster(roster)
    return roster


def publish_roster_and_schedule() -> Dict[str, Any]:
    """Write roster + fee schedule to downloads and federation dir."""
    _ensure_dirs()
    roster = build_roster(sign=True)
    schedule = fee_schedule_payload()
    keys = ensure_roster_keys()

    def _write(path: str, obj: Any) -> str:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, sort_keys=True)
            fh.write("\n")
        # sha256 sidecar
        digest = hashlib.sha256(
            open(path, "rb").read()
        ).hexdigest()
        with open(path + ".sha256", "w", encoding="utf-8") as fh:
            fh.write(f"{digest}  {os.path.basename(path)}\n")
        return digest

    paths = {
        "roster_latest": os.path.join(DOWNLOADS_DIR, "coordinator-roster-latest.json"),
        "roster_versioned": os.path.join(
            DOWNLOADS_DIR, f"coordinator-roster-v{roster['roster_version']}.json"
        ),
        "fee_schedule": os.path.join(
            DOWNLOADS_DIR, "coordinator-fee-schedule-latest.json"
        ),
        "roster_pubkey": os.path.join(DOWNLOADS_DIR, "coordinator-roster-root.pub"),
        "local_roster": os.path.join(FEDERATION_DIR, "roster-latest.json"),
        "local_schedule": os.path.join(FEDERATION_DIR, "fee-schedule-latest.json"),
    }
    digests = {}
    digests["roster"] = _write(paths["roster_latest"], roster)
    _write(paths["roster_versioned"], roster)
    digests["fee_schedule"] = _write(paths["fee_schedule"], schedule)
    _write(paths["local_roster"], roster)
    _write(paths["local_schedule"], schedule)
    with open(paths["roster_pubkey"], "w", encoding="utf-8") as fh:
        fh.write(keys["public_key_b64"] + "\n")

    with mesh_db._conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO federation_roster_log
                (roster_version, payload_json, signature_b64, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                int(roster["roster_version"]),
                json.dumps(roster, sort_keys=True),
                roster.get("signature_b64") or "",
                _now(),
            ),
        )

    # Try mesh publish (best-effort)
    mesh_keys = []
    try:
        from chain_mesh import assets as mesh_assets
        import tempfile

        for label, path in (
            ("roster", paths["roster_latest"]),
            ("fee-schedule", paths["fee_schedule"]),
        ):
            asset_key = f"assets/coordinator/{label}/latest.json"
            mesh_assets.publish_asset(
                path,
                asset_key=asset_key,
                display_name=f"coordinator-{label}",
                version=str(roster["roster_version"]),
                mime_type="application/json",
                anchor=False,
            )
            mesh_keys.append(asset_key)
    except Exception:
        pass

    return {
        "ok": True,
        "roster_version": roster["roster_version"],
        "paths": paths,
        "digests": digests,
        "public_urls": {
            "roster": f"{PUBLIC_ROOT}/downloads/coordinator-roster-latest.json",
            "fee_schedule": f"{PUBLIC_ROOT}/downloads/coordinator-fee-schedule-latest.json",
            "pubkey": f"{PUBLIC_ROOT}/downloads/coordinator-roster-root.pub",
        },
        "verify": verify_roster(roster),
        "mesh_keys": mesh_keys,
        "signing_key_id": keys["signing_key_id"],
    }


# ---------------------------------------------------------------------------
# Slash (ledger)
# ---------------------------------------------------------------------------

def apply_slash(
    *,
    seat_id: str,
    code: str,
    reason: str = "",
) -> Dict[str, Any]:
    init_federation_db()
    code = code.upper().strip()
    if code not in SLASH_FRACTION:
        return {"ok": False, "error": f"unknown slash code {code}"}
    frac = float(SLASH_FRACTION[code])
    now = _now()
    with mesh_db._conn() as conn:
        row = conn.execute(
            "SELECT * FROM federation_seats WHERE seat_id = ?", (seat_id,)
        ).fetchone()
        if not row:
            return {"ok": False, "error": "seat not found"}
        locked = float(row["bond_locked_stone"] or 0)
        amount = round(locked * frac, 8)
        treasury = round(amount * SLASH_TREASURY_SHARE, 8)
        burn = round(amount * SLASH_BURN_SHARE, 8)
        new_locked = max(0.0, locked - amount)
        status = row["status"]
        if code in ("S3",):
            status = "suspended_slash"
        if code in ("S4", "S5", "S6"):
            status = "banned"
        if code == "S2":
            status = "suspended_silence"
        if code == "S0":
            status = "suspended_nonpay"
        conn.execute(
            """
            INSERT INTO federation_slash_events
                (seat_id, code, fraction, amount_stone, treasury_stone, burn_stone, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (seat_id, code, frac, amount, treasury, burn, reason[:500], now),
        )
        conn.execute(
            """
            UPDATE federation_seats
            SET bond_locked_stone = ?, status = ?, updated_at = ?
            WHERE seat_id = ?
            """,
            (new_locked, status, now, seat_id),
        )
    return {
        "ok": True,
        "seat_id": seat_id,
        "code": code,
        "fraction": frac,
        "amount_stone": amount,
        "treasury_stone": treasury,
        "burn_stone": burn,
        "burn_on_join": False,
        "note": "Slash is offense-only; admission package is never burned on join.",
    }


# ---------------------------------------------------------------------------
# Witness lifecycle prune (§10B)
# ---------------------------------------------------------------------------

def prune_witness_assets(
    *,
    retention_days: int = WITNESS_RETENTION_DAYS,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Mark old witness mesh assets non-current and prune capsule rows."""
    init_federation_db()
    cutoff = _now() - max(1, retention_days) * 86400
    removed_assets = 0
    removed_capsules = 0
    with mesh_db._conn() as conn:
        rows = conn.execute(
            """
            SELECT asset_id, asset_key, display_name, created_at
            FROM chain_assets
            WHERE (asset_key LIKE 'assets/witness/%' OR display_name LIKE 'witness-%')
              AND created_at < ?
              AND is_current = 1
            """,
            (cutoff,),
        ).fetchall()
        removed_assets = len(rows)
        if not dry_run and rows:
            conn.execute(
                """
                UPDATE chain_assets
                SET is_current = 0
                WHERE (asset_key LIKE 'assets/witness/%' OR display_name LIKE 'witness-%')
                  AND created_at < ?
                  AND is_current = 1
                """,
                (cutoff,),
            )
        # Capsule table
        try:
            cap = conn.execute(
                "SELECT COUNT(*) AS n FROM quasar_witness_capsules WHERE created_at < ?",
                (cutoff,),
            ).fetchone()
            removed_capsules = int(cap["n"] if cap else 0)
            if not dry_run and removed_capsules:
                conn.execute(
                    "DELETE FROM quasar_witness_capsules WHERE created_at < ?",
                    (cutoff,),
                )
        except Exception:
            removed_capsules = 0

    return {
        "ok": True,
        "retention_days": retention_days,
        "cutoff_iso": _utc_iso(cutoff),
        "assets_marked_stale": removed_assets,
        "capsules_deleted": removed_capsules,
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# Status / tick
# ---------------------------------------------------------------------------

def parameters_payload() -> Dict[str, Any]:
    return {
        "ok": True,
        "witness_quorum_w_req": W_REQ,
        "witness_window_sec": W_WIN,
        "status_min_peers_c_min": C_MIN,
        "max_tip_lag_blocks_l_max": L_MAX,
        "o_min_multi_operator_marketing": O_MIN_V1,
        "d_min_phase1": D_MIN_PHASE1,
        "clock_skew_s_max": S_MAX,
        "emit_silence_alert_sec": E_SILENCE,
        "witness_retention_days": WITNESS_RETENTION_DAYS,
        "this_device_id": THIS_DEVICE_ID,
        "this_operator_id": THIS_OPERATOR_ID,
    }


def status_payload(rpc: Optional[Callable] = None) -> Dict[str, Any]:
    init_federation_db()
    tip = {}
    if rpc:
        try:
            info = rpc("getblockchaininfo")
            tip = {
                "height": int(info.get("blocks") or 0),
                "bestblockhash": info.get("bestblockhash"),
                "synced": float(info.get("verificationprogress") or 0) > 0.999,
            }
        except Exception as exc:
            tip = {"error": str(exc)}
    seats = list_seats()
    active = [s for s in seats.get("seats") or [] if s.get("status") in ("active", "grace")]
    ops = {s.get("operator_id") for s in active}
    # Never publish on status (too heavy for HTTP). Upkeep tick publishes.
    roster_meta: Dict[str, Any] = {}
    try:
        if os.path.isfile(os.path.join(DOWNLOADS_DIR, "coordinator-roster-latest.json")):
            with open(
                os.path.join(DOWNLOADS_DIR, "coordinator-roster-latest.json"),
                encoding="utf-8",
            ) as fh:
                r = json.load(fh)
            roster_meta = {
                "roster_version": r.get("roster_version"),
                "verify": verify_roster(r) if r.get("signature_b64") else {},
            }
    except Exception:
        roster_meta = {}
    return {
        "ok": True,
        "phase": "federation",
        "device_id": THIS_DEVICE_ID,
        "operator_id": THIS_OPERATOR_ID,
        "tip": tip,
        "gates": gates_payload(),
        "parameters": parameters_payload(),
        "fee_schedule_version": FEE_SCHEDULE_VERSION,
        "open_join_enabled": OPEN_JOIN_ENABLED,
        "active_seats": len(active),
        "operator_count": len(ops),
        "multi_operator_claim_ok": len(ops) >= O_MIN_V1,
        "claim_guard": "fee ≠ multi-op; O_min counts distinct operator_id",
        "payment_addresses": load_payment_addresses(),
        "roster_urls": {
            "latest": f"{PUBLIC_ROOT}/downloads/coordinator-roster-latest.json",
            "fee_schedule": f"{PUBLIC_ROOT}/downloads/coordinator-fee-schedule-latest.json",
            "docs_fee_plan": f"{PUBLIC_ROOT}/downloads/Bloodstone-Coordinator-Federation-Remediation-And-Membership-Fee.md",
            "docs_ops": f"{PUBLIC_ROOT}/downloads/Bloodstone-Decentralized-Coordinator-Federation-Ops-Topology.md",
        },
        "publish": roster_meta,
        "seats": active,
    }


def federation_tick(rpc: Optional[Callable] = None) -> Dict[str, Any]:
    """Upkeep: founding seat, addresses, prune dry stats, publish roster."""
    out: Dict[str, Any] = {"ok": True, "ts": _utc_iso()}
    try:
        out["founding"] = ensure_local_founding_seat()
    except Exception as exc:
        out["founding"] = {"ok": False, "error": str(exc)}
    if rpc:
        try:
            out["addresses"] = ensure_payment_addresses(rpc)
        except Exception as exc:
            out["addresses"] = {"ok": False, "error": str(exc)}
    try:
        out["prune"] = prune_witness_assets(dry_run=False)
    except Exception as exc:
        out["prune"] = {"ok": False, "error": str(exc)}
    try:
        out["publish"] = publish_roster_and_schedule()
    except Exception as exc:
        out["publish"] = {"ok": False, "error": str(exc)}
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _wallet_rpc():
    import requests

    conf = os.environ.get("BLOODSTONE_CONF", "/root/.bloodstone/bloodstone.conf")
    vals: Dict[str, str] = {}
    if os.path.isfile(conf):
        with open(conf, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip()
    user = vals.get("rpcuser", "bloodstone")
    password = vals.get("rpcpassword", "")
    port = vals.get("rpcport", "18332")
    wallet = os.environ.get("COORD_FEDERATION_WALLET", "mine")
    url = f"http://{user}:{password}@127.0.0.1:{port}/wallet/{wallet}"

    def call(method: str, params=None):
        r = requests.post(
            url,
            json={
                "jsonrpc": "1.0",
                "id": "federation",
                "method": method,
                "params": params or [],
            },
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(data["error"])
        return data["result"]

    return call


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Coordinator federation ops CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Init DB, keys, founding seat, publish")
    sub.add_parser("status", help="Print federation status JSON")
    sub.add_parser("publish", help="Publish roster + fee schedule")
    sub.add_parser("fee-schedule", help="Print fee schedule")
    g = sub.add_parser("close-gate", help="Close a phase gate")
    g.add_argument("gate_id")
    g.add_argument("--note", default="")
    g.add_argument("--force", action="store_true")
    sub.add_parser("gates", help="List gates")
    sub.add_parser("prune-witness", help="Prune old witness assets/capsules")
    sub.add_parser("addresses", help="Ensure payment addresses")
    sub.add_parser("self-test", help="Run internal consistency checks")
    t = sub.add_parser("tick", help="Full upkeep tick")
    args = p.parse_args(argv)

    init_federation_db()
    rpc = None
    try:
        rpc = _wallet_rpc()
    except Exception:
        rpc = None

    if args.cmd == "init":
        ensure_roster_keys()
        ensure_local_founding_seat()
        if rpc:
            ensure_payment_addresses(rpc)
        print(json.dumps(publish_roster_and_schedule(), indent=2))
        return 0
    if args.cmd == "status":
        print(json.dumps(status_payload(rpc), indent=2))
        return 0
    if args.cmd == "publish":
        print(json.dumps(publish_roster_and_schedule(), indent=2))
        return 0
    if args.cmd == "fee-schedule":
        print(json.dumps(fee_schedule_payload(), indent=2))
        return 0
    if args.cmd == "close-gate":
        print(
            json.dumps(
                close_gate(args.gate_id, note=args.note, force=args.force),
                indent=2,
            )
        )
        return 0
    if args.cmd == "gates":
        print(json.dumps(gates_payload(), indent=2))
        return 0
    if args.cmd == "prune-witness":
        print(json.dumps(prune_witness_assets(), indent=2))
        return 0
    if args.cmd == "addresses":
        if not rpc:
            print(json.dumps({"ok": False, "error": "rpc unavailable"}, indent=2))
            return 1
        print(json.dumps(ensure_payment_addresses(rpc), indent=2))
        return 0
    if args.cmd == "tick":
        print(json.dumps(federation_tick(rpc), indent=2))
        return 0
    if args.cmd == "self-test":
        errs = []
        sch = fee_schedule_payload()
        if sch["base_seat"]["yearly_subscription_stone"] != 400_000:
            errs.append("sub amount")
        if sch["base_seat"]["standing_bond_stone"] != 2_000_000:
            errs.append("bond amount")
        if sch["role_topups_stone"]["pool"]["additional_bond_stone"] != 500_000:
            errs.append("pool topup")
        if sch["role_topups_stone"]["electrumx"]["additional_bond_stone"] != 500_000:
            errs.append("electrumx topup")
        if sch["role_topups_stone"]["catalog"]["additional_bond_stone"] != 1_000_000:
            errs.append("catalog topup")
        if sch["base_seat"]["burn_on_join_or_renewal"] is not False:
            errs.append("burn on join")
        br = bond_required_for_roles(["witness", "catalog", "pool", "electrumx"])
        if br != 2_000_000 + 1_000_000 + 500_000 + 500_000:
            errs.append(f"bond stack {br}")
        ensure_local_founding_seat()
        pub = publish_roster_and_schedule()
        if not pub.get("verify", {}).get("ok"):
            errs.append("roster verify failed")
        # tamper test
        roster = build_roster(sign=True)
        bad = dict(roster)
        bad["roster_version"] = 999999
        if verify_roster(bad).get("ok"):
            errs.append("tamper should fail")
        # gate order: reopen G1 then ensure G0 blocks unless closed
        open_gate("G1", note="self-test reset")
        if is_gate_closed("G0"):
            r = close_gate("G1", note="self-test after G0", force=False)
            if not r.get("ok"):
                errs.append("G1 after G0 closed should succeed")
        else:
            r = close_gate("G1", note="self-test", force=False)
            if r.get("ok"):
                errs.append("G1 should require G0")
            close_gate("G0", note="self-test bootstrap", force=True)
            if not close_gate("G1", note="self-test", force=False).get("ok"):
                errs.append("G1 after G0")
        print(
            json.dumps(
                {"ok": not errs, "errors": errs, "publish": pub.get("public_urls")},
                indent=2,
            )
        )
        return 0 if not errs else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
