"""Wave H — DTN gossip protocol for peer + bundle rumor exchange beyond mDNS."""

from __future__ import annotations

from chain_mesh.security import public_error
import hashlib
import os
import random
import time
from typing import Any, Dict, List, Optional

from chain_mesh import db as mesh_db

GOSSIP_FORMAT = "bloodstone_dtn_gossip/v1"
GOSSIP_ENABLE = os.environ.get("DTN_GOSSIP_ENABLE", "1").strip() not in ("0", "false", "no")
GOSSIP_MAX_PEERS_PER_ROUND = max(1, int(os.environ.get("DTN_GOSSIP_PEERS_PER_ROUND", "5")))
GOSSIP_MAX_RUMORS = max(5, int(os.environ.get("DTN_GOSSIP_MAX_RUMORS", "30")))
GOSSIP_MAX_HOPS = max(1, int(os.environ.get("DTN_GOSSIP_MAX_HOPS", "6")))
GOSSIP_RUMOR_TTL_SEC = max(300, int(os.environ.get("DTN_GOSSIP_RUMOR_TTL_SEC", "3600")))
GOSSIP_BUNDLE_HINTS = max(0, int(os.environ.get("DTN_GOSSIP_BUNDLE_HINTS", "12")))
GOSSIP_TIMEOUT_SEC = max(5, int(os.environ.get("DTN_GOSSIP_TIMEOUT_SEC", "25")))

_LAST_ROUND: Dict[str, Any] = {}


def _now() -> int:
    return int(time.time())


def _conn():
    mesh_db.init_db()
    return mesh_db._conn()


def _node_id() -> str:
    return (os.environ.get("DTN_NODE_ID") or "pi-edge").strip()[:64]


def _region() -> str:
    return (os.environ.get("DTN_DEFAULT_REGION", "global") or "global").strip()[:32]


