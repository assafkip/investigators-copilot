"""AbuseIPDB: crowd-reported abuse confidence, reports, ISP, usage type. Needs $ABUSEIPDB_API_KEY. T3.

Ported from assafkip/kipi investigations/enrich/abuseipdb.py. Free tier: 1,000 checks/day.
A crowd score is never a crosslink (q-investigation.md evidence tiers).
"""
from __future__ import annotations

from . import _common as c
from .base import Adapter

_CHECK = "https://api.abuseipdb.com/api/v2/check"


class AbuseIpDbAdapter(Adapter):
    slug = "abuseipdb"
    display_name = "AbuseIPDB (IP abuse reports)"
    env_var = "ABUSEIPDB_API_KEY"
    signup_url = "https://www.abuseipdb.com/register"
    category = "reputation"
    tier = "T3"
    keyless = False
    watched_types = ("ip",)

    def run(self, query, mode=None, timeout=30):
        ip = c.require_ip(query, "abuseipdb")
        key = self.get_key()
        body = c.get_json(f"{_CHECK}?{c.qs({'ipAddress': ip, 'maxAgeInDays': 90, 'verbose': ''})}",
                          timeout=timeout, headers={"Key": key})
        d = (body or {}).get("data") or {}
        score = d.get("abuseConfidenceScore") or 0
        summary = (f"abuse confidence {score}/100; {d.get('totalReports') or 0} report(s); "
                   f"last {str(d.get('lastReportedAt') or '')[:10] or 'never'}\n"
                   f"{d.get('isp') or '?'} | {d.get('countryCode') or '?'} | usage {d.get('usageType') or '?'}"
                   + (" | TOR exit" if d.get("isTor") else ""))
        d.pop("reports", None)
        header = c.res(self, "document", f"AbuseIPDB: {ip}", summary,
                       url=f"https://www.abuseipdb.com/check/{ip}", raw_json=d,
                       confidence="high" if score >= 75 else "medium" if score >= 25 else "low")
        hosts = [h.lower() for h in ([d.get("domain")] + (d.get("hostnames") or [])) if h]
        return [header] + [c.res(self, "url", h, f"Hostname/domain reported on {ip} (AbuseIPDB).",
                                 url=f"http://{h}", confidence="low") for h in dict.fromkeys(hosts)]
