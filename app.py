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

DATABASE = os.environ.get("FINDIT_DB", "/tmp/findit.db" if os.environ.get("VERCEL") else "findit.db")
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

@app.route("/api/items", methods=["GET"])
def list_items():
    """Open items only: a matched item leaves the feed."""
    q = request.args.get("q", "").strip()
    name = request.args.get("item", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()

    sql, params = "SELECT * FROM items WHERE status = 'open'", []
    if q:
        sql += " AND (title LIKE ? OR description LIKE ? OR location LIKE ?)"
        params += [f"%{q}%"] * 3
    if name:
        sql += " AND title LIKE ?"
        params.append(f"%{name}%")
    if date_from:
        sql += " AND found_on >= ?"
        params.append(date_from)
    if date_to:
        sql += " AND found_on <= ?"
        params.append(date_to)

    rows = get_db().execute(sql + " ORDER BY id DESC", params).fetchall()
    return jsonify([public_item(r) for r in rows])


@app.route("/api/items", methods=["POST"])
def create_item():
    """JSON: title, description, email, email_confirm (required);
    category, location, found_on 'YYYY-MM-DD' (optional; category defaults to 'Other',
    found_on to today and can't be in the future)."""
    data = body()
    title = field(data, "title", "Item name", 100)
    description = field(data, "description", "Description", 2000)
    category = field(data, "category", "Category", 50, required=False) or "Other"
    location = field(data, "location", "Location", 200, required=False)
    email = email_field(data)
    found_on = date_field(data, "found_on", "Date found") or date.today().isoformat()

    db = get_db()
    cur = db.execute(
        "INSERT INTO items (title, description, category, location, found_on, email, review_token) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title, description, category, location, found_on, email, secrets.token_urlsafe(24)))
    db.commit()
    row = db.execute("SELECT * FROM items WHERE id = ?", (cur.lastrowid,)).fetchone()
    return jsonify(public_item(row)), 201

@app.route("/api/items/<int:item_id>/claims", methods=["POST"])
def create_claim(item_id):
    """JSON: description, email, email_confirm (required);
    details, phone, lost_where, lost_on 'YYYY-MM-DD' (optional).
    The claim goes to the reporter's mailbox. Nothing here lets anyone read it."""
    db = get_db()
    item = db.execute("SELECT * FROM items WHERE id = ? AND status = 'open'", (item_id,)).fetchone()
    if item is None:
        return jsonify({"error": "This item is not available to claim"}), 404

    data = body()
    description = field(data, "description", "Description", 2000)
    details = field(data, "details", "Identifying details", 2000, required=False)
    lost_where = field(data, "lost_where", "Where it was lost", 200, required=False)
    lost_on = date_field(data, "lost_on", "Date lost")
    email = email_field(data)
    phone = field(data, "phone", "Phone", 30, required=False)

    cur = db.execute(
        "INSERT INTO claims (item_id, description, details, lost_where, lost_on, email, phone) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (item_id, description, details, lost_where, lost_on, email, phone))
    db.commit()

    lost_note = " (note: that is after the day you found it)" if lost_on and lost_on > item["found_on"] else ""
    sent = send_email(item["email"], f"Claim on your found item {reference(item_id)}: {item['title']}", f"""\
Someone says this is theirs: {reference(item_id)} - {item['title']}

THE ITEM YOU REPORTED
{item['description']}
Category: {item['category']}
Found: {item['found_on']} {item['location']}

THEIR DESCRIPTION
{description}

IDENTIFYING DETAILS THEY GAVE
{details or 'none given'}

LOST: {lost_on or 'date not given'}, {lost_where or 'place not given'}{lost_note}

THEIR CONTACT
Email: {email}
Phone: {phone or 'not given'}

Compare their description with the item, then mark it as a match or not here
(all claims on this item are listed on that page):
{BASE_URL}/review/{item['review_token']}

Keep this link private: anyone who has it can see the claims.
""")
    if not sent:  # don't keep a claim the reporter never received
        db.execute("DELETE FROM claims WHERE id = ?", (cur.lastrowid,))
        db.commit()
        return jsonify({"error": "We couldn't deliver your claim. Please try again later."}), 502
    return jsonify({"message": "Your claim was emailed to the person who found the item."}), 201


# ---------- Reporter review (private link from the email) ----------

REVIEW_PAGE = """<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claims for {{ ref }}</title>
<style>
 body{font-family:system-ui,sans-serif;max-width:640px;margin:1.5rem auto;padding:0 1rem}
 .box{border:1px solid #8884;border-radius:8px;padding:.75rem 1rem;margin:.75rem 0;white-space:pre-wrap}
 .note{background:#8882;border-radius:8px;padding:.75rem 1rem}
 button{padding:.5rem 1rem;margin-right:.5rem}
</style>
<h1>{{ item.title }} ({{ ref }})</h1>
<div class="box">{{ item.description }}
Category: {{ item.category }}
Found: {{ item.found_on }} {{ item.location }}</div>
{% if item.status == 'returned' %}<p class="note">Match confirmed. This item is no longer in the feed. Reach out to the claimant below.</p>{% endif %}
{% if error %}<p class="note">{{ error }}</p>{% endif %}
<h2>Claims ({{ claims|length }})</h2>
{% for c in claims %}
<div class="box"><b>{{ {'match': 'Match', 'no_match': 'Not a match'}.get(c.status, 'Awaiting your review') }}</b>
{{ c.description }}
Identifying details: {{ c.details or 'none given' }}
Lost: {{ c.lost_on or 'date not given' }}, {{ c.lost_where or 'place not given' }}{% if c.lost_on and c.lost_on > item.found_on %} (note: after the day it was found){% endif %}
{% if c.status != 'no_match' %}Email: {{ c.email }}{% if c.phone %} / Phone: {{ c.phone }}{% endif %}{% endif %}</div>
{% if c.status == 'pending' and item.status == 'open' %}
<form method="post" action="{{ url_for('review_decide', token=token, claim_id=c.id) }}">
 <button name="decision" value="match">This is a match</button>
 <button name="decision" value="no_match">Not a match</button>
</form>
{% endif %}
{% else %}<p>No claims yet.</p>{% endfor %}"""


def item_by_token(token):
    item = get_db().execute("SELECT * FROM items WHERE review_token = ?", (token,)).fetchone()
    return item or abort(404)


def review_response(token, error=None, status=200):
    db = get_db()
    item = item_by_token(token)
    claims = db.execute("SELECT * FROM claims WHERE item_id = ? ORDER BY id", (item["id"],)).fetchall()
    page = render_template_string(REVIEW_PAGE, item=item, claims=claims, token=token,
                                  ref=reference(item["id"]), error=error)
    return page, status


@app.before_request
def handle_preflight():
    """Answer CORS preflights explicitly so the Vite dev server / Vercel frontend
    never gets a 405 on OPTIONS."""
    if request.method == "OPTIONS" and request.path.startswith("/api/"):
        return ("", 204)


@app.after_request
def allow_frontend(resp):
    """CORS: the React front end is served from a different origin than this API."""
    if request.path.startswith("/api/") and request.headers.get("Origin") in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = request.headers["Origin"]
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
        resp.headers["Vary"] = "Origin"
    return resp


@app.after_request
def keep_token_private(resp):
    if request.path.startswith("/review/"):
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@app.route("/review/<token>")
def review_page(token):
    return review_response(token)


@app.route("/review/<token>/claims/<int:claim_id>", methods=["POST"])
def review_decide(token, claim_id):
    decision = request.form.get("decision")
    if decision not in ("match", "no_match"):
        abort(400, "Choose match or not a match")
    db = get_db()
    item_id = item_by_token(token)["id"]
    # Atomic: only one claim can win, and only while the item is still open.
    ok = decision == "no_match" or db.execute(
        "UPDATE items SET status = 'returned' WHERE id = ? AND status = 'open'", (item_id,)).rowcount
    ok = ok and db.execute(
        "UPDATE claims SET status = ? WHERE id = ? AND item_id = ? AND status = 'pending'",
        (decision, claim_id, item_id)).rowcount
    if not ok:
        db.rollback()
        return review_response(token, "That claim was already reviewed, or a match is already confirmed.", 409)
    db.commit()
    return redirect(url_for("review_page", token=token), code=303)



@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


os.makedirs(os.path.dirname(os.path.abspath(DATABASE)) or ".", exist_ok=True)

with sqlite3.connect(DATABASE) as _db:
    _db.executescript(SCHEMA)
    if "category" not in [row[1] for row in _db.execute("PRAGMA table_info(items)")]:
        # database created before categories existed
        _db.execute("ALTER TABLE items ADD COLUMN category TEXT NOT NULL DEFAULT 'Other'")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=os.environ.get("FLASK_DEBUG") == "1")
