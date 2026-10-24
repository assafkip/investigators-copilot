"""theHarvester: emails, hosts, IPs and ASNs for a domain from public sources. T3.

New adapter, subprocess only (theHarvester is GPL-2.0; it is never imported).
Mode = comma-separated theHarvester sources (default: keyless ones). Output is read
from the JSON file theHarvester writes with -f.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from . import _common as c
from . import base
from .base import Adapter, EnrichmentError, NotConfiguredError

_DEFAULT_SOURCES = "crtsh,certspotter,hackertarget,rapiddns,duckduckgo,otx,urlscan"
_KEYS = ("emails", "hosts", "ips", "asns", "interesting_urls", "linkedin_people", "twitter_people")


def _binary() -> str | None:
    return c.which("theHarvester", "theharvester")


class TheHarvesterAdapter(Adapter):
    slug = "theharvester"
    display_name = "theHarvester (emails / hosts / IPs)"
    signup_url = "pipx install git+https://github.com/laramies/theHarvester"
    category = "infra"
    tier = "T3"
    watched_types = ("domain",)
    license_note = "GPL-2.0: subprocess only"

    def missing(self):
        return [] if _binary() else ["bin:theHarvester"]

    def modes(self):
        return [_DEFAULT_SOURCES]

    def run(self, query, mode=None, timeout=600):
        domain = c.require_domain(query, "theharvester")
        exe = _binary()
        if not exe:
            raise NotConfiguredError(f"theharvester: not installed ({self.signup_url})")
        with tempfile.TemporaryDirectory(prefix="harvester-") as tmp:
            stem = Path(tmp) / "out"
            log = base.run_bin([exe, "-d", domain, "-b", mode or _DEFAULT_SOURCES, "-f", str(stem)],
                               timeout=max(timeout, 300))
            out = Path(f"{stem}.json")
            if not out.exists():
                raise EnrichmentError(f"theharvester: no JSON written; tail: {log[-300:]!r}")
            try:
                data = json.loads(out.read_text() or "{}")
            except json.JSONDecodeError as exc:
                raise EnrichmentError("theharvester: unparseable JSON output") from exc
        found = {k: sorted(set(data.get(k) or [])) for k in _KEYS if data.get(k)}
        header = c.res(self, "document", f"theHarvester: {domain}",
                       "; ".join(f"{k}: {len(v)}" for k, v in found.items()) or "nothing found",
                       raw_json={"domain": domain, "sources": mode or _DEFAULT_SOURCES, **found},
                       confidence="low")
        rows = [c.res(self, "record", e, f"Email seen for {domain} (theHarvester).", confidence="low")
                for e in found.get("emails", [])]
        rows += [c.res(self, "url", h.split(":")[0], f"Host seen for {domain} (theHarvester).",
                       url=f"http://{h.split(':')[0]}", confidence="low") for h in found.get("hosts", [])]
        warning = c.volume_warning(len(rows), "theHarvester rows")
        if warning:
            header.summary += f"\n{warning}"
            return [header]
        return [header] + rows
