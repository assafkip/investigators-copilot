"""GitLab profile lookup via gitlab.com/api/v4/users?username=. Keyless, T3.

Ported from assafkip/hydra src/osint/gitlab-user.ts. GITLAB_TOKEN is optional
(PRIVATE-TOKEN header, higher limits). Username-match guard: only an object whose
username equals the query is accepted.
"""
from __future__ import annotations

import json
import os
import urllib.parse

from ._identity_common import EMAIL_RE, T3_NOTE, clean_handle, fetch, http_url_or_none, lead
from .base import Adapter, EnrichmentError

ENDPOINT = "https://gitlab.com/api/v4/users?username="


def fetch_user(username: str, timeout: int) -> dict | None:
    headers = {"Accept": "application/json"}
    if os.environ.get("GITLAB_TOKEN", "").strip():
        headers["PRIVATE-TOKEN"] = os.environ["GITLAB_TOKEN"].strip()
    status, body = fetch(ENDPOINT + urllib.parse.quote(username), timeout=timeout, headers=headers)
    if status != 200:
        raise EnrichmentError(f"gitlab_user: HTTP {status}")
    try:
        users = json.loads(body)
    except json.JSONDecodeError as exc:
        raise EnrichmentError("gitlab_user: non-JSON body") from exc
    if not isinstance(users, list):
        raise EnrichmentError("gitlab_user: unexpected response shape")
    return next((u for u in users if isinstance(u, dict)
                 and str(u.get("username", "")).lower() == username.lower()), None)


class GitlabUserAdapter(Adapter):
    slug = "gitlab_user"
    display_name = "GitLab user profile (gitlab.com API)"
    category = "identity"
    tier = "T3"
    watched_types = ("handle",)

    def run(self, query, mode=None, timeout=30):
        username = clean_handle(query, self.slug)
        user = fetch_user(username, timeout)
        if user is None:
            return [lead(f"GitLab: {username} [no public user]", "gitlab.com returned no matching user.",
                         raw={"username": username, "exists": False}, rtype="document")]
        keep = ("username", "id", "name", "state", "public_email", "location", "bio", "organization",
                "job_title", "website_url", "twitter", "linkedin", "created_at")
        facts = {k: user.get(k) for k in keep}
        summary = "\n".join(f"{k}: {v}" for k, v in facts.items() if v not in (None, "")) + "\n" + T3_NOTE
        rows = [lead(f"GitLab: {username}" + (f" -- {user['name']}" if user.get("name") else ""), summary,
                     url=http_url_or_none(user.get("web_url")) or f"https://gitlab.com/{username}",
                     raw=facts, rtype="profile", confidence="medium")]
        email = user.get("public_email") or ""
        if EMAIL_RE.match(email):
            rows.append(lead(email.lower(), f"Public email on GitLab profile of {username}.", rtype="record"))
        site = http_url_or_none(user.get("website_url"))
        if site:
            rows.append(lead(f"website of {username}", f"GitLab website field of {username}.", url=site))
        return rows
