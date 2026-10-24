"""StopForumSpam: crowd-reported spam frequency for an IP, email or username. Keyless, T3.

Ported from hydra src/osint/stopforumspam.ts (extended to email/username, which the
same API accepts). Mode: ip | email | username (auto-detected by default).
"""
from __future__ import annotations

from . import _common as c
from .base import Adapter, EnrichmentError

_URL = "https://api.stopforumspam.org/api"


class StopForumSpamAdapter(Adapter):
    slug = "stopforumspam"
    display_name = "StopForumSpam (spam reports)"
    category = "reputation"
    tier = "T3"
    watched_types = ("ip", "email", "handle")

    def modes(self):
        return ["auto", "ip", "email", "username"]

    def run(self, query, mode=None, timeout=30):
        q = (query or "").strip()
        if not q:
            raise EnrichmentError("stopforumspam: empty query")
        kind = mode if mode in ("ip", "email", "username") else \
            "ip" if c.is_ip(q) else "email" if "@" in q else "username"
        body = c.get_json(f"{_URL}?{c.qs({kind: q, 'json': ''})}", timeout=timeout)
        if not isinstance(body, dict) or body.get("success") != 1:
            raise EnrichmentError(f"StopForumSpam: {(body or {}).get('error', 'request failed')}")
        rec = body.get(kind) or {}
        appears = rec.get("appears") or 0
        summary = (f"reported {rec.get('frequency', 0)} time(s); last seen {rec.get('lastseen', '?')}"
                   + (f"; country {rec['country']}" if rec.get("country") else "")
                   if appears else "no spam reports on record")
        return [c.res(self, "document", f"StopForumSpam {kind}: {q}", summary,
                      url=f"https://www.stopforumspam.com/search?q={q}", raw_json=rec,
                      confidence="medium" if appears else "low")]
