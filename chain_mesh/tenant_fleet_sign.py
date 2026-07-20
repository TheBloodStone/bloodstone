"""Wave U — HMAC-signed tenant fleet snapshots (gossip + DTN)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

TENANT_SNAPSHOT_FORMAT = "bloodstone_tenant_snapshot/v1"
TENANT_SNAPSHOT_MAX_AGE_SEC = max(60, int(os.environ.get("TENANT_SNAPSHOT_MAX_AGE_SEC", "3600")))


def _env_flag(name: str, *, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() not in ("0", "false", "no")


def _sign_enable() -> bool:
    return _env_flag("TENANT_SNAPSHOT_SIGN_ENABLE", default=os.environ.get("AI_GOSSIP_SIGN_ENABLE", "1"))


def _verify_enable() -> bool:
    return _env_flag("TENANT_SNAPSHOT_VERIFY", default=os.environ.get("AI_GOSSIP_VERIFY", "1"))


def _explicit_signing_key() -> Optional[bytes]:
    explicit = (os.environ.get("TENANT_SNAPSHOT_SIGNING_KEY") or "").strip()
    if explicit:
        return explicit.encode("utf-8")
    path = (os.environ.get("TENANT_SNAPSHOT_SIGNING_KEY_FILE") or "").strip()
    if path and os.path.isfile(path):
        with open(path, "rb") as fh:
            return fh.read().strip()
    ag = (os.environ.get("AI_GOSSIP_SIGNING_KEY") or "").strip()
    if ag:
        return ag.encode("utf-8")
    ap = (os.environ.get("AI_GOSSIP_SIGNING_KEY_FILE") or "").strip()
    if ap and os.path.isfile(ap):
        with open(ap, "rb") as fh:
            return fh.read().strip()
    return None


def _fleet_key_configured() -> bool:
    return _explicit_signing_key() is not None


def _require_fleet_key() -> bool:
    if os.environ.get("TENANT_SNAPSHOT_REQUIRE_FLEET_KEY", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return True
    if _fleet_key_configured() and os.environ.get("TENANT_SNAPSHOT_ALLOW_UNSIGNED") is None:
        return True
    return False


def _allow_unsigned() -> bool:
    if _require_fleet_key():
        return _env_flag("TENANT_SNAPSHOT_ALLOW_UNSIGNED", default="0")
    return _env_flag("TENANT_SNAPSHOT_ALLOW_UNSIGNED", default="1")


def _node_id() -> str:
    return (os.environ.get("DTN_NODE_ID") or "pi-edge").strip()[:64]


def _signing_key() -> bytes:
    key = _explicit_signing_key()
    if key:
        return key
    seed = f"{_node_id()}:bloodstone-tenant-snapshot:v1"
    return hashlib.sha256(seed.encode("utf-8")).digest()


def _now() -> int:
    return int(time.time())


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
    body["signed_at"] = int(body.get("signed_at") or body.get("updated_at") or _now())
    body["format"] = TENANT_SNAPSHOT_FORMAT
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

    signed_at = int(snapshot.get("signed_at") or snapshot.get("updated_at") or 0)
    if signed_at > 0 and (_now() - signed_at) > TENANT_SNAPSHOT_MAX_AGE_SEC:
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
            rejected.append({"blurt_account": snap.get("blurt_account"), "reason": reason})
    return accepted, rejected


def status_payload() -> Dict[str, Any]:
    return {
        "ok": True,
        "format": TENANT_SNAPSHOT_FORMAT,
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
        "max_age_sec": TENANT_SNAPSHOT_MAX_AGE_SEC,
        "node_id": _node_id(),
    }