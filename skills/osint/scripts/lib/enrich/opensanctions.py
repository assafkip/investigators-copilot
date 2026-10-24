"""OpenSanctions entity matching (sanctions, PEPs, debarment, crime lists). T3 lead.

New adapter. Tries a local yente server first ($YENTE_URL, default
http://localhost:8000; self-hosted, no key, no query leaves the machine), then the
hosted API with $OPENSANCTIONS_API_KEY. Graded T3: it is an aggregated, fuzzy-matched
dataset. Each hit names its source datasets; cite the underlying government list
(e.g. run `ofac` for US SDN) before treating a match as a T1 record.
Modes: entity (default, LegalEntity) | person | company | search (free text).
"""
from __future__ import annotations

import os
import urllib.parse

from . import _common as c
from .base import Adapter, EnrichmentError, NotConfiguredError

_HOSTED = "https://api.opensanctions.org"
_SCHEMA = {"entity": "LegalEntity", "person": "Person", "company": "Company"}


def _yente_base() -> str:
    return (os.environ.get("YENTE_URL") or "http://localhost:8000").rstrip("/")


def _yente_up(timeout: int) -> bool:
    try:
        c.get_json(_yente_base() + "/healthz", timeout=min(timeout, 3))
        return True
    except EnrichmentError:
        return False


class OpenSanctionsAdapter(Adapter):
    slug = "opensanctions"
    display_name = "OpenSanctions (local yente or hosted API)"
    env_var = "OPENSANCTIONS_API_KEY"
    signup_url = "https://www.opensanctions.org/api/"
    category = "sanctions"
    tier = "T3"
    watched_types = ("person", "org")

    def modes(self):
        return [*_SCHEMA, "search"]

    def missing(self):
        if os.environ.get(self.env_var, "").strip() or os.environ.get("YENTE_URL", "").strip():
            return []
        return [f"${self.env_var} (or a local yente at $YENTE_URL)"]

    def _endpoint(self, timeout):
        if _yente_up(timeout):
            return _yente_base(), {}
        key = os.environ.get(self.env_var, "").strip()
        if not key:
            raise NotConfiguredError(f"opensanctions: no yente at {_yente_base()} and ${self.env_var} unset "
                                     f"({self.signup_url}; or docker run yente)")
        return _HOSTED, {"Authorization": f"ApiKey {key}"}

    def run(self, query, mode=None, timeout=30):
        q = (query or "").strip()
        if not q:
            raise EnrichmentError("opensanctions: empty query")
        m = (mode or "entity").lower()
        if m != "search" and m not in _SCHEMA:
            raise EnrichmentError(f"opensanctions: unknown mode {mode!r}")
        base_url, headers = self._endpoint(timeout)
        if m == "search":
            body = c.get_json(f"{base_url}/search/default?{c.qs({'q': q, 'limit': 20})}",
                              timeout=timeout, headers=headers)
            rows = (body or {}).get("results")
        else:
            payload = {"queries": {"q": {"schema": _SCHEMA[m], "properties": {"name": [q]}}}}
            body = c.get_json(f"{base_url}/match/default", timeout=timeout, headers=headers, data=payload)
            rows = (((body or {}).get("responses") or {}).get("q") or {}).get("results")
        if not isinstance(rows, list):
            raise EnrichmentError("opensanctions: unexpected response shape")
        return [self._row(r, base_url) for r in rows[:25]]

    def _row(self, r, base_url):
        props = r.get("properties") or {}
        score = r.get("score")
        summary = (f"{r.get('schema')} | score {score if score is not None else 'n/a'} | "
                   f"match={r.get('match')} | datasets: {', '.join(r.get('datasets') or [])}\n"
                   + "\n".join(f"{k}: {', '.join(map(str, props[k][:5]))}"
                               for k in ("topics", "country", "birthDate", "nationality", "program", "alias")
                               if props.get(k)))
        return c.res(self, "record", r.get("caption") or r.get("id", "?"), summary,
                     url=f"https://www.opensanctions.org/entities/{urllib.parse.quote(r.get('id', ''))}/",
                     raw_json={**r, "endpoint": base_url},
                     confidence="medium" if r.get("match") else "low")
