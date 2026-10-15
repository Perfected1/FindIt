import json
import os
import re
import secrets
import smtplib
import sqlite3
import urllib.error
import urllib.request
from datetime import date, timedelta
from email.message import EmailMessage

from flask import (Flask, abort, g, jsonify, redirect, render_template_string,
                   request, url_for)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024

DATABASE = os.environ.get("FINDIT_DB", "findit.db")
BASE_URL = os.environ.get("FINDIT_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
SMTP_HOST = os.environ.get("SMTP_HOST")
BREVO_API_KEY = os.environ.get("BREVO_API_KEY")  # sends over HTTPS; use where SMTP ports are blocked
MAIL_FROM = os.environ.get("MAIL_FROM", "findit@localhost")
# Front ends allowed to call the API from a browser (comma-separated origins).
ALLOWED_ORIGINS = {o.strip() for o in os.environ.get(
    "FINDIT_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,https://findit-rosy.vercel.app"
).split(",") if o.strip()}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

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
