"""HackerTarget reverse-IP: the other domains hosted on the same IPv4. Keyless, T3.

Ported from hydra src/osint/reverse-ip.ts. Co-hosting is a weak shared-hosting
signal, never proof of a relationship (a big shared host has hundreds of unrelated
tenants), so every row is a T3 lead. HackerTarget reports EVERY failure (bad IP,
quota) as a plaintext body with HTTP 200; those raise, never read as "no neighbors".
Free tier: about 50 queries/day per source IP.
"""
from __future__ import annotations

from . import _common as c
from .base import Adapter, EnrichmentError

_URL = "https://api.hackertarget.com/reverseiplookup/"


class ReverseIpAdapter(Adapter):
    slug = "reverse_ip"
    display_name = "HackerTarget reverse IP (co-hosted domains)"
    signup_url = "https://hackertarget.com/ip-tools/"
    category = "infra"
    tier = "T3"
    watched_types = ("ip",)

    def run(self, query, mode=None, timeout=30):
        ip = c.require_ip(query, "reverse_ip", v4_only=True)
        text = c.get_text(f"{_URL}?{c.qs({'q': ip})}", timeout=timeout).strip()
        low = text.lower()
        if low.startswith("no dns a records"):
            return []
        if not text or low.startswith("error") or "api count exceeded" in low:
            raise EnrichmentError(f"HackerTarget: {text[:120] or 'empty response'}")
        domains = []
        for line in text.splitlines():
            d = line.strip().lower().rstrip(".")
            if c.DOMAIN_RE.match(d) and d not in domains:
                domains.append(d)
        warning = c.volume_warning(len(domains), "co-hosted domains")
        header = c.res(self, "document", f"reverse IP: {ip} -- {len(domains)} co-hosted domain(s)",
                       "Shared-hosting neighbors: a lead, not proof of a relationship."
                       + (f"\n{warning}" if warning else ""),
                       raw_json={"ip": ip, "domains": domains}, confidence="low")
        rows = [] if warning else [c.res(self, "url", d, f"Co-hosted on {ip} (HackerTarget).",
                                         url=f"http://{d}", confidence="low") for d in domains]
        return [header] + rows
