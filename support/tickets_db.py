"""SQLite storage for support tickets."""

import os
import secrets
import sqlite3
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/root")
import bloodstone_time

DB_PATH = os.environ.get("SUPPORT_DB", "/root/bloodstone-support/tickets.db")


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_id TEXT NOT NULL UNIQUE,
                view_token TEXT NOT NULL,
                email TEXT NOT NULL,
                name TEXT,
                category TEXT NOT NULL,
                subject TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                author TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id)
            );
            CREATE INDEX IF NOT EXISTS idx_tickets_public_id ON tickets(public_id);
            """
        )


def _now():
    return bloodstone_time.now_pacific()


def _public_id():
    return f"BS-{secrets.token_hex(4).upper()}"


def _view_token():
    return secrets.token_urlsafe(24)


def create_ticket(email, name, category, subject, body):
    public_id = _public_id()
    view_token = _view_token()
    now = _now()
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO tickets (public_id, view_token, email, name, category, subject, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?)
            """,
            (public_id, view_token, email.strip().lower(), (name or "").strip(), category, subject.strip(), now, now),
        )
        ticket_id = cur.lastrowid
        conn.execute(
            "INSERT INTO messages (ticket_id, author, body, created_at) VALUES (?, ?, ?, ?)",
            (ticket_id, name or email, body.strip(), now),
        )
    return public_id, view_token


def get_ticket_by_public_id(public_id, view_token=None):
    with _conn() as conn:
        if view_token:
            row = conn.execute(
                "SELECT * FROM tickets WHERE public_id = ? AND view_token = ?",
                (public_id.strip().upper(), view_token.strip()),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM tickets WHERE public_id = ?",
                (public_id.strip().upper(),),
            ).fetchone()
        if not row:
            return None, []
        messages = conn.execute(
            "SELECT * FROM messages WHERE ticket_id = ? ORDER BY id ASC",
            (row["id"],),
        ).fetchall()
        return dict(row), [dict(m) for m in messages]


def add_reply(ticket_id, author, body, status=None):
    now = _now()
    with _conn() as conn:
        conn.execute(
            "INSERT INTO messages (ticket_id, author, body, created_at) VALUES (?, ?, ?, ?)",
            (ticket_id, author, body.strip(), now),
        )
        if status:
            conn.execute(
                "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, ticket_id),
            )
        else:
            conn.execute(
                "UPDATE tickets SET updated_at = ? WHERE id = ?",
                (now, ticket_id),
            )


def list_tickets(status=None):
    with _conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM tickets WHERE status = ? ORDER BY updated_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tickets ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]


def ticket_counts():
    with _conn() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM tickets GROUP BY status"
        ).fetchall()
        return {r["status"]: r["n"] for r in rows}