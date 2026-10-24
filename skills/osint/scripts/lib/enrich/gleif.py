"""GLEIF LEI registry: legal name, LEI, jurisdiction, address, status, parent links. Keyless, T1.

Ported from hydra src/osint/gleif.ts. An LEI record (ISO 17442) is maintained by an
accredited issuer: a registry record (T1). It does not list officers (OpenCorporates
does, keyed). Modes: name (default, fuzzy legal-name filter) | lei (exact LEI).
"""
from __future__ import annotations

import re
import urllib.parse

from . import _common as c
from .base import Adapter, EnrichmentError

_URL = "https://api.gleif.org/api/v1/lei-records"
_LEI_RE = re.compile(r"^[A-Z0-9]{18}[0-9]{2}$")
_HDR = {"Accept": "application/vnd.api+json"}


class GleifAdapter(Adapter):
    slug = "gleif"
    display_name = "GLEIF LEI registry"
    category = "records"
    tier = "T1"
    watched_types = ("org",)

    def modes(self):
        return ["name", "lei"]

    def run(self, query, mode=None, timeout=30):
        q = (query or "").strip()
        if not q:
            raise EnrichmentError("gleif: empty query")
        if mode == "lei" or _LEI_RE.match(q.upper()):
            body = c.get_json(f"{_URL}/{urllib.parse.quote(q.upper())}", timeout=timeout,
                              headers=_HDR, empty_on=(404,))
            records = [body.get("data")] if body and body.get("data") else []
        else:
            body = c.get_json(f"{_URL}?{c.qs({'filter[entity.legalName]': q, 'page[size]': 10})}",
                              timeout=timeout, headers=_HDR)
            if not isinstance(body, dict) or not isinstance(body.get("data"), list):
                raise EnrichmentError("gleif: unexpected response shape")
            records = body["data"]
        return [self._row(r) for r in records if (r.get("attributes") or {}).get("entity")]

    def _row(self, rec):
        attrs = rec.get("attributes") or {}
        ent = attrs.get("entity") or {}
        name = (ent.get("legalName") or {}).get("name", "")
        addr = ent.get("legalAddress") or {}
        others = [o.get("name") for o in ent.get("otherNames") or [] if o.get("name")]
        rel = rec.get("relationships") or {}
        summary = (f"LEI {attrs.get('lei')} | jurisdiction {ent.get('jurisdiction')} | "
                   f"entity {ent.get('status')} | registration {(attrs.get('registration') or {}).get('status')}\n"
                   f"address: {', '.join(addr.get('addressLines') or [])}, {addr.get('city')}, {addr.get('country')}"
                   + (f"\nother names: {', '.join(others)}" if others else "")
                   + (f"\nownership links: {', '.join(k for k in ('direct-parent', 'ultimate-parent', 'direct-children') if k in rel)}"
                      if rel else ""))
        return c.res(self, "record", name, summary, url=f"https://search.gleif.org/#/record/{attrs.get('lei')}",
                     raw_json=attrs, confidence="high")
