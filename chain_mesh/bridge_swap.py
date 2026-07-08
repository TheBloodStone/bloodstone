"""Wave L — BLURT ↔ STONE bridge with HTLC-style atomic swap intents."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
import uuid
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Dict, List, Optional, Tuple

import requests

from chain_mesh import db as mesh_db
from chain_mesh import storage_credits as storage

BRIDGE_FORMAT = "bloodstone_bridge_swap/v1"
BRIDGE_ENABLE = os.environ.get("BRIDGE_SWAP_ENABLE", "1").strip() not in (
    "0",
    "false",
    "no",
)
BLURT_RPC_NODES = [
    n.strip()
    for n in os.environ.get(
        "BLURT_REGISTRY_RPC_NODES", "https://rpc.blurt.blog,https://blurt-rpc.saboin.com"
    ).split(",")
    if n.strip()
]
BRIDGE_OUTPOST = os.environ.get(
    "BLURT_BRIDGE_OUTPOST_ACCOUNT", "bloodstone-bridge"
).lstrip("@").lower()
BRIDGE_STONE_ADDRESS = (os.environ.get("BRIDGE_STONE_ADDRESS") or "").strip()
BRIDGE_STONE_PER_BLURT = Decimal(
    os.environ.get("BRIDGE_STONE_PER_BLURT", "100000000")
)
BRIDGE_BLURT_PER_STONE = Decimal(
    os.environ.get("BRIDGE_BLURT_PER_STONE", str(1 / BRIDGE_STONE_PER_BLURT))
)
MIN_BLURT_SWAP = Decimal(os.environ.get("BRIDGE_MIN_BLURT", "1"))
MIN_STONE_SWAP = Decimal(os.environ.get("BRIDGE_MIN_STONE", "10000000"))
BRIDGE_SWAP_TTL_SEC = max(300, int(os.environ.get("BRIDGE_SWAP_TTL_SEC", "3600")))
BRIDGE_BLURT_SCALE = 3
BRIDGE_STONE_SCALE = 8

SWAP_LOCK_MEMO_RE = re.compile(
    r"^swap:lock:([a-zA-Z0-9\-]{8,64})$",
    re.IGNORECASE,
)
STONE_ADDR_RE = re.compile(r"^[A-Za-z0-9]{25,62}$")
BLURT_ACCOUNT_RE = re.compile(r"^[a-z0-9\-\.]{3,16}$", re.IGNORECASE)

_LAST_SYNC: Dict[str, Any] = {}


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def _quantize_blurt(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("invalid BLURT amount")
    if amount <= 0:
        raise ValueError("BLURT amount must be positive")
    return amount.quantize(
        Decimal("0." + "0" * BRIDGE_BLURT_SCALE),
        rounding=ROUND_DOWN,
    )


def _quantize_stone(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("invalid STONE amount")
    if amount <= 0:
        raise ValueError("STONE amount must be positive")
    return amount.quantize(
        Decimal("0." + "0" * BRIDGE_STONE_SCALE),
        rounding=ROUND_DOWN,
    )


def _swap_id() -> str:
    return f"bswap-{uuid.uuid4().hex[:16]}"


def _hash_preimage(preimage: str) -> str:
    return hashlib.sha256((preimage or "").encode()).hexdigest()


def init_bridge_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bridge_swap_intents (
                swap_id TEXT PRIMARY KEY,
                direction TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                stone_address TEXT NOT NULL DEFAULT '',
                blurt_account TEXT NOT NULL DEFAULT '',
                blurt_amount TEXT NOT NULL DEFAULT '',
                stone_amount TEXT NOT NULL DEFAULT '',
                secret_hash TEXT NOT NULL,
                preimage TEXT NOT NULL DEFAULT '',
                lock_memo TEXT NOT NULL DEFAULT '',
                blurt_txid TEXT NOT NULL DEFAULT '',
                stone_txid TEXT NOT NULL DEFAULT '',
                credits_bytes INTEGER NOT NULL DEFAULT 0,
                expires_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_bridge_swap_status
                ON bridge_swap_intents(status, expires_at DESC);
            CREATE INDEX IF NOT EXISTS idx_bridge_swap_blurt_tx
                ON bridge_swap_intents(blurt_txid);

            CREATE TABLE IF NOT EXISTS bridge_swap_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                swap_id TEXT NOT NULL,
                event TEXT NOT NULL,
                detail_json TEXT NOT NULL DEFAULT '{}',
                created_at INTEGER NOT NULL
            );
            """
        )


def _log_event(swap_id: str, event: str, detail: Optional[Dict[str, Any]] = None) -> None:
    init_bridge_db()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO bridge_swap_ledger (swap_id, event, detail_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (swap_id, event[:32], json.dumps(detail or {}), _now()),
        )


def quote_swap(
    *,
    direction: str,
    amount: Any,
    stone_address: str = "",
    blurt_account: str = "",
) -> Dict[str, Any]:
    init_bridge_db()
    dirn = (direction or "").strip().lower()
    if dirn not in ("blurt_to_stone", "stone_to_blurt"):
        raise ValueError("direction must be blurt_to_stone or stone_to_blurt")

    stone = (stone_address or "").strip()
    blurt = (blurt_account or "").lstrip("@").lower()

    if dirn == "blurt_to_stone":
        blurt_amt = _quantize_blurt(amount)
        if blurt_amt < MIN_BLURT_SWAP:
            raise ValueError(f"minimum BLURT swap is {MIN_BLURT_SWAP}")
        if stone and not STONE_ADDR_RE.match(stone):
            raise ValueError("invalid stone_address")
        stone_amt = _quantize_stone(blurt_amt * BRIDGE_STONE_PER_BLURT)
        if stone_amt < MIN_STONE_SWAP:
            raise ValueError(f"swap too small — less than {MIN_STONE_SWAP} STONE")
        credits_bytes = int(blurt_amt * storage.BYTES_PER_BLURT)
        return {
            "ok": True,
            "format": BRIDGE_FORMAT,
            "direction": dirn,
            "blurt_amount": str(blurt_amt),
            "stone_amount": str(stone_amt),
            "stone_address": stone,
            "blurt_account": blurt,
            "rate_stone_per_blurt": str(BRIDGE_STONE_PER_BLURT),
            "credits_bytes": credits_bytes,
            "outpost_account": BRIDGE_OUTPOST,
        }

    stone_amt = _quantize_stone(amount)
    if stone_amt < MIN_STONE_SWAP:
        raise ValueError(f"minimum STONE swap is {MIN_STONE_SWAP}")
    if blurt and not BLURT_ACCOUNT_RE.match(blurt):
        raise ValueError("invalid blurt_account")
    blurt_amt = _quantize_blurt(stone_amt * BRIDGE_BLURT_PER_STONE)
    if blurt_amt < MIN_BLURT_SWAP:
        raise ValueError(f"swap too small — less than {MIN_BLURT_SWAP} BLURT")
    return {
        "ok": True,
        "format": BRIDGE_FORMAT,
        "direction": dirn,
        "blurt_amount": str(blurt_amt),
        "stone_amount": str(stone_amt),
        "stone_address": stone,
        "blurt_account": blurt,
        "rate_blurt_per_stone": str(BRIDGE_BLURT_PER_STONE),
        "bridge_stone_address": BRIDGE_STONE_ADDRESS or None,
        "outpost_account": BRIDGE_OUTPOST,
    }


def initiate_swap(
    *,
    direction: str,
    amount: Any,
    stone_address: str = "",
    blurt_account: str = "",
) -> Dict[str, Any]:
    if not BRIDGE_ENABLE:
        raise RuntimeError("bridge swap disabled (BRIDGE_SWAP_ENABLE off)")

    quote = quote_swap(
        direction=direction,
        amount=amount,
        stone_address=stone_address,
        blurt_account=blurt_account,
    )
    dirn = quote["direction"]
    swap_id = _swap_id()
    preimage = secrets.token_hex(32)
    secret_hash = _hash_preimage(preimage)
    lock_memo = f"swap:lock:{swap_id}"
    now = _now()
    expires = now + BRIDGE_SWAP_TTL_SEC

    init_bridge_db()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO bridge_swap_intents (
                swap_id, direction, status, stone_address, blurt_account,
                blurt_amount, stone_amount, secret_hash, lock_memo,
                credits_bytes, expires_at, created_at, updated_at
            ) VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                swap_id,
                dirn,
                quote.get("stone_address") or "",
                quote.get("blurt_account") or "",
                quote["blurt_amount"],
                quote["stone_amount"],
                secret_hash,
                lock_memo,
                int(quote.get("credits_bytes") or 0),
                expires,
                now,
                now,
            ),
        )
    _log_event(swap_id, "initiated", {"direction": dirn, "quote": quote})

    funding: Dict[str, Any]
    if dirn == "blurt_to_stone":
        funding = {
            "action": "send_blurt",
            "to_account": BRIDGE_OUTPOST,
            "amount": quote["blurt_amount"],
            "memo": lock_memo,
            "memo_format": "swap:lock:<swap_id>",
        }
    else:
        funding = {
            "action": "send_stone",
            "to_address": BRIDGE_STONE_ADDRESS or None,
            "amount": quote["stone_amount"],
            "memo": lock_memo,
            "note": "Include swap_id in STONE payment reference; attest via /bridge/attest",
        }

    return {
        "ok": True,
        "format": BRIDGE_FORMAT,
        "swap_id": swap_id,
        "direction": dirn,
        "status": "pending",
        "secret_hash": secret_hash,
        "preimage": preimage,
        "expires_at": expires,
        "quote": quote,
        "funding": funding,
        "claim_requires": "preimage",
    }


def _get_intent(swap_id: str) -> Optional[Dict[str, Any]]:
    init_bridge_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM bridge_swap_intents WHERE swap_id = ?",
            ((swap_id or "").strip(),),
        ).fetchone()
    return dict(row) if row else None


def attest_stone_funding(*, swap_id: str, stone_txid: str) -> Dict[str, Any]:
    """Beta attestation for STONE→BLURT leg when on-chain indexer is unavailable."""
    if not BRIDGE_ENABLE:
        raise RuntimeError("bridge swap disabled")

    intent = _get_intent(swap_id)
    if not intent:
        raise ValueError("swap not found")
    if intent["direction"] != "stone_to_blurt":
        raise ValueError("attest only applies to stone_to_blurt swaps")
    if intent["status"] not in ("pending", "funded"):
        raise ValueError(f"swap status is {intent['status']}")

    txid = (stone_txid or "").strip()
    if len(txid) < 8:
        raise ValueError("stone_txid required")

    now = _now()
    with _conn() as conn:
        conn.execute(
            """
            UPDATE bridge_swap_intents
            SET status = 'funded', stone_txid = ?, updated_at = ?
            WHERE swap_id = ?
            """,
            (txid, now, swap_id),
        )
    _log_event(swap_id, "stone_attested", {"stone_txid": txid})
    return {"ok": True, "swap_id": swap_id, "status": "funded", "stone_txid": txid}


