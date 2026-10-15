"""Shared env config. All secrets come from the environment, never hardcoded."""
import os
import re

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
