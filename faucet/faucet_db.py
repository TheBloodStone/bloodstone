"""SQLite storage for faucet claims and donation log."""

import os
import random
import sqlite3
import time

DB_PATH = os.environ.get("FAUCET_DB", "/root/bloodstone-faucet/faucet.db")

DEFAULT_COOLDOWN_MIN_HOURS = 3
DEFAULT_COOLDOWN_MAX_HOURS = 6


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL,
                amount REAL NOT NULL,
                txid TEXT,
                ip TEXT,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_claims_address_time
                ON claims(address, created_at);
            CREATE INDEX IF NOT EXISTS idx_claims_ip_time
                ON claims(ip, created_at);

            CREATE TABLE IF NOT EXISTS donations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                txid TEXT NOT NULL UNIQUE,
                from_address TEXT,
                amount REAL NOT NULL,
                created_at INTEGER NOT NULL
            );
            """
        )
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(claims)").fetchall()
        }
        if "cooldown_until" not in cols:
            conn.execute("ALTER TABLE claims ADD COLUMN cooldown_until INTEGER")
        if "user_id" not in cols:
            conn.execute("ALTER TABLE claims ADD COLUMN user_id INTEGER")
        conn.execute(
            """
            UPDATE claims
            SET cooldown_until = created_at + ?
            WHERE cooldown_until IS NULL
            """,
            (DEFAULT_COOLDOWN_MAX_HOURS * 3600,),
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_claims_address_cooldown
                ON claims(address, cooldown_until)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_claims_ip_cooldown
                ON claims(ip, cooldown_until)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_claims_ip_user
                ON claims(ip, user_id)
            """
        )
        _backfill_claim_user_ids(conn)


def random_cooldown_seconds(min_hours=None, max_hours=None):
    lo = int(float(min_hours if min_hours is not None else DEFAULT_COOLDOWN_MIN_HOURS))
    hi = int(float(max_hours if max_hours is not None else DEFAULT_COOLDOWN_MAX_HOURS))
    if lo > hi:
        lo, hi = hi, lo
    lo = max(1, lo)
    hi = max(lo, hi)
    return random.randint(lo * 3600, hi * 3600)


def active_cooldown_for_address(address):
    now = int(time.time())
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT cooldown_until FROM claims
            WHERE address = ? AND cooldown_until > ?
            ORDER BY cooldown_until DESC LIMIT 1
            """,
            (address, now),
        ).fetchone()
    return int(row["cooldown_until"]) if row else None


def active_cooldown_for_ip(ip):
    if not ip:
        return None
    now = int(time.time())
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT cooldown_until FROM claims
            WHERE ip = ? AND cooldown_until > ?
            ORDER BY cooldown_until DESC LIMIT 1
            """,
            (ip, now),
        ).fetchone()
    return int(row["cooldown_until"]) if row else None


def active_ip_claim(ip):
    if not ip:
        return None
    now = int(time.time())
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT address, user_id, cooldown_until FROM claims
            WHERE ip = ? AND cooldown_until > ?
            ORDER BY cooldown_until DESC LIMIT 1
            """,
            (ip, now),
        ).fetchone()
    return dict(row) if row else None


def bound_user_id_for_ip(ip):
    """First wallet account that claimed from this IP (one IP → one account)."""
    if not ip:
        return None
    with _conn() as conn:
        row = conn.execute(
            """
            SELECT user_id FROM claims
            WHERE ip = ? AND user_id IS NOT NULL
            ORDER BY id ASC LIMIT 1
            """,
            (ip,),
        ).fetchone()
    return int(row["user_id"]) if row else None


def _backfill_claim_user_ids(conn):
    users_db_path = os.environ.get(
        "WALLET_WEB_DB", "/root/bloodstone-wallet-web/users.db"
    )
    if not os.path.isfile(users_db_path):
        return
    try:
        conn.execute("ATTACH DATABASE ? AS wallet_users", (users_db_path,))
        conn.execute(
            """
            UPDATE claims
            SET user_id = (
                SELECT id FROM wallet_users.users
                WHERE wallet_users.users.primary_receive_address = claims.address
                ORDER BY id ASC LIMIT 1
            )
            WHERE user_id IS NULL
            """
        )
    except sqlite3.Error:
        pass
    finally:
        try:
            conn.execute("DETACH DATABASE wallet_users")
        except sqlite3.Error:
            pass


def record_claim(address, amount, txid, ip, cooldown_until, user_id=None):
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO claims (address, amount, txid, ip, created_at, cooldown_until, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(address),
                float(amount),
                str(txid) if txid is not None else None,
                str(ip) if ip else None,
                int(time.time()),
                int(cooldown_until),
                int(user_id) if user_id is not None else None,
            ),
        )


def recent_claims(limit=15):
    with _conn() as conn:
        return conn.execute(
            "SELECT address, amount, txid, created_at FROM claims ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()


def record_donation(txid, from_address, amount):
    with _conn() as conn:
        try:
            conn.execute(
                "INSERT INTO donations (txid, from_address, amount, created_at) VALUES (?, ?, ?, ?)",
                (txid, from_address, amount, int(time.time())),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def recent_donations(limit=15):
    with _conn() as conn:
        return conn.execute(
            "SELECT from_address, amount, txid, created_at FROM donations ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()


def donation_total():
    with _conn() as conn:
        row = conn.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM donations").fetchone()
        return float(row["total"] if row else 0)