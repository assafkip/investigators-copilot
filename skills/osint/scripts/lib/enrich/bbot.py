"""BBOT (Black Lantern Security) recursive recon: subdomains, IPs, ports, emails. T3.

New adapter, subprocess only (BBOT is AGPL-3.0; it is never imported). Reads the
NDJSON event stream from `bbot ... --json`. Modes:
  passive (default) -- subdomain-enum preset with `-rf passive` (no packets to the target)
  subdomain-enum    -- full preset (includes DNS brute force)
  <any preset name> -- passed through to `-p`
BBOT runs can take many minutes; the timeout floor is 600s.
"""
from __future__ import annotations

import json

from . import _common as c
from . import base
from .base import Adapter, NotConfiguredError

_KEEP = {"DNS_NAME": "url", "IP_ADDRESS": "record", "OPEN_TCP_PORT": "record",
         "EMAIL_ADDRESS": "record", "URL": "url", "ASN": "record", "TECHNOLOGY": "record",
         "FINDING": "record", "VULNERABILITY": "record", "SOCIAL": "url", "CODE_REPOSITORY": "url"}


def parse_events(out: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for line in (out or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype, data = ev.get("type"), ev.get("data")
        if etype not in _KEEP or data in (None, ""):
            continue
        value = data if isinstance(data, str) else (data.get("url") or data.get("description")
                                                    or data.get("technology") or json.dumps(data))
        bucket = found.setdefault(etype, [])
        if value not in bucket:
            bucket.append(value)
    return found


class BbotAdapter(Adapter):
    slug = "bbot"
    display_name = "BBOT recursive recon"
    signup_url = "pipx install bbot"
    requires_bin = ("bbot",)
    category = "infra"
    tier = "T3"
    watched_types = ("domain", "ip", "org")
    license_note = "AGPL-3.0: subprocess only"

    def modes(self):
        return ["passive", "subdomain-enum", "email-enum", "cloud-enum"]

    def run(self, query, mode=None, timeout=900):
        target = (query or "").strip()
        exe = c.which("bbot")
        if not exe:
            raise NotConfiguredError(f"bbot: not installed ({self.signup_url})")
        m = mode or "passive"
        preset = ["-p", "subdomain-enum", "-rf", "passive"] if m == "passive" else ["-p", m]
        out = base.run_bin([exe, "-t", target, *preset, "-y", "--json", "--silent"], timeout=max(timeout, 600))
        found = parse_events(out)
        total = sum(len(v) for v in found.values())
        header = c.res(self, "document", f"bbot {m}: {target} -- {total} events",
                       "; ".join(f"{k}: {len(v)}" for k, v in found.items()) or "no events",
                       raw_json={"target": target, "mode": m, "events": found}, confidence="low")
        warning = c.volume_warning(total, "bbot events")
        if warning:
            header.summary += f"\n{warning}"
            return [header]
        return [header] + [c.res(self, _KEEP[k], v, f"bbot {k} for {target}",
                                 url=f"http://{v}" if k == "DNS_NAME" else (v if v.startswith("http") else None),
                                 raw_json={"event_type": k}, confidence="low")
                           for k, vals in found.items() for v in vals]
