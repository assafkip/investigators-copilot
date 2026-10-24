"""Ahmia clearnet index of .onion sites (no Tor client needed). Keyless, T3 leads.

Ported from assafkip/kipi investigations/enrich/darkweb.py. Ahmia returns HTML;
onion hosts are regexed out. A search hit is a hypothesis, never a finding.
"""
from __future__ import annotations

import re
import urllib.parse

from . import _common as c
from .base import Adapter, EnrichmentError

_AHMIA = "https://ahmia.fi/search/?q="
_ONION_RE = re.compile(r"\b([a-z2-7]{16,56}\.onion)\b", re.IGNORECASE)


class DarkwebAdapter(Adapter):
    slug = "darkweb"
    display_name = "Ahmia .onion search"
    category = "search"
    tier = "T3"
    watched_types = ("domain", "org", "handle", "email", "text")

    def run(self, query, mode=None, timeout=60):
        q = (query or "").strip()
        if not q:
            raise EnrichmentError("darkweb: empty query")
        html = c.get_text(_AHMIA + urllib.parse.quote(q), timeout=timeout)
        if "ahmia" not in html.lower():
            raise EnrichmentError("darkweb: Ahmia returned an unrecognized page (blocked or changed)")
        hosts = list(dict.fromkeys(h.lower() for h in _ONION_RE.findall(html)))
        return [c.res(self, "url", h, f"Ahmia .onion hit for {q!r} (T3 lead, unverified).",
                      url=f"http://{h}", confidence="low") for h in hosts]
