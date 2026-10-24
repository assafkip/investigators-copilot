"""Infrastructure recon: RDAP / WHOIS / DNS / reverse DNS / SPF+DMARC. Keyless, T1.

Ported from assafkip/kipi investigations/enrich/infra.py. Changes on port:
  - RDAP is the primary registration source (rdap.org follows the IANA bootstrap);
    raw `whois` only supplements a redacted registrant, and only if installed.
  - `dig` is optional: without it DNS and PTR go over DNS-over-HTTPS (dns.google).
  - dns_deep (SPF / DMARC / mail provider) delegates to dns_deep.py (DoH). The AXFR
    probe was dropped: an AXFR attempt touches the target's nameservers (active).

Slugs: `infra` (modes whois|rdap|dns|reverse|dns_deep) and `rdap` (domain or IP).
"""
from __future__ import annotations

import urllib.parse

from . import _common as c
from . import base
from .base import Adapter, EnrichmentError

_DNS_TYPES = ("A", "AAAA", "MX", "NS", "TXT", "CNAME")
_REGISTRANT_PREFIXES = ("registrant", "registrar", "creation date", "registry expiry",
                        "admin name", "admin email", "admin phone")


# -- RDAP ---------------------------------------------------------------------

def _vcard_name(entity: dict) -> str:
    for item in (entity.get("vcardArray") or [None, []])[1] or []:
        if isinstance(item, list) and item and item[0] == "fn":
            return str(item[-1])
    return ""


def rdap_lookup(target: str, timeout: int) -> tuple[dict, list[str]]:
    """(raw RDAP JSON, rendered lines) for a domain or IP. Raises on failure."""
    kind = "ip" if c.is_ip(target) else "domain"
    url = f"https://rdap.org/{kind}/{urllib.parse.quote(target)}"
    data = base.http_json(url, headers={"Accept": "application/rdap+json"}, timeout=timeout)
    if not isinstance(data, dict):
        raise EnrichmentError("RDAP: unexpected response shape")
    lines = [f"{k}: {data[k]}" for k in ("ldhName", "name", "handle", "startAddress",
                                          "endAddress", "country") if data.get(k)]
    lines += [f"{ev.get('eventAction')}: {ev.get('eventDate')}" for ev in data.get("events") or []]
    lines += [f"status: {s}" for s in data.get("status") or []]
    for ent in data.get("entities") or []:
        roles = ",".join(ent.get("roles") or [])
        name = _vcard_name(ent) or ent.get("handle", "")
        if roles or name:
            lines.append(f"{roles or 'entity'}: {name}")
    ns = [n.get("ldhName") for n in data.get("nameservers") or [] if n.get("ldhName")]
    if ns:
        lines.append("nameservers: " + ", ".join(ns))
    return data, lines


def _has_registrant(lines: list[str]) -> bool:
    return any("registrant" in ln.partition(":")[0].lower() and ln.partition(":")[2].strip()
               for ln in lines)


def _whois_supplement(domain: str, timeout: int) -> str:
    """Registrant lines from raw whois, or '' when whois is absent or fails."""
    if not c.which("whois"):
        return ""
    try:
        raw = base.run_bin(["whois", domain], timeout=timeout)
    except EnrichmentError:
        return ""
    return "\n".join(ln.strip() for ln in raw.splitlines()
                     if ln.strip().lower().startswith(_REGISTRANT_PREFIXES))


# -- DNS (dig if present, else DoH) -------------------------------------------

def dns_records(name: str, rtype: str, timeout: int) -> list[str]:
    if c.which("dig"):
        out = base.run_bin(["dig", "+short", name, rtype], timeout=timeout)
        return [ln.strip() for ln in out.splitlines() if ln.strip()]
    return c.doh(name, rtype, timeout)


def reverse_dns(ip: str, timeout: int) -> list[str]:
    if c.which("dig"):
        out = base.run_bin(["dig", "+short", "-x", ip], timeout=timeout)
        return [ln.strip().rstrip(".") for ln in out.splitlines() if ln.strip()]
    return [p.rstrip(".") for p in c.doh(c.ptr_name(ip), "PTR", timeout)]


class RdapAdapter(Adapter):
    slug = "rdap"
    display_name = "RDAP registration record (domain or IP)"
    category = "infra"
    tier = "T1"
    watched_types = ("domain", "ip")

    def run(self, query, mode=None, timeout=30):
        target = c.bare_host(query)
        if not target:
            raise EnrichmentError("rdap: empty target")
        data, lines = rdap_lookup(target, timeout)
        link = next((ln.get("href") for ln in data.get("links") or [] if ln.get("rel") == "self"), None)
        return [c.res(self, "record", f"RDAP: {target}", "\n".join(lines) or "(empty RDAP record)",
                      url=link, raw_json=data, confidence="high")]


class InfraAdapter(Adapter):
    slug = "infra"
    display_name = "Infra recon (RDAP/WHOIS, DNS, reverse DNS, SPF/DMARC)"
    category = "infra"
    tier = "T1"
    watched_types = ("domain", "ip")

    def modes(self):
        return ["whois", "rdap", "dns", "reverse", "dns_deep"]

    def run(self, query, mode=None, timeout=30):
        target = c.bare_host(query)
        if not target:
            raise EnrichmentError("infra: empty target")
        m = (mode or "").lower()
        if m in ("", "auto", "default"):
            m = "reverse" if c.is_ip(target) else "whois"
        handler = {"whois": self._whois, "rdap": self._whois, "dns": self._dns,
                   "reverse": self._reverse, "dns_deep": self._dns_deep}.get(m)
        if handler is None:
            raise EnrichmentError(f"infra: unknown mode {mode!r} (use {', '.join(self.modes())})")
        return handler(target, timeout)

    def _whois(self, target, timeout):
        data, lines = rdap_lookup(target, timeout)
        text, source = "\n".join(lines), "RDAP"
        if not c.is_ip(target) and not _has_registrant(lines):
            extra = _whois_supplement(target, min(timeout, 15))
            if extra:
                text, source = f"{text}\n\n[registrant via raw whois]\n{extra}", "RDAP+whois"
        return [c.res(self, "record", f"WHOIS/RDAP: {target}", f"[{source}]\n{text}"[:4000],
                      url=f"https://rdap.org/{'ip' if c.is_ip(target) else 'domain'}/{target}",
                      raw_json={"source": source, "rdap": data}, confidence="high")]

    def _dns(self, target, timeout):
        records = {rt: dns_records(target, rt, timeout) for rt in _DNS_TYPES}
        records = {k: v for k, v in records.items() if v}
        summary = "\n".join(f"{k}: {', '.join(v)}" for k, v in records.items()) or "No DNS records."
        return [c.res(self, "record", f"DNS: {target}", summary[:4000],
                      raw_json={"domain": target, "records": records}, confidence="high")]

    def _reverse(self, target, timeout):
        ip = c.require_ip(target, "infra reverse")
        ptrs = reverse_dns(ip, timeout)
        return [c.res(self, "record", f"Reverse DNS: {ip}", ", ".join(ptrs) or "No PTR record.",
                      raw_json={"ip": ip, "ptr": ptrs}, confidence="high")]

    def _dns_deep(self, target, timeout):
        from .dns_deep import DnsDeepAdapter
        return DnsDeepAdapter().run(target, timeout=timeout)
