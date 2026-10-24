"""Certificate transparency (crt.sh): every hostname ever issued a cert. Keyless, T1.

Ported from assafkip/kipi investigations/enrich/crtsh.py.
"""
from __future__ import annotations

import urllib.parse

from .base import Adapter, EnrichmentError, EnrichmentResult, http_json


class CrtShAdapter(Adapter):
    slug = "crtsh"
    display_name = "crt.sh certificate transparency"
    category = "infra"
    tier = "T1"
    watched_types = ("domain",)

    def run(self, query, mode=None, timeout=60):
        domain = query.strip().lower().removeprefix("*.")
        if "." not in domain:
            raise EnrichmentError(f"crtsh: not a domain: {query!r}")
        url = "https://crt.sh/?" + urllib.parse.urlencode({"q": f"%.{domain}", "output": "json"})
        rows = http_json(url, timeout=timeout)
        names: dict[str, dict] = {}
        for row in rows if isinstance(rows, list) else []:
            for name in str(row.get("name_value", "")).splitlines():
                name = name.strip().lower().removeprefix("*.")
                if name and name not in names:
                    names[name] = {"first_seen": row.get("not_before"), "issuer": row.get("issuer_name")}
        return [EnrichmentResult("record", name, f"cert first seen {meta['first_seen']}; issuer {meta['issuer']}",
                                 url=f"https://crt.sh/?q={urllib.parse.quote(name)}", raw_json=meta,
                                 confidence="high", tier="T1")
                for name, meta in sorted(names.items())]
