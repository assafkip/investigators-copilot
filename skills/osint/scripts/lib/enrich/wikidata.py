"""Wikidata entity resolution: label, aliases, official website, social handles. Keyless, T3.

Ported from hydra src/osint/wikidata.ts. Crowd-edited, so every value is a lead.
A top search hit unrelated to the query is dropped rather than attributed.
"""
from __future__ import annotations

from . import _common as c
from .base import Adapter, EnrichmentError

_API = "https://www.wikidata.org/w/api.php"
_PROPS = {"P856": "website", "P2002": "twitter", "P2037": "github", "P2013": "facebook",
          "P2003": "instagram", "P4264": "linkedin_company", "P6634": "linkedin_person",
          "P1278": "lei", "P159": "hq", "P17": "country", "P571": "inception"}


def _claim(claims: dict, pid: str):
    snak = ((claims.get(pid) or [{}])[0].get("mainsnak") or {})
    val = (snak.get("datavalue") or {}).get("value")
    if isinstance(val, dict):
        return val.get("id") or val.get("time") or val.get("text")
    return val


class WikidataAdapter(Adapter):
    slug = "wikidata"
    display_name = "Wikidata entity lookup"
    category = "records"
    tier = "T3"
    watched_types = ("org", "person")

    def run(self, query, mode=None, timeout=30):
        name = (query or "").strip()
        if not name:
            raise EnrichmentError("wikidata: empty query")
        search = c.get_json(f"{_API}?{c.qs({'action': 'wbsearchentities', 'search': name, 'language': 'en',
                                             'format': 'json', 'type': 'item', 'limit': 5})}", timeout=timeout)
        hits = [h for h in (search or {}).get("search") or []
                if name_ok(name, h.get("label", ""), h.get("aliases") or [])]
        if not hits:
            return []
        ids = "|".join(h["id"] for h in hits)
        got = c.get_json(f"{_API}?{c.qs({'action': 'wbgetentities', 'ids': ids, 'props': 'aliases|claims',
                                          'languages': 'en', 'format': 'json'})}", timeout=timeout)
        ents = (got or {}).get("entities") or {}
        return [self._row(h, ents.get(h["id"]) or {}) for h in hits]

    def _row(self, hit, ent):
        claims = ent.get("claims") or {}
        facts = {k: _claim(claims, pid) for pid, k in _PROPS.items() if _claim(claims, pid)}
        aliases = [a.get("value") for a in (ent.get("aliases") or {}).get("en", [])][:10]
        summary = f"{hit.get('description') or ''}\naliases: {', '.join(aliases) or '(none)'}\n" + \
            "\n".join(f"{k}: {v}" for k, v in facts.items())
        return c.res(self, "profile", f"{hit.get('label')} ({hit['id']})", summary.strip(),
                     url=f"https://www.wikidata.org/wiki/{hit['id']}",
                     raw_json={"id": hit["id"], "aliases": aliases, **facts}, confidence="low")


def name_ok(query: str, label: str, aliases: list) -> bool:
    return c.name_related(query, label) or any(c.name_related(query, a) for a in aliases)
