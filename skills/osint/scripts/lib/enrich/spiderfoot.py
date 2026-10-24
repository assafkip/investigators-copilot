"""SpiderFoot automated OSINT scan (MIT). T3.

New adapter. Two transports:
  - CLI (default): `sf.py` / `spiderfoot` on PATH, run synchronously with
    `-s <target> -u <usecase> -o json -q`. Mode = use case: passive (default) |
    footprint | investigate | all. `passive` sends no packets to the target.
  - REST ($SPIDERFOOT_URL, e.g. http://127.0.0.1:5001): mode `results` with
    query = an existing scan id returns that scan's events (start long scans in the UI).
"""
from __future__ import annotations

import json
import os

from . import _common as c
from . import base
from .base import Adapter, EnrichmentError, NotConfiguredError

_SKIP_TYPES = {"ROOT", "Scan Target"}


def parse_cli(out: str) -> list[dict]:
    text = (out or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        rows = []
        for line in text.splitlines():
            line = line.strip().rstrip(",")
            if line.startswith("{"):
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        if not rows:
            raise EnrichmentError("spiderfoot: unparseable CLI output")
        return rows


def _rest_rows(body) -> list[dict]:
    """/scaneventresults rows are positional: [last_seen, data, source, module, ..., type]."""
    rows = []
    for r in body if isinstance(body, list) else []:
        if isinstance(r, list) and len(r) >= 5:
            rows.append({"generated": r[0], "data": r[1], "source": r[2], "module": r[3], "type": r[-1]})
    return rows


class SpiderFootAdapter(Adapter):
    slug = "spiderfoot"
    display_name = "SpiderFoot (CLI or REST)"
    signup_url = "pip install -r requirements.txt from github.com/smicallef/spiderfoot, or docker"
    category = "search"
    tier = "T3"
    watched_types = ("domain", "ip", "email", "person", "handle", "org")
    license_note = "MIT; subprocess / REST"

    def missing(self):
        ok = c.which("sf.py", "spiderfoot") or os.environ.get("SPIDERFOOT_URL", "").strip()
        return [] if ok else ["bin:sf.py or $SPIDERFOOT_URL"]

    def modes(self):
        return ["passive", "footprint", "investigate", "all", "results"]

    def run(self, query, mode=None, timeout=1800):
        q = (query or "").strip()
        if not q:
            raise EnrichmentError("spiderfoot: empty query")
        m = (mode or "passive").lower()
        if m == "results":
            rows = self._rest(q, timeout)
        else:
            exe = c.which("sf.py", "spiderfoot")
            if not exe:
                raise NotConfiguredError("spiderfoot: no sf.py/spiderfoot on PATH (or use $SPIDERFOOT_URL "
                                         "with mode=results)")
            rows = parse_cli(base.run_bin([exe, "-s", q, "-u", m, "-o", "json", "-q"],
                                          timeout=max(timeout, 600)))
        return self._results(q, m, rows)

    def _rest(self, scan_id, timeout):
        url = os.environ.get("SPIDERFOOT_URL", "").strip().rstrip("/")
        if not url:
            raise NotConfiguredError("spiderfoot: set $SPIDERFOOT_URL for mode=results")
        body = c.get_json(f"{url}/scaneventresults?{c.qs({'id': scan_id, 'eventType': 'ALL'})}", timeout=timeout)
        return _rest_rows(body)

    def _results(self, q, m, rows):
        by_type: dict[str, list[str]] = {}
        for r in rows:
            etype = str(r.get("type") or "")
            if etype and etype not in _SKIP_TYPES and r.get("data"):
                vals = by_type.setdefault(etype, [])
                if str(r["data"]) not in vals:
                    vals.append(str(r["data"])[:500])
        total = sum(len(v) for v in by_type.values())
        header = c.res(self, "document", f"SpiderFoot {m}: {q} -- {total} events",
                       "; ".join(f"{k}: {len(v)}" for k, v in sorted(by_type.items())) or "no events",
                       raw_json={"target": q, "mode": m, "events": by_type}, confidence="low")
        warning = c.volume_warning(total, "SpiderFoot events")
        if warning:
            header.summary += f"\n{warning}"
            return [header]
        return [header] + [c.res(self, "record", v[:200], f"SpiderFoot {k} for {q}", raw_json={"event_type": k},
                                 confidence="low") for k, vals in by_type.items() for v in vals]
