#!/usr/bin/env python3
"""Bloodstone DEX — trustless name marketplace using atomic transactions."""

import json
import os
import re
import secrets
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

sys.path.insert(0, "/root")
import bloodstone_branding
import bloodstone_time

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import atomic_trade
import dex_db
import dex_rpc
import wallet_session

import sys

WALLET_WEB_DIR = os.environ.get("WALLET_WEB_DIR", "/root/bloodstone-wallet-web")
if WALLET_WEB_DIR not in sys.path:
    sys.path.insert(0, WALLET_WEB_DIR)

import users_db  # noqa: E402
import wallet_rpc  # noqa: E402

PUBLIC_ROOT = os.environ.get(
    "BLOODSTONE_PUBLIC_ROOT", "https://bloodstonewallet.mytunnel.org"
)
WALLET_LOGIN_PATH = os.environ.get("WALLET_LOGIN_PATH", "/wallet/login")

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,59}$", re.I)

app = Flask(__name__)
dex_db.init_db()

from prefix_middleware import apply_prefix  # noqa: E402

apply_prefix(app)

app.config.update(
    SESSION_COOKIE_NAME="bs_dex_session",
    SESSION_COOKIE_PATH="/dex/",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
app.secret_key = wallet_session.load_wallet_session_secret()


@app.before_request
def configure_session_cookie():
    app.config["SESSION_COOKIE_SECURE"] = bool(request.is_secure)
    root = (request.script_root or "").rstrip("/")
    app.config["SESSION_COOKIE_PATH"] = f"{root}/" if root else "/"


def wallet_login_url(next_path="/dex/"):
    from urllib.parse import quote

    return f"{PUBLIC_ROOT}{WALLET_LOGIN_PATH}?next={quote(next_path)}"


def wallet_context():
    user = wallet_session.current_wallet_user()
    if not user:
        return {
            "wallet_user": None,
            "wallet_primary_address": None,
            "wallet_login_url": wallet_login_url("/dex/"),
        }
    try:
        address = wallet_session.primary_address_for_user(user)
    except Exception:
        address = None
    return {
        "wallet_user": user,
        "wallet_primary_address": address,
        "wallet_login_url": wallet_login_url("/dex/"),
    }


@app.context_processor
def inject_globals():
    return {
        "public_root": PUBLIC_ROOT,
        "csrf_token": csrf_token,
        **wallet_context(),
        **bloodstone_branding.header_brand_context(PUBLIC_ROOT, "⚖"),
    }


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def verify_csrf():
    return request.form.get("csrf_token") == session.get("csrf_token")


def require_user():
    user = wallet_session.current_wallet_user()
    if not user:
        return None
    if not user.get("wallet_name"):
        return None
    return user


def normalize_name(raw):
    name = (raw or "").strip().lower()
    if not name:
        raise ValueError("Name is required")
    if "/" not in name:
        name = f"p/{name}"
    namespace, local = name.split("/", 1)
    if namespace not in ("d", "p", "g"):
        raise ValueError("Namespace must be d/, p/, or g/")
    if not NAME_RE.match(local):
        raise ValueError("Invalid name format")
    return f"{namespace}/{local}"


def parse_price(raw):
    try:
        price = Decimal(str(raw).strip())
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Invalid price") from exc
    if price <= 0:
        raise ValueError("Price must be positive")
    if price > Decimal("1000000"):
        raise ValueError("Price too large")
    return price


def fmt_time(ts):
    if not ts:
        return "—"
    return bloodstone_time.format_pacific(ts, "%Y-%m-%d %H:%M %Z")


def order_type_label(order_type):
    return {
        "name_sale": "Name transfer",
        "ask": "Sell (ask)",
        "bid": "Buy offer (bid)",
    }.get(order_type, order_type)


def enrich_order(row):
    data = dict(row)
    data["type_label"] = order_type_label(data["order_type"])
    data["created_fmt"] = fmt_time(data["created_at"])
    data["filled_fmt"] = fmt_time(data["filled_at"])
    return data


def user_names(wallet_name):
    try:
        entries = dex_rpc.name_list(wallet_name)
    except Exception:
        return []
    owned = []
    for entry in entries:
        if entry.get("ismine"):
            owned.append(entry)
    return owned


def validate_listing_utxo(order):
    if not order["name_txid"] or order["name_vout"] is None:
        return True
    try:
        atomic_trade.name_utxo_fresh(order["name_txid"], order["name_vout"])
        return True
    except RuntimeError:
        return False


@app.route("/")
def index():
    orders = [enrich_order(r) for r in dex_db.list_orders(limit=40)]
    return render_template(
        "index.html",
        orders=orders,
        open_count=dex_db.open_order_count(),
    )


@app.route("/my")
def my_orders():
    user = require_user()
    if not user:
        flash("Log in to view your DEX orders.", "error")
        return redirect(wallet_login_url("/dex/my"))
    rows = dex_db.orders_for_user(user["username"])
    return render_template(
        "my.html",
        orders=[enrich_order(r) for r in rows],
        names=user_names(user["wallet_name"]),
    )


@app.route("/sell", methods=["GET", "POST"])
def sell():
    user = require_user()
    if not user:
        flash("Log in with your web wallet to list names for sale.", "error")
        return redirect(wallet_login_url("/dex/sell"))

    names = user_names(user["wallet_name"])
    if request.method == "GET":
        return render_template("sell.html", names=names)

    if not verify_csrf():
        flash("Invalid form token. Refresh and try again.", "error")
        return redirect(url_for("sell"))

    try:
        name = normalize_name(request.form.get("name"))
        price = parse_price(request.form.get("price"))
        listing_type = (request.form.get("listing_type") or "name_sale").strip()
        title = (request.form.get("title") or "").strip()[:120] or None
        new_value = (request.form.get("value") or "{}").strip() or "{}"
        json.loads(new_value)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("sell"))
    except json.JSONDecodeError:
        flash("Value must be valid JSON.", "error")
        return redirect(url_for("sell"))

    wallet_name = user["wallet_name"]
    try:
        name_data = atomic_trade.verify_name_owned(wallet_name, name)
    except RuntimeError as exc:
        flash(str(exc), "error")
        return redirect(url_for("sell"))

    if listing_type == "name_sale":
        order_id = dex_db.create_order(
            "name_sale",
            name,
            price,
            value=name_data.get("value", "{}"),
            title=title,
            seller_username=user["username"],
            seller_wallet=wallet_name,
            name_txid=name_data["txid"],
            name_vout=int(name_data["vout"]),
        )
        flash(f"Listed {name} for {price:g} STONE.", "success")
        return redirect(url_for("order_detail", order_id=order_id))

    if listing_type == "ask":
        try:
            built = atomic_trade.build_ask(wallet_name, name, new_value, price)
        except RuntimeError as exc:
            flash(f"Could not build ask: {exc}", "error")
            return redirect(url_for("sell"))
        order_id = dex_db.create_order(
            "ask",
            name,
            price,
            value=new_value,
            title=title,
            seller_username=user["username"],
            seller_wallet=wallet_name,
            partial_tx_hex=built["hex"],
            name_txid=built["name_txid"],
            name_vout=built["name_vout"],
        )
        flash(f"Posted ask for {name} at {price:g} STONE.", "success")
        return redirect(url_for("order_detail", order_id=order_id))

    flash("Unknown listing type.", "error")
    return redirect(url_for("sell"))


