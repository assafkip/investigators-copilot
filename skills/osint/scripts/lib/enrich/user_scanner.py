"""user-scanner wrapper (kaifcodec/user-scanner): handle or email. Subprocess, T3.

Runs `user-scanner -u <handle>` or `user-scanner -e <email>` with `-f json -o
<tmp>/out.json`; the report is a list of {status, reason, site_name, url, ...}
where status "Found" (username) / "Registered" (email) is a hit.
Install: pipx install user-scanner.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ._identity_common import EMAIL_RE, T3_NOTE, BinAdapter, clean_email, clean_handle, http_url_or_none, lead
from .base import EnrichmentError

HIT_STATUSES = {"found", "registered"}


def parse_report(rows: list) -> list[dict]:
    hits = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and str(row.get("status", "")).lower() in HIT_STATUSES:
            hits.append({"site": row.get("site_name"), "url": http_url_or_none(row.get("url")),
                         "category": row.get("category"), "extra": row.get("extra")})
    return hits


class UserScannerAdapter(BinAdapter):
    slug = "user_scanner"
    display_name = "user-scanner (handle/email registration check, subprocess)"
    requires_bin = ("user-scanner",)
    install_name = "user-scanner"
    watched_types = ("handle", "email")
    license_note = "invoked as a subprocess"

    def run(self, query, mode=None, timeout=600):
        is_email = EMAIL_RE.match((query or "").strip()) is not None
        value = clean_email(query, self.slug) if is_email else clean_handle(query, self.slug)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out.json"
            proc = self.exec_tool(["user-scanner", "-e" if is_email else "-u", value, "-f", "json",
                                   "-o", str(out)], timeout=max(timeout, 300), cwd=tmp)
            if not out.is_file():
                raise self.fail(proc, "no JSON report written")
            try:
                hits = parse_report(json.loads(out.read_text()))
            except json.JSONDecodeError as exc:
                raise EnrichmentError("user_scanner: unreadable JSON report") from exc
        header = lead(f"user-scanner: {value} -- {len(hits)} hit(s)",
                      ", ".join(str(h["site"]) for h in hits[:60]) + f"\n{T3_NOTE}",
                      raw={"query": value, "sites": [h["site"] for h in hits]}, rtype="document",
                      confidence="medium")
        return [header] + [lead(f"{h['site']}: {value}", f"user-scanner hit on {h['site']}. {T3_NOTE}",
                                url=h["url"], raw=h) for h in hits]
