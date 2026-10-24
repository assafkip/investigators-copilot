"""Shodan host intelligence: open ports, services, hostnames, CVEs. T3 (scanner output).

Ported from assafkip/kipi investigations/enrich/shodan.py. Two tiers, chosen by key:
  - keyed ($SHODAN_API_KEY): full host record (banners, org, ASN, vulns)
  - keyless: internetdb.shodan.io (ports, CPEs, hostnames, tags, vulns; no banners)
A domain is resolved to its IP first (Shodan's resolver when keyed, else DoH).
"""
from __future__ import annotations

import os
import urllib.parse

from . import _common as c
from .base import Adapter, EnrichmentError, HTTPStatusError

_HOST = "https://api.shodan.io/shodan/host/"
_RESOLVE = "https://api.shodan.io/dns/resolve"
_INTERNETDB = "https://internetdb.shodan.io/"
_MAX_HOSTNAMES = 50


def _resolve(target: str, key: str, timeout: int) -> str:
    if c.is_ip(target):
        return target
    if key:
        data = c.get_json(f"{_RESOLVE}?{c.qs({'hostnames': target, 'key': key})}", timeout=timeout)
        if isinstance(data, dict) and data.get(target):
            return str(data[target])
    ips = [a for a in c.doh(target, "A", timeout) if c.is_ip(a)]
    if not ips:
        raise EnrichmentError(f"shodan: could not resolve {target!r} to an IP")
    return ips[0]


class ShodanAdapter(c.OptionalKeyMixin, Adapter):
    slug = "shodan"
    display_name = "Shodan (ports / services / CVEs; keyless InternetDB fallback)"
    env_var = "SHODAN_API_KEY"
    signup_url = "https://account.shodan.io/register"
    category = "infra"
    tier = "T3"
    watched_types = ("ip", "domain")

    def modes(self):
        return ["auto", "internetdb", "host"]

    def run(self, query, mode=None, timeout=30):
        target = c.bare_host(query)
        if not target:
            raise EnrichmentError("shodan: empty query")
        key = os.environ.get(self.env_var, "").strip()
        if mode == "host" and not key:
            self.get_key()
        if mode == "internetdb":
            key = ""
        ip = _resolve(target, key, timeout)
        try:
            return self._keyed(key, ip, timeout) if key else self._keyless(ip, timeout)
        except HTTPStatusError as exc:
            if exc.status == 404:
                return []  # Shodan has no record of this host
            raise

    def _keyed(self, key, ip, timeout):
        data = c.get_json(f"{_HOST}{urllib.parse.quote(ip)}?{c.qs({'key': key})}", timeout=timeout)
        svcs = [f"{s.get('port')}/{s.get('transport') or 'tcp'} {s.get('product') or ''} {s.get('version') or ''}".strip()
                for s in (data.get("data") or [])[:25]]
        summary = (f"{data.get('org') or data.get('isp') or 'unknown org'} | {data.get('asn') or ''} | "
                   f"{data.get('country_name') or ''}\nports: {data.get('ports') or []}\n"
                   f"services: {'; '.join(svcs)}\nCVEs: {', '.join(sorted(data.get('vulns') or [])[:20])}")
        data.pop("data", None)  # banners are bulky; summary keeps the useful part
        return self._rows(ip, summary, data, data.get("hostnames") or [])

    def _keyless(self, ip, timeout):
        data = c.get_json(_INTERNETDB + urllib.parse.quote(ip), timeout=timeout)
        summary = (f"(keyless InternetDB)\nports: {data.get('ports') or []}\n"
                   f"CPEs: {', '.join((data.get('cpes') or [])[:12])}\n"
                   f"tags: {', '.join(data.get('tags') or [])}\n"
                   f"CVEs: {', '.join(sorted(data.get('vulns') or [])[:20])}")
        return self._rows(ip, summary, data, data.get("hostnames") or [])

    def _rows(self, ip, summary, raw, hostnames):
        header = c.res(self, "record", f"Shodan: {ip}", summary, url=f"https://www.shodan.io/host/{ip}",
                       raw_json=raw, confidence="medium")
        return [header] + [c.res(self, "url", h.lower(), f"Hostname seen on {ip} (Shodan).",
                                 url=f"http://{h.lower()}", confidence="medium")
                           for h in hostnames[:_MAX_HOSTNAMES] if h]
