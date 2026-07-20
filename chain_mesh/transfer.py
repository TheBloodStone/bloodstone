"""BSM2 mesh transfer service — create, anchor, attest, and deliver."""

from __future__ import annotations

from chain_mesh.security import public_error
import json
import time
from typing import Any, Dict, List, Optional

from chain_mesh import assets as mesh_assets
from chain_mesh import db as mesh_db
from chain_mesh.anchor import anchor_asset_on_chain
from chain_mesh.merkle import merkle_root
from chain_mesh.store import chunk_exists
from chain_mesh import transfer_protocol as tp


def _init_transfer_tables() -> None:
    with mesh_db._conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS chain_mesh_transfers (
                transfer_id TEXT PRIMARY KEY,
                sender TEXT NOT NULL DEFAULT '',
                recipient TEXT NOT NULL DEFAULT '',
                display_name TEXT NOT NULL DEFAULT '',
                mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
                file_size INTEGER NOT NULL,
                file_sha256 TEXT NOT NULL,
                merkle_root TEXT NOT NULL,
                chunk_count INTEGER NOT NULL,
                chunks_json TEXT NOT NULL,
                asset_key TEXT NOT NULL,
                asset_id TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                anchor_txid TEXT,
                anchor_height INTEGER,
                anchor_confirmations INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                claimed_at INTEGER,
                claimed_by TEXT NOT NULL DEFAULT '',
                expires_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_mesh_transfers_recipient
                ON chain_mesh_transfers(recipient, status, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_mesh_transfers_sender
                ON chain_mesh_transfers(sender, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_mesh_transfers_status
                ON chain_mesh_transfers(status, updated_at DESC);

            CREATE TABLE IF NOT EXISTS chain_mesh_transfer_attestations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transfer_id TEXT NOT NULL,
                chunk_hash TEXT NOT NULL,
                device_id TEXT NOT NULL DEFAULT '',
                worker TEXT NOT NULL DEFAULT '',
                job_id TEXT NOT NULL DEFAULT '',
                nonce_hex TEXT NOT NULL DEFAULT '',
                work_digest TEXT NOT NULL,
                bytes_attested INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                UNIQUE(transfer_id, chunk_hash, device_id, work_digest)
            );
            CREATE INDEX IF NOT EXISTS idx_transfer_attest_tid
                ON chain_mesh_transfer_attestations(transfer_id, created_at DESC);
            """
        )


_init_transfer_tables()


def _row_to_transfer(row: Dict[str, Any]) -> Dict[str, Any]:
    chunks = json.loads(row.get("chunks_json") or "[]")
    return tp.build_transfer_manifest(
        transfer_id=row["transfer_id"],
        sender=row["sender"],
        recipient=row["recipient"],
        display_name=row["display_name"],
        mime_type=row["mime_type"],
        file_size=int(row["file_size"]),
        file_sha256=row["file_sha256"],
        merkle_root=row["merkle_root"],
        chunks=chunks,
        asset_key=row.get("asset_key"),
        anchor_txid=row.get("anchor_txid"),
        status=row["status"],
        created_at=int(row["created_at"]),
    )


def _chunks_on_mesh(chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    missing = []
    peer_sets = []
    for chunk in chunks:
        h = str(chunk.get("chunk_hash") or "").lower()
        if not chunk_exists(h):
            missing.append(h)
        peers = mesh_db.peers_for_chunk(h)
        peer_sets.append(len(peers))
    min_peers = min(peer_sets) if peer_sets else 0
    return {
        "chunks_total": len(chunks),
        "chunks_missing": len(missing),
        "min_peer_count": min_peers,
        "missing_sample": missing[:8],
    }


def create_transfer_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Register a new BSM2 transfer (chunks must already be on mesh)."""
    sender = str(payload.get("sender") or payload.get("sender_address") or "").strip()
    recipient = str(payload.get("recipient") or payload.get("recipient_address") or "").strip()
    display_name = str(payload.get("display_name") or payload.get("filename") or "payload").strip()
    mime_type = str(payload.get("mime_type") or "application/octet-stream").strip()
    fsize = int(payload.get("file_size") or 0)
    fhash = str(payload.get("file_sha256") or "").strip().lower()
    root = str(payload.get("merkle_root") or "").strip().lower()
    chunks = list(payload.get("chunks") or [])
    anchor = bool(payload.get("anchor", True))
    ttl_hours = int(payload.get("ttl_hours") or 168)

    if not sender or not recipient:
        raise ValueError("sender and recipient addresses required")
    if fsize <= 0 or fsize > mesh_assets.MAX_ASSET_PUBLISH_BYTES:
        raise ValueError(f"file_size must be 1..{mesh_assets.MAX_ASSET_PUBLISH_BYTES}")
    if len(fhash) != 64:
        raise ValueError("file_sha256 must be 64 hex chars")
    if len(root) != 64:
        raise ValueError("merkle_root must be 64 hex chars")

    normalized = mesh_assets._validate_chunk_manifest(chunks, file_size=fsize)
    computed = merkle_root([c["chunk_hash"] for c in normalized])
    if computed != root:
        raise ValueError("merkle_root does not match chunk hashes")

    transfer_id = str(payload.get("transfer_id") or "").strip().lower()
    if not transfer_id or len(transfer_id) != 64:
        transfer_id = tp.transfer_id_for(
            sender=sender,
            recipient=recipient,
            file_sha256=fhash,
            nonce=str(payload.get("nonce") or ""),
        )

    user_asset_key = str(payload.get("asset_key") or "").strip()
    if user_asset_key:
        asset_key = mesh_assets.normalize_asset_key(user_asset_key)
    else:
        asset_key = tp.transfer_asset_key(transfer_id, display_name)
    now = int(time.time())
    expires_at = now + max(3600, ttl_hours * 3600)

    with mesh_db._conn() as conn:
        existing = conn.execute(
            "SELECT transfer_id FROM chain_mesh_transfers WHERE transfer_id = ?",
            (transfer_id,),
        ).fetchone()
        if existing:
            raise ValueError("transfer_id already exists")

        conn.execute(
            """
            INSERT INTO chain_mesh_transfers (
                transfer_id, sender, recipient, display_name, mime_type,
                file_size, file_sha256, merkle_root, chunk_count, chunks_json,
                asset_key, status, created_at, updated_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                transfer_id,
                sender,
                recipient,
                display_name,
                mime_type,
                fsize,
                fhash,
                root,
                len(normalized),
                json.dumps(normalized),
                asset_key,
                tp.TRANSFER_STATUS_DRAFT,
                now,
                now,
                expires_at,
            ),
        )

    result: Dict[str, Any] = {
        "ok": True,
        "transfer_id": transfer_id,
        "asset_key": asset_key,
        "status": tp.TRANSFER_STATUS_DRAFT,
        "mesh": _chunks_on_mesh(normalized),
        "message": "Transfer registered. Anchor on-chain to begin miner-attested replication.",
    }

    if user_asset_key:
        try:
            publish_result = mesh_assets.publish_asset_manifest(
                asset_key=asset_key,
                display_name=display_name,
                version=str(payload.get("version") or ""),
                mime_type=mime_type,
                file_size=fsize,
                file_sha256=fhash,
                merkle_root_hex=root,
                chunks=normalized,
                anchor=bool(payload.get("mesh_anchor", anchor)),
            )
            result["mesh_publish"] = publish_result
            result["overwrite"] = True
        except Exception as exc:
            result["mesh_publish"] = {"ok": False, "error": public_error(exc)}

    if anchor:
        anchor_result = anchor_transfer_payload(transfer_id)
        result["anchor"] = anchor_result
        result["status"] = anchor_result.get("status", tp.TRANSFER_STATUS_ANCHORING)

    return result


def anchor_transfer(transfer_id: str, *, wallet: Optional[str] = None) -> Dict[str, Any]:
    tid = (transfer_id or "").strip().lower()
    with mesh_db._conn() as conn:
        row = conn.execute(
            "SELECT * FROM chain_mesh_transfers WHERE transfer_id = ?",
            (tid,),
        ).fetchone()
        if not row:
            raise ValueError("transfer not found")
        data = dict(row)

    payload_bytes = tp.build_transfer_anchor_payload(
        transfer_id=tid,
        merkle_root=data["merkle_root"],
        recipient_address=data["recipient"],
    )
    wname = wallet or None
    anchor_result = _anchor_bsm2_payload(
        payload_bytes=payload_bytes,
        wallet=wname,
    )

    now = int(time.time())
    status = tp.TRANSFER_STATUS_REPLICATING
    with mesh_db._conn() as conn:
        conn.execute(
            """
            UPDATE chain_mesh_transfers
            SET status = ?, anchor_txid = ?, anchor_height = ?,
                anchor_confirmations = ?, updated_at = ?
            WHERE transfer_id = ?
            """,
            (
                status,
                anchor_result.get("txid"),
                int(anchor_result.get("anchor_height") or 0),
                int(anchor_result.get("confirmations") or 0),
                now,
                tid,
            ),
        )

    chunks = json.loads(data["chunks_json"] or "[]")
    mesh = _chunks_on_mesh(chunks)
    if mesh["chunks_missing"] == 0 and mesh["min_peer_count"] >= 2:
        _mark_transfer_ready(tid)

    return {
        "ok": True,
        "transfer_id": tid,
        "status": status,
        "anchor": anchor_result,
        "mesh": mesh,
    }


def anchor_transfer_payload(transfer_id: str, *, wallet: Optional[str] = None) -> Dict[str, Any]:
    return anchor_transfer(transfer_id, wallet=wallet)


def _anchor_bsm2_payload(*, payload_bytes: bytes, wallet: Optional[str] = None) -> Dict[str, Any]:
    import os
    import sys

    sys.path.insert(0, "/root/bloodstone-wallet-web")
    import wallet_rpc  # noqa: E402

    wname = (wallet or os.environ.get("CHAIN_MESH_ANCHOR_WALLET", "mine")).strip()
    wallet_rpc.ensure_wallet_loaded(wname)
    data_hex = payload_bytes.hex()
    raw = wallet_rpc.rpc("createrawtransaction", [[], {"data": data_hex}], wallet=wname)
    funded = wallet_rpc.rpc("fundrawtransaction", [raw], wallet=wname)
    signed = wallet_rpc.rpc("signrawtransactionwithwallet", [funded["hex"]], wallet=wname)
    if not signed.get("complete"):
        raise RuntimeError(f"BSM2 anchor signing incomplete: {signed!r}")
    txid = wallet_rpc.rpc("sendrawtransaction", [signed["hex"]])
    height = 0
    confirmations = 0
    try:
        tx = wallet_rpc.rpc("gettransaction", [txid], wallet=wname)
        confirmations = int(tx.get("confirmations") or 0)
        if confirmations > 0 and tx.get("blockhash"):
            header = wallet_rpc.rpc("getblockheader", [tx["blockhash"]])
            height = int(header.get("height") or 0)
    except RuntimeError:
        pass
    return {
        "ok": True,
        "txid": txid,
        "anchor_height": height,
        "confirmations": confirmations,
        "payload_hex": data_hex,
        "wallet": wname,
        "magic": "BSM2",
    }


def _mark_transfer_ready(transfer_id: str) -> None:
    with mesh_db._conn() as conn:
        conn.execute(
            """
            UPDATE chain_mesh_transfers
            SET status = ?, updated_at = ?
            WHERE transfer_id = ? AND status IN ('anchoring', 'replicating')
            """,
            (tp.TRANSFER_STATUS_READY, int(time.time()), transfer_id),
        )


def attest_transfer_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Record miner hash-power attestation for relaying a transfer chunk.

    Miners should call this after a share is accepted by the pool, binding
    the share's job_id + nonce to the chunk they stored/forwarded.
    """
    transfer_id = str(payload.get("transfer_id") or "").strip().lower()
    chunk_hash = str(payload.get("chunk_hash") or "").strip().lower()
    device_id = str(payload.get("device_id") or "").strip()
    worker = str(payload.get("worker") or "").strip()
    job_id = str(payload.get("job_id") or "").strip()
    nonce_hex = str(payload.get("nonce_hex") or payload.get("nonce") or "").strip().lower()

    if len(transfer_id) != 64:
        raise ValueError("transfer_id required")
    if len(chunk_hash) != 64:
        raise ValueError("chunk_hash required")
    if not device_id:
        raise ValueError("device_id required")
    if not job_id or not nonce_hex:
        raise ValueError("job_id and nonce_hex required (from last accepted share)")

    digest = tp.work_digest(
        transfer_id=transfer_id,
        chunk_hash=chunk_hash,
        job_id=job_id,
        nonce_hex=nonce_hex,
    )

    with mesh_db._conn() as conn:
        row = conn.execute(
            "SELECT * FROM chain_mesh_transfers WHERE transfer_id = ?",
            (transfer_id,),
        ).fetchone()
        if not row:
            raise ValueError("transfer not found")
        data = dict(row)
        if data["status"] not in tp.ACTIVE_STATUSES and data["status"] != tp.TRANSFER_STATUS_DRAFT:
            raise ValueError(f"transfer status is {data['status']}")

        chunks = json.loads(data["chunks_json"] or "[]")
        chunk_row = next(
            (c for c in chunks if str(c.get("chunk_hash") or "").lower() == chunk_hash),
            None,
        )
        if not chunk_row:
            raise ValueError("chunk_hash not in transfer manifest")
        if not chunk_exists(chunk_hash):
            raise ValueError("chunk not on mesh — upload chunk before attesting")

        size = int(chunk_row.get("size") or 0)
        now = int(time.time())
        try:
            conn.execute(
                """
                INSERT INTO chain_mesh_transfer_attestations (
                    transfer_id, chunk_hash, device_id, worker, job_id,
                    nonce_hex, work_digest, bytes_attested, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transfer_id,
                    chunk_hash,
                    device_id,
                    worker,
                    job_id,
                    nonce_hex,
                    digest,
                    size,
                    now,
                ),
            )
        except Exception:
            return {
                "ok": True,
                "duplicate": True,
                "work_digest": digest,
                "bytes_attested": size,
            }

        mesh_db.upsert_peer(
            device_id=device_id,
            peer_kind=str(payload.get("peer_kind") or "android-miner"),
            model=str(payload.get("model") or ""),
            capacity_bytes=int(payload.get("capacity_bytes") or 0),
            chunk_hashes=[chunk_hash],
        )

        conn.execute(
            "UPDATE chain_mesh_transfers SET updated_at = ? WHERE transfer_id = ?",
            (now, transfer_id),
        )

    mesh = _chunks_on_mesh(chunks)
    if mesh["chunks_missing"] == 0 and mesh["min_peer_count"] >= 2:
        _mark_transfer_ready(transfer_id)

    return {
        "ok": True,
        "transfer_id": transfer_id,
        "chunk_hash": chunk_hash,
        "work_digest": digest,
        "bytes_attested": size,
        "mesh": mesh,
    }


def get_transfer_payload(transfer_id: str) -> Dict[str, Any]:
    tid = (transfer_id or "").strip().lower()
    with mesh_db._conn() as conn:
        row = conn.execute(
            "SELECT * FROM chain_mesh_transfers WHERE transfer_id = ?",
            (tid,),
        ).fetchone()
    if not row:
        return {"ok": False, "error": "transfer not found"}
    data = dict(row)
    manifest = _row_to_transfer(data)
    chunks = manifest["chunks"]
    mesh = _chunks_on_mesh(chunks)
    attest_count = conn_attestation_count(tid)
    from chain_mesh import assignment as mesh_assign

    assign = mesh_assign.assignment_info()
    return {
        "ok": True,
        "transfer": manifest,
        "mesh": mesh,
        "attestations": attest_count,
        "assignment": assign,
        "assignment_note": assign.get("note", ""),
    }


def conn_attestation_count(transfer_id: str) -> Dict[str, Any]:
    with mesh_db._conn() as conn:
        rows = conn.execute(
            """
            SELECT COUNT(*) AS n, COALESCE(SUM(bytes_attested), 0) AS bytes
            FROM chain_mesh_transfer_attestations
            WHERE transfer_id = ?
            """,
            (transfer_id,),
        ).fetchone()
        devices = conn.execute(
            """
            SELECT COUNT(DISTINCT device_id) AS n
            FROM chain_mesh_transfer_attestations
            WHERE transfer_id = ?
            """,
            (transfer_id,),
        ).fetchone()
    return {
        "count": int(rows["n"] if rows else 0),
        "bytes_attested": int(rows["bytes"] if rows else 0),
        "devices": int(devices["n"] if devices else 0),
    }


def list_transfers_for_recipient(
    recipient: str,
    *,
    status: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    addr = (recipient or "").strip()
    clauses = ["recipient = ?"]
    params: List[Any] = [addr]
    if status:
        clauses.append("status = ?")
        params.append(status)
    params.append(max(1, min(200, int(limit))))
    sql = (
        "SELECT transfer_id, sender, recipient, display_name, file_size, status, "
        "anchor_txid, created_at, updated_at FROM chain_mesh_transfers "
        f"WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?"
    )
    with mesh_db._conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {
        "ok": True,
        "recipient": addr,
        "transfers": [dict(r) for r in rows],
        "count": len(rows),
    }


def claim_transfer_payload(transfer_id: str, *, claimant: str) -> Dict[str, Any]:
    tid = (transfer_id or "").strip().lower()
    who = (claimant or "").strip()
    now = int(time.time())
    with mesh_db._conn() as conn:
        row = conn.execute(
            "SELECT * FROM chain_mesh_transfers WHERE transfer_id = ?",
            (tid,),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "transfer not found"}
        data = dict(row)
        if who and data["recipient"] and who != data["recipient"]:
            return {"ok": False, "error": "recipient mismatch"}
        conn.execute(
            """
            UPDATE chain_mesh_transfers
            SET status = ?, claimed_at = ?, claimed_by = ?, updated_at = ?
            WHERE transfer_id = ?
            """,
            (tp.TRANSFER_STATUS_CLAIMED, now, who or data["recipient"], now, tid),
        )
    manifest = _row_to_transfer(data)
    return {"ok": True, "transfer_id": tid, "status": tp.TRANSFER_STATUS_CLAIMED, "transfer": manifest}


def transfer_status_payload() -> Dict[str, Any]:
    writable = mesh_assets.writable_keys_payload(limit=100)
    with mesh_db._conn() as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS n
            FROM chain_mesh_transfers
            GROUP BY status
            """
        ).fetchall()
        att = conn.execute(
            """
            SELECT COUNT(*) AS n, COALESCE(SUM(bytes_attested), 0) AS bytes
            FROM chain_mesh_transfer_attestations
            """
        ).fetchone()
    return {
        "ok": True,
        "protocol": tp.TRANSFER_PROTOCOL,
        "magic": "BSM2",
        "by_status": {str(r["status"]): int(r["n"]) for r in rows},
        "attestations": {
            "count": int(att["n"] if att else 0),
            "bytes_attested": int(att["bytes"] if att else 0),
        },
        "writable_keys": writable.get("keys") or [],
        "writable_keys_note": writable.get("note", ""),
        "description": (
            "BSM2 mesh transfers: on-chain anchor + miner hash-power attestation "
            "for chunk relay. Pass asset_key to overwrite an existing mesh file. "
            "See transfer_protocol.py for full spec."
        ),
    }