"""SQLite setup. One file DB; call init_db() once at import."""
import os
import sqlite3

from flask import g

from .config import DATABASE

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL,                 -- public
    category     TEXT NOT NULL DEFAULT 'Other', -- public
    location     TEXT NOT NULL DEFAULT '',      -- public, optional
    found_on     TEXT NOT NULL,                 -- YYYY-MM-DD
    email        TEXT NOT NULL,                 -- private
    review_token TEXT NOT NULL UNIQUE,          -- private link sent to the reporter
    status       TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'returned'))
);
CREATE TABLE IF NOT EXISTS claims (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     INTEGER NOT NULL REFERENCES items(id),
    description TEXT NOT NULL,                  -- what the item is
    details     TEXT NOT NULL,                  -- identifying details only the owner knows
    lost_where  TEXT NOT NULL DEFAULT '',       -- where they think they lost it
    lost_on     TEXT NOT NULL DEFAULT '',       -- YYYY-MM-DD
    email       TEXT NOT NULL,
    phone       TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'match', 'no_match'))
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(exception):
    db = g.pop("db", None)
    if db:
        db.close()


def init_db():
    os.makedirs(os.path.dirname(os.path.abspath(DATABASE)) or ".", exist_ok=True)
    with sqlite3.connect(DATABASE) as _db:
        _db.executescript(SCHEMA)
        if "category" not in [row[1] for row in _db.execute("PRAGMA table_info(items)")]:
            # database created before categories existed
            _db.execute("ALTER TABLE items ADD COLUMN category TEXT NOT NULL DEFAULT 'Other'")
