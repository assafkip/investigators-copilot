"""Sherlock wrapper: a handle across ~400 sites. Subprocess only (MIT), T3.

Runs `sherlock <user> --csv --folderoutput <tmp> --print-found --no-color
--timeout 15` and reads <tmp>/<user>.csv (exists == Claimed); falls back to the
`[+] Site: url` stdout lines. Install: pipx install sherlock-project.
"""
from __future__ import annotations

import csv
import re
import tempfile
from pathlib import Path

from ._identity_common import T3_NOTE, BinAdapter, clean_handle, http_url_or_none, lead

FOUND_LINE = re.compile(r"^\[\+\]\s*([^:]+):\s*(https?://\S+)")


def parse_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        return [{"site": row.get("name"), "url": http_url_or_none(row.get("url_user"))}
                for row in csv.DictReader(fh) if str(row.get("exists", "")).lower() == "claimed"]


def parse_stdout(text: str) -> list[dict]:
    hits = []
    for line in text.splitlines():
        match = FOUND_LINE.match(line.strip())
        if match:
            hits.append({"site": match.group(1).strip(), "url": http_url_or_none(match.group(2))})
    return hits


class SherlockAdapter(BinAdapter):
    slug = "sherlock"
    display_name = "Sherlock username sweep (subprocess)"
    requires_bin = ("sherlock",)
    install_name = "sherlock"
    watched_types = ("handle",)
    license_note = "MIT; invoked as a subprocess"

    def run(self, query, mode=None, timeout=600):
        user = clean_handle(query, self.slug)
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.exec_tool(["sherlock", user, "--csv", "--folderoutput", tmp, "--print-found",
                                   "--no-color", "--timeout", "15"], timeout=max(timeout, 300))
            report = Path(tmp) / f"{user}.csv"
            hits = parse_csv(report) if report.is_file() else parse_stdout(proc.stdout or "")
            if not report.is_file() and proc.returncode != 0:
                raise self.fail(proc, "sherlock failed")
        header = lead(f"sherlock: {user} -- claimed on {len(hits)} site(s)",
                      ", ".join(h["site"] or "?" for h in hits[:60]) + f"\n{T3_NOTE}",
                      raw={"username": user, "sites": [h["site"] for h in hits]}, rtype="document",
                      confidence="medium")
        return [header] + [lead(f"{h['site']}: {user}", f"sherlock: account claimed on {h['site']}. {T3_NOTE}",
                                url=h["url"], raw=h) for h in hits if h["url"]]
