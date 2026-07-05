"""Shared Bloodstone coin icon for site headers (admin upload)."""

from __future__ import annotations

import os
from typing import Dict, Optional

BRANDING_DIR = os.environ.get(
    "BLOODSTONE_INSTALLER_BRANDING_DIR", "/var/www/bloodstone/branding"
)
ICON_PNG_NAME = "installer-icon.png"


def _icon_path() -> str:
    return os.path.join(BRANDING_DIR, ICON_PNG_NAME)


def coin_icon_configured() -> bool:
    return os.path.isfile(_icon_path())


def _normalize_public_root(public_root: str = "") -> str:
    root = (public_root or os.environ.get("BLOODSTONE_PUBLIC_ROOT", "")).strip().rstrip(
        "/"
    )
    for suffix in ("/mining", "/wallet", "/explorer", "/faucet", "/dex", "/support"):
        if root.endswith(suffix):
            root = root[: -len(suffix)]
            break
    return root


def coin_icon_url(public_root: str = "") -> Optional[str]:
    if not coin_icon_configured():
        return None
    root = _normalize_public_root(public_root)
    path = f"/branding/{ICON_PNG_NAME}"
    return f"{root}{path}" if root else path


def header_brand_context(
    public_root: str = "", fallback_icon: str = "💎"
) -> Dict[str, Optional[str]]:
    url = coin_icon_url(public_root)
    if url:
        url = f"{url}?v={int(os.path.getmtime(_icon_path()))}"
    return {
        "coin_icon_url": url,
        "brand_fallback_icon": fallback_icon,
    }