"""npm maintainer -> packages via the anonymous registry search. Keyless, T3.

Ported from assafkip/hydra src/osint/npm-user.ts. Each package yields its npm
page and source repo; only the publisher email belonging to THIS username is a
lead (a co-maintainer's email is not). Package authorship is self-asserted.
"""
from __future__ import annotations

import json
import re
import urllib.parse

from ._identity_common import EMAIL_RE, T3_NOTE, clean_handle, fetch, http_url_or_none, lead
from .base import Adapter, EnrichmentError

ENDPOINT = "https://registry.npmjs.org/-/v1/search"
PKG_RE = re.compile(r"^(@[a-z0-9][a-z0-9._~-]*/)?[a-z0-9][a-z0-9._~-]*$")
MAX_PACKAGES = 25


def search(username: str, timeout: int) -> list[dict]:
    url = ENDPOINT + "?" + urllib.parse.urlencode({"text": f"maintainer:{username}", "size": MAX_PACKAGES})
    status, body = fetch(url, timeout=timeout, headers={"Accept": "application/json"})
    if status != 200:
        raise EnrichmentError(f"npm_user: HTTP {status}")
    try:
        objects = json.loads(body).get("objects")
    except (json.JSONDecodeError, AttributeError) as exc:
        raise EnrichmentError("npm_user: unexpected response body") from exc
    if not isinstance(objects, list):
        raise EnrichmentError("npm_user: unexpected response shape")
    return [o.get("package") for o in objects[:MAX_PACKAGES] if isinstance(o, dict) and o.get("package")]


def package_rows(username: str, pkg: dict) -> tuple[list, str | None]:
    rows, name = [], str(pkg.get("name") or "")
    if PKG_RE.match(name):
        path = "/".join(urllib.parse.quote(p, safe="@") for p in name.split("/"))
        rows.append(lead(f"npm: {name}", f"Package maintained by {username}.",
                         url=f"https://www.npmjs.com/package/{path}"))
    repo = (pkg.get("links") or {}).get("repository") or ""
    repo = http_url_or_none(repo.removeprefix("git+").removesuffix(".git"))
    if repo:
        rows.append(lead(f"source repo of {name}", f"Repository of a {username} package.", url=repo))
    pub = pkg.get("publisher") or {}
    email = pub.get("email") or ""
    mine = str(pub.get("username", "")).lower() == username.lower() and EMAIL_RE.match(email)
    return rows, (email.lower() if mine else None)


class NpmUserAdapter(Adapter):
    slug = "npm_user"
    display_name = "npm maintainer packages (registry search)"
    category = "identity"
    tier = "T3"
    watched_types = ("handle",)

    def run(self, query, mode=None, timeout=30):
        username = clean_handle(query, self.slug)
        rows, emails = [], []
        for pkg in search(username, timeout):
            pkg_rows, email = package_rows(username, pkg)
            rows += pkg_rows
            if email and email not in emails:
                emails.append(email)
        rows += [lead(e, f"npm publisher email of {username}.", rtype="record") for e in emails]
        header = lead(f"npm: {username} -- {sum(1 for r in rows if r.title.startswith('npm: '))} package(s)",
                      f"Packages found by maintainer:{username} search. {T3_NOTE}",
                      url=f"https://www.npmjs.com/~{urllib.parse.quote(username)}",
                      raw={"username": username, "publisher_emails": emails}, rtype="document",
                      confidence="medium")
        return [header] + rows
