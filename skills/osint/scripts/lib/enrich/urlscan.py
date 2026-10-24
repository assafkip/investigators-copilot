"""urlscan.io passive search of EXISTING scans: related domains + IPs. T3.

Ported from assafkip/kipi investigations/enrich/urlscan.py. Never submits a new scan
(that is an active, logged action that can leak the target). Public search works
keyless (rate limited); $URLSCAN_API_KEY raises the quota.
"""
from __future__ import annotations

import os

from . import _common as c
from .base import Adapter, EnrichmentError

_SEARCH = "https://urlscan.io/api/v1/search/"
_MAX_NODES = 50


def build_query(target: str) -> str:
    host = c.bare_host(target)
    return f"ip:{host}" if c.is_ip(host) else f"domain:{host}"


class UrlscanAdapter(c.OptionalKeyMixin, Adapter):
    slug = "urlscan"
    display_name = "urlscan.io (search existing scans)"
    env_var = "URLSCAN_API_KEY"
    signup_url = "https://urlscan.io/user/signup"
    category = "reputation"
    tier = "T3"
    watched_types = ("domain", "url", "ip")

    def run(self, query, mode=None, timeout=30):
        if not (query or "").strip():
            raise EnrichmentError("urlscan: empty query")
        key = os.environ.get(self.env_var, "").strip()
        q = build_query(query)
        data = c.get_json(f"{_SEARCH}?{c.qs({'q': q, 'size': 100})}", timeout=timeout,
                          headers={"API-Key": key} if key else None)
        results = data.get("results") or []
        domains, ips = {}, {}
        for r in results:
            page = r.get("page") or {}
            if page.get("domain"):
                domains.setdefault(page["domain"].lower(), page.get("server") or "")
            if page.get("ip"):
                ips.setdefault(page["ip"], page.get("asnname") or "")
        latest = (results[0].get("task") or {}) if results else {}
        header = c.res(self, "document", f"urlscan: {q}",
                       f"{data.get('total', len(results))} scan(s); latest {str(latest.get('time', ''))[:10]} "
                       f"{latest.get('url', '')}\nrelated domains: {len(domains)}; related IPs: {len(ips)}",
                       url=f"https://urlscan.io/search/#{q}",
                       raw_json={"query": q, "total": data.get("total"), "domains": sorted(domains),
                                 "ips": sorted(ips)}, confidence="medium")
        nodes = [c.res(self, "url", d, f"Seen in urlscan scans for {q} (server {s or '?'}).",
                       url=f"http://{d}", confidence="medium") for d, s in sorted(domains.items())]
        nodes += [c.res(self, "record", ip, f"IP serving pages in urlscan scans for {q} ({a or '?'}).",
                        confidence="medium") for ip, a in sorted(ips.items())]
        return [header] + nodes[:_MAX_NODES]
