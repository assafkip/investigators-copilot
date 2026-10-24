"""Gravatar: email -> public profile + linked accounts. Keyless, T3.

Ported from assafkip/kipi investigations/enrich/gravatar.py. Gravatar keys a
public profile by the MD5 of the trimmed, lowercased address (and the newer
SHA-256 form). A 404 is a real answer (no public Gravatar), not a failure.
Every linked account is SELF-ASSERTED by the profile owner: a T3 lead.
"""
from __future__ import annotations

import hashlib
import json

from ._identity_common import T3_NOTE, clean_email, fetch, http_url_or_none, lead
from .base import Adapter, EnrichmentError

PROFILE_URL = "https://en.gravatar.com/{hash}.json"
AVATAR_URL = "https://gravatar.com/avatar/{hash}"


def email_hash(email: str) -> str:
    return hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest()  # noqa: S324 (Gravatar's id)


def fetch_profile(digest: str, timeout: int) -> dict | None:
    """Profile entry dict, None on 404; raises on any other failure."""
    status, body = fetch(PROFILE_URL.format(hash=digest), timeout=timeout,
                         headers={"Accept": "application/json"})
    if status == 404:
        return None
    if status != 200:
        raise EnrichmentError(f"gravatar: HTTP {status}")
    try:
        entries = json.loads(body).get("entry") or []
    except (json.JSONDecodeError, AttributeError) as exc:
        raise EnrichmentError("gravatar: non-JSON profile body (rate limited or down)") from exc
    return entries[0] if entries and isinstance(entries[0], dict) else {}


def _account_rows(email: str, accounts: list) -> list:
    rows = []
    for acct in accounts:
        url = http_url_or_none(acct.get("url"))
        if not url:
            continue
        svc = acct.get("shortname") or acct.get("domain") or "account"
        rows.append(lead(f"{svc}: {acct.get('username') or url}",
                         f"Linked from {email}'s Gravatar profile (self-asserted). {T3_NOTE}", url=url,
                         raw={"service": svc, "username": acct.get("username"), "verified": acct.get("verified")}))
    return rows


class GravatarAdapter(Adapter):
    slug = "gravatar"
    display_name = "Gravatar (email -> profile + linked accounts)"
    category = "identity"
    tier = "T3"
    watched_types = ("email",)

    def run(self, query, mode=None, timeout=30):
        email = clean_email(query, self.slug)
        digest = email_hash(email)
        entry = fetch_profile(digest, timeout)
        if entry is None:
            return [lead(f"Gravatar: {email} [no profile]", "No public Gravatar profile for this address.",
                         raw={"email": email, "hash": digest, "profile": False}, rtype="document")]
        accounts = [a for a in entry.get("accounts") or [] if isinstance(a, dict)]
        display = entry.get("displayName") or entry.get("preferredUsername") or ""
        facts = {"email": email, "hash": digest, "display_name": display,
                 "username": entry.get("preferredUsername"), "location": entry.get("currentLocation"),
                 "about": entry.get("aboutMe"), "avatar": AVATAR_URL.format(hash=digest),
                 "linked_accounts": len(accounts)}
        summary = "\n".join(f"{k}: {v}" for k, v in facts.items() if v not in (None, "")) + "\n" + T3_NOTE
        url = http_url_or_none(entry.get("profileUrl")) or f"https://gravatar.com/{digest}"
        header = lead(f"Gravatar: {email}" + (f" -- {display}" if display else ""), summary,
                      url=url, raw=facts, rtype="profile", confidence="medium")
        return [header] + _account_rows(email, accounts)
