"""Partner publish helpers (e.g. Blurt bulk tenant) — token auth, namespaced keys."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from chain_mesh.config import PUBLISH_TOKEN

BLURT_PARTNER_KEY_PREFIX = "assets/blurt/"
RENTAL_KEY_PREFIX = "assets/rental/"


def verify_partner_publish_token(payload: Dict[str, Any]) -> None:
    token = str(payload.get("publish_token") or "").strip()
    if not PUBLISH_TOKEN or token != PUBLISH_TOKEN:
        raise PermissionError("invalid publish token")


def require_blurt_partner_asset_key(asset_key: str) -> str:
    from chain_mesh.assets import normalize_asset_key

    key = normalize_asset_key(asset_key)
    if not key.startswith(BLURT_PARTNER_KEY_PREFIX):
        raise PermissionError(
            f"partner publish restricted to keys under {BLURT_PARTNER_KEY_PREFIX}"
        )
    return key


def verify_rental_publish(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate renter token and return the active rental order."""
    import pool_hashrate_rental as phr

    order_id = str(
        payload.get("rental_order_id") or payload.get("order_id") or ""
    ).strip()
    token = str(
        payload.get("renter_token")
        or payload.get("rental_token")
        or payload.get("publish_token")
        or ""
    ).strip()
    return phr.verify_renter_token(order_id, token)


def require_rental_asset_key(asset_key: str, order: Dict[str, Any]) -> str:
    from chain_mesh.assets import normalize_asset_key

    key = normalize_asset_key(asset_key)
    prefix = str(order.get("mesh_key_prefix") or "").strip()
    if not prefix.endswith("/"):
        prefix += "/"
    if not key.startswith(prefix):
        raise PermissionError(
            f"rental publish restricted to keys under {prefix}"
        )
    return key


def rental_auth_from_payload(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """Return (order, normalized asset_key) after rental token + key checks."""
    order = verify_rental_publish(payload)
    asset_key = require_rental_asset_key(
        str(payload.get("asset_key") or ""), order
    )
    return order, asset_key