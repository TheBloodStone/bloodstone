"""Wave O — HMAC-signed AI provider gossip snapshots."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

AI_GOSSIP_SNAPSHOT_FORMAT = "bloodstone_ai_gossip_snapshot/v1"
AI_GOSSIP_MAX_AGE_SEC = max(60, int(os.environ.get("AI_GOSSIP_MAX_AGE_SEC", "600")))


def _env_flag(name: str, *, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() not in ("0", "false", "no")


def _sign_enable() -> bool:
    return _env_flag("AI_GOSSIP_SIGN_ENABLE")


def _verify_enable() -> bool:
    return _env_flag("AI_GOSSIP_VERIFY")


def _explicit_signing_key() -> Optional[bytes]:
    explicit = (os.environ.get("AI_GOSSIP_SIGNING_KEY") or "").strip()
    if explicit:
        return explicit.encode("utf-8")
    path = (os.environ.get("AI_GOSSIP_SIGNING_KEY_FILE") or "").strip()
    if path and os.path.isfile(path):
        with open(path, "rb") as fh:
            return fh.read().strip()
    return None


def _fleet_key_configured() -> bool:
    return _explicit_signing_key() is not None


def _require_fleet_key() -> bool:
    if os.environ.get("AI_GOSSIP_REQUIRE_FLEET_KEY", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return True
    if _fleet_key_configured() and os.environ.get("AI_GOSSIP_ALLOW_UNSIGNED") is None:
        return True
    return False


def _allow_unsigned() -> bool:
    if _require_fleet_key():
        return _env_flag("AI_GOSSIP_ALLOW_UNSIGNED", default="0")
    return _env_flag("AI_GOSSIP_ALLOW_UNSIGNED", default="1")


def _now() -> int:
    return int(time.time())


def _node_id() -> str:
    return (os.environ.get("DTN_NODE_ID") or "pi-edge").strip()[:64]


def _signing_key() -> bytes:
    key = _explicit_signing_key()
    if key:
        return key
    # Beta fallback — per-node derived secret (operators should set AI_GOSSIP_SIGNING_KEY)
    seed = f"{_node_id()}:bloodstone-ai-gossip:v1"
    return hashlib.sha256(seed.encode("utf-8")).digest()


def canonical_snapshot_bytes(snapshot: Dict[str, Any]) -> bytes:
    body = {
        k: v
        for k, v in snapshot.items()
        if k not in ("signature", "signer_node_id", "signed_at", "format")
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_snapshot(snapshot: Dict[str, Any], *, signer_node_id: str = "") -> Dict[str, Any]:
    signer = (signer_node_id or snapshot.get("node_id") or _node_id()).strip()[:64]
    body = dict(snapshot)
    body["signer_node_id"] = signer
    body["signed_at"] = int(body.get("signed_at") or _now())
    body["format"] = AI_GOSSIP_SNAPSHOT_FORMAT
    if _sign_enable():
        digest = hmac.new(_signing_key(), canonical_snapshot_bytes(body), hashlib.sha256).hexdigest()
        body["signature"] = digest
    return body


def verify_snapshot(snapshot: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(snapshot, dict):
        return False, "snapshot must be object"
    if not _verify_enable():
        return True, "verify disabled"
    if _require_fleet_key() and not _fleet_key_configured():
        return False, "fleet signing key not configured on node"

    signature = str(snapshot.get("signature") or "").strip().lower()
    if not signature:
        if _allow_unsigned():
            return True, "unsigned allowed"
        return False, "missing signature"

    signer = str(snapshot.get("signer_node_id") or snapshot.get("node_id") or "").strip()
    if not signer:
        return False, "missing signer_node_id"

    provider_id = str(snapshot.get("provider_id") or "").strip()
    if provider_id:
        allowed = {f"{signer}-ai", signer}
        if provider_id not in allowed and not provider_id.startswith(f"{signer}-"):
            return False, "provider_id does not match signer node"

    signed_at = int(snapshot.get("signed_at") or snapshot.get("last_seen") or 0)
    if signed_at > 0 and (_now() - signed_at) > AI_GOSSIP_MAX_AGE_SEC:
        return False, "snapshot too old"

    expected = hmac.new(_signing_key(), canonical_snapshot_bytes(snapshot), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False, "invalid signature"
    return True, "ok"


def sign_snapshots(snapshots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [sign_snapshot(s) for s in snapshots if isinstance(s, dict)]


def filter_verified_snapshots(
    snapshots: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    for snap in snapshots or []:
        if not isinstance(snap, dict):
            rejected.append({"snapshot": snap, "reason": "not object"})
            continue
        ok, reason = verify_snapshot(snap)
        if ok:
            accepted.append(snap)
        else:
            rejected.append({"provider_id": snap.get("provider_id"), "reason": reason})
    return accepted, rejected


def status_payload() -> Dict[str, Any]:
    return {
        "ok": True,
        "format": AI_GOSSIP_SNAPSHOT_FORMAT,
        "sign_enable": _sign_enable(),
        "verify": _verify_enable(),
        "allow_unsigned": _allow_unsigned(),
        "fleet_key_configured": _fleet_key_configured(),
        "require_fleet_key": _require_fleet_key(),
        "enforcement_mode": (
            "fleet_strict"
            if _require_fleet_key() and not _allow_unsigned()
            else "beta_permissive"
        ),
        "max_age_sec": AI_GOSSIP_MAX_AGE_SEC,
        "node_id": _node_id(),
    }