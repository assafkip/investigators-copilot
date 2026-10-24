"""RIPEstat network-info: IP -> announcing ASN(s) + covering BGP prefix. Keyless, T1.

Ported from hydra src/osint/ripestat.ts. RIPE's routing collectors are an
independent second source next to Team Cymru (asn.py).
"""
from __future__ import annotations

from . import _common as c
from .base import Adapter, EnrichmentError

_URL = "https://stat.ripe.net/data/network-info/data.json"


class RipestatAdapter(Adapter):
    slug = "ripestat"
    display_name = "RIPEstat network-info (ASN + prefix)"
    category = "infra"
    tier = "T3"  # ASN/BGP routing data is not in the T1 list of .claude/rules/q-investigation.md
    watched_types = ("ip",)

    def run(self, query, mode=None, timeout=30):
        ip = c.require_ip(query, "ripestat")
        body = c.get_json(f"{_URL}?{c.qs({'resource': ip})}", timeout=timeout)
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise EnrichmentError("ripestat: unexpected response shape")
        prefix = (data.get("prefix") or "").strip()
        asns = [f"AS{str(a).upper().removeprefix('AS')}" for a in (data.get("asns") or [])[:20]]
        header = c.res(self, "record", f"RIPEstat: {ip}",
                       f"prefix {prefix or '(none)'}; announced by {', '.join(asns) or '(no ASN)'}",
                       url=f"https://stat.ripe.net/{ip}", raw_json=data, confidence="high")
        return [header] + [c.res(self, "profile", a, f"Announces {ip} (prefix {prefix}).",
                                 raw_json={"asn": a, "prefix": prefix}, confidence="high") for a in asns]
