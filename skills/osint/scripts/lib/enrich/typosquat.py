"""Lookalike-domain candidates via dnstwist, each liveness-checked over DoH. Keyless, T3.

Ported from assafkip/kipi investigations/enrich/typosquat.py. dnstwist is used as a
library when importable, else the `dnstwist` binary (`--registered --format json`).
NotConfiguredError when neither is present. Every row is T3: a generated lookalike
that happens to resolve is a lead, not evidence of impersonation. Run `infra` /
`rdap` / `crtsh` on a live candidate to get its T1 records.
"""
from __future__ import annotations

import json

from . import _common as c
from . import base
from .base import Adapter, EnrichmentError, NotConfiguredError

_MAX_CHECK = 25


def _generate_lib(domain: str) -> list[tuple[str, str]]:
    import dnstwist  # optional dependency
    fuzzer = dnstwist.Fuzzer(domain)
    fuzzer.generate()
    return [(p["domain"], p.get("fuzzer", "")) for p in fuzzer.domains if p.get("domain") != domain]


def _live_lib(domain: str, timeout: int) -> tuple[list, list[str], int]:
    candidates = _generate_lib(domain)
    live, dead = [], []
    for dom, fz in candidates[:_MAX_CHECK]:
        ips = [a for a in c.doh(dom, "A", min(timeout, 10)) if c.is_ip(a)]
        (live.append((dom, fz, ips)) if ips else dead.append(dom))
    return live, dead, len(candidates)


def _live_bin(domain: str, timeout: int) -> tuple[list, list[str], int]:
    out = base.run_bin(["dnstwist", "--registered", "--format", "json", domain], timeout=max(timeout, 300))
    try:
        rows = json.loads(out or "[]")
    except json.JSONDecodeError as exc:
        raise EnrichmentError("dnstwist: non-JSON output") from exc
    live = [(r["domain"], r.get("fuzzer", ""), r.get("dns_a") or []) for r in rows
            if r.get("domain") != domain and r.get("fuzzer") != "*original"]
    return live, [], len(rows)


class TyposquatAdapter(Adapter):
    slug = "typosquat"
    display_name = "dnstwist typosquat candidates"
    category = "infra"
    tier = "T3"
    watched_types = ("domain",)
    signup_url = "pip install dnstwist"

    def missing(self):
        try:
            import dnstwist  # noqa: F401
            return []
        except ImportError:
            return [] if c.which("dnstwist") else ["bin:dnstwist (or pip install dnstwist)"]

    def run(self, query, mode=None, timeout=60):
        domain = c.require_domain(query, "typosquat")
        if self.missing():
            raise NotConfiguredError("typosquat: install dnstwist (pip install dnstwist)")
        try:
            import dnstwist  # noqa: F401
            live, dead, total = _live_lib(domain, timeout)
        except ImportError:
            live, dead, total = _live_bin(domain, timeout)
        header = c.res(self, "document", f"typosquat: {domain} -- {total} candidates, {len(live)} resolving",
                       "Resolving lookalikes are LEADS (T3). Unresolved sample: " + (", ".join(dead[:30]) or "(none)"),
                       url=f"https://dnstwist.it/?domain={domain}",
                       raw_json={"domain": domain, "total": total, "live": [d for d, _, _ in live],
                                 "unresolved_checked": dead}, confidence="low")
        return [header] + [c.res(self, "url", d, f"Resolving lookalike of {domain} ({fz}); A: {', '.join(ips)}",
                                 url=f"http://{d}", raw_json={"fuzzer": fz, "a": ips}, confidence="low")
                           for d, fz, ips in live]