def claim_swap(*, swap_id: str, preimage: str) -> Dict[str, Any]:
    if not BRIDGE_ENABLE:
        raise RuntimeError("bridge swap disabled")

    intent = _get_intent(swap_id)
    if not intent:
        raise ValueError("swap not found")
    if intent["status"] == "claimed":
        return {"ok": True, "duplicate": True, "swap_id": swap_id, "status": "claimed"}
    if intent["status"] != "funded":
        raise ValueError(f"swap not funded (status={intent['status']})")
    if _now() > int(intent["expires_at"]):
        _expire_swap(swap_id)
        raise ValueError("swap expired")

    pre = (preimage or "").strip()
    if _hash_preimage(pre) != str(intent["secret_hash"]):
        raise ValueError("invalid preimage")

    now = _now()
    result: Dict[str, Any] = {"ok": True, "swap_id": swap_id, "direction": intent["direction"]}

    if intent["direction"] == "blurt_to_stone":
        addr = str(intent["stone_address"] or "").strip()
        if not addr:
            raise ValueError("stone_address missing on intent")
        credits = int(intent["credits_bytes"] or 0)
        credit = storage.credit_from_blurt_transfer(
            stone_address=addr,
            bytes_credited=credits,
            blurt_txid=str(intent["blurt_txid"] or ""),
            blurt_from=str(intent["blurt_account"] or ""),
            blurt_amount=str(intent["blurt_amount"] or ""),
            memo=str(intent["lock_memo"] or ""),
        )
        result["storage_credit"] = credit
        result["stone_amount"] = intent["stone_amount"]
        result["credits_bytes"] = credits
    else:
        result["blurt_payout"] = {
            "account": intent["blurt_account"],
            "amount": intent["blurt_amount"],
            "status": "ledger_recorded",
            "note": "BLURT payout queued — operator sends from bridge pool",
        }

    with _conn() as conn:
        conn.execute(
            """
            UPDATE bridge_swap_intents
            SET status = 'claimed', preimage = ?, updated_at = ?
            WHERE swap_id = ?
            """,
            (pre, now, swap_id),
        )
    _log_event(swap_id, "claimed", result)
    result["status"] = "claimed"
    return result


def _expire_swap(swap_id: str) -> None:
    with _conn() as conn:
        conn.execute(
            """
            UPDATE bridge_swap_intents
            SET status = 'expired', updated_at = ?
            WHERE swap_id = ? AND status IN ('pending', 'funded')
            """,
            (_now(), swap_id),
        )


def expire_stale_swaps() -> Dict[str, Any]:
    init_bridge_db()
    now = _now()
    with _conn() as conn:
        cur = conn.execute(
            """
            UPDATE bridge_swap_intents
            SET status = 'expired', updated_at = ?
            WHERE status IN ('pending', 'funded') AND expires_at < ?
            """,
            (now, now),
        )
    expired = int(cur.rowcount)
    return {"ok": True, "expired": expired}


def _rpc_account_history(account: str, *, limit: int = 50) -> List[Dict[str, Any]]:
    payload = {
        "jsonrpc": "2.0",
        "method": "get_account_history",
        "params": [account, -1, limit, ["transfer"]],
        "id": 1,
    }
    for node in BLURT_RPC_NODES:
        try:
            resp = requests.post(node, json=payload, timeout=20)
            body = resp.json()
            if "result" in body:
                return list(body["result"] or [])
        except Exception:
            continue
    return []


def sync_bridge_transfers(*, limit: int = 40) -> Dict[str, Any]:
    """Index BLURT lock transfers to the bridge outpost."""
    if not BRIDGE_ENABLE:
        return {"ok": True, "skipped": True, "reason": "BRIDGE_SWAP_ENABLE off"}

    init_bridge_db()
    expire_stale_swaps()
    funded = 0
    skipped = 0
    now = _now()

    for entry in _rpc_account_history(BRIDGE_OUTPOST, limit=limit):
        op = entry.get("op") or {}
        if not isinstance(op, dict):
            continue
        if str(op.get("type") or "") != "transfer":
            continue
        trx = op.get("trx") or {}
        memo = str(trx.get("memo") or "").strip()
        match = SWAP_LOCK_MEMO_RE.match(memo)
        if not match:
            skipped += 1
            continue
        swap_id = match.group(1)
        intent = _get_intent(swap_id)
        if not intent:
            skipped += 1
            continue
        if intent["status"] not in ("pending", "funded"):
            skipped += 1
            continue
        txid = str(entry.get("trx_id") or "")
        with _conn() as conn:
            dup = conn.execute(
                "SELECT swap_id FROM bridge_swap_intents WHERE blurt_txid = ? AND swap_id != ?",
                (txid, swap_id),
            ).fetchone()
            if dup:
                skipped += 1
                continue
            conn.execute(
                """
                UPDATE bridge_swap_intents
                SET status = 'funded',
                    blurt_txid = ?,
                    blurt_account = ?,
                    updated_at = ?
                WHERE swap_id = ?
                """,
                (
                    txid,
                    str(trx.get("from") or intent["blurt_account"]),
                    now,
                    swap_id,
                ),
            )
        _log_event(swap_id, "blurt_funded", {"blurt_txid": txid})
        funded += 1

    result = {"ok": True, "funded": funded, "skipped": skipped, "outpost": BRIDGE_OUTPOST}
    _LAST_SYNC.clear()
    _LAST_SYNC.update(result)
    return result


def list_intents(*, status: str = "", limit: int = 50) -> Dict[str, Any]:
    init_bridge_db()
    lim = max(1, min(200, int(limit)))
    st = (status or "").strip().lower()
    with _conn() as conn:
        if st:
            rows = conn.execute(
                """
                SELECT swap_id, direction, status, stone_address, blurt_account,
                       blurt_amount, stone_amount, lock_memo, blurt_txid, stone_txid,
                       credits_bytes, expires_at, created_at, updated_at
                FROM bridge_swap_intents
                WHERE status = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (st, lim),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT swap_id, direction, status, stone_address, blurt_account,
                       blurt_amount, stone_amount, lock_memo, blurt_txid, stone_txid,
                       credits_bytes, expires_at, created_at, updated_at
                FROM bridge_swap_intents
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (lim,),
            ).fetchall()
        pending = conn.execute(
            "SELECT COUNT(*) AS c FROM bridge_swap_intents WHERE status = 'pending'"
        ).fetchone()["c"]
        funded = conn.execute(
            "SELECT COUNT(*) AS c FROM bridge_swap_intents WHERE status = 'funded'"
        ).fetchone()["c"]
        claimed = conn.execute(
            "SELECT COUNT(*) AS c FROM bridge_swap_intents WHERE status = 'claimed'"
        ).fetchone()["c"]
    return {
        "ok": True,
        "format": BRIDGE_FORMAT,
        "intents": [dict(r) for r in rows],
        "counts": {
            "pending": int(pending),
            "funded": int(funded),
            "claimed": int(claimed),
        },
    }


def status_payload() -> Dict[str, Any]:
    init_bridge_db()
    counts = list_intents(limit=1).get("counts") or {}
    public = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    return {
        "ok": True,
        "format": BRIDGE_FORMAT,
        "enabled": BRIDGE_ENABLE,
        "outpost_account": BRIDGE_OUTPOST,
        "bridge_stone_address": BRIDGE_STONE_ADDRESS or None,
        "rates": {
            "stone_per_blurt": str(BRIDGE_STONE_PER_BLURT),
            "blurt_per_stone": str(BRIDGE_BLURT_PER_STONE),
            "bytes_per_blurt": storage.BYTES_PER_BLURT,
        },
        "limits": {
            "min_blurt": str(MIN_BLURT_SWAP),
            "min_stone": str(MIN_STONE_SWAP),
            "ttl_sec": BRIDGE_SWAP_TTL_SEC,
        },
        "memo_formats": {
            "lock": "swap:lock:<swap_id>",
            "storage_rail": storage.STORAGE_MEMO_RE.pattern,
        },
        "counts": counts,
        "last_sync": dict(_LAST_SYNC),
        "apis": {
            "status": f"{public}/api/convergence/bridge/status",
            "quote": f"{public}/api/convergence/bridge/quote",
            "initiate": f"{public}/api/convergence/bridge/initiate",
            "claim": f"{public}/api/convergence/bridge/claim",
            "attest": f"{public}/api/convergence/bridge/attest",
            "intents": f"{public}/api/convergence/bridge/intents",
            "sync": f"{public}/api/convergence/bridge/sync",
        },
    }