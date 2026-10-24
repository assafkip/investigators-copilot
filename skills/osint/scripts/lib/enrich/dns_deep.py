"""Deep DNS: SPF + DMARC records over DNS-over-HTTPS, parsed into mail-infra pivots. Keyless, T1.

Ported from hydra src/osint/dns-deep.ts (plus the mail-provider guess from kipi
infra.py dns_deep). A published TXT record is a non-fakeable DNS record (T1). The
relationships it implies (an SPF include = an authorized third-party sender) are
read off the record, not inferred. No AXFR: that would touch the target's servers.
A domain that publishes neither SPF nor DMARC returns one record saying so.
"""
from __future__ import annotations

import re

from . import _common as c
from .base import Adapter

_PROVIDERS = {
    "google.com": "Google Workspace", "googlemail.com": "Google Workspace",
    "outlook.com": "Microsoft 365", "protection.outlook.com": "Microsoft 365",
    "protonmail.ch": "Proton Mail", "zoho.com": "Zoho Mail", "zoho.eu": "Zoho Mail",
    "mimecast.com": "Mimecast", "pphosted.com": "Proofpoint", "yandex.net": "Yandex Mail",
    "mail.ru": "Mail.ru", "secureserver.net": "GoDaddy", "messagingengine.com": "Fastmail",
    "icloud.com": "iCloud Mail", "amazonses.com": "Amazon SES",
}
_SPF_MECH = re.compile(r"^[+\-~?]?(include|redirect|a|mx|ip4|ip6|exists|ptr)[:=]?(.*)$", re.I)


def mail_provider(mx_hosts: list[str]) -> str:
    for host in mx_hosts:
        h = host.lower().rstrip(".")
        for suffix, name in _PROVIDERS.items():
            if h == suffix or h.endswith("." + suffix):
                return name
    return ""


def parse_spf(spf: str) -> list[tuple[str, str, str]]:
    """(kind, value, mechanism) for every pivotable SPF mechanism."""
    out = []
    for tok in spf.split():
        m = _SPF_MECH.match(tok)
        if not m:
            continue
        mech, arg = m.group(1).lower(), m.group(2).strip().rstrip(".")
        if mech in ("ip4", "ip6"):
            ip = arg.split("/")[0]
            if c.is_ip(ip):
                out.append(("ip", ip, mech))
        elif arg and c.DOMAIN_RE.match(arg.lower()):
            out.append(("domain", arg.lower(), mech))
    return out


def parse_dmarc(dmarc: str) -> tuple[str, list[str]]:
    """(policy, report-collection domains) from a DMARC record."""
    pol = re.search(r"\bp=([a-z]+)", dmarc, re.I)
    domains = []
    for m in re.finditer(r"\b(?:rua|ruf)=([^;]+)", dmarc, re.I):
        for uri in m.group(1).split(","):
            addr = re.sub(r"^mailto:", "", uri.strip(), flags=re.I)
            host = addr.rpartition("@")[2].lower().rstrip(".").split("!")[0]
            if "@" in addr and c.DOMAIN_RE.match(host) and host not in domains:
                domains.append(host)
    return (pol.group(1).lower() if pol else "none"), domains


class DnsDeepAdapter(Adapter):
    slug = "dns_deep"
    display_name = "SPF / DMARC / mail provider (DoH)"
    category = "infra"
    tier = "T1"
    watched_types = ("domain",)

    def run(self, query, mode=None, timeout=30):
        domain = c.require_domain(query, "dns_deep")
        spf = next((t for t in c.doh(domain, "TXT", timeout) if t.lower().startswith("v=spf1")), "")
        dmarc = next((t for t in c.doh(f"_dmarc.{domain}", "TXT", timeout)
                      if t.lower().startswith("v=dmarc1")), "")
        mx = [r.split()[-1].rstrip(".") for r in c.doh(domain, "MX", timeout) if r.strip()]
        provider = mail_provider(mx)
        spf_items = parse_spf(spf) if spf else []
        policy, report_domains = parse_dmarc(dmarc) if dmarc else ("(no DMARC)", [])
        header = c.res(self, "record", f"DNS deep: {domain}",
                       f"SPF: {spf or '(none)'}\nDMARC: {dmarc or '(none -- no policy)'}\n"
                       f"MX: {', '.join(mx) or '(none)'}\nmail provider: {provider or 'unknown'}",
                       raw_json={"domain": domain, "spf": spf, "dmarc": dmarc, "dmarc_policy": policy,
                                 "mx": mx, "mail_provider": provider,
                                 "spf_mechanisms": spf_items, "dmarc_report_domains": report_domains},
                       confidence="high")
        rows = [c.res(self, "record", value, f"SPF {mech} of {domain} (authorized sender)",
                      raw_json={"kind": kind, "mechanism": mech}, confidence="high")
                for kind, value, mech in spf_items]
        rows += [c.res(self, "record", d, f"DMARC report domain (p={policy}) of {domain}",
                       raw_json={"kind": "domain"}, confidence="high") for d in report_domains]
        return [header] + rows
