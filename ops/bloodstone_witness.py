"""QUASAR Phase 2 — mesh witness capsules (bloodstone/witness-capsule/v1)."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from chain_mesh import db as mesh_db

CAPSULE_TYPE = "bloodstone/witness-capsule/v1"
WITNESS_DIR = os.environ.get(
    "QUASAR_WITNESS_MESH_PREFIX", "assets/witness"
)
REQUIRED_QUORUM = int(os.environ.get("QUASAR_WITNESS_QUORUM", "3"))
QUORUM_WINDOW_SEC = int(os.environ.get("QUASAR_WITNESS_WINDOW_SEC", "7200"))
PUBLISH_MESH = os.environ.get("QUASAR_WITNESS_PUBLISH_MESH", "1") == "1"
# Tip-height disagreement: ≥2 distinct heights among recent mesh signers.
HEIGHT_DISAGREE_MIN_HEIGHTS = max(
    2, int(os.environ.get("QUASAR_WITNESS_HEIGHT_DISAGREE_MIN_HEIGHTS", "2"))
)
HEIGHT_DISAGREE_MIN_SIGNERS = max(
    1, int(os.environ.get("QUASAR_WITNESS_HEIGHT_DISAGREE_MIN_SIGNERS", "1"))
)
# Re-run AI review when fingerprint is unchanged only after this cooldown.
AI_REVIEW_COOLDOWN_SEC = max(
    60, int(os.environ.get("QUASAR_WITNESS_AI_REVIEW_COOLDOWN_SEC", "300"))
)
AI_REVIEW_STATE_FILE = os.environ.get(
    "QUASAR_WITNESS_AI_REVIEW_STATE",
    "/var/lib/bloodstone/quasar-witness-tip-review.json",
)


def _now() -> int:
    return int(time.time())


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def init_witness_db() -> None:
    mesh_db.init_db()
    with mesh_db._conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS quasar_witness_capsules (
                capsule_id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                tip_hash TEXT NOT NULL,
                height INTEGER NOT NULL,
                node_mode TEXT NOT NULL DEFAULT 'full',
                peer_count INTEGER NOT NULL DEFAULT 0,
                issued_at TEXT NOT NULL,
                mesh_key TEXT NOT NULL DEFAULT '',
                asset_key TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_quasar_witness_tip
                ON quasar_witness_capsules(tip_hash, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_quasar_witness_device
                ON quasar_witness_capsules(device_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_quasar_witness_height
                ON quasar_witness_capsules(height, created_at DESC);

            CREATE TABLE IF NOT EXISTS quasar_witness_tip_reviews (
                review_id TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                local_tip_hash TEXT NOT NULL DEFAULT '',
                local_tip_height INTEGER NOT NULL DEFAULT 0,
                disagreement_json TEXT NOT NULL DEFAULT '{}',
                review_json TEXT NOT NULL DEFAULT '{}',
                operator_decision TEXT NOT NULL DEFAULT '',
                operator_note TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_quasar_witness_tip_reviews_fp
                ON quasar_witness_tip_reviews(fingerprint, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_quasar_witness_tip_reviews_created
                ON quasar_witness_tip_reviews(created_at DESC);
            """
        )


def _canonical_capsule_body(capsule: Dict[str, Any]) -> Dict[str, Any]:
    body = dict(capsule)
    body.pop("capsule_id", None)
    body.pop("signature", None)
    return body


def capsule_id_for(capsule: Dict[str, Any]) -> str:
    raw = json.dumps(_canonical_capsule_body(capsule), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_capsule(capsule: Dict[str, Any]) -> Dict[str, Any]:
    if str(capsule.get("type") or "") != CAPSULE_TYPE:
        raise ValueError(f"type must be {CAPSULE_TYPE}")
    height = int(capsule.get("height") or 0)
    tip_hash = str(capsule.get("tip_hash") or "").strip().lower()
    device_id = str(capsule.get("device_id") or "").strip().lower()
    if height <= 0 or len(tip_hash) != 64 or not device_id:
        raise ValueError("height, tip_hash, and device_id required")
    algo_work = capsule.get("algo_work")
    if not isinstance(algo_work, dict):
        raise ValueError("algo_work object required")
    out = {
        "type": CAPSULE_TYPE,
        "height": height,
        "tip_hash": tip_hash,
        "algo_work": {str(k): str(v) for k, v in algo_work.items()},
        "peer_count": max(0, int(capsule.get("peer_count") or 0)),
        "node_mode": str(capsule.get("node_mode") or "full")[:24],
        "device_id": device_id,
        "mesh_key": str(capsule.get("mesh_key") or device_id)[:128],
        "issued_at": str(capsule.get("issued_at") or _utc_now()),
    }
    out["capsule_id"] = capsule_id_for(out)
    return out


def build_capsule_from_rpc(
    rpc: Callable,
    *,
    device_id: str,
    node_mode: str = "coordinator",
    peer_count: int = 0,
    mesh_key: str = "",
) -> Dict[str, Any]:
    info = rpc("getblockchaininfo")
    mining = rpc("getmininginfo")
    height = int(info.get("blocks") or 0)
    tip_hash = str(info.get("bestblockhash") or "").strip().lower()
    diff = mining.get("difficulty") or {}
    if isinstance(diff, dict):
        algo_work = {str(k): str(v) for k, v in diff.items()}
    else:
        algo_work = {"chain": str(diff)}
    return validate_capsule(
        {
            "type": CAPSULE_TYPE,
            "height": height,
            "tip_hash": tip_hash,
            "algo_work": algo_work,
            "peer_count": peer_count,
            "node_mode": node_mode,
            "device_id": device_id,
            "mesh_key": mesh_key or device_id,
            "issued_at": _utc_now(),
        }
    )


def _mesh_asset_key(device_id: str, height: int) -> str:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in device_id)[:48]
    return f"{WITNESS_DIR}/{month}/{safe}-{height}.json"


def _publish_capsule_asset(capsule: Dict[str, Any]) -> str:
    if not PUBLISH_MESH:
        return ""
    try:
        from chain_mesh import assets as mesh_assets
    except Exception:
        return ""
    asset_key = _mesh_asset_key(capsule["device_id"], capsule["height"])
    fd, path = tempfile.mkstemp(suffix=".json", prefix="witness-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(capsule, fh, indent=2, sort_keys=True)
            fh.write("\n")
        mesh_assets.publish_asset(
            path,
            asset_key=asset_key,
            display_name=f"witness-{capsule['device_id']}-{capsule['height']}",
            version=str(capsule["height"]),
            mime_type="application/json",
            anchor=False,
        )
        return asset_key
    except Exception:
        return ""
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def ingest_capsule(capsule: Dict[str, Any], *, publish: bool = True) -> Dict[str, Any]:
    init_witness_db()
    normalized = validate_capsule(capsule)
    asset_key = ""
    if publish:
        asset_key = _publish_capsule_asset(normalized)
    now = _now()
    with mesh_db._conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO quasar_witness_capsules (
                capsule_id, device_id, tip_hash, height, node_mode, peer_count,
                issued_at, mesh_key, asset_key, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["capsule_id"],
                normalized["device_id"],
                normalized["tip_hash"],
                normalized["height"],
                normalized["node_mode"],
                normalized["peer_count"],
                normalized["issued_at"],
                normalized["mesh_key"],
                asset_key,
                json.dumps(normalized, sort_keys=True),
                now,
            ),
        )
    return {"ok": True, "capsule": normalized, "asset_key": asset_key}


def list_capsules(
    *,
    tip_hash: str = "",
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    init_witness_db()
    limit = max(1, min(200, int(limit)))
    offset = max(0, int(offset))
    clauses = []
    params: List[Any] = []
    if tip_hash:
        clauses.append("tip_hash = ?")
        params.append(tip_hash.strip().lower())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with mesh_db._conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM quasar_witness_capsules {where}",
            params,
        ).fetchone()
        rows = conn.execute(
            f"""
            SELECT capsule_id, device_id, tip_hash, height, node_mode, peer_count,
                   issued_at, mesh_key, asset_key, created_at
            FROM quasar_witness_capsules {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        ).fetchall()
    return {
        "ok": True,
        "total": int(total["n"] if total else 0),
        "capsules": [dict(r) for r in rows],
        "limit": limit,
        "offset": offset,
    }


def quorum_for_tip(
    tip_hash: str,
    *,
    window_sec: int = QUORUM_WINDOW_SEC,
) -> Dict[str, Any]:
    init_witness_db()
    tip = (tip_hash or "").strip().lower()
    if len(tip) != 64:
        return {
            "ok": False,
            "quorum_depth": 0,
            "required_quorum": REQUIRED_QUORUM,
            "status": "unknown",
        }
    # Latest capsule per mesh_key only — historical tips in the window must not
    # create a permanent multi-hash "split" as the chain advances.
    latest = latest_capsules_by_mesh(window_sec=window_sec)
    signers = [
        {
            "mesh_key": c.get("mesh_key"),
            "device_id": c.get("device_id"),
            "last_at": c.get("created_at"),
            "height": c.get("height"),
            "tip_hash": c.get("tip_hash"),
        }
        for c in latest
        if str(c.get("tip_hash") or "").strip().lower() == tip
    ]
    depth = len(signers)
    by_tip: Dict[str, Dict[str, Any]] = {}
    for c in latest:
        th = str(c.get("tip_hash") or "").strip().lower()
        if not th:
            continue
        bucket = by_tip.setdefault(
            th,
            {"tip_hash": th, "signers": 0, "height": int(c.get("height") or 0)},
        )
        bucket["signers"] += 1
        # Prefer the max height observed for this tip_hash cluster
        bucket["height"] = max(int(bucket.get("height") or 0), int(c.get("height") or 0))
    dominant = sorted(
        by_tip.values(),
        key=lambda r: (-int(r.get("signers") or 0), -int(r.get("height") or 0)),
    )[:5]
    split = False
    if len(dominant) >= 2:
        top = int(dominant[0].get("signers") or 0)
        second = int(dominant[1].get("signers") or 0)
        if second >= 2 and top <= second + 1:
            split = True
    # Also split when latest-per-mesh heights disagree (tip-height disagreement).
    if len(latest) >= 2:
        hc = Counter(int(c.get("height") or 0) for c in latest)
        qualifying = sum(
            1 for h, n in hc.items() if n >= HEIGHT_DISAGREE_MIN_SIGNERS and h > 0
        )
        if qualifying >= HEIGHT_DISAGREE_MIN_HEIGHTS:
            split = True
    if split:
        status = "split"
    elif depth >= REQUIRED_QUORUM:
        status = "live"
    elif depth > 0:
        status = "pending"
    else:
        status = "awaiting"
    return {
        "ok": True,
        "tip_hash": tip,
        "quorum_depth": depth,
        "required_quorum": REQUIRED_QUORUM,
        "signers": signers,
        "dominant_tips": dominant,
        "status": status,
        "window_sec": window_sec,
    }


def latest_capsules_by_mesh(
    *,
    window_sec: int = QUORUM_WINDOW_SEC,
) -> List[Dict[str, Any]]:
    """Most recent capsule per mesh_key inside the quorum window."""
    init_witness_db()
    cutoff = _now() - max(300, int(window_sec))
    with mesh_db._conn() as conn:
        rows = conn.execute(
            """
            SELECT c.mesh_key, c.device_id, c.tip_hash, c.height, c.node_mode,
                   c.peer_count, c.issued_at, c.created_at, c.capsule_id
            FROM quasar_witness_capsules c
            INNER JOIN (
                SELECT mesh_key, MAX(created_at) AS last_at
                FROM quasar_witness_capsules
                WHERE created_at >= ?
                GROUP BY mesh_key
            ) latest
              ON c.mesh_key = latest.mesh_key AND c.created_at = latest.last_at
            ORDER BY c.height DESC, c.created_at DESC
            """,
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


def _height_cluster_key(height: int, tip_hash: str) -> str:
    return f"{int(height)}:{str(tip_hash or '').strip().lower()}"


def detect_tip_height_disagreement(
    local_tip_hash: str = "",
    local_tip_height: int = 0,
    *,
    window_sec: int = QUORUM_WINDOW_SEC,
) -> Dict[str, Any]:
    """Detect multi-height (and multi-hash) disagreement among recent mesh witnesses."""
    local_hash = (local_tip_hash or "").strip().lower()
    local_h = int(local_tip_height or 0)
    latest = latest_capsules_by_mesh(window_sec=window_sec)
    clusters: Dict[str, Dict[str, Any]] = {}
    for cap in latest:
        h = int(cap.get("height") or 0)
        th = str(cap.get("tip_hash") or "").strip().lower()
        key = _height_cluster_key(h, th)
        bucket = clusters.setdefault(
            key,
            {
                "height": h,
                "tip_hash": th,
                "signers": 0,
                "mesh_keys": [],
                "device_ids": [],
            },
        )
        bucket["signers"] += 1
        mk = str(cap.get("mesh_key") or "")
        did = str(cap.get("device_id") or "")
        if mk and mk not in bucket["mesh_keys"]:
            bucket["mesh_keys"].append(mk)
        if did and did not in bucket["device_ids"]:
            bucket["device_ids"].append(did)

    heights = sorted(
        clusters.values(),
        key=lambda c: (-int(c.get("signers") or 0), -int(c.get("height") or 0)),
    )
    # Collapse pure height set (ignore hash) for spread
    by_height: Dict[int, int] = {}
    for c in heights:
        hh = int(c.get("height") or 0)
        by_height[hh] = by_height.get(hh, 0) + int(c.get("signers") or 0)
    distinct_heights = sorted(by_height.keys(), reverse=True)
    height_spread = (
        (max(distinct_heights) - min(distinct_heights)) if distinct_heights else 0
    )
    distinct_tip_hashes = sorted({str(c.get("tip_hash") or "") for c in heights if c.get("tip_hash")})
    total_signers = len(latest)

    qualifying_heights = [
        h for h, n in by_height.items() if n >= HEIGHT_DISAGREE_MIN_SIGNERS
    ]
    multi_height = len(qualifying_heights) >= HEIGHT_DISAGREE_MIN_HEIGHTS
    multi_hash_same_height = False
    if not multi_height and len(heights) >= 2:
        # same height, different tip hashes with competitive signers
        top = int(heights[0].get("signers") or 0)
        second = int(heights[1].get("signers") or 0)
        if (
            int(heights[0].get("height") or 0) == int(heights[1].get("height") or 0)
            and heights[0].get("tip_hash") != heights[1].get("tip_hash")
            and second >= 2
            and top <= second + 1
        ):
            multi_hash_same_height = True

    stale_vs_local = [
        c for c in heights if local_h and int(c.get("height") or 0) < local_h
    ]
    ahead_of_local = [
        c for c in heights if local_h and int(c.get("height") or 0) > local_h
    ]
    disagreement = bool(multi_height or multi_hash_same_height)
    # Local lag: mesh majority ahead of local by ≥1 with ≥2 signers also counts
    if not disagreement and ahead_of_local:
        top_ahead = ahead_of_local[0]
        if int(top_ahead.get("signers") or 0) >= 2 and int(top_ahead.get("height") or 0) >= local_h + 1:
            disagreement = True

    parts = [
        f"h={','.join(str(h) for h in distinct_heights[:8])}",
        f"th={','.join(t[:12] for t in distinct_tip_hashes[:6])}",
        f"local={local_h}:{local_hash[:12]}",
        f"n={total_signers}",
    ]
    fingerprint = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]

    reason = "aligned"
    if multi_height:
        reason = "multi_height"
    elif multi_hash_same_height:
        reason = "multi_hash_same_height"
    elif disagreement and ahead_of_local:
        reason = "mesh_ahead_of_local"

    return {
        "ok": True,
        "disagreement": disagreement,
        "reason": reason,
        "fingerprint": fingerprint,
        "local_tip_hash": local_hash,
        "local_tip_height": local_h,
        "window_sec": window_sec,
        "height_spread": height_spread,
        "distinct_heights": distinct_heights,
        "distinct_tip_hashes": distinct_tip_hashes,
        "total_signers": total_signers,
        "heights": heights[:12],
        "stale_vs_local": stale_vs_local[:8],
        "ahead_of_local": ahead_of_local[:8],
        "latest_capsules": latest[:24],
    }


def _persist_review_file(payload: Dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(AI_REVIEW_STATE_FILE) or "/var/lib/bloodstone", exist_ok=True)
        with open(AI_REVIEW_STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
    except OSError:
        pass


def store_tip_review(
    disagreement: Dict[str, Any],
    review: Dict[str, Any],
    *,
    operator_decision: str = "",
    operator_note: str = "",
) -> Dict[str, Any]:
    init_witness_db()
    now = _now()
    fp = str(disagreement.get("fingerprint") or "none")
    review_id = hashlib.sha256(
        f"{fp}:{now}:{json.dumps(review, sort_keys=True)}".encode("utf-8")
    ).hexdigest()[:40]
    row = {
        "review_id": review_id,
        "fingerprint": fp,
        "local_tip_hash": str(disagreement.get("local_tip_hash") or ""),
        "local_tip_height": int(disagreement.get("local_tip_height") or 0),
        "disagreement": disagreement,
        "review": review,
        "operator_decision": (operator_decision or "")[:64],
        "operator_note": (operator_note or "")[:500],
        "created_at": now,
        "updated_at": now,
    }
    with mesh_db._conn() as conn:
        conn.execute(
            """
            INSERT INTO quasar_witness_tip_reviews (
                review_id, fingerprint, local_tip_hash, local_tip_height,
                disagreement_json, review_json, operator_decision, operator_note,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["review_id"],
                row["fingerprint"],
                row["local_tip_hash"],
                row["local_tip_height"],
                json.dumps(disagreement, sort_keys=True),
                json.dumps(review, sort_keys=True),
                row["operator_decision"],
                row["operator_note"],
                now,
                now,
            ),
        )
    _persist_review_file(
        {
            "ok": True,
            "review_id": review_id,
            "fingerprint": fp,
            "disagreement": {
                "disagreement": disagreement.get("disagreement"),
                "reason": disagreement.get("reason"),
                "height_spread": disagreement.get("height_spread"),
                "distinct_heights": disagreement.get("distinct_heights"),
                "local_tip_height": disagreement.get("local_tip_height"),
                "local_tip_hash": disagreement.get("local_tip_hash"),
            },
            "review": review,
            "operator_decision": row["operator_decision"],
            "operator_note": row["operator_note"],
            "created_at": now,
            "updated_utc": _utc_now(),
        }
    )
    return row


