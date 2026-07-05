#!/usr/bin/env python3
"""Bloodstone testnet faucet — claim STONE or fund the faucet from your wallet."""

import os
import re
import secrets
import sys
import threading
import time
from datetime import datetime, timezone
from urllib.parse import quote

sys.path.insert(0, "/root")
import bloodstone_branding
import bloodstone_time

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import faucet_db
import faucet_rpc
import wallet_session

SECRETS_PATH = os.environ.get("FAUCET_SECRETS", "/root/bloodstone-faucet/secrets.conf")
WALLET_LOGIN_PATH = os.environ.get("WALLET_LOGIN_PATH", "/wallet/login")
PUBLIC_ROOT = os.environ.get(
    "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
)

LEGACY_ADDR = re.compile(r"^S[1-9A-HJ-NP-Za-km-z]{25,34}$")
BECH32_ADDR = re.compile(r"^stone1[0-9a-z]{20,}$", re.I)

app = Flask(__name__)
faucet_db.init_db()

_STATUS_CACHE_LOCK = threading.Lock()
_STATUS_CACHE: dict = {}

from prefix_middleware import apply_prefix  # noqa: E402

apply_prefix(app)


def load_config():
    values = {
        "claim_amount": 1.0,
        "claim_cooldown_min_hours": 3,
        "claim_cooldown_max_hours": 6,
        "min_faucet_balance": 0.5,
    }
    if os.path.isfile(SECRETS_PATH):
        with open(SECRETS_PATH, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                values[key.strip()] = val.strip()
    # Legacy single cooldown value maps to a fixed window.
    if "claim_cooldown_hours" in values and "claim_cooldown_min_hours" not in values:
        legacy = int(float(values["claim_cooldown_hours"]))
        values["claim_cooldown_min_hours"] = str(legacy)
        values["claim_cooldown_max_hours"] = str(legacy)
    values["claim_amount"] = float(values.get("claim_amount", 1.0))
    values["claim_cooldown_min_hours"] = int(
        float(values.get("claim_cooldown_min_hours", 3))
    )
    values["claim_cooldown_max_hours"] = int(
        float(values.get("claim_cooldown_max_hours", 6))
    )
    if values["claim_cooldown_min_hours"] > values["claim_cooldown_max_hours"]:
        values["claim_cooldown_min_hours"], values["claim_cooldown_max_hours"] = (
            values["claim_cooldown_max_hours"],
            values["claim_cooldown_min_hours"],
        )
    values["min_faucet_balance"] = float(values.get("min_faucet_balance", 0.5))
    return values


def get_config():
    return load_config()

app.config.update(
    SESSION_COOKIE_NAME="bs_faucet_session",
    SESSION_COOKIE_PATH="/faucet/",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
app.secret_key = wallet_session.load_wallet_session_secret()


def wallet_login_url(next_path="/faucet/"):
    return f"{PUBLIC_ROOT}{WALLET_LOGIN_PATH}?next={quote(next_path)}"


def wallet_context():
    user = wallet_session.current_wallet_user()
    if not user:
        return {
            "wallet_user": None,
            "wallet_primary_address": None,
            "wallet_login_url": wallet_login_url("/faucet/"),
        }
    try:
        address = wallet_session.primary_address_for_user(user)
    except Exception:
        address = None
    return {
        "wallet_user": user,
        "wallet_primary_address": address,
        "wallet_login_url": wallet_login_url("/faucet/"),
    }


@app.context_processor
def inject_globals():
    ctx = wallet_context()
    return {
        "public_root": PUBLIC_ROOT,
        "claim_amount": get_config()["claim_amount"],
        "cooldown_min_hours": get_config()["claim_cooldown_min_hours"],
        "cooldown_max_hours": get_config()["claim_cooldown_max_hours"],
        "csrf_token": csrf_token,
        **ctx,
        **bloodstone_branding.header_brand_context(PUBLIC_ROOT, "💧"),
    }


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def verify_csrf():
    return request.form.get("csrf_token") == session.get("csrf_token")


def client_ip():
    return (request.headers.get("X-Real-IP") or request.remote_addr or "").strip()


def valid_address(addr):
    return bool(LEGACY_ADDR.match(addr) or BECH32_ADDR.match(addr))


def _fmt_wait_until(until_ts):
    remaining = max(0, int(until_ts) - int(time.time()))
    hours, rem = divmod(remaining, 3600)
    minutes, _ = divmod(rem, 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    if minutes:
        return f"{minutes}m"
    return "a moment"


def _fmt_time_utc(until_ts):
    return bloodstone_time.format_pacific(until_ts, "%Y-%m-%d %H:%M %Z")


def wallet_donate_url(address, amount=None):
    params = f"address={quote(address)}&comment={quote('Faucet donation')}"
    if amount:
        params += f"&amount={quote(str(amount))}"
    path = f"/wallet/send?{params}"
    return f"{PUBLIC_ROOT}/wallet/login?next={quote(path)}"


def _build_faucet_status():
    try:
        faucet_rpc.sync_donations()
        info = faucet_rpc.wallet_info()
        address = faucet_rpc.primary_address()
        return {
            "ok": True,
            "address": address,
            "balance": info["spendable"],
            "txcount": info["txcount"],
            "donate_url": wallet_donate_url(address),
            "donate_5_url": wallet_donate_url(address, 5),
            "donate_10_url": wallet_donate_url(address, 10),
            "donate_25_url": wallet_donate_url(address, 25),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def faucet_status(use_cache: bool = True):
    ttl = float(os.environ.get("FAUCET_STATUS_CACHE_SEC", "45"))
    now = time.time()
    if use_cache:
        with _STATUS_CACHE_LOCK:
            entry = _STATUS_CACHE.get("status")
            if entry and now - entry[0] < ttl:
                return entry[1]
            stale = entry[1] if entry else None
    else:
        stale = None
    try:
        status = _build_faucet_status()
    except Exception as exc:
        if stale is not None:
            return stale
        return {"ok": False, "error": str(exc)}
    with _STATUS_CACHE_LOCK:
        _STATUS_CACHE["status"] = (now, status)
    return status


@app.template_filter("faucet_time")
def faucet_time_filter(ts):
    if not ts:
        return "—"
    try:
        return bloodstone_time.format_pacific(int(ts))
    except (TypeError, ValueError):
        return str(ts)


@app.route("/")
def index():
    status = faucet_status()
    return render_template(
        "index.html",
        status=status,
        recent_claims=faucet_db.recent_claims(),
        recent_donations=faucet_db.recent_donations(),
        donation_total=faucet_db.donation_total(),
    )


@app.route("/claim", methods=["POST"])
def claim():
    if not verify_csrf():
        flash("Invalid form token. Refresh and try again.", "error")
        return redirect(url_for("index"))

    user = wallet_session.current_wallet_user()
    if not user:
        flash("Log in to your web wallet to claim STONE.", "error")
        return redirect(wallet_login_url("/faucet/"))
    if not user.get("wallet_name"):
        flash("Finish wallet setup before claiming from the faucet.", "error")
        return redirect(f"{PUBLIC_ROOT}/wallet/setup-wallet")

    try:
        address = wallet_session.primary_address_for_user(user)
    except Exception as exc:
        flash(f"Could not load your wallet address: {exc}", "error")
        return redirect(url_for("index"))

    if not valid_address(address):
        flash("Your wallet primary address is invalid. Contact support.", "error")
        return redirect(url_for("index"))

    status = faucet_status(use_cache=False)
    if not status.get("ok"):
        flash(f"Faucet unavailable: {status.get('error', 'node offline')}", "error")
        return redirect(url_for("index"))

    cfg = get_config()
    amount = cfg["claim_amount"]
    if status["balance"] < max(amount, cfg["min_faucet_balance"]):
        flash(
            "Faucet is empty — fund it from your wallet using the Donate section.",
            "error",
        )
        return redirect(url_for("index"))

    ip = client_ip()
    user_id = int(user["id"])
    bound_user_id = faucet_db.bound_user_id_for_ip(ip)
    if bound_user_id is not None and bound_user_id != user_id:
        flash(
            "This IP address is already linked to another wallet account. "
            "Log in with that account to claim, or use a different network.",
            "error",
        )
        return redirect(url_for("index"))

    address_wait = faucet_db.active_cooldown_for_address(address)
    if address_wait:
        flash(
            f"This address can claim again in {_fmt_wait_until(address_wait)} "
            f"(after {_fmt_time_utc(address_wait)}).",
            "error",
        )
        return redirect(url_for("index"))

    active_ip_claim = faucet_db.active_ip_claim(ip)
    if active_ip_claim:
        ip_wait = int(active_ip_claim["cooldown_until"])
        if (
            active_ip_claim.get("user_id") is not None
            and int(active_ip_claim["user_id"]) != user_id
        ):
            flash(
                f"This IP recently claimed from another account. "
                f"Try again in {_fmt_wait_until(ip_wait)} "
                f"(after {_fmt_time_utc(ip_wait)}), or use the same account.",
                "error",
            )
            return redirect(url_for("index"))
        flash(
            f"This IP can claim again in {_fmt_wait_until(ip_wait)} "
            f"(after {_fmt_time_utc(ip_wait)}).",
            "error",
        )
        return redirect(url_for("index"))

    try:
        txid = faucet_rpc.send_to_address(address, amount)
    except Exception as exc:
        flash(f"Claim failed: {exc}", "error")
        return redirect(url_for("index"))

    cooldown_seconds = faucet_db.random_cooldown_seconds(
        cfg["claim_cooldown_min_hours"],
        cfg["claim_cooldown_max_hours"],
    )
    cooldown_until = int(time.time()) + cooldown_seconds
    faucet_db.record_claim(address, amount, txid, ip, cooldown_until, user_id=user_id)
    flash(f"Sent {amount:g} STONE to {address}.", "success")
    return render_template(
        "claim_success.html",
        address=address,
        amount=amount,
        txid=txid,
        explorer_tx=f"{PUBLIC_ROOT}/explorer/tx/{txid}",
        next_claim_at=_fmt_time_utc(cooldown_until),
        next_claim_wait=_fmt_wait_until(cooldown_until),
    )


@app.route("/fund")
def fund():
    status = faucet_status()
    return render_template(
        "fund.html",
        status=status,
        recent_donations=faucet_db.recent_donations(),
        donation_total=faucet_db.donation_total(),
    )


@app.route("/live")
def live():
    return {"ok": True, "service": "faucet"}


@app.route("/health")
def health():
    status = faucet_status()
    code = 200 if status.get("ok") else 503
    return {"ok": status.get("ok", False), "balance": status.get("balance")}, code