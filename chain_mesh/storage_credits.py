"""BLURT → STONE storage credit rail — memo `storage:<STONE_ADDRESS>:<bytes>`."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from chain_mesh import db as mesh_db

STORAGE_MEMO_RE = re.compile(
    r"^storage:([A-Za-z0-9]{25,62}):(\d+)$",
    re.IGNORECASE,
)
BLURT_RPC_NODES = [
    n.strip()
    for n in os.environ.get(
        "BLURT_REGISTRY_RPC_NODES", "https://rpc.blurt.blog,https://blurt-rpc.saboin.com"
    ).split(",")
    if n.strip()
]
OUTPOST_ACCOUNT = os.environ.get(
    "BLURT_STORAGE_OUTPOST_ACCOUNT", "bloodstone-storage"
).lstrip("@").lower()
BYTES_PER_BLURT = int(os.environ.get("STORAGE_BYTES_PER_BLURT", str(1024 * 1024 * 1024)))
ENFORCE_QUOTA = os.environ.get("STORAGE_CREDIT_ENFORCE", "0").strip() in ("1", "true", "yes")


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def init_storage_credits_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS storage_credit_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stone_address TEXT NOT NULL,
                bytes_credited INTEGER NOT NULL DEFAULT 0,
                bytes_consumed INTEGER NOT NULL DEFAULT 0,
                blurt_txid TEXT NOT NULL DEFAULT '',
                blurt_from TEXT NOT NULL DEFAULT '',
                blurt_amount TEXT NOT NULL DEFAULT '',
                memo TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_storage_credit_tx
                ON storage_credit_ledger(blurt_txid);
            CREATE INDEX IF NOT EXISTS idx_storage_credit_addr
                ON storage_credit_ledger(stone_address);
            CREATE TABLE IF NOT EXISTS storage_usage (
                stone_address TEXT PRIMARY KEY,
                bytes_used INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL
            );
            """
        )


def parse_storage_memo(memo: str) -> Optional[Tuple[str, int]]:
    m = STORAGE_MEMO_RE.match((memo or "").strip())
    if not m:
        return None
    return m.group(1), int(m.group(2))


def credit_from_blurt_transfer(
    *,
    stone_address: str,
    bytes_credited: int,
    blurt_txid: str = "",
    blurt_from: str = "",
    blurt_amount: str = "",
    memo: str = "",
) -> Dict[str, Any]:
    init_storage_credits_db()
    addr = (stone_address or "").strip()
    if not addr:
        raise ValueError("stone_address required")
    credited = max(0, int(bytes_credited))
    txid = (blurt_txid or "").strip()
    with _conn() as conn:
        if txid:
            existing = conn.execute(
                "SELECT id FROM storage_credit_ledger WHERE blurt_txid = ?",
                (txid,),
            ).fetchone()
            if existing:
                return {"ok": True, "duplicate": True, "stone_address": addr}
        cur = conn.execute(
            """
            INSERT INTO storage_credit_ledger (
                stone_address, bytes_credited, bytes_consumed,
                blurt_txid, blurt_from, blurt_amount, memo, created_at
            ) VALUES (?, ?, 0, ?, ?, ?, ?, ?)
            """,
            (addr, credited, txid, blurt_from, blurt_amount, memo, _now()),
        )
        return {"ok": True, "id": int(cur.lastrowid), "stone_address": addr, "bytes_credited": credited}


def record_usage(
    stone_address: str,
    *,
    delta_bytes: int,
    blurt_account: str = "",
    tenant_id: str = "",
) -> Dict[str, Any]:
    init_storage_credits_db()
    addr = (stone_address or "").strip()
    delta = int(delta_bytes)
    now = _now()
    if (blurt_account or "").strip():
        try:
            from chain_mesh import storage_tenant_quota as tenant

            tenant.record_tenant_storage_usage(
                blurt_account=str(blurt_account),
                stone_address=addr,
                delta_bytes=delta,
                tenant_id=str(tenant_id or ""),
            )
        except Exception:
            pass
    with _conn() as conn:
        row = conn.execute(
            "SELECT bytes_used FROM storage_usage WHERE stone_address = ?",
            (addr,),
        ).fetchone()
        used = int(row["bytes_used"]) if row else 0
        used = max(0, used + delta)
        if row:
            conn.execute(
                "UPDATE storage_usage SET bytes_used = ?, updated_at = ? WHERE stone_address = ?",
                (used, now, addr),
            )
        else:
            conn.execute(
                "INSERT INTO storage_usage (stone_address, bytes_used, updated_at) VALUES (?, ?, ?)",
                (addr, used, now),
            )
    return {"ok": True, "stone_address": addr, "bytes_used": used}


def quota_summary(stone_address: str) -> Dict[str, Any]:
    init_storage_credits_db()
    addr = (stone_address or "").strip()
    with _conn() as conn:
        credited = conn.execute(
            "SELECT COALESCE(SUM(bytes_credited), 0) AS total FROM storage_credit_ledger WHERE stone_address = ?",
            (addr,),
        ).fetchone()["total"]
        row = conn.execute(
            "SELECT bytes_used FROM storage_usage WHERE stone_address = ?",
            (addr,),
        ).fetchone()
        used = int(row["bytes_used"]) if row else 0
    remaining = max(0, int(credited) - used)
    return {
        "ok": True,
        "stone_address": addr,
        "bytes_credited": int(credited),
        "bytes_used": used,
        "bytes_remaining": remaining,
        "enforce_quota": ENFORCE_QUOTA,
    }


def check_publish_allowed(
    stone_address: str,
    file_size: int,
    *,
    blurt_account: str = "",
    tenant_id: str = "",
) -> Dict[str, Any]:
    if (blurt_account or "").strip():
        try:
            from chain_mesh import storage_tenant_quota as tenant

            return tenant.check_tenant_storage_allowed(
                stone_address=stone_address,
                byte_size=int(file_size),
                blurt_account=str(blurt_account or ""),
                tenant_id=str(tenant_id or ""),
            )
        except Exception:
            pass
    q = quota_summary(stone_address)
    if not ENFORCE_QUOTA or not stone_address:
        return {"ok": True, "allowed": True, "quota": q, "reason": "quota enforcement off"}
    need = max(0, int(file_size))
    if q["bytes_remaining"] >= need:
        return {"ok": True, "allowed": True, "quota": q}
    return {
        "ok": True,
        "allowed": False,
        "quota": q,
        "reason": f"insufficient storage credits: need {need}, have {q['bytes_remaining']}",
    }


def _blurt_rpc(method: str, params: List[Any]) -> Any:
    last_err = None
    for node in BLURT_RPC_NODES:
        try:
            resp = requests.post(
                node,
                json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1},
                timeout=25,
            )
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("error"):
                raise RuntimeError(payload["error"])
            return payload.get("result")
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"Blurt RPC failed: {last_err}")


def sync_outpost_transfers(*, limit: int = 50) -> Dict[str, Any]:
    """Scan BLURT transfers to outpost account and credit storage memos."""
    init_storage_credits_db()
    acct = OUTPOST_ACCOUNT
    history = _blurt_rpc(
        "database_api.get_account_history",
        [acct, -1, limit, 1000000000],
    )
    credited = 0
    skipped = 0
    for entry in history or []:
        op = entry.get("op") or []
        if len(op) < 2 or op[0] != "transfer":
            continue
        body = op[1] or {}
        if str(body.get("to", "")).lstrip("@").lower() != acct:
            continue
        memo = str(body.get("memo") or "")
        parsed = parse_storage_memo(memo)
        if not parsed:
            amount_field = str(body.get("amount") or "")
            parts = amount_field.split()
            if len(parts) >= 2 and parts[1].upper() == "BLURT":
                try:
                    blurt_amt = float(parts[0])
                    bytes_from_blurt = int(blurt_amt * BYTES_PER_BLURT)
                    stone = str(body.get("from") or "").lstrip("@").lower()
                    if bytes_from_blurt > 0 and stone:
                        credit_from_blurt_transfer(
                            stone_address=stone,
                            bytes_credited=bytes_from_blurt,
                            blurt_txid=str(entry.get("trx_id") or ""),
                            blurt_from=stone,
                            blurt_amount=parts[0],
                            memo=f"blurt:{blurt_amt}",
                        )
                        credited += 1
                    else:
                        skipped += 1
                except (TypeError, ValueError):
                    skipped += 1
            else:
                skipped += 1
            continue
        stone_addr, byte_amt = parsed
        credit_from_blurt_transfer(
            stone_address=stone_addr,
            bytes_credited=byte_amt,
            blurt_txid=str(entry.get("trx_id") or ""),
            blurt_from=str(body.get("from") or ""),
            blurt_amount=str(body.get("amount") or ""),
            memo=memo,
        )
        credited += 1
    return {
        "ok": True,
        "outpost_account": acct,
        "credited": credited,
        "skipped": skipped,
        "bytes_per_blurt": BYTES_PER_BLURT,
    }