def latest_tip_review(*, fingerprint: str = "") -> Optional[Dict[str, Any]]:
    init_witness_db()
    with mesh_db._conn() as conn:
        if fingerprint:
            row = conn.execute(
                """
                SELECT * FROM quasar_witness_tip_reviews
                WHERE fingerprint = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (fingerprint,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT * FROM quasar_witness_tip_reviews
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["disagreement"] = json.loads(d.pop("disagreement_json") or "{}")
    except Exception:
        d["disagreement"] = {}
        d.pop("disagreement_json", None)
    try:
        d["review"] = json.loads(d.pop("review_json") or "{}")
    except Exception:
        d["review"] = {}
        d.pop("review_json", None)
    return d


def record_operator_decision(
    review_id: str,
    decision: str,
    *,
    note: str = "",
) -> Dict[str, Any]:
    """Operator confirmation path after AI review (does not auto-clear consensus)."""
    init_witness_db()
    rid = (review_id or "").strip()
    decision_n = (decision or "").strip().lower()[:64]
    allowed = {
        "confirm_halt",
        "prefer_local",
        "prefer_mesh",
        "dismiss",
        "investigating",
    }
    if decision_n not in allowed:
        raise ValueError(f"decision must be one of {sorted(allowed)}")
    now = _now()
    with mesh_db._conn() as conn:
        cur = conn.execute(
            """
            UPDATE quasar_witness_tip_reviews
            SET operator_decision = ?, operator_note = ?, updated_at = ?
            WHERE review_id = ?
            """,
            (decision_n, (note or "")[:500], now, rid),
        )
        if cur.rowcount == 0:
            raise ValueError("unknown review_id")
        row = conn.execute(
            "SELECT * FROM quasar_witness_tip_reviews WHERE review_id = ?",
            (rid,),
        ).fetchone()
    out = dict(row) if row else {"review_id": rid, "operator_decision": decision_n}
    try:
        out["disagreement"] = json.loads(out.pop("disagreement_json") or "{}")
    except Exception:
        pass
    try:
        out["review"] = json.loads(out.pop("review_json") or "{}")
    except Exception:
        pass
    _persist_review_file(
        {
            "ok": True,
            "review_id": rid,
            "operator_decision": decision_n,
            "operator_note": (note or "")[:500],
            "review": out.get("review"),
            "updated_utc": _utc_now(),
        }
    )
    return {"ok": True, "review": out}


def ensure_tip_height_ai_review(
    local_tip_hash: str,
    local_tip_height: int,
    *,
    force: bool = False,
    window_sec: int = QUORUM_WINDOW_SEC,
) -> Dict[str, Any]:
    """Detect tip-height disagreement and run/cache SpaceXAI (or heuristic) review."""
    disagreement = detect_tip_height_disagreement(
        local_tip_hash,
        local_tip_height,
        window_sec=window_sec,
    )
    fp = str(disagreement.get("fingerprint") or "")
    existing = latest_tip_review(fingerprint=fp) if fp else latest_tip_review()
    now = _now()
    if (
        not force
        and existing
        and str(existing.get("fingerprint") or "") == fp
        and (now - int(existing.get("created_at") or 0)) < AI_REVIEW_COOLDOWN_SEC
    ):
        return {
            "ok": True,
            "cached": True,
            "disagreement": disagreement,
            "review": existing.get("review") or {},
            "review_id": existing.get("review_id"),
            "operator_decision": existing.get("operator_decision") or "",
            "operator_note": existing.get("operator_note") or "",
            "created_at": existing.get("created_at"),
        }

    if not disagreement.get("disagreement") and not force:
        return {
            "ok": True,
            "cached": False,
            "disagreement": disagreement,
            "review": {
                "ok": True,
                "reviewer": "none",
                "skipped": True,
                "action": "monitor",
                "severity": "low",
                "rationale": "No tip-height disagreement among recent mesh witnesses.",
                "confidence": 1.0,
            },
            "review_id": None,
            "operator_decision": "",
            "operator_note": "",
        }

    try:
        from bloodstone_witness_ai import review_tip_disagreement
    except Exception:
        review_tip_disagreement = None  # type: ignore

    if review_tip_disagreement is None:
        review = {
            "ok": False,
            "reviewer": "none",
            "action": "keep_halt",
            "severity": "high",
            "confidence": 0.0,
            "rationale": "bloodstone_witness_ai module unavailable",
            "factors": ["import_error"],
            "prefer": "none",
        }
    else:
        review = review_tip_disagreement(disagreement)

    stored = store_tip_review(disagreement, review)
    return {
        "ok": True,
        "cached": False,
        "disagreement": disagreement,
        "review": review,
        "review_id": stored.get("review_id"),
        "operator_decision": stored.get("operator_decision") or "",
        "operator_note": stored.get("operator_note") or "",
        "created_at": stored.get("created_at"),
    }


def witness_status_payload(
    tip_hash: str,
    tip_height: int,
    *,
    run_ai_review: bool = True,
) -> Dict[str, Any]:
    quorum = quorum_for_tip(tip_hash)
    capsules = list_capsules(tip_hash=tip_hash, limit=10)
    anchors = 0
    try:
        from chain_mesh.anchor_index import ensure_fresh, list_anchors

        ensure_fresh()
        anchors = int(list_anchors(limit=1).get("total") or 0)
    except Exception:
        anchors = 0

    tip_review: Dict[str, Any] = {}
    height_disagreement: Dict[str, Any] = {}
    try:
        if run_ai_review:
            tip_review = ensure_tip_height_ai_review(tip_hash, tip_height)
        else:
            height_disagreement = detect_tip_height_disagreement(tip_hash, tip_height)
            tip_review = {
                "ok": True,
                "disagreement": height_disagreement,
                "review": latest_tip_review() or {},
            }
    except Exception as exc:
        tip_review = {
            "ok": False,
            "error": str(exc)[:300],
            "disagreement": detect_tip_height_disagreement(tip_hash, tip_height),
        }

    disagreement = tip_review.get("disagreement") or {}
    review = tip_review.get("review") or {}
    status = str(quorum.get("status", "awaiting"))
    if disagreement.get("disagreement"):
        # Height disagreement is treated as a split for spend/deposit policy.
        status = "split"

    return {
        "phase": 2,
        "status": status,
        "quorum_depth": int(quorum.get("quorum_depth") or 0),
        "required_quorum": REQUIRED_QUORUM,
        "tip_hash": tip_hash,
        "tip_height": tip_height,
        "recent_capsules": capsules.get("capsules") or [],
        "dominant_tips": quorum.get("dominant_tips") or [],
        "mesh_anchors_indexed": anchors,
        "capsule_schema": CAPSULE_TYPE,
        "submit_url": "/api/quasar/witness/submit",
        "tip_height_disagreement": {
            "active": bool(disagreement.get("disagreement")),
            "reason": disagreement.get("reason"),
            "height_spread": disagreement.get("height_spread"),
            "distinct_heights": disagreement.get("distinct_heights") or [],
            "distinct_tip_hashes": disagreement.get("distinct_tip_hashes") or [],
            "total_signers": disagreement.get("total_signers") or 0,
            "heights": disagreement.get("heights") or [],
            "fingerprint": disagreement.get("fingerprint"),
        },
        "ai_review": {
            "review_id": tip_review.get("review_id"),
            "cached": bool(tip_review.get("cached")),
            "reviewer": review.get("reviewer"),
            "model": review.get("model"),
            "action": review.get("action"),
            "severity": review.get("severity"),
            "confidence": review.get("confidence"),
            "prefer": review.get("prefer"),
            "recommended_height": review.get("recommended_height"),
            "recommended_tip_hash": review.get("recommended_tip_hash"),
            "rationale": review.get("rationale"),
            "factors": review.get("factors") or [],
            "fallback": review.get("fallback"),
            "ai_error": review.get("ai_error"),
            "operator_decision": tip_review.get("operator_decision") or "",
            "operator_note": tip_review.get("operator_note") or "",
            "created_at": tip_review.get("created_at"),
            "review_url": "/api/quasar/witness/tip-review",
            "full_ai_review_enabled": _full_ai_review_enabled_flag(),
        },
    }


def _full_ai_review_enabled_flag() -> bool:
    try:
        import quasar_ai_settings as qas

        return bool(qas.full_ai_review_enabled())
    except Exception:
        return os.environ.get("QUASAR_WITNESS_AI_ENABLE", "1").strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )