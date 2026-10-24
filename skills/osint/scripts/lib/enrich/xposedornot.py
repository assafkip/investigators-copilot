"""XposedOrNot: which breach corpora list an email address. Keyless, T3 lead.

Ported from hydra src/osint/xposedornot.ts. Breach-DB presence is a lead, not proof
the address was breached or belongs to the subject. 404 / "Not found" = no records.
"""
from __future__ import annotations

import urllib.parse

from . import _common as c
from .base import Adapter, EnrichmentError

_URL = "https://api.xposedornot.com/v1/check-email/"


class XposedOrNotAdapter(Adapter):
    slug = "xposedornot"
    display_name = "XposedOrNot breach check (email)"
    category = "identity"
    tier = "T3"
    watched_types = ("email",)

    def run(self, query, mode=None, timeout=30):
        addr = (query or "").strip().lower()
        if "@" not in addr:
            raise EnrichmentError(f"xposedornot: {query!r} is not an email address")
        body = c.get_json(_URL + urllib.parse.quote(addr), timeout=timeout, empty_on=(404,))
        if body is None:
            return []
        if not isinstance(body, dict):
            raise EnrichmentError("xposedornot: unexpected response shape")
        breaches = body.get("breaches")
        if not (isinstance(breaches, list) and breaches and isinstance(breaches[0], list)):
            err = str(body.get("Error") or "").lower()
            if err and err != "not found":
                raise EnrichmentError(f"xposedornot: {body.get('Error')}")
            return []
        names = [str(n) for n in breaches[0][:100] if isinstance(n, str)]
        return [c.res(self, "document", f"XposedOrNot: {addr} in {len(names)} breach record(s)",
                      "T3 lead (not proof): " + ", ".join(names),
                      url="https://xposedornot.com/", raw_json={"email": addr, "breaches": names},
                      confidence="low")]
