"""ipwho.is: IP -> ASN, ISP/org, connection domain, geo. Keyless, T3.

Ported from hydra src/osint/ipwho-is.ts. Tier note: hydra labels this T1, but
ipwho.is is a commercial geo/ISP aggregation, not a registry or routing record, so
it is graded T3 here. Use `asn` / `ripestat` / `rdap` for the T1 routing record.
"""
from __future__ import annotations

from . import _common as c
from .base import Adapter, EnrichmentError

_URL = "https://ipwho.is/"


class IpWhoIsAdapter(Adapter):
    slug = "ipwhois"
    display_name = "ipwho.is (IP geo / ISP / ASN)"
    category = "infra"
    tier = "T3"
    watched_types = ("ip",)

    def run(self, query, mode=None, timeout=30):
        ip = c.require_ip(query, "ipwhois")
        body = c.get_json(_URL + ip, timeout=timeout)
        if not isinstance(body, dict):
            raise EnrichmentError("ipwho.is: unexpected response shape")
        if body.get("success") is False:
            raise EnrichmentError(f"ipwho.is: {body.get('message') or 'lookup failed'}")
        conn = body.get("connection") or {}
        geo = ", ".join(x for x in (body.get("city"), body.get("region"), body.get("country")) if x)
        summary = " | ".join(x for x in (
            conn.get("asn") and f"AS{conn['asn']}", conn.get("isp") and f"ISP {conn['isp']}",
            conn.get("org") and f"org {conn['org']}", conn.get("domain") and f"domain {conn['domain']}",
            geo and f"geo {geo}") if x)
        return [c.res(self, "record", f"ipwho.is: {ip}", summary or "(no data)", raw_json=body,
                      confidence="medium")]
