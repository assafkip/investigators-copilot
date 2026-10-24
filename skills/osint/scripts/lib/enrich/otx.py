"""AlienVault OTX: threat pulses + passive DNS for an indicator. Needs $OTX_API_KEY. T3.

Ported from assafkip/kipi investigations/enrich/otx.py. Passive DNS rows are
historical observations from a feed, not live DNS: T3 leads. Re-resolve with
`doh` / `infra dns` for a T1 record.
"""
from __future__ import annotations

import re
import urllib.parse

from . import _common as c
from .base import Adapter, EnrichmentError

_BASE = "https://otx.alienvault.com/api/v1/indicators"
_HASH_RE = re.compile(r"^(?:[a-fA-F0-9]{32}|[a-fA-F0-9]{40}|[a-fA-F0-9]{64})$")
_DNS_TYPES = {"IPv4", "IPv6", "domain", "hostname"}
_MAX_NODES = 40


def detect_type(value: str) -> str:
    v = value.strip()
    if "://" in v:
        return "url"
    if c.IPV4_RE.match(v):
        return "IPv4"
    if _HASH_RE.match(v):
        return "file"
    if c.is_ip(v):
        return "IPv6"
    return "hostname" if v.strip(".").count(".") >= 2 else "domain"


class OtxAdapter(Adapter):
    slug = "otx"
    display_name = "AlienVault OTX (pulses + passive DNS)"
    env_var = "OTX_API_KEY"
    signup_url = "https://otx.alienvault.com/"
    category = "reputation"
    tier = "T3"
    keyless = False
    watched_types = ("domain", "ip", "url", "file")

    def _get(self, otype, indicator, section, key, timeout):
        url = f"{_BASE}/{otype}/{urllib.parse.quote(indicator, safe='')}/{section}"
        return c.get_json(url, timeout=timeout, headers={"X-OTX-API-KEY": key}, empty_on=(404,)) or {}

    def run(self, query, mode=None, timeout=30):
        indicator = (query or "").strip()
        if not indicator:
            raise EnrichmentError("otx: empty query")
        key = self.get_key()
        otype = detect_type(indicator)
        out = [self._general(key, otype, indicator, timeout)]
        if otype in _DNS_TYPES:
            out += self._passive_dns(key, otype, indicator, timeout)
        return out

    def _general(self, key, otype, indicator, timeout):
        pinfo = (self._get(otype, indicator, "general", key, timeout).get("pulse_info") or {})
        pulses = pinfo.get("pulses") or []
        count = pinfo.get("count") if isinstance(pinfo.get("count"), int) else len(pulses)
        names = [p.get("name") for p in pulses[:8] if p.get("name")]
        tags = sorted({t for p in pulses for t in (p.get("tags") or [])})[:15]
        summary = f"{count} OTX pulse(s) [{otype}]" + (f"\npulses: {', '.join(names)}" if names else "") \
            + (f"\ntags: {', '.join(tags)}" if tags else "")
        return c.res(self, "document", f"OTX: {indicator}", summary,
                     url=f"https://otx.alienvault.com/indicator/{otype}/{indicator}",
                     raw_json={"type": otype, "pulse_count": count, "pulses": names, "tags": tags},
                     confidence="high" if count >= 3 else "medium" if count else "low")

    def _passive_dns(self, key, otype, indicator, timeout):
        rows, seen = [], set()
        for row in self._get(otype, indicator, "passive_dns", key, timeout).get("passive_dns") or []:
            val = (row.get("hostname") if otype.startswith("IPv") else row.get("address")) or ""
            val = val.strip().lower()
            if val and val not in seen:
                seen.add(val)
                rows.append(c.res(self, "record", val,
                                  f"Passive DNS with {indicator} ({row.get('record_type', '?')}, "
                                  f"last {row.get('last', '?')})", raw_json=row, confidence="medium"))
        return rows[:_MAX_NODES]
