"""GHunt wrapper: Google account behind an email. AGPL-3.0, subprocess only, T3.

Runs `ghunt email <email> --json <tmp>/out.json`. Needs a one-time interactive
`ghunt login` (stored by GHunt itself); without it the run fails and this
adapter raises NotConfiguredError. The JSON is walked generically (GHunt's
schema shifts between releases): Gaia id, display names, and every URL
(profile photo, Maps contributions, calendar) become leads.
Install: pipx install ghunt && ghunt login.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ._identity_common import T3_NOTE, BinAdapter, clean_email, http_url_or_none, lead
from .base import EnrichmentError, NotConfiguredError

ID_KEYS = {"personid", "gaiaid", "gaia_id"}
NAME_KEYS = {"fullname", "displayname", "full_name"}


def walk(node, found: dict) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, (str, int)) and key.lower() in ID_KEYS:
                found["ids"].add(str(value))
            elif isinstance(value, str) and key.lower() in NAME_KEYS and value.strip():
                found["names"].add(value.strip())
            walk(value, found)
    elif isinstance(node, list):
        for item in node:
            walk(item, found)
    elif isinstance(node, str) and http_url_or_none(node):
        found["urls"].add(node)


def extract(data) -> dict:
    found = {"ids": set(), "names": set(), "urls": set()}
    walk(data, found)
    return {k: sorted(v) for k, v in found.items()}


class GhuntAdapter(BinAdapter):
    slug = "ghunt"
    display_name = "GHunt Google-account lookup (subprocess)"
    requires_bin = ("ghunt",)
    watched_types = ("email",)
    license_note = "AGPL-3.0: subprocess only, never imported"

    def run(self, query, mode=None, timeout=180):
        email = clean_email(query, self.slug)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            proc = self.exec_tool(["ghunt", "email", email, "--json", str(out)], timeout=max(timeout, 120))
            if not out.is_file():
                text = f"{proc.stdout}\n{proc.stderr}".lower()
                if "login" in text or "creds" in text or "cookies" in text:
                    raise NotConfiguredError("ghunt: not logged in (run `ghunt login` once, interactively)")
                raise self.fail(proc, "no JSON written (account not found or GHunt error)")
            try:
                info = extract(json.loads(out.read_text()))
            except json.JSONDecodeError as exc:
                raise EnrichmentError("ghunt: unreadable JSON output") from exc
        header = lead(f"GHunt: {email} -- gaia {', '.join(info['ids']) or 'unknown'}",
                      f"names: {', '.join(info['names']) or 'none'}\nurls: {len(info['urls'])}\n{T3_NOTE}",
                      raw={"email": email, **info}, rtype="profile", confidence="medium")
        return [header] + [lead(f"GHunt link for {email}", url, url=url) for url in info["urls"][:40]]