@app.route("/bid", methods=["GET", "POST"])
def bid():
    user = require_user()
    if not user:
        flash("Log in to post a buy offer.", "error")
        return redirect(wallet_login_url("/dex/bid"))

    if request.method == "GET":
        return render_template("bid.html")

    if not verify_csrf():
        flash("Invalid form token. Refresh and try again.", "error")
        return redirect(url_for("bid"))

    try:
        name = normalize_name(request.form.get("name"))
        price = parse_price(request.form.get("price"))
        new_value = (request.form.get("value") or "{}").strip() or "{}"
        title = (request.form.get("title") or "").strip()[:120] or None
        json.loads(new_value)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("bid"))
    except json.JSONDecodeError:
        flash("Value must be valid JSON.", "error")
        return redirect(url_for("bid"))

    wallet_name = user["wallet_name"]
    try:
        built = atomic_trade.build_bid(wallet_name, name, new_value, price)
    except RuntimeError as exc:
        flash(f"Could not build bid: {exc}", "error")
        return redirect(url_for("bid"))

    order_id = dex_db.create_order(
        "bid",
        name,
        price,
        value=new_value,
        title=title,
        buyer_username=user["username"],
        buyer_wallet=wallet_name,
        partial_tx_hex=built["hex"],
        name_txid=built["name_txid"],
        name_vout=built["name_vout"],
    )
    flash(f"Posted bid on {name} for {price:g} STONE.", "success")
    return redirect(url_for("order_detail", order_id=order_id))


@app.route("/order/<int:order_id>")
def order_detail(order_id):
    row = dex_db.get_order(order_id)
    if not row:
        flash("Order not found.", "error")
        return redirect(url_for("index"))
    order = enrich_order(row)
    order["utxo_valid"] = validate_listing_utxo(row)
    return render_template("order.html", order=order)


