"""WP1 draft / watch state — SQLite."""
from __future__ import annotations

import os
import sqlite3
import time
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
              open_min_deadline INTEGER NOT NULL DEFAULT 0,
              open_min_met_at INTEGER,
              funded_at INTEGER,
              provisioned_at INTEGER,
              confirmed_total REAL NOT NULL DEFAULT 0,
              fee_freeze_json TEXT,
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
            CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);
            CREATE INDEX IF NOT EXISTS idx_drafts_ticker ON drafts(ticker);
            CREATE INDEX IF NOT EXISTS idx_credits_draft ON burn_credits(draft_id);
            """
        )
        # Lightweight migrations for DBs created before open-min / freeze columns.
        cols = {r[1] for r in c.execute("PRAGMA table_info(drafts)").fetchall()}
        alters = {
            "open_min_deadline": "INTEGER NOT NULL DEFAULT 0",
            "open_min_met_at": "INTEGER",
            "confirmed_total": "REAL NOT NULL DEFAULT 0",
            "fee_freeze_json": "TEXT",
        }
        for col, decl in alters.items():
            if col not in cols:
                c.execute(f"ALTER TABLE drafts ADD COLUMN {col} {decl}")
        # Backfill open_min_deadline for rows that predate the column (created_at + 48h).
        c.execute(
            """
            UPDATE drafts
               SET open_min_deadline = created_at + 172800
             WHERE open_min_deadline = 0 OR open_min_deadline IS NULL
            """
        )


def row_to_dict(row) -> dict:
    if row is None:
        return {}
    return {k: row[k] for k in row.keys()}
