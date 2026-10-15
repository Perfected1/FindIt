"""Request validation + public serializers. Aborts 400 on bad input."""
from datetime import date, timedelta

from flask import abort, request

from .config import EMAIL_RE


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
