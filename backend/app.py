"""FindIt API. Thin wiring: routes + CORS; logic lives in config/db/helpers/email/review."""
import os
import secrets
from datetime import date

from flask import Flask, abort, jsonify, redirect, request, url_for

from .config import ALLOWED_ORIGINS, BASE_URL
from .db import close_db, get_db, init_db
from .email import send_email
from .helpers import body, date_field, email_field, field, public_item, reference
from .review import item_by_token, review_response

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024
app.teardown_appcontext(close_db)


@app.errorhandler(400)
def bad_request(err):
    return jsonify({"error": err.description}), 400


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


init_db()

if __name__ == "__main__":
    # Local dev: python -m backend.app  (from repo root)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=os.environ.get("FLASK_DEBUG") == "1")