def _self_base_url() -> str:
    explicit = (os.environ.get("DTN_GOSSIP_SELF_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    from chain_mesh import dtn_tls as tls
    from chain_mesh import mdns_discovery as mdns

    host = mdns._lan_ip()
    use_tls = tls.DTN_TLS_PEER
    return tls.peer_url(host, tls.DTN_LAN_WEB_PORT, tls=use_tls)


def _peer_record(
    *,
    node_id: str,
    base_url: str,
    region: str = "",
    tls: Optional[bool] = None,
    tls_port: Optional[int] = None,
    hop: int = 0,
    seen_at: Optional[int] = None,
) -> Dict[str, Any]:
    from chain_mesh import dtn_tls as tls_mod

    url = tls_mod.normalize_peer_base_url(
        base_url,
        tls_hint=tls,
        tls_port=tls_port,
    )
    return {
        "node_id": (node_id or url).strip()[:64],
        "base_url": url,
        "region": (region or _region()).strip()[:32],
        "tls": bool(tls if tls is not None else tls_mod.DTN_TLS_PEER),
        "tls_port": int(tls_port if tls_port is not None else tls_mod.DTN_LAN_TLS_PORT),
        "hop": max(0, int(hop)),
        "seen_at": int(seen_at if seen_at is not None else _now()),
    }


def build_exchange_payload() -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    dtn.init_dtn_db()
    self_url = _self_base_url()
    peers_out: List[Dict[str, Any]] = []
    if self_url:
        peers_out.append(
            _peer_record(
                node_id=_node_id(),
                base_url=self_url,
                region=_region(),
                hop=0,
            )
        )

    peer_rows = (dtn.list_dtn_peers(limit=GOSSIP_MAX_RUMORS).get("peers") or [])
    for row in peer_rows:
        url = str(row.get("base_url") or "").strip()
        if not url or url == self_url:
            continue
        peers_out.append(
            _peer_record(
                node_id=str(row.get("node_id") or ""),
                base_url=url,
                region=str(row.get("region") or ""),
                hop=1,
                seen_at=int(row.get("last_seen") or _now()),
            )
        )
        if len(peers_out) >= GOSSIP_MAX_RUMORS:
            break

    bundle_hints = _recent_bundle_hints()
    quorum_snapshots: List[Dict[str, Any]] = []
    try:
        from chain_mesh import planetary_quorum as planetary

        if planetary.PLANETARY_ENABLE:
            snap = planetary.build_quorum_snapshot()
            if snap:
                quorum_snapshots.append(snap)
    except Exception:
        pass

    ai_provider_snapshots: List[Dict[str, Any]] = []
    try:
        from chain_mesh import ai_routing as ai

        if ai.AI_ROUTING_ENABLE:
            ai_provider_snapshots = ai.build_gossip_snapshots()
    except Exception:
        pass

    tenant_snapshots: List[Dict[str, Any]] = []
    try:
        from chain_mesh import tenant_fleet_sync as tfleet

        tenant_snapshots = tfleet.collect_tenant_snapshots(limit=20)
    except Exception:
        pass

    tenant_quorum_snapshots: List[Dict[str, Any]] = []
    try:
        from chain_mesh import tenant_fleet_quorum as tquorum

        snap = tquorum.build_quorum_snapshot()
        if snap:
            tenant_quorum_snapshots.append(snap)
    except Exception:
        pass

    tenant_manifest_snapshots: List[Dict[str, Any]] = []
    try:
        from chain_mesh import tenant_manifest_gossip as tmgossip

        tenant_manifest_snapshots = tmgossip.build_manifest_snapshots()
    except Exception:
        pass

    tenant_route_snapshots: List[Dict[str, Any]] = []
    try:
        from chain_mesh import tenant_route_ledger as tledger

        tenant_route_snapshots = tledger.build_route_gossip_snapshots()
    except Exception:
        pass

    tenant_planetary_snapshots: List[Dict[str, Any]] = []
    try:
        from chain_mesh import tenant_planetary_quorum as tplanetary

        if tplanetary.TENANT_PLANETARY_ENABLE:
            tenant_planetary_snapshots = tplanetary.build_planetary_gossip_snapshots()
    except Exception:
        pass

    return {
        "ok": True,
        "format": GOSSIP_FORMAT,
        "node_id": _node_id(),
        "region": _region(),
        "self": peers_out[0] if peers_out else _peer_record(node_id=_node_id(), base_url=self_url or ""),
        "peers": peers_out,
        "bundle_hints": bundle_hints,
        "quorum_snapshots": quorum_snapshots,
        "ai_provider_snapshots": ai_provider_snapshots,
        "tenant_snapshots": tenant_snapshots,
        "tenant_quorum_snapshots": tenant_quorum_snapshots,
        "tenant_manifest_snapshots": tenant_manifest_snapshots,
        "tenant_route_snapshots": tenant_route_snapshots,
        "tenant_planetary_snapshots": tenant_planetary_snapshots,
        "max_hops": GOSSIP_MAX_HOPS,
        "rumor_ttl_sec": GOSSIP_RUMOR_TTL_SEC,
    }


def _recent_bundle_hints() -> List[Dict[str, Any]]:
    if GOSSIP_BUNDLE_HINTS <= 0:
        return []
    cutoff = _now() - GOSSIP_RUMOR_TTL_SEC
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT bundle_sha256, bundle_id, last_seen_at
            FROM dtn_seen_bundles
            WHERE last_seen_at >= ?
            ORDER BY last_seen_at DESC
            LIMIT ?
            """,
            (cutoff, GOSSIP_BUNDLE_HINTS),
        ).fetchall()
    return [
        {
            "sha256": str(r["bundle_sha256"]),
            "bundle_id": str(r["bundle_id"] or ""),
            "node_id": _node_id(),
            "seen_at": int(r["last_seen_at"]),
        }
        for r in rows
        if str(r["bundle_sha256"] or "").strip()
    ]


def ingest_exchange_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn

    if str(payload.get("format") or "") != GOSSIP_FORMAT:
        raise ValueError(f"unsupported gossip format (expected {GOSSIP_FORMAT})")

    dtn.init_dtn_db()
    now = _now()
    cutoff = now - GOSSIP_RUMOR_TTL_SEC
    peers_registered = 0
    peers_skipped = 0
    bundle_hints_recorded = 0
    source_node = str(payload.get("node_id") or "").strip()[:64]

    items: List[Dict[str, Any]] = []
    self_row = payload.get("self")
    if isinstance(self_row, dict):
        items.append(self_row)
    for row in payload.get("peers") or []:
        if isinstance(row, dict):
            items.append(row)

    for row in items:
        hop = int(row.get("hop") or 0)
        if hop > GOSSIP_MAX_HOPS:
            peers_skipped += 1
            continue
        seen_at = int(row.get("seen_at") or now)
        if seen_at < cutoff:
            peers_skipped += 1
            continue
        base_url = str(row.get("base_url") or "").strip()
        if not base_url:
            peers_skipped += 1
            continue
        try:
            dtn.register_dtn_peer(
                base_url=base_url,
                node_id=str(row.get("node_id") or ""),
                region=str(row.get("region") or ""),
                source="gossip",
                tls_hint=row.get("tls"),
                tls_port=int(row["tls_port"]) if row.get("tls_port") is not None else None,
            )
            peers_registered += 1
        except ValueError:
            peers_skipped += 1

    for hint in payload.get("bundle_hints") or []:
        if not isinstance(hint, dict):
            continue
        sha = str(hint.get("sha256") or "").strip().lower()
        if len(sha) != 64:
            continue
        seen_at = int(hint.get("seen_at") or now)
        if seen_at < cutoff:
            continue
        bundle_id = str(hint.get("bundle_id") or "")
        with _conn() as conn:
            conn.execute(
                """
                INSERT INTO dtn_seen_bundles (
                    bundle_sha256, bundle_id, first_seen_at, last_seen_at, import_count
                ) VALUES (?, ?, ?, ?, 0)
                ON CONFLICT(bundle_sha256) DO UPDATE SET
                    bundle_id = CASE WHEN excluded.bundle_id != '' THEN excluded.bundle_id ELSE bundle_id END,
                    last_seen_at = MAX(last_seen_at, excluded.last_seen_at)
                """,
                (sha, bundle_id, seen_at, seen_at),
            )
        bundle_hints_recorded += 1

    quorum_votes = 0
    try:
        from chain_mesh import planetary_quorum as planetary

        if planetary.PLANETARY_ENABLE:
            snaps = [
                row
                for row in (payload.get("quorum_snapshots") or [])
                if isinstance(row, dict)
            ]
            ingest_q = planetary.ingest_quorum_snapshots(snaps)
            quorum_votes = int(ingest_q.get("votes_recorded") or 0)
    except Exception:
        pass

    ai_votes = 0
    try:
        from chain_mesh import ai_routing as ai

        if ai.AI_ROUTING_ENABLE:
            snaps = [
                row
                for row in (payload.get("ai_provider_snapshots") or [])
                if isinstance(row, dict)
            ]
            ingest_a = ai.ingest_gossip_snapshots(snaps)
            ai_votes = int(ingest_a.get("recorded") or 0)
    except Exception:
        pass

    tenant_votes = 0
    tenant_quorum_votes = 0
    tenant_manifest_indexed = 0
    tenant_route_recorded = 0
    tenant_planetary_votes = 0
    try:
        from chain_mesh import tenant_fleet_quorum as tquorum

        snaps = [
            row for row in (payload.get("tenant_snapshots") or []) if isinstance(row, dict)
        ]
        ingest_t = tquorum.ingest_with_quorum(
            snaps, reporter_node_id=str(payload.get("node_id") or "")
        )
        if tquorum.QUORUM_ENFORCE:
            tenant_votes = int((ingest_t.get("applied") or {}).get("applied") or 0)
        else:
            tenant_votes = int((ingest_t.get("ingest") or {}).get("recorded") or 0)
        quorum_snaps = [
            row
            for row in (payload.get("tenant_quorum_snapshots") or [])
            if isinstance(row, dict)
        ]
        ingest_q = tquorum.ingest_quorum_snapshots(quorum_snaps)
        tenant_quorum_votes = int(ingest_q.get("votes_recorded") or 0)
        try:
            from chain_mesh import tenant_manifest_gossip as tmgossip

            manifest_snaps = [
                row
                for row in (payload.get("tenant_manifest_snapshots") or [])
                if isinstance(row, dict)
            ]
            ingest_m = tmgossip.ingest_manifest_snapshots(manifest_snaps)
            tenant_manifest_indexed = int(ingest_m.get("indexed") or 0)
        except Exception:
            pass
        try:
            from chain_mesh import tenant_route_ledger as tledger

            route_snaps = [
                row
                for row in (payload.get("tenant_route_snapshots") or [])
                if isinstance(row, dict)
            ]
            ingest_r = tledger.ingest_route_snapshots(route_snaps)
            tenant_route_recorded = int(ingest_r.get("recorded") or 0)
        except Exception:
            pass
        try:
            from chain_mesh import tenant_planetary_quorum as tplanetary

            if tplanetary.TENANT_PLANETARY_ENABLE:
                planetary_snaps = [
                    row
                    for row in (payload.get("tenant_planetary_snapshots") or [])
                    if isinstance(row, dict)
                ]
                ingest_p = tplanetary.ingest_planetary_snapshots(planetary_snaps)
                tenant_planetary_votes = int(ingest_p.get("votes_recorded") or 0)
        except Exception:
            pass
    except Exception:
        pass

    return {
        "ok": True,
        "format": GOSSIP_FORMAT,
        "from_node": source_node,
        "peers_registered": peers_registered,
        "peers_skipped": peers_skipped,
        "bundle_hints_recorded": bundle_hints_recorded,
        "quorum_votes_recorded": quorum_votes,
        "ai_providers_recorded": ai_votes,
        "tenant_bindings_recorded": tenant_votes,
        "tenant_quorum_votes_recorded": tenant_quorum_votes,
        "tenant_manifests_indexed": tenant_manifest_indexed,
        "tenant_routes_recorded": tenant_route_recorded,
        "tenant_planetary_votes_recorded": tenant_planetary_votes,
        "reply": build_exchange_payload(),
    }


def gossip_round(*, limit: int = 0) -> Dict[str, Any]:
    from chain_mesh import dtn_sync as dtn
    from chain_mesh import dtn_tls as tls

    if not GOSSIP_ENABLE:
        return {"ok": True, "skipped": True, "reason": "DTN_GOSSIP_ENABLE off"}

    dtn.init_dtn_db()
    n = max(1, int(limit or GOSSIP_MAX_PEERS_PER_ROUND))
    peers = (dtn.list_dtn_peers(limit=50).get("peers") or [])
    self_url = _self_base_url()
    candidates = [
        str(p.get("base_url") or "").rstrip("/")
        for p in peers
        if str(p.get("base_url") or "").strip()
        and str(p.get("base_url") or "").rstrip("/") != self_url
        and str(p.get("source") or "") != "gossip-stale"
    ]
    if not candidates:
        result = {
            "ok": True,
            "skipped": True,
            "reason": "no gossip peers available",
            "exchanged": 0,
        }
        _LAST_ROUND.clear()
        _LAST_ROUND.update(result)
        return result

    random.shuffle(candidates)
    targets = candidates[:n]
    outbound = build_exchange_payload()
    exchanged = 0
    registered = 0
    bundle_hints = 0
    errors: List[Dict[str, Any]] = []

    for base in targets:
        url = f"{base.rstrip('/')}/api/convergence/dtn/gossip/exchange"
        try:
            resp = tls.post_json(url, outbound, timeout=GOSSIP_TIMEOUT_SEC)
            if resp.status_code >= 400:
                errors.append({"peer": base, "error": f"HTTP {resp.status_code}"})
                continue
            body = resp.json()
            if not body.get("ok"):
                errors.append({"peer": base, "error": str(body.get("error") or "exchange failed")})
                continue
            ingest = ingest_exchange_payload(body)
            exchanged += 1
            registered += int(ingest.get("peers_registered") or 0)
            bundle_hints += int(ingest.get("bundle_hints_recorded") or 0)
        except Exception as exc:
            errors.append({"peer": base, "error": public_error(exc)})

    result = {
        "ok": True,
        "exchanged": exchanged,
        "targets": len(targets),
        "peers_registered": registered,
        "bundle_hints_recorded": bundle_hints,
        "errors": errors[:5],
    }
    _LAST_ROUND.clear()
    _LAST_ROUND.update(result)
    return result


def status_payload() -> Dict[str, Any]:
    public = os.environ.get("BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org").rstrip("/")
    return {
        "ok": True,
        "format": GOSSIP_FORMAT,
        "enabled": GOSSIP_ENABLE,
        "node_id": _node_id(),
        "region": _region(),
        "self_url": _self_base_url() or None,
        "max_peers_per_round": GOSSIP_MAX_PEERS_PER_ROUND,
        "max_rumors": GOSSIP_MAX_RUMORS,
        "max_hops": GOSSIP_MAX_HOPS,
        "rumor_ttl_sec": GOSSIP_RUMOR_TTL_SEC,
        "bundle_hints": GOSSIP_BUNDLE_HINTS,
        "last_round": dict(_LAST_ROUND),
        "apis": {
            "exchange": f"{public}/api/convergence/dtn/gossip/exchange",
            "round": f"{public}/api/convergence/dtn/gossip/round",
            "status": f"{public}/api/convergence/dtn/gossip/status",
        },
    }