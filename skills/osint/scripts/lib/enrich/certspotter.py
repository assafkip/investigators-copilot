"""Cert Spotter (SSLMate) certificate-transparency issuances. Keyless, T1.

Ported from hydra src/osint/certspotter.ts. A second CT index independent of
crt.sh, so it surfaces names crt.sh misses and vice versa. Only the queried domain
and its subdomains are emitted (an unrelated SAN on a shared cert is dropped).
Keyless tier is rate limited; $CERTSPOTTER_API_KEY raises it.
"""
from __future__ import annotations

import os

from . import _common as c
from .base import Adapter, EnrichmentError

_URL = "https://api.certspotter.com/v1/issuances"


class CertSpotterAdapter(c.OptionalKeyMixin, Adapter):
    slug = "certspotter"
    display_name = "Cert Spotter CT issuances"
    env_var = "CERTSPOTTER_API_KEY"
    signup_url = "https://sslmate.com/certspotter/api/"
    category = "infra"
    tier = "T1"
    watched_types = ("domain",)

    def run(self, query, mode=None, timeout=60):
        domain = c.require_domain(query, "certspotter").removeprefix("*.")
        key = os.environ.get(self.env_var, "").strip()
        headers = {"Authorization": f"Bearer {key}"} if key else None
        url = f"{_URL}?{c.qs({'domain': domain, 'include_subdomains': 'true', 'expand': ['dns_names', 'issuer']})}"
        rows = c.get_json(url, timeout=timeout, headers=headers, empty_on=(404,))
        if rows is None:
            return []
        if not isinstance(rows, list):
            raise EnrichmentError("certspotter: unexpected response shape")
        names: dict[str, dict] = {}
        for row in rows:
            issuer = (row.get("issuer") or {}).get("friendly_name") or (row.get("issuer") or {}).get("name")
            for raw in row.get("dns_names") or []:
                host = str(raw).lower().removeprefix("*.")
                if (host == domain or host.endswith("." + domain)) and host not in names:
                    names[host] = {"not_before": row.get("not_before"), "issuer": issuer, "id": row.get("id")}
        return [c.res(self, "record", h, f"CT issuance {m['not_before']}; issuer {m['issuer']}",
                      url=f"https://crt.sh/?q={h}",
                      raw_json=m, confidence="high") for h, m in sorted(names.items())]
