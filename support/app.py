#!/usr/bin/env python3
"""Bloodstone support ticket system."""

import os
import re
from functools import wraps

from flask import (
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

import sys

sys.path.insert(0, "/root")
import bloodstone_branding
import tickets_db

SECRETS_PATH = os.environ.get("SUPPORT_SECRETS", "/root/bloodstone-support/secrets.conf")
PUBLIC_ROOT = os.environ.get(
    "BLOODSTONE_PUBLIC_ROOT", "https://rodcoinwallet.duckdns.org"
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CATEGORIES = [
    ("mining", "Mining / pools"),
    ("wallet", "Wallet"),
    ("explorer", "Explorer"),
    ("node", "Node / sync"),
    ("account", "Account access"),
    ("other", "Other"),
]
STATUSES = ["open", "pending", "closed"]

app = Flask(__name__)
tickets_db.init_db()

from prefix_middleware import apply_prefix  # noqa: E402
from prefix_redirect import prefixed_path, safe_redirect_target  # noqa: E402

apply_prefix(app)


def load_secrets():
    values = {}
    if os.path.isfile(SECRETS_PATH):
        with open(SECRETS_PATH, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                values[key.strip()] = val.strip()
    app.secret_key = values.get("secret_key") or os.urandom(32).hex()
    return values.get("admin_password_hash")


app.config["ADMIN_PASSWORD_HASH"] = load_secrets()


@app.context_processor
def inject_globals():
    return {
        "public_root": PUBLIC_ROOT,
        "categories": CATEGORIES,
        "statuses": STATUSES,
        **bloodstone_branding.header_brand_context(PUBLIC_ROOT, "💎"),
    }


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not app.config.get("ADMIN_PASSWORD_HASH"):
            flash("Admin panel disabled (no password configured).", "error")
            return redirect(url_for("index"))
        if not session.get("support_admin"):
            query = request.query_string.decode() if request.query_string else None
            return redirect(
                url_for("admin_login", next=prefixed_path(request.path, query))
            )
        return view(*args, **kwargs)

    return wrapped


@app.route("/live")
def live():
    return {"ok": True, "service": "support"}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/submit", methods=["POST"])
def submit():
    email = request.form.get("email", "").strip()
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "other")
    subject = request.form.get("subject", "").strip()
    body = request.form.get("body", "").strip()

    if not EMAIL_RE.match(email):
        flash("Enter a valid email address.", "error")
        return redirect(url_for("index"))
    if len(subject) < 4:
        flash("Subject must be at least 4 characters.", "error")
        return redirect(url_for("index"))
    if len(body) < 10:
        flash("Please describe your issue in more detail.", "error")
        return redirect(url_for("index"))
    if category not in dict(CATEGORIES):
        category = "other"

    public_id, view_token = tickets_db.create_ticket(email, name, category, subject, body)
    return render_template(
        "ticket_submitted.html",
        public_id=public_id,
        view_token=view_token,
        view_url=url_for("view_ticket", public_id=public_id, token=view_token, _external=True),
    )


@app.route("/ticket/<public_id>")
def view_ticket(public_id):
    token = request.args.get("token", "").strip()
    if not token:
        return render_template("ticket_lookup.html", public_id=public_id.upper())
    ticket, messages = tickets_db.get_ticket_by_public_id(public_id, token)
    if not ticket:
        flash("Ticket not found or invalid access link.", "error")
        return redirect(url_for("lookup"))
    return render_template("ticket_view.html", ticket=ticket, messages=messages, token=token)


@app.route("/lookup", methods=["GET", "POST"])
def lookup():
    if request.method == "POST":
        public_id = request.form.get("public_id", "").strip().upper()
        token = request.form.get("token", "").strip()
        if public_id and token:
            return redirect(url_for("view_ticket", public_id=public_id, token=token))
        flash("Enter ticket ID and access token.", "error")
    return render_template("ticket_lookup.html")


@app.route("/ticket/<public_id>/reply", methods=["POST"])
def user_reply(public_id):
    token = request.form.get("token", "").strip()
    body = request.form.get("body", "").strip()
    ticket, _ = tickets_db.get_ticket_by_public_id(public_id, token)
    if not ticket:
        flash("Ticket not found.", "error")
        return redirect(url_for("lookup"))
    if ticket["status"] == "closed":
        flash("This ticket is closed.", "error")
        return redirect(url_for("view_ticket", public_id=public_id, token=token))
    if len(body) < 3:
        flash("Reply too short.", "error")
        return redirect(url_for("view_ticket", public_id=public_id, token=token))
    tickets_db.add_reply(ticket["id"], ticket.get("name") or ticket["email"], body, status="open")
    flash("Reply sent.", "success")
    return redirect(url_for("view_ticket", public_id=public_id, token=token))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pw_hash = app.config.get("ADMIN_PASSWORD_HASH")
        if pw_hash and check_password_hash(pw_hash, request.form.get("password", "")):
            session["support_admin"] = True
            return redirect(
                safe_redirect_target(request.args.get("next"), "admin_dashboard")
            )
        flash("Invalid password.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("support_admin", None)
    return redirect(url_for("index"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    status = request.args.get("status")
    tickets = tickets_db.list_tickets(status=status if status in STATUSES else None)
    return render_template(
        "admin_dashboard.html",
        tickets=tickets,
        counts=tickets_db.ticket_counts(),
        filter_status=status,
    )


@app.route("/admin/ticket/<public_id>", methods=["GET", "POST"])
@admin_required
def admin_ticket(public_id):
    ticket, messages = tickets_db.get_ticket_by_public_id(public_id)
    if not ticket:
        flash("Ticket not found.", "error")
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        body = request.form.get("body", "").strip()
        status = request.form.get("status", ticket["status"])
        if status not in STATUSES:
            status = ticket["status"]
        if body:
            tickets_db.add_reply(ticket["id"], "Support", body, status=status)
            flash("Reply posted.", "success")
        elif status != ticket["status"]:
            tickets_db.add_reply(ticket["id"], "Support", f"Status changed to {status}.", status=status)
            flash("Status updated.", "success")
        return redirect(url_for("admin_ticket", public_id=public_id))
    return render_template("admin_ticket.html", ticket=ticket, messages=messages)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8886, debug=False)