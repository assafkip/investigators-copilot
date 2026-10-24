"""CourtListener (Free Law Project) REST v4 search: court opinions, RECAP dockets, judges. T1.

New adapter. A court record is T1. Search hits are name matches, so a party-name hit
still needs a second identifier (case number, address, counsel) before attribution.
$COURTLISTENER_API_TOKEN is optional for search (anonymous works at a lower rate) and
is sent as `Authorization: Token ...` when set. Query syntax is CourtListener's
(e.g. "John Doe" with quotes, caseName:(acme), docketNumber:"1:21-cv-00123").
Modes: dockets (default, RECAP federal filings) | opinions | oral | people.
"""
from __future__ import annotations

import os

from . import _common as c
from .base import Adapter, EnrichmentError, HTTPStatusError, NotConfiguredError

_SEARCH = "https://www.courtlistener.com/api/rest/v4/search/"
_SITE = "https://www.courtlistener.com"
_TYPES = {"dockets": "r", "opinions": "o", "oral": "oa", "people": "p"}


def _title(row: dict) -> str:
    return row.get("caseName") or row.get("name") or row.get("case_name") or row.get("docketNumber") or "(untitled)"


def _summary(row: dict) -> str:
    parts = [row.get("court") or row.get("court_citation_string"),
             row.get("docketNumber") and f"docket {row['docketNumber']}",
             (row.get("dateFiled") or row.get("dateArgued")) and f"filed {row.get('dateFiled') or row.get('dateArgued')}",
             row.get("dateTerminated") and f"terminated {row['dateTerminated']}",
             row.get("suitNature") and f"nature {row['suitNature']}",
             row.get("party") and f"parties: {', '.join(row['party'][:8])}"]
    return " | ".join(str(p) for p in parts if p)


class CourtListenerAdapter(c.OptionalKeyMixin, Adapter):
    slug = "courtlistener"
    display_name = "CourtListener (US court records)"
    env_var = "COURTLISTENER_API_TOKEN"
    signup_url = "https://www.courtlistener.com/sign-in/"
    category = "records"
    tier = "T1"
    watched_types = ("person", "org", "text")

    def modes(self):
        return list(_TYPES)

    def run(self, query, mode=None, timeout=60):
        q = (query or "").strip()
        if not q:
            raise EnrichmentError("courtlistener: empty query")
        rtype = _TYPES.get((mode or "dockets").lower())
        if rtype is None:
            raise EnrichmentError(f"courtlistener: unknown mode {mode!r} (use {', '.join(_TYPES)})")
        token = os.environ.get(self.env_var, "").strip()
        try:
            body = c.get_json(f"{_SEARCH}?{c.qs({'q': q, 'type': rtype})}", timeout=timeout,
                              headers={"Authorization": f"Token {token}"} if token else None)
        except HTTPStatusError as exc:
            if exc.status in (401, 403) and not token:
                raise NotConfiguredError(f"CourtListener refused an anonymous call; set ${self.env_var} "
                                         f"({self.signup_url}, free account)") from exc
            if exc.status == 429 and not token:
                raise EnrichmentError(f"CourtListener rate-limited the anonymous call (HTTP 429); "
                                      f"a free ${self.env_var} raises the limit") from exc
            raise
        rows = (body or {}).get("results")
        if not isinstance(rows, list):
            raise EnrichmentError("courtlistener: unexpected response shape")
        out = [c.res(self, "record", _title(r), _summary(r) or "(no metadata)",
                     url=_SITE + r["absolute_url"] if r.get("absolute_url") else None,
                     raw_json={k: v for k, v in r.items() if k not in ("opinions", "recap_documents")}, confidence="medium")
               for r in rows[:50]]
        if out and (body or {}).get("count"):
            out[0].raw_json["total_count"] = body["count"]
        return out
