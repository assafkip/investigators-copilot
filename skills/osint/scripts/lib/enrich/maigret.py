"""Maigret wrapper: a handle across ~3000 sites. Subprocess only (MIT), T3.

Runs `maigret <user> --json simple --folderoutput <tmp> --no-progressbar
--no-color --timeout N` and parses the report_<user>_simple.json it writes
(one key per site where the account was CLAIMED). Install: pipx install maigret.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ._identity_common import T3_NOTE, BinAdapter, clean_handle, http_url_or_none, lead
from .base import EnrichmentError


def parse_report(data: dict) -> list[dict]:
    hits = []
    for site, entry in (data or {}).items():
        if not isinstance(entry, dict):
            continue
        status = entry.get("status") if isinstance(entry.get("status"), dict) else {}
        if status and str(status.get("status", "Claimed")).lower() != "claimed":
            continue
        url = http_url_or_none(entry.get("url_user") or status.get("url"))
        hits.append({"site": site, "url": url, "tags": status.get("tags") or entry.get("tags"),
                     "ids": status.get("ids") or {}})
    return hits


class MaigretAdapter(BinAdapter):
    slug = "maigret"
    display_name = "Maigret username sweep (subprocess)"
    requires_bin = ("maigret",)
    watched_types = ("handle",)
    license_note = "MIT; invoked as a subprocess"

    def run(self, query, mode=None, timeout=600):
        user = clean_handle(query, self.slug)
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.exec_tool(["maigret", user, "--json", "simple", "--folderoutput", tmp,
                                   "--no-progressbar", "--no-color", "--timeout", "15"],
                                  timeout=max(timeout, 300))
            reports = sorted(Path(tmp).rglob("*.json"))
            if not reports:
                raise self.fail(proc, "no JSON report written")
            try:
                hits = parse_report(json.loads(reports[0].read_text()))
            except json.JSONDecodeError as exc:
                raise EnrichmentError(f"maigret: unreadable report {reports[0].name}") from exc
        header = lead(f"maigret: {user} -- claimed on {len(hits)} site(s)",
                      ", ".join(h["site"] for h in hits[:60]) + f"\n{T3_NOTE}",
                      raw={"username": user, "sites": [h["site"] for h in hits]}, rtype="document",
                      confidence="medium")
        return [header] + [lead(f"{h['site']}: {user}", f"maigret: account claimed on {h['site']}. {T3_NOTE}",
                                url=h["url"], raw=h) for h in hits if h["url"]]
