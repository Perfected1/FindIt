"""Reporter review page (private token link from the claim email)."""
from flask import abort, render_template_string

from .db import get_db
from .helpers import reference

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
