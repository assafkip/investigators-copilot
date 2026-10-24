"""DNS over HTTPS (dns.google): A / AAAA / NS / MX / TXT / CNAME / CAA. Keyless, T1.

Ported from hydra src/osint/doh.ts. Works where `dig` is not installed and where
outbound UDP/53 is blocked. Mode = one record type, or `all` (default).
Override the resolver with $OSINT_DOH_URL (any Google-JSON-compatible endpoint).
"""
from __future__ import annotations

from . import _common as c
from .base import Adapter, EnrichmentError

_ALL = ("A", "AAAA", "NS", "MX", "TXT", "CNAME", "CAA")


class DohAdapter(Adapter):
    slug = "doh"
    display_name = "DNS over HTTPS (dns.google)"
    category = "infra"
    tier = "T1"
    watched_types = ("domain", "ip")

    def modes(self):
        return ["all", *_ALL, "PTR"]

    def run(self, query, mode=None, timeout=30):
        target = c.bare_host(query)
        if not target:
            raise EnrichmentError("doh: empty target")
        m = (mode or "all").upper()
        if c.is_ip(target) or m == "PTR":
            ip = c.require_ip(target, "doh PTR")
            ptrs = [p.rstrip(".") for p in c.doh(c.ptr_name(ip), "PTR", timeout)]
            return [c.res(self, "record", f"PTR {ip}", ", ".join(ptrs) or "No PTR record.",
                          raw_json={"ip": ip, "PTR": ptrs}, confidence="high")]
        types = _ALL if m == "ALL" else (m,)
        if any(t not in c.DOH_TYPES for t in types):
            raise EnrichmentError(f"doh: unsupported record type {mode!r}")
        records = {t: c.doh(target, t, timeout) for t in types}
        records = {t: v for t, v in records.items() if v}
        rows = [c.res(self, "record", f"{t} {target}", ", ".join(v), raw_json={"type": t, "values": v},
                      confidence="high") for t, v in records.items()]
        return rows or [c.res(self, "record", f"DNS {target}", "No records (NXDOMAIN or NODATA).",
                              raw_json={"domain": target, "records": {}}, confidence="high")]
