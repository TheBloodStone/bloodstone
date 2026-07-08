"""Wallet OAuth settings (Discord / X) stored in the wallet referrals DB."""

from __future__ import annotations

import os
import sys
from typing import Any, Dict

_WALLET_WEB = os.environ.get(
    "BLOODSTONE_WALLET_WEB_DIR", "/root/bloodstone-wallet-web"
)
if _WALLET_WEB not in sys.path:
    sys.path.insert(0, _WALLET_WEB)

import referral_db  # noqa: E402
import x_oauth  # noqa: E402

X_SETTING_KEYS = ("x_client_id", "x_client_secret", "x_redirect_uri")


def wallet_public_base() -> str:
    public_root = os.environ.get(
        "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
    ).rstrip("/")
    return f"{public_root}/wallet"


def load_x_settings() -> Dict[str, str]:
    referral_db.init_db()
    settings = referral_db.all_settings()
    return {key: settings.get(key, "") for key in X_SETTING_KEYS}


def save_x_settings(form: Dict[str, str]) -> None:
    referral_db.init_db()
    for key in X_SETTING_KEYS:
        val = (form.get(key) or "").strip()
        if key.endswith("_secret") and not val:
            continue
        referral_db.set_setting(key, val)


def x_admin_context() -> Dict[str, Any]:
    settings = load_x_settings()
    base = wallet_public_base()
    probe = x_oauth.probe_credentials() if x_oauth.oauth_configured() else None
    return {
        "x_settings": settings,
        "x_oauth_redirect_uri": x_oauth.redirect_uri(base),
        "x_oauth_ready": x_oauth.oauth_configured(),
        "x_oauth_probe_ok": bool(probe and probe.get("ok")),
        "x_oauth_probe_error": (probe or {}).get("error", ""),
        "wallet_login_url": f"{base}/login",
        "wallet_admin_url": f"{base}/admin",
    }