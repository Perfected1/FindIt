"""Outgoing mail. Tries Brevo HTTPS API, plain SMTP, or log-print (dev)."""
import json
import os
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from flask import current_app

from .config import BREVO_API_KEY, MAIL_FROM, SMTP_HOST


def send_email(to, subject, text):
    """True if the mail provider accepted it."""
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
            current_app.logger.exception("Brevo could not send email to %s", to)
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
        current_app.logger.exception("Could not send email to %s", to)
        return False
