"""Email intel: triage an address, or pivot raw headers to source IPs. Keyless, T3.

Ported from assafkip/kipi investigations/enrich/email_intel.py. Modes:

  triage  (default)  user@domain -> MX hosts, mail provider, SPF, DMARC policy,
                     disposable-domain flag. DNS goes over DNS-over-HTTPS
                     (Cloudflare, then Google) so no dnspython dependency.
  headers            raw RFC-822 headers -> Received hop chain + every public IP,
                     origin (bottom-most public) IP flagged. Auto-selected when the
                     query contains "Received:".
  holehe             account-registration enumeration, delegated to the holehe
                     adapter (GPL-3.0, subprocess only).

The DNS facts themselves are records, but this adapter's job is identity triage
of a person's address, so its results are tagged T3 leads. For a T1 DNS record
cite the infra/doh adapters directly.
"""
from __future__ import annotations

import ipaddress
import json
import re
import urllib.parse
from email import message_from_string

from ._identity_common import clean_email, lead
from .base import Adapter, EnrichmentError, http_json

DOH_ENDPOINTS = ("https://cloudflare-dns.com/dns-query", "https://dns.google/resolve")
MAX_HEADER_BYTES = 256_000
MAX_HOPS = 50
DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "guerrillamail.net", "sharklasers.com",
    "10minutemail.com", "temp-mail.org", "tempmail.com", "tempmail.dev", "yopmail.com",
    "trashmail.com", "dispostable.com", "getnada.com", "maildrop.cc", "mohmal.com",
    "mintemail.com", "throwawaymail.com", "fakeinbox.com", "spamgourmet.com",
    "mailnesia.com", "tempinbox.com", "emailondeck.com", "burnermail.io", "33mail.com",
    "anonaddy.me",
}
MX_PROVIDERS = (
    ("gmail-smtp-in.l.google.com", "Gmail (consumer)"),
    ("aspmx.l.google.com", "Google Workspace"), ("googlemail.com", "Google Workspace"),
    ("google.com", "Google Workspace"), ("protection.outlook.com", "Microsoft 365"),
    ("olc.protection.outlook.com", "Microsoft 365 (consumer)"), ("zoho.com", "Zoho Mail"),
    ("zoho.eu", "Zoho Mail"), ("protonmail.ch", "Proton Mail"), ("proton.me", "Proton Mail"),
    ("yandex.net", "Yandex Mail"), ("yandex.ru", "Yandex Mail"), ("mail.ru", "Mail.ru"),
    ("icloud.com", "Apple iCloud Mail"), ("pphosted.com", "Proofpoint (corporate filter)"),
    ("mimecast.com", "Mimecast (corporate filter)"),
    ("barracudanetworks.com", "Barracuda (corporate filter)"), ("mailgun.org", "Mailgun"),
    ("sendgrid.net", "SendGrid"), ("secureserver.net", "GoDaddy email"),
    ("emailsrvr.com", "Rackspace email"), ("ovh.net", "OVH email"),
)
_IP4_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
_IP6_RE = re.compile(r"\b((?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F:]{1,40})\b")
_TXT_CHUNK_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
_RTYPE = {"MX": 15, "TXT": 16}


def doh_query(name: str, rtype: str, timeout: int = 10) -> list[str]:
    """Answer data strings for name/rtype. [] on NXDOMAIN/no answer; raises if every resolver fails."""
    errors = []
    for endpoint in DOH_ENDPOINTS:
        url = endpoint + "?" + urllib.parse.urlencode({"name": name, "type": rtype})
        try:
            data = http_json(url, headers={"Accept": "application/dns-json"}, timeout=timeout)
        except EnrichmentError as exc:
            errors.append(str(exc))
            continue
        if data.get("Status") not in (0, 3):
            errors.append(f"{endpoint}: DNS status {data.get('Status')}")
            continue
        return [a.get("data", "") for a in data.get("Answer") or [] if a.get("type") == _RTYPE[rtype]]
    raise EnrichmentError(f"email: DoH {rtype} lookup failed for {name}: {'; '.join(errors)}")


def txt_records(name: str, timeout: int = 10) -> list[str]:
    out = []
    for data in doh_query(name, "TXT", timeout):
        chunks = _TXT_CHUNK_RE.findall(data)
        out.append("".join(chunks) if chunks else data)
    return out


def mx_hosts(domain: str, timeout: int = 10) -> list[str]:
    pairs = []
    for data in doh_query(domain, "MX", timeout):
        pref, _, host = data.partition(" ")
        host = host.strip().rstrip(".").lower()
        if host:
            pairs.append((int(pref) if pref.isdigit() else 99, host))
    return [h for _, h in sorted(pairs)]


def identify_provider(hosts: list[str]) -> str | None:
    """Longest matching MX suffix wins (olc.protection.outlook.com beats protection.outlook.com)."""
    ranked = sorted(MX_PROVIDERS, key=lambda pair: len(pair[0]), reverse=True)
    for host in hosts:
        for suffix, provider in ranked:
            if host == suffix or host.endswith("." + suffix):
                return provider
    return None


def dmarc_policy(domain: str, timeout: int = 10) -> tuple[str | None, str | None]:
    """(record, found_at): exact domain first, then parents down to two labels."""
    labels = domain.split(".")
    for i in range(max(1, len(labels) - 1)):
        candidate = ".".join(labels[i:])
        found = [t for t in txt_records(f"_dmarc.{candidate}", timeout) if t.lower().startswith("v=dmarc1")]
        if found:
            return found[0], candidate
    return None, None


def public_ips(text: str) -> list[str]:
    out = []
    for raw in _IP4_RE.findall(text) + _IP6_RE.findall(text):
        try:
            addr = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if addr.is_global and str(addr) not in out:
            out.append(str(addr))
    return out


def parse_received_chain(raw_headers: str) -> dict:
    """Received hops top (nearest) to bottom (origin); origin = bottom-most hop with a public IP."""
    if len(raw_headers) > MAX_HEADER_BYTES:
        raise EnrichmentError(f"email: header block over {MAX_HEADER_BYTES} bytes; paste headers only")
    raw_headers = raw_headers.replace("\r\n", "\n").split("\n\n", 1)[0]
    msg = message_from_string(raw_headers)
    hops = []
    for i, line in enumerate((msg.get_all("Received") or [])[:MAX_HOPS]):
        flat = " ".join(str(line).split())
        hops.append({"hop": i + 1, "line": flat[:300], "ips": public_ips(flat)})
    origin = next((h["ips"][0] for h in reversed(hops) if h["ips"]), None)
    x_orig = public_ips(str(msg.get("X-Originating-IP") or ""))
    return {"hops": hops, "origin_ip": origin, "x_originating_ip": x_orig[0] if x_orig else None,
            "from": msg.get("From"), "return_path": msg.get("Return-Path"),
            "auth_results": " ".join(str(msg.get("Authentication-Results") or "").split())[:300] or None}


class EmailIntelAdapter(Adapter):
    slug = "email_intel"
    display_name = "Email intel (MX/SPF/DMARC triage + header Received-chain -> IPs)"
    category = "identity"
    tier = "T3"
    watched_types = ("email",)

    def modes(self):
        return ["triage", "headers", "holehe"]

    def run(self, query, mode=None, timeout=60):
        mode = (mode or "triage").lower()
        if mode == "triage" and "received:" in (query or "").lower():
            mode = "headers"
        if mode == "headers":
            return self._headers(query)
        if mode == "holehe":
            from .holehe import HoleheAdapter
            return HoleheAdapter().run(query, timeout=max(timeout, 120))
        if mode != "triage":
            raise EnrichmentError(f"email_intel: unknown mode {mode!r}")
        return self._triage(clean_email(query, self.slug), min(timeout, 15))

    def _triage(self, email: str, timeout: int):
        domain = email.rsplit("@", 1)[1]
        hosts = mx_hosts(domain, timeout)
        provider = identify_provider(hosts)
        spf = [t for t in txt_records(domain, timeout) if t.lower().startswith("v=spf1")]
        dmarc, dmarc_at = dmarc_policy(domain, timeout)
        policy = (re.search(r"\bp=([a-z]+)", dmarc or "", re.I) or [None, None])[1]
        facts = {"email": email, "domain": domain, "mx": hosts, "provider": provider,
                 "spf": spf[0] if len(spf) == 1 else None, "spf_permerror": len(spf) > 1,
                 "dmarc": dmarc, "dmarc_at": dmarc_at, "dmarc_policy": policy and policy.lower(),
                 "disposable": domain in DISPOSABLE_DOMAINS}
        title = f"Email triage: {email}" + (" [DISPOSABLE]" if facts["disposable"] else "") + \
            (f" [{provider}]" if provider else "")
        rows = [lead(title, self._triage_summary(facts), raw=facts, rtype="document",
                     confidence="high" if hosts else "medium")]
        rows += [lead(host, f"MX host for {domain}" + (f" ({provider})" if provider else ""),
                      rtype="record", confidence="medium") for host in hosts[:5]]
        return rows

    @staticmethod
    def _triage_summary(f: dict) -> str:
        spf = "PERMERROR (multiple v=spf1)" if f["spf_permerror"] else (f["spf"] or "NONE (spoofable)")
        dmarc = f"{f['dmarc']} (at {f['dmarc_at']})" if f["dmarc"] else "NONE (no policy)"
        return "\n".join([
            f"MX: {', '.join(f['mx']) or 'NONE (implicit A-record fallback possible)'}",
            f"provider: {f['provider'] or 'unrecognized'}", f"SPF: {spf[:160]}",
            f"DMARC: {dmarc[:160]}", f"disposable: {'YES' if f['disposable'] else 'no'}"])

    def _headers(self, query: str):
        raw = (query or "").strip()
        if ":" not in raw:
            raise EnrichmentError("email_intel: mode=headers needs raw RFC-822 headers as the query")
        chain = parse_received_chain(raw)
        if not chain["hops"]:
            raise EnrichmentError("email_intel: no Received headers found in the pasted text")
        lines = [f"hop {h['hop']}: {h['line'][:160]}" + (f" [IPs: {', '.join(h['ips'])}]" if h["ips"] else "")
                 for h in chain["hops"]]
        meta = {k: chain[k] for k in ("origin_ip", "x_originating_ip", "from", "return_path", "auth_results")}
        rows = [lead(f"Header hop chain ({len(chain['hops'])} hops) origin {chain['origin_ip'] or 'not found'}",
                     json.dumps(meta) + "\n" + "\n".join(lines), raw=chain, rtype="document", confidence="high")]
        seen = []
        for hop in chain["hops"]:
            for ip in (i for i in hop["ips"] if i not in seen):
                seen.append(ip)
                role = "ORIGIN source IP" if ip == chain["origin_ip"] else "relay source IP"
                rows.append(lead(ip, f"{role} (Received hop {hop['hop']}); pivot via asn/rdap/shodan",
                                 rtype="ioc", confidence="high" if role.startswith("ORIGIN") else "medium"))
        return rows
