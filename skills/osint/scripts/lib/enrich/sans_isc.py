"""SANS ISC / DShield: attack reports and threat-feed membership for an IP. Keyless, T3.

Ported from hydra src/osint/sans-isc.ts. Honeypot/firewall reports are a crowd feed,
never a crosslink.
"""
from __future__ import annotations

from . import _common as c
from .base import Adapter, EnrichmentError

_URL = "https://isc.sans.edu/api/ip/"


class SansIscAdapter(Adapter):
    slug = "sans_isc"
    display_name = "SANS ISC / DShield IP reports"
    category = "reputation"
    tier = "T3"
    watched_types = ("ip",)

    def run(self, query, mode=None, timeout=30):
        ip = c.require_ip(query, "sans_isc")
        body = c.get_json(f"{_URL}{ip}?json", timeout=timeout)
        rec = body.get("ip") if isinstance(body, dict) else None
        if not isinstance(rec, dict):
            raise EnrichmentError("SANS ISC: unexpected response shape")
        feeds = sorted((rec.get("threatfeeds") or {}).keys())
        summary = (f"reports: {rec.get('count') or 0}; targets: {rec.get('attacks') or 0}; "
                   f"AS: {rec.get('asname') or '?'} {rec.get('network') or ''}"
                   + (f"\nthreat feeds: {', '.join(feeds)}" if feeds else "")
                   + (f"\ncomment: {rec['comment']}" if rec.get("comment") else ""))
        return [c.res(self, "document", f"SANS ISC: {ip}", summary,
                      url=f"https://isc.sans.edu/ipinfo/{ip}", raw_json=rec,
                      confidence="medium" if rec.get("count") else "low")]
