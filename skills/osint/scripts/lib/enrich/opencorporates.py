"""OpenCorporates company registry: companies and officers. T1 (government registry data).

Ported from assafkip/kipi investigations/enrich/opencorporates.py. $OPENCORPORATES_API_KEY
is sent when set. A keyless call is attempted otherwise; if OpenCorporates refuses it
(it now requires a token for most use) the adapter raises NotConfiguredError.
Modes: company (default) | officer.
"""
from __future__ import annotations

import os

from . import _common as c
from .base import Adapter, EnrichmentError, HTTPStatusError, NotConfiguredError

_API = "https://api.opencorporates.com/v0.4"


class OpenCorporatesAdapter(Adapter):
    slug = "opencorporates"
    display_name = "OpenCorporates (company registry)"
    env_var = "OPENCORPORATES_API_KEY"
    signup_url = "https://opencorporates.com/api_accounts/new"
    category = "records"
    tier = "T1"
    keyless = False
    watched_types = ("org", "person")

    def modes(self):
        return ["company", "officer"]

    def run(self, query, mode=None, timeout=30):
        q = (query or "").strip()
        if not q:
            raise EnrichmentError("opencorporates: empty query")
        key = os.environ.get(self.env_var, "").strip()
        params = {"q": q, "per_page": 30, **({"api_token": key} if key else {})}
        officer = mode == "officer"
        path = "officers/search" if officer else "companies/search"
        try:
            body = c.get_json(f"{_API}/{path}?{c.qs(params)}", timeout=timeout)
        except HTTPStatusError as exc:
            if not key and exc.status in (401, 403, 429):
                raise NotConfiguredError(f"OpenCorporates refused a keyless call (HTTP {exc.status}); "
                                         f"set ${self.env_var} ({self.signup_url})") from exc
            raise
        results = (body or {}).get("results") or {}
        if officer:
            return [self._officer(o.get("officer") or {}) for o in results.get("officers") or []]
        return [self._company(x.get("company") or {}) for x in results.get("companies") or []]

    def _company(self, co):
        summary = (f"#{co.get('company_number')} | {co.get('jurisdiction_code')} | "
                   f"status {co.get('current_status') or '?'} | incorporated {co.get('incorporation_date') or '?'}"
                   f"\naddress: {co.get('registered_address_in_full') or '?'}")
        return c.res(self, "record", co.get("name", ""), summary, url=co.get("opencorporates_url"),
                     raw_json=co, confidence="high")

    def _officer(self, o):
        comp = o.get("company") or {}
        summary = (f"{o.get('position') or 'officer'} of {comp.get('name', '?')} ({o.get('jurisdiction_code')}); "
                   f"{o.get('start_date') or '?'} to {o.get('end_date') or 'present'}")
        return c.res(self, "record", o.get("name", ""), summary,
                     url=o.get("opencorporates_url") or comp.get("opencorporates_url"),
                     raw_json=o, confidence="high")

