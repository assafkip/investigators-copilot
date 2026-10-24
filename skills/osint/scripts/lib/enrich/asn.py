"""IP -> origin ASN -> netblock owner via Team Cymru's DNS TXT service. Keyless, T3.

Ported from assafkip/kipi investigations/enrich/asn.py. dnspython is optional:
when it is not installed the same TXT records are fetched over DoH (dns.google),
so no extra dependency or `dig` binary is required. Accepts an IPv4 or AS<n>.
"""
from __future__ import annotations

import re

from . import _common as c
from .base import Adapter, EnrichmentError

_ASN_RE = re.compile(r"^(?:AS)?(\d+)$", re.IGNORECASE)


def cymru_txt(name: str, timeout: int) -> str:
    """First TXT string for a Cymru name, '' when the name has no record."""
    try:
        import dns.resolver  # optional dependency, imported lazily
    except ImportError:
        answers = c.doh(name, "TXT", timeout)
        return answers[0] if answers else ""
    try:
        ans = dns.resolver.resolve(name, "TXT", lifetime=timeout)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return ""  # no record is an empty answer, not a failure
    except Exception as exc:
        raise EnrichmentError(f"Cymru DNS {name}: {exc}") from exc
    for r in ans:
        return r.to_text().strip('"')
    return ""


def asn_name(asn_num: str, timeout: int) -> str:
    txt = cymru_txt(f"AS{asn_num}.asn.cymru.com", timeout)
    return txt.split("|")[-1].strip() if txt else ""


class AsnAdapter(Adapter):
    slug = "asn"
    display_name = "ASN / netblock owner (Team Cymru)"
    category = "infra"
    tier = "T3"  # ASN/BGP routing data is not in the T1 list of .claude/rules/q-investigation.md
    watched_types = ("ip", "asn")

    def run(self, query, mode=None, timeout=20):
        q = (query or "").strip()
        if c.IPV4_RE.match(q):
            return self._from_ip(q, timeout)
        m = _ASN_RE.match(q)
        if m:
            return self._from_asn(m.group(1), timeout)
        raise EnrichmentError(f"asn: {query!r} is not an IPv4 address or AS number")

    def _from_ip(self, ip, timeout):
        rev = ".".join(reversed(ip.split(".")))
        txt = cymru_txt(f"{rev}.origin.asn.cymru.com", timeout)
        if not txt:
            return [c.res(self, "record", f"ASN: {ip} -- no BGP origin", "No BGP origin for this IP.",
                          raw_json={"ip": ip}, confidence="medium")]
        fields = [f.strip() for f in txt.split("|")] + ["", "", "", ""]
        asn_num = fields[0].split()[0] if fields[0] else ""
        org = asn_name(asn_num, timeout) if asn_num else ""
        raw = {"ip": ip, "asn": f"AS{asn_num}", "prefix": fields[1], "country": fields[2],
               "registry": fields[3], "allocated": fields[4], "as_owner": org}
        header = c.res(self, "record", f"ASN: {ip} -> AS{asn_num} ({org or 'unknown'})",
                       f"AS{asn_num} | prefix {fields[1]} | {fields[2]} | owner: {org or 'unknown'}",
                       url=f"https://bgp.he.net/AS{asn_num}", raw_json=raw, confidence="high")
        return [header, c.res(self, "profile", f"AS{asn_num}", f"BGP origin AS for {ip} ({org or 'unknown'}).",
                              raw_json={"asn": f"AS{asn_num}", "as_owner": org}, confidence="high")]

    def _from_asn(self, asn_num, timeout):
        org = asn_name(asn_num, timeout)
        return [c.res(self, "record", f"AS{asn_num} -> {org or 'unknown'}", f"AS{asn_num} owner: {org or 'unknown'}",
                      url=f"https://bgp.he.net/AS{asn_num}",
                      raw_json={"asn": f"AS{asn_num}", "as_owner": org}, confidence="high")]