@app.route("/order/<int:order_id>/buy", methods=["POST"])
def buy_order(order_id):
    user = require_user()
    if not user:
        flash("Log in to buy this listing.", "error")
        return redirect(wallet_login_url(f"/dex/order/{order_id}"))

    if not verify_csrf():
        flash("Invalid form token. Refresh and try again.", "error")
        return redirect(url_for("order_detail", order_id=order_id))

    row = dex_db.get_order(order_id)
    if not row or row["status"] != "open":
        flash("This order is no longer available.", "error")
        return redirect(url_for("index"))

    if row["seller_username"] == user["username"]:
        flash("You cannot buy your own listing.", "error")
        return redirect(url_for("order_detail", order_id=order_id))

    if not validate_listing_utxo(row):
        flash("Listing is stale — name UTXO has changed.", "error")
        return redirect(url_for("order_detail", order_id=order_id))

    buyer_wallet = user["wallet_name"]
    try:
        buyer_address = wallet_session.primary_address_for_user(user)
    except Exception as exc:
        flash(f"Could not load your address: {exc}", "error")
        return redirect(url_for("order_detail", order_id=order_id))

    try:
        if row["order_type"] == "name_sale":
            tx_hex = atomic_trade.build_name_sale(
                row["seller_wallet"],
                row["name"],
                buyer_wallet,
                buyer_address,
                row["price"],
            )
        elif row["order_type"] == "ask":
            if not row["partial_tx_hex"]:
                raise RuntimeError("Ask transaction missing")
            tx_hex = atomic_trade.complete_ask(
                buyer_wallet, row["partial_tx_hex"], row["price"]
            )
        else:
            flash("Bid orders are accepted by the seller, not bought directly.", "error")
            return redirect(url_for("order_detail", order_id=order_id))

        txid = atomic_trade.broadcast(tx_hex)
    except RuntimeError as exc:
        flash(f"Trade failed: {exc}", "error")
        return redirect(url_for("order_detail", order_id=order_id))

    dex_db.mark_filled(
        order_id,
        txid,
        buyer_username=user["username"],
        buyer_wallet=buyer_wallet,
    )
    flash(f"Trade broadcast — tx {txid[:16]}…", "success")
    return redirect(url_for("order_detail", order_id=order_id))


@app.route("/order/<int:order_id>/accept", methods=["POST"])
def accept_order(order_id):
    user = require_user()
    if not user:
        flash("Log in to accept this bid.", "error")
        return redirect(wallet_login_url(f"/dex/order/{order_id}"))

    if not verify_csrf():
        flash("Invalid form token. Refresh and try again.", "error")
        return redirect(url_for("order_detail", order_id=order_id))

    row = dex_db.get_order(order_id)
    if not row or row["status"] != "open" or row["order_type"] != "bid":
        flash("This bid is not available.", "error")
        return redirect(url_for("index"))

    if row["buyer_username"] == user["username"]:
        flash("You cannot accept your own bid.", "error")
        return redirect(url_for("order_detail", order_id=order_id))

    if row["seller_username"] and row["seller_username"] != user["username"]:
        flash("Only the name owner can accept this bid.", "error")
        return redirect(url_for("order_detail", order_id=order_id))

    wallet_name = user["wallet_name"]
    try:
        atomic_trade.verify_name_owned(wallet_name, row["name"])
    except RuntimeError as exc:
        flash(str(exc), "error")
        return redirect(url_for("order_detail", order_id=order_id))

    if not validate_listing_utxo(row):
        flash("Bid is stale — name UTXO has changed.", "error")
        return redirect(url_for("order_detail", order_id=order_id))

    try:
        tx_hex = atomic_trade.accept_bid(
            wallet_name, row["partial_tx_hex"], row["name"]
        )
        txid = atomic_trade.broadcast(tx_hex)
    except RuntimeError as exc:
        flash(f"Accept failed: {exc}", "error")
        return redirect(url_for("order_detail", order_id=order_id))

    dex_db.mark_filled(
        order_id,
        txid,
        buyer_username=row["buyer_username"],
        buyer_wallet=row["buyer_wallet"],
        seller_username=user["username"],
        seller_wallet=wallet_name,
    )
    flash(f"Bid accepted — tx {txid[:16]}…", "success")
    return redirect(url_for("order_detail", order_id=order_id))


@app.route("/order/<int:order_id>/cancel", methods=["POST"])
def cancel_order(order_id):
    user = require_user()
    if not user:
        flash("Log in to cancel your order.", "error")
        return redirect(wallet_login_url(f"/dex/order/{order_id}"))

    if not verify_csrf():
        flash("Invalid form token. Refresh and try again.", "error")
        return redirect(url_for("order_detail", order_id=order_id))

    if not dex_db.cancel_order(order_id, user["username"]):
        flash("Could not cancel this order.", "error")
    else:
        flash("Order cancelled.", "success")
    return redirect(url_for("order_detail", order_id=order_id))


@app.route("/api/orders")
def api_orders():
    status = request.args.get("status", "open")
    order_type = request.args.get("type")
    rows = dex_db.list_orders(status=status, order_type=order_type, limit=100)
    return jsonify([enrich_order(r) for r in rows])


@app.route("/live")
def live():
    return {"ok": True, "service": "dex"}


@app.route("/health")
def health():
    try:
        dex_rpc.gettxout(
            "0" * 64,
            0,
        )
        node_ok = True
    except Exception:
        node_ok = False
    return {
        "ok": node_ok,
        "open_orders": dex_db.open_order_count(),
    }, (200 if node_ok else 503)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8896, debug=False)