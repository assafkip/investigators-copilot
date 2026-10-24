"""Shared helpers for enrichment adapters (not an adapter: the registry skips `_` modules).

Every network call goes through `base.http_get` / `base.http_json` / `base.run_bin`,
looked up at CALL time, so tests can monkeypatch those three names on `base` and
cover every adapter without network.
"""
from __future__ import annotations

import ipaddress
import os
import re
import shutil
import urllib.parse

from . import base
from .base import EnrichmentError, EnrichmentResult, HTTPStatusError

DOH_URL = os.environ.get("OSINT_DOH_URL", "https://dns.google/resolve")
DOH_TYPES = {"A": 1, "NS": 2, "CNAME": 5, "SOA": 6, "PTR": 12, "MX": 15,
             "TXT": 16, "AAAA": 28, "CAA": 257}
IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
ETH_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9_](?:[a-z0-9_-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.I)
MAX_ROWS = int(os.environ.get("OSINT_MATERIALIZE_THRESHOLD", "50"))


# -- result construction ------------------------------------------------------

def res(adapter, result_type: str, title: str, summary: str, **kw) -> EnrichmentResult:
    """EnrichmentResult stamped with the adapter's tier unless `tier=` overrides it."""
    kw.setdefault("tier", adapter.tier)
    return EnrichmentResult(result_type, title, summary, **kw)


def volume_warning(n: int, what: str) -> str | None:
    """Over the materialize threshold: keep the full set in raw_json, emit no child rows."""
    if n <= MAX_ROWS:
        return None
    return (f"LARGE RESULT: {n} {what} (threshold {MAX_ROWS}). Full set kept in raw_json; "
            "no child rows emitted -- pick a subset to pivot on.")


# -- input normalization ------------------------------------------------------

def bare_host(target: str) -> str:
    """URL / host:port / host -> lowercase bare host."""
    t = (target or "").strip().lower()
    host = t.split("://", 1)[-1].split("/", 1)[0].split("@")[-1]
    if host.startswith("["):
        return host[1:].split("]", 1)[0]
    if host.count(":") == 1:
        host = host.split(":", 1)[0]
    return host.strip(".")


def is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value.strip())
        return True
    except ValueError:
        return False


def require_ip(value: str, who: str, v4_only: bool = False) -> str:
    ip = (value or "").strip()
    if not is_ip(ip) or (v4_only and not IPV4_RE.match(ip)):
        raise EnrichmentError(f"{who}: {value!r} is not an IP{'v4' if v4_only else ''} address")
    return ip


def require_domain(value: str, who: str) -> str:
    host = bare_host(value)
    if not DOMAIN_RE.match(host):
        raise EnrichmentError(f"{who}: {value!r} is not a domain")
    return host


def name_related(query: str, candidate: str) -> bool:
    """Loose relatedness guard (ported from hydra isNameRelated)."""
    norm = lambda s: re.sub(r"[^a-z0-9]+", "", (s or "").lower())  # noqa: E731
    q, c = norm(query), norm(candidate)
    return len(q) >= 2 and len(c) >= 2 and (q in c or c in q)


# -- HTTP ---------------------------------------------------------------------

def get_json(url: str, *, timeout: int, headers: dict | None = None,
             empty_on: tuple = (), data: dict | None = None):
    """base.http_json, but a status listed in `empty_on` returns None (a documented
    "nothing here" answer). Any other failure still raises."""
    try:
        return base.http_json(url, headers=headers, timeout=timeout, data=data)
    except HTTPStatusError as exc:
        if exc.status in empty_on:
            return None
        raise


def get_text(url: str, *, timeout: int, headers: dict | None = None) -> str:
    return base.http_get(url, headers=headers, timeout=timeout).decode("utf-8", "replace")


def qs(params: dict) -> str:
    return urllib.parse.urlencode(params, doseq=True)


# -- DNS over HTTPS -----------------------------------------------------------

def doh(name: str, rtype: str, timeout: int = 15) -> list[str]:
    """Answer data strings for one record type. NXDOMAIN / NODATA -> []. SERVFAIL raises."""
    body = base.http_json(f"{DOH_URL}?{qs({'name': name, 'type': rtype})}",
                          headers={"Accept": "application/dns-json"}, timeout=timeout)
    if not isinstance(body, dict):
        raise EnrichmentError("DoH: unexpected response shape")
    status = body.get("Status")
    if status not in (0, 3):
        raise EnrichmentError(f"DoH {rtype} {name}: DNS status {status}")
    want = DOH_TYPES.get(rtype.upper())
    out = []
    for ans in body.get("Answer") or []:
        if want is None or ans.get("type") == want:
            data = str(ans.get("data", ""))
            if rtype.upper() == "TXT":
                data = data.strip('"').replace('" "', "")
            out.append(data)
    return out


def ptr_name(ip: str) -> str:
    return ipaddress.ip_address(ip).reverse_pointer


def which(*names: str) -> str | None:
    for n in names:
        path = shutil.which(n)
        if path:
            return path
    return None


class OptionalKeyMixin:
    """For adapters whose key only raises a quota / unlocks a sub-mode: keyless works,
    so --list must not report the key as missing."""

    def missing(self) -> list[str]:
        return [f"bin:{b}" for b in self.requires_bin if not shutil.which(b)]
