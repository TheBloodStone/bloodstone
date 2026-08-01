"""WP1 draft / watch state — SQLite."""
from __future__ import annotations
import os, sqlite3, time
from pathlib import Path

DB = Path(os.environ.get("FORK_LAB_WP1_DB", "/var/lib/bloodstone/fork_lab_wp1.db"))

def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    return c

def init():
    with connect() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS drafts (
              draft_id TEXT PRIMARY KEY,
              ticker TEXT NOT NULL,
              name TEXT NOT NULL,
              creator_address TEXT NOT NULL,
              fee_stone REAL NOT NULL,
              open_min_stone REAL NOT NULL,
              burn_address TEXT NOT NULL UNIQUE,
              status TEXT NOT NULL DEFAULT 'open',
              created_at INTEGER NOT NULL,
              expires_at INTEGER NOT NULL,
              funded_at INTEGER,
              provisioned_at INTEGER,
              detail_json TEXT
            );
            CREATE TABLE IF NOT EXISTS burn_credits (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              draft_id TEXT NOT NULL,
              txid TEXT NOT NULL,
              vout INTEGER NOT NULL DEFAULT 0,
              amount REAL NOT NULL,
              confs INTEGER NOT NULL DEFAULT 0,
              seen_at INTEGER NOT NULL,
              UNIQUE(txid, vout)
            );
            """
        )
