"""DePIN memo rails — compute:<STONE>:<job_id> and bandwidth:<STONE>:<bytes>."""

from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from chain_mesh import db as mesh_db

COMPUTE_MEMO_RE = re.compile(
    r"^compute:([A-Za-z0-9]{25,62}):([a-zA-Z0-9\-_]{1,64})$",
    re.IGNORECASE,
)
BANDWIDTH_MEMO_RE = re.compile(
    r"^bandwidth:([A-Za-z0-9]{25,62}):(\d+)$",
    re.IGNORECASE,
)
JOB_ID_RE = re.compile(r"^[a-zA-Z0-9\-_]{1,64}$")

BLURT_RPC_NODES = [
    n.strip()
    for n in os.environ.get(
        "BLURT_REGISTRY_RPC_NODES", "https://rpc.blurt.blog,https://blurt-rpc.saboin.com"
    ).split(",")
    if n.strip()
]
DEPIN_OUTPOST_ACCOUNT = os.environ.get(
    "BLURT_DEPIN_OUTPOST_ACCOUNT", "bloodstone-depin"
).lstrip("@").lower()
FLOPS_PER_BLURT = int(os.environ.get("COMPUTE_FLOPS_PER_BLURT", str(1_000_000_000)))
BYTES_PER_BLURT_BANDWIDTH = int(
    os.environ.get("BANDWIDTH_BYTES_PER_BLURT", str(100 * 1024 * 1024))
)
ENFORCE_COMPUTE = os.environ.get("COMPUTE_CREDIT_ENFORCE", "0").strip() in ("1", "true", "yes")
ENFORCE_BANDWIDTH = os.environ.get("BANDWIDTH_CREDIT_ENFORCE", "0").strip() in (
    "1",
    "true",
    "yes",
)


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def init_depin_db() -> None:
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS compute_credit_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stone_address TEXT NOT NULL,
                job_id TEXT NOT NULL DEFAULT '',
                flops_credited INTEGER NOT NULL DEFAULT 0,
                flops_consumed INTEGER NOT NULL DEFAULT 0,
                blurt_txid TEXT NOT NULL DEFAULT '',
                blurt_from TEXT NOT NULL DEFAULT '',
                blurt_amount TEXT NOT NULL DEFAULT '',
                memo TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_compute_credit_tx
                ON compute_credit_ledger(blurt_txid);
            CREATE INDEX IF NOT EXISTS idx_compute_credit_addr
                ON compute_credit_ledger(stone_address);

            CREATE TABLE IF NOT EXISTS compute_usage (
                stone_address TEXT PRIMARY KEY,
                flops_used INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bandwidth_credit_ledger (
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
            CREATE UNIQUE INDEX IF NOT EXISTS idx_bandwidth_credit_tx
                ON bandwidth_credit_ledger(blurt_txid);
            CREATE INDEX IF NOT EXISTS idx_bandwidth_credit_addr
                ON bandwidth_credit_ledger(stone_address);

            CREATE TABLE IF NOT EXISTS bandwidth_usage (
                stone_address TEXT PRIMARY KEY,
                bytes_used INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL
            );
            """
        )


def parse_compute_memo(memo: str) -> Optional[Tuple[str, str]]:
    m = COMPUTE_MEMO_RE.match((memo or "").strip())
    if not m:
        return None
    return m.group(1), m.group(2)


def parse_bandwidth_memo(memo: str) -> Optional[Tuple[str, int]]:
    m = BANDWIDTH_MEMO_RE.match((memo or "").strip())
    if not m:
        return None
    return m.group(1), int(m.group(2))


def credit_compute(
    *,
    stone_address: str,
    job_id: str,
    flops_credited: int,
    blurt_txid: str = "",
    blurt_from: str = "",
    blurt_amount: str = "",
    memo: str = "",
) -> Dict[str, Any]:
    init_depin_db()
    addr = (stone_address or "").strip()
    jid = (job_id or "").strip()
    if not addr or not jid:
        raise ValueError("stone_address and job_id required")
    credited = max(0, int(flops_credited))
    txid = (blurt_txid or "").strip()
    with _conn() as conn:
        if txid:
            existing = conn.execute(
                "SELECT id FROM compute_credit_ledger WHERE blurt_txid = ?",
                (txid,),
            ).fetchone()
            if existing:
                return {"ok": True, "duplicate": True, "stone_address": addr, "job_id": jid}
        cur = conn.execute(
            """
            INSERT INTO compute_credit_ledger (
                stone_address, job_id, flops_credited, flops_consumed,
                blurt_txid, blurt_from, blurt_amount, memo, created_at
            ) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?)
            """,
            (addr, jid, credited, txid, blurt_from, blurt_amount, memo, _now()),
        )
        return {
            "ok": True,
            "id": int(cur.lastrowid),
            "stone_address": addr,
            "job_id": jid,
            "flops_credited": credited,
        }


def credit_bandwidth(
    *,
    stone_address: str,
    bytes_credited: int,
    blurt_txid: str = "",
    blurt_from: str = "",
    blurt_amount: str = "",
    memo: str = "",
) -> Dict[str, Any]:
    init_depin_db()
    addr = (stone_address or "").strip()
    credited = max(0, int(bytes_credited))
    txid = (blurt_txid or "").strip()
    with _conn() as conn:
        if txid:
            existing = conn.execute(
                "SELECT id FROM bandwidth_credit_ledger WHERE blurt_txid = ?",
                (txid,),
            ).fetchone()
            if existing:
                return {"ok": True, "duplicate": True, "stone_address": addr}
        cur = conn.execute(
            """
            INSERT INTO bandwidth_credit_ledger (
                stone_address, bytes_credited, bytes_consumed,
                blurt_txid, blurt_from, blurt_amount, memo, created_at
            ) VALUES (?, ?, 0, ?, ?, ?, ?, ?)
            """,
            (addr, credited, txid, blurt_from, blurt_amount, memo, _now()),
        )
        return {
            "ok": True,
            "id": int(cur.lastrowid),
            "stone_address": addr,
            "bytes_credited": credited,
        }


def compute_quota(stone_address: str) -> Dict[str, Any]:
    init_depin_db()
    addr = (stone_address or "").strip()
    with _conn() as conn:
        credited = conn.execute(
            """
            SELECT COALESCE(SUM(flops_credited), 0) AS total
            FROM compute_credit_ledger WHERE stone_address = ?
            """,
            (addr,),
        ).fetchone()["total"]
        row = conn.execute(
            "SELECT flops_used FROM compute_usage WHERE stone_address = ?",
            (addr,),
        ).fetchone()
        used = int(row["flops_used"]) if row else 0
        jobs = conn.execute(
            """
            SELECT job_id, flops_credited, created_at
            FROM compute_credit_ledger
            WHERE stone_address = ?
            ORDER BY created_at DESC LIMIT 20
            """,
            (addr,),
        ).fetchall()
    remaining = max(0, int(credited) - used)
    return {
        "ok": True,
        "rail": "compute",
        "stone_address": addr,
        "flops_credited": int(credited),
        "flops_used": used,
        "flops_remaining": remaining,
        "enforce_quota": ENFORCE_COMPUTE,
        "recent_jobs": [dict(r) for r in jobs],
        "memo_format": "compute:<STONE_ADDRESS>:<job_id>",
    }


def bandwidth_quota(stone_address: str) -> Dict[str, Any]:
    init_depin_db()
    addr = (stone_address or "").strip()
    with _conn() as conn:
        credited = conn.execute(
            """
            SELECT COALESCE(SUM(bytes_credited), 0) AS total
            FROM bandwidth_credit_ledger WHERE stone_address = ?
            """,
            (addr,),
        ).fetchone()["total"]
        row = conn.execute(
            "SELECT bytes_used FROM bandwidth_usage WHERE stone_address = ?",
            (addr,),
        ).fetchone()
        used = int(row["bytes_used"]) if row else 0
    remaining = max(0, int(credited) - used)
    return {
        "ok": True,
        "rail": "bandwidth",
        "stone_address": addr,
        "bytes_credited": int(credited),
        "bytes_used": used,
        "bytes_remaining": remaining,
        "enforce_quota": ENFORCE_BANDWIDTH,
        "memo_format": "bandwidth:<STONE_ADDRESS>:<bytes>",
    }


def check_bandwidth_allowed(stone_address: str, byte_size: int) -> Dict[str, Any]:
    q = bandwidth_quota(stone_address)
    if not ENFORCE_BANDWIDTH or not stone_address:
        return {"ok": True, "allowed": True, "quota": q, "reason": "bandwidth enforcement off"}
    need = max(0, int(byte_size))
    if q["bytes_remaining"] >= need:
        return {"ok": True, "allowed": True, "quota": q}
    return {
        "ok": True,
        "allowed": False,
        "quota": q,
        "reason": f"insufficient bandwidth credits: need {need}, have {q['bytes_remaining']}",
    }


def check_compute_allowed(
    stone_address: str,
    *,
    flops_budget: int = 0,
    job_id: str = "",
    blurt_author: str = "",
    tenant_id: str = "",
) -> Dict[str, Any]:
    if (blurt_author or "").strip():
        try:
            from chain_mesh import compute_tenant_quota as tenant

            return tenant.check_tenant_compute_allowed(
                stone_address=stone_address,
                flops_budget=int(flops_budget),
                job_id=str(job_id or ""),
                blurt_author=str(blurt_author or ""),
                tenant_id=str(tenant_id or ""),
            )
        except Exception:
            pass
    q = compute_quota(stone_address)
    if not ENFORCE_COMPUTE or not stone_address:
        return {"ok": True, "allowed": True, "quota": q, "reason": "compute enforcement off"}
    jid = (job_id or "").strip()
    memo_ok = any(str(r.get("job_id") or "") == jid for r in (q.get("recent_jobs") or [])) if jid else False
    need = max(0, int(flops_budget))
    remaining = int(q.get("flops_remaining") or 0)
    if memo_ok or (need > 0 and remaining >= need) or (need <= 0 and remaining > 0):
        return {"ok": True, "allowed": True, "quota": q, "memo_credited": memo_ok}
    return {
        "ok": True,
        "allowed": False,
        "quota": q,
        "memo_credited": memo_ok,
        "reason": (
            f"insufficient compute credits: need {need} FLOPS, have {remaining}"
            if need > 0
            else "no compute credits — pay BLURT memo compute:<STONE>:<job_id>"
        ),
    }


def depin_quota_summary(stone_address: str) -> Dict[str, Any]:
    return {
        "ok": True,
        "stone_address": (stone_address or "").strip(),
        "compute": compute_quota(stone_address),
        "bandwidth": bandwidth_quota(stone_address),
        "outpost_account": DEPIN_OUTPOST_ACCOUNT,
        "flops_per_blurt": FLOPS_PER_BLURT,
        "bandwidth_bytes_per_blurt": BYTES_PER_BLURT_BANDWIDTH,
    }


def record_compute_usage(
    stone_address: str,
    *,
    delta_flops: int,
    blurt_author: str = "",
    tenant_id: str = "",
) -> Dict[str, Any]:
    init_depin_db()
    addr = (stone_address or "").strip()
    delta = int(delta_flops)
    now = _now()
    if (blurt_author or "").strip():
        try:
            from chain_mesh import compute_tenant_quota as tenant

            tenant.record_tenant_compute_usage(
                blurt_author=str(blurt_author),
                stone_address=addr,
                delta_flops=delta,
                tenant_id=str(tenant_id or ""),
            )
        except Exception:
            pass
    with _conn() as conn:
        row = conn.execute(
            "SELECT flops_used FROM compute_usage WHERE stone_address = ?",
            (addr,),
        ).fetchone()
        used = max(0, int(row["flops_used"]) + delta) if row else max(0, delta)
        if row:
            conn.execute(
                "UPDATE compute_usage SET flops_used = ?, updated_at = ? WHERE stone_address = ?",
                (used, now, addr),
            )
        else:
            conn.execute(
                "INSERT INTO compute_usage (stone_address, flops_used, updated_at) VALUES (?, ?, ?)",
                (addr, used, now),
            )
    return {"ok": True, "stone_address": addr, "flops_used": used}


def record_bandwidth_usage(stone_address: str, *, delta_bytes: int) -> Dict[str, Any]:
    init_depin_db()
    addr = (stone_address or "").strip()
    delta = int(delta_bytes)
    now = _now()
    with _conn() as conn:
        row = conn.execute(
            "SELECT bytes_used FROM bandwidth_usage WHERE stone_address = ?",
            (addr,),
        ).fetchone()
        used = max(0, int(row["bytes_used"]) + delta) if row else max(0, delta)
        if row:
            conn.execute(
                "UPDATE bandwidth_usage SET bytes_used = ?, updated_at = ? WHERE stone_address = ?",
                (used, now, addr),
            )
        else:
            conn.execute(
                "INSERT INTO bandwidth_usage (stone_address, bytes_used, updated_at) VALUES (?, ?, ?)",
                (addr, used, now),
            )
    return {"ok": True, "stone_address": addr, "bytes_used": used}


def _blurt_amount_to_float(amount_field: str) -> float:
    parts = str(amount_field or "").split()
    if len(parts) >= 2 and parts[1].upper() == "BLURT":
        return float(parts[0])
    return 0.0


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


def sync_depin_transfers(*, limit: int = 50) -> Dict[str, Any]:
    """Scan BLURT transfers to DePIN outpost for compute + bandwidth memos."""
    init_depin_db()
    acct = DEPIN_OUTPOST_ACCOUNT
    history = _blurt_rpc(
        "database_api.get_account_history",
        [acct, -1, limit, 1000000000],
    )
    compute_credited = 0
    bandwidth_credited = 0
    skipped = 0
    for entry in history or []:
        op = entry.get("op") or []
        if len(op) < 2 or op[0] != "transfer":
            continue
        body = op[1] or {}
        if str(body.get("to", "")).lstrip("@").lower() != acct:
            continue
        memo = str(body.get("memo") or "")
        txid = str(entry.get("trx_id") or "")
        blurt_from = str(body.get("from") or "")
        blurt_amount = str(body.get("amount") or "")

        compute_parsed = parse_compute_memo(memo)
        if compute_parsed:
            stone_addr, job_id = compute_parsed
            flops = int(_blurt_amount_to_float(blurt_amount) * FLOPS_PER_BLURT)
            if flops <= 0:
                flops = FLOPS_PER_BLURT
            credit_compute(
                stone_address=stone_addr,
                job_id=job_id,
                flops_credited=flops,
                blurt_txid=txid,
                blurt_from=blurt_from,
                blurt_amount=blurt_amount,
                memo=memo,
            )
            compute_credited += 1
            continue

        bandwidth_parsed = parse_bandwidth_memo(memo)
        if bandwidth_parsed:
            stone_addr, byte_amt = bandwidth_parsed
            credit_bandwidth(
                stone_address=stone_addr,
                bytes_credited=byte_amt,
                blurt_txid=txid,
                blurt_from=blurt_from,
                blurt_amount=blurt_amount,
                memo=memo,
            )
            bandwidth_credited += 1
            continue

        skipped += 1

    return {
        "ok": True,
        "outpost_account": acct,
        "compute_credited": compute_credited,
        "bandwidth_credited": bandwidth_credited,
        "skipped": skipped,
        "flops_per_blurt": FLOPS_PER_BLURT,
        "bandwidth_bytes_per_blurt": BYTES_PER_BLURT_BANDWIDTH,
    }