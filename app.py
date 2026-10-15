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


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db:
        db.close()


@app.errorhandler(400)
def bad_request(err):
    return jsonify({"error": err.description}), 400


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "Send a JSON object")
    return data


def field(data, name, label, max_len, required=True):
    value = data.get(name) or ""
    if not isinstance(value, str):
        abort(400, f"{label} must be text")
    value = value.strip()
    if required and not value:
        abort(400, f"{label} is required")
    if len(value) > max_len:
        abort(400, f"{label} is too long")
    return value


def email_field(data):
    """Email is entered twice (README); both must match."""
    email = field(data, "email", "Email", 254)
    if not EMAIL_RE.match(email):
        abort(400, "Enter a valid email address")
    if email.lower() != field(data, "email_confirm", "Email confirmation", 254).lower():
        abort(400, "The two email addresses do not match")
    return email


def date_field(data, name, label):
    """Optional YYYY-MM-DD date that isn't in the future; '' if not given."""
    value = field(data, name, label, 10, required=False)
    if value:
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            abort(400, f"{label} must look like 2026-10-31")
        if parsed > date.today() + timedelta(days=1):  # a day of slack for time zones
            abort(400, f"{label} can't be in the future")
    return value


def reference(item_id):
    return f"FND-{item_id:04d}"


def public_item(row):
    """What everyone may see: never the email or the review token."""
    return {"id": row["id"], "reference": reference(row["id"]), "title": row["title"],
            "description": row["description"], "category": row["category"], "location": row["location"],
            "found_on": row["found_on"]}


def send_email(to, subject, text):
    """True if the mail provider accepted it. Tries, in order: Brevo's HTTPS API
    (BREVO_API_KEY), plain SMTP (SMTP_HOST), or prints it (development)."""
    subject = " ".join(subject.split())  # no line breaks in headers
    if BREVO_API_KEY:
        request_ = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=json.dumps({"sender": {"email": MAIL_FROM}, "to": [{"email": to}],
                             "subject": subject, "textContent": text}).encode(),
            headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json",
                     "Accept": "application/json"})
        try:
            urllib.request.urlopen(request_, timeout=10).close()
            return True
        except (urllib.error.URLError, OSError):
            app.logger.exception("Brevo could not send email to %s", to)
            return False

    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = MAIL_FROM, to, subject
    msg.set_content(text)
    if not SMTP_HOST:
        print(f"\n--- email (no mail provider set) ---\nTo: {to}\nSubject: {subject}\n\n{text}\n")
        return True
    try:
        with smtplib.SMTP(SMTP_HOST, int(os.environ.get("SMTP_PORT", "587")), timeout=10) as smtp:
            smtp.starttls()
            if os.environ.get("SMTP_USER"):
                smtp.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
            smtp.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError):
        app.logger.exception("Could not send email to %s", to)
        return False
