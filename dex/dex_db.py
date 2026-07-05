"""SQLite order book for the Bloodstone DEX."""

import os
import sqlite3
import time

DB_PATH = os.environ.get("DEX_DB", "/root/bloodstone-dex/dex.db")

ORDER_TYPES = ("name_sale", "ask", "bid", "hashrate_rental")
STATUSES = ("open", "filled", "cancelled")


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_type TEXT NOT NULL,
                name TEXT NOT NULL,
                value TEXT NOT NULL DEFAULT '{}',
                price REAL NOT NULL,
                title TEXT,
                seller_username TEXT,
                seller_wallet TEXT,
                buyer_username TEXT,
                buyer_wallet TEXT,
                partial_tx_hex TEXT,
                name_txid TEXT,
                name_vout INTEGER,
                status TEXT NOT NULL DEFAULT 'open',
                fill_txid TEXT,
                created_at INTEGER NOT NULL,
                filled_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_orders_status_created
                ON orders(status, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_orders_name_status
                ON orders(name, status);
            CREATE INDEX IF NOT EXISTS idx_orders_seller
                ON orders(seller_username, status);
            """
        )


def create_order(
    order_type,
    name,
    price,
    *,
    value="{}",
    title=None,
    seller_username=None,
    seller_wallet=None,
    buyer_username=None,
    buyer_wallet=None,
    partial_tx_hex=None,
    name_txid=None,
    name_vout=None,
):
    if order_type not in ORDER_TYPES:
        raise ValueError(f"Invalid order type: {order_type}")
    now = int(time.time())
    with _conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO orders (
                order_type, name, value, price, title,
                seller_username, seller_wallet,
                buyer_username, buyer_wallet,
                partial_tx_hex, name_txid, name_vout,
                status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (
                order_type,
                name,
                value,
                float(price),
                title,
                seller_username,
                seller_wallet,
                buyer_username,
                buyer_wallet,
                partial_tx_hex,
                name_txid,
                name_vout,
                now,
            ),
        )
        return int(cur.lastrowid)


def get_order(order_id):
    with _conn() as conn:
        return conn.execute(
            "SELECT * FROM orders WHERE id = ?", (int(order_id),)
        ).fetchone()


def list_orders(*, status="open", order_type=None, limit=50):
    query = "SELECT * FROM orders WHERE status = ?"
    params = [status]
    if order_type:
        query += " AND order_type = ?"
        params.append(order_type)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(int(limit))
    with _conn() as conn:
        return conn.execute(query, params).fetchall()


def orders_for_user(username, *, status=None, limit=30):
    query = """
        SELECT * FROM orders
        WHERE seller_username = ? OR buyer_username = ?
    """
    params = [username, username]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(int(limit))
    with _conn() as conn:
        return conn.execute(query, params).fetchall()


def mark_filled(
    order_id,
    fill_txid,
    *,
    buyer_username=None,
    buyer_wallet=None,
    seller_username=None,
    seller_wallet=None,
):
    now = int(time.time())
    with _conn() as conn:
        conn.execute(
            """
            UPDATE orders
            SET status = 'filled', fill_txid = ?, filled_at = ?,
                buyer_username = COALESCE(?, buyer_username),
                buyer_wallet = COALESCE(?, buyer_wallet),
                seller_username = COALESCE(?, seller_username),
                seller_wallet = COALESCE(?, seller_wallet)
            WHERE id = ? AND status = 'open'
            """,
            (
                fill_txid,
                now,
                buyer_username,
                buyer_wallet,
                seller_username,
                seller_wallet,
                int(order_id),
            ),
        )


def cancel_order(order_id, username):
    with _conn() as conn:
        row = conn.execute(
            "SELECT seller_username, buyer_username, status FROM orders WHERE id = ?",
            (int(order_id),),
        ).fetchone()
        if not row or row["status"] != "open":
            return False
        owners = {row["seller_username"], row["buyer_username"]}
        if username not in owners:
            return False
        conn.execute(
            "UPDATE orders SET status = 'cancelled' WHERE id = ?",
            (int(order_id),),
        )
        return True


def open_order_count():
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM orders WHERE status = 'open'"
        ).fetchone()
        return int(row["c"] if row else 0)