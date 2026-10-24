"""Hacker News profile via the official Firebase API. Keyless, T3.

Ported from assafkip/hydra src/osint/hackernews-user.ts. The API returns JSON
`null` (not 404) for a nonexistent user. Links and emails in the free-text
`about` bio are pulled out as leads (capped).
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import urllib.parse

from ._identity_common import T3_NOTE, clean_handle, fetch, http_url_or_none, lead
from .base import Adapter, EnrichmentError

ENDPOINT = "https://hacker-news.firebaseio.com/v0/user/{id}.json"
EMAIL_RE = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", re.I)
URL_RE = re.compile(r"https?://[^\s\"'<>)]+", re.I)
MAX_BIO_PIVOTS = 25


def bio_pivots(user_id: str, about: str) -> list:
    text = html.unescape(about)  # keep tags: the link lives in href="..."
    rows = []
    for raw in list(dict.fromkeys(URL_RE.findall(text)))[:MAX_BIO_PIVOTS]:
        url = http_url_or_none(raw.rstrip(".,;"))
        if url:
            rows.append(lead(f"link in HN bio of {user_id}", url, url=url))
    for email in list(dict.fromkeys(e.lower() for e in EMAIL_RE.findall(text)))[:MAX_BIO_PIVOTS]:
        rows.append(lead(email.lower(), f"Email in HN bio of {user_id} (self-asserted).", rtype="record"))
    return rows


class HackernewsUserAdapter(Adapter):
    slug = "hackernews_user"
    display_name = "Hacker News user profile"
    category = "identity"
    tier = "T3"
    watched_types = ("handle",)

    def run(self, query, mode=None, timeout=30):
        user_id = clean_handle(query, self.slug)
        status, body = fetch(ENDPOINT.format(id=urllib.parse.quote(user_id)), timeout=timeout)
        if status != 200:
            raise EnrichmentError(f"hackernews_user: HTTP {status}")
        try:
            user = json.loads(body)
        except json.JSONDecodeError as exc:
            raise EnrichmentError("hackernews_user: non-JSON body") from exc
        profile = f"https://news.ycombinator.com/user?id={urllib.parse.quote(user_id)}"
        if user is None:
            return [lead(f"Hacker News: {user_id} [no such user]", "API returned null.",
                         raw={"id": user_id, "exists": False}, rtype="document")]
        if not isinstance(user, dict) or str(user.get("id", "")).lower() != user_id.lower():
            raise EnrichmentError("hackernews_user: response id does not match the query")
        created = user.get("created")
        facts = {"id": user.get("id"), "karma": user.get("karma"),
                 "created": dt.datetime.fromtimestamp(created, dt.timezone.utc).date().isoformat()
                 if isinstance(created, (int, float)) else None,
                 "submissions": len(user.get("submitted") or []), "about": (user.get("about") or "")[:500]}
        summary = "\n".join(f"{k}: {v}" for k, v in facts.items() if v not in (None, "")) + "\n" + T3_NOTE
        header = lead(f"Hacker News: {user_id}", summary, url=profile, raw=facts, rtype="profile",
                      confidence="medium")
        return [header] + bio_pivots(user_id, user.get("about") or "")
