"""GitHub profile lookup via api.github.com. Keyless (GITHUB_TOKEN optional), T3.

Ported from assafkip/hydra src/osint/github-user.ts. Every profile field (name,
company, blog, email, twitter) is SELF-ASSERTED by the account owner: a T3 lead.
Login-echo guard: the API's login must equal the query, else the response is
refused (never attribute another account to the queried handle).
"""
from __future__ import annotations

import json
import re
import urllib.parse

from ._identity_common import EMAIL_RE, T3_NOTE, clean_handle, fetch, github_headers, http_url_or_none, lead
from .base import Adapter, EnrichmentError

ENDPOINT = "https://api.github.com/users/"
TWITTER_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")


def fetch_user(login: str, timeout: int) -> dict | None:
    status, body = fetch(ENDPOINT + urllib.parse.quote(login), timeout=timeout, headers=github_headers())
    if status == 404:
        return None
    if status != 200:
        raise EnrichmentError(f"github_user: HTTP {status} (403/429 = rate limit; set GITHUB_TOKEN)")
    try:
        user = json.loads(body)
    except json.JSONDecodeError as exc:
        raise EnrichmentError("github_user: non-JSON body") from exc
    if not isinstance(user, dict) or str(user.get("login", "")).lower() != login.lower():
        raise EnrichmentError("github_user: response login does not match the query")
    return user


def pivots(login: str, user: dict) -> list:
    rows = []
    if user.get("company"):
        rows.append(lead(str(user["company"]).lstrip("@"), f"GitHub company field of {login} (self-asserted).",
                         rtype="record"))
    blog = user.get("blog") or ""
    blog = http_url_or_none(blog if blog.startswith("http") else f"https://{blog}") if blog else None
    if blog:
        rows.append(lead(f"blog of {login}", f"GitHub blog field of {login}.", url=blog))
    if user.get("email") and EMAIL_RE.match(user["email"]):
        rows.append(lead(user["email"].lower(), f"Public email on GitHub profile of {login}.", rtype="record"))
    twitter = str(user.get("twitter_username") or "").lstrip("@")
    if twitter and TWITTER_RE.match(twitter):
        rows.append(lead(f"Twitter/X: {twitter}", f"Linked on GitHub profile of {login} (self-asserted).",
                         url=f"https://x.com/{twitter}"))
    return rows


class GithubUserAdapter(Adapter):
    slug = "github_user"
    display_name = "GitHub user profile (api.github.com)"
    category = "identity"
    tier = "T3"
    watched_types = ("handle",)
    signup_url = "https://github.com/settings/tokens (optional GITHUB_TOKEN)"

    def run(self, query, mode=None, timeout=30):
        login = clean_handle(query, self.slug)
        user = fetch_user(login, timeout)
        if user is None:
            return [lead(f"GitHub: {login} [no such user]", "api.github.com returned 404.",
                         raw={"login": login, "exists": False}, rtype="document")]
        keep = ("login", "id", "name", "company", "blog", "location", "email", "bio", "twitter_username",
                "public_repos", "followers", "following", "created_at", "updated_at")
        facts = {k: user.get(k) for k in keep}
        summary = "\n".join(f"{k}: {v}" for k, v in facts.items() if v not in (None, "")) + "\n" + T3_NOTE
        header = lead(f"GitHub: {login}" + (f" -- {user['name']}" if user.get("name") else ""), summary,
                      url=http_url_or_none(user.get("html_url")) or f"https://github.com/{login}",
                      raw=facts, rtype="profile", confidence="medium")
        return [header] + pivots(login, user)
