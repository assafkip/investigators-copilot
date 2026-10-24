#!/usr/bin/env python3
"""ioc-reputation.py -- bulk reputation lookups for an iocs.json (from extract-intake.py).

Sources (stdlib urllib only; lookups are GETs, nothing is submitted for scanning):
  internetdb  -- Shodan InternetDB, keyless            (ip)
  abuseipdb   -- AbuseIPDB v2 check, $ABUSEIPDB_API_KEY (ip)
  greynoise   -- GreyNoise community, $GREYNOISE_API_KEY (ip)
  virustotal  -- VirusTotal v3, $VT_API_KEY            (ip, domain, url, file_hash)
A source with no key is reported as `not configured -- add a key`, never silently dropped.
Non-public IPs (RFC1918, loopback, documentation ranges) are skipped, not sent anywhere.

EVERY row is T3 (automated tool output): a reputation score is a lead, never a finding.
OPSEC: each lookup discloses the indicator to that provider. Do not run this on
indicators whose disclosure could tip off a subject without founder sign-off.

Input: iocs.json shaped {"iocs": [{"field_type": "ip"|"domain"|"url"|"file_hash", "value"}]}
       or a bare list of such objects. Several files may be given.
Output: CSV (default ioc-reputation.csv next to the first input):
  ioc, type, source, status, verdict, score, details, queried_at, evidence_tier

Usage:
  python3 ioc-reputation.py extracted/<doc>/iocs.json [...] [--out rep.csv]
      [--sources internetdb,abuseipdb,greynoise,virustotal] [--types ip,domain]
      [--max 200] [--delay 1.0] [--vt-delay 15] [--timeout 20]
Exit: 0 ok (individual lookup errors are rows with status=error); 1 input error.
"""

from __future__ import annotations

import argparse
import base64
import csv
import ipaddress
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USER_AGENT = "copilot-ioc-reputation/1.0"
ALL_SOURCES = ["internetdb", "abuseipdb", "greynoise", "virustotal"]
SOURCE_TYPES = {"internetdb": {"ip"}, "abuseipdb": {"ip"}, "greynoise": {"ip"},
                "virustotal": {"ip", "domain", "url", "file_hash"}}
SOURCE_KEYS = {"abuseipdb": "ABUSEIPDB_API_KEY", "greynoise": "GREYNOISE_API_KEY",
               "virustotal": "VT_API_KEY"}
COLUMNS = ["ioc", "type", "source", "status", "verdict", "score", "details", "queried_at",
           "evidence_tier"]


class HttpResult:
    def __init__(self, code: int, body: dict | None):
        self.code = code
        self.body = body


def http_get_json(url: str, headers: dict, timeout: float) -> HttpResult:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return HttpResult(resp.status, json.loads(resp.read().decode("utf-8") or "{}"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            body = {"raw": raw[:300]}
        return HttpResult(exc.code, body)


# ---------------- per-source adapters: (status, verdict, score, details) ----------------

def q_internetdb(value, _type, _key, get, timeout):
    r = get(f"https://internetdb.shodan.io/{urllib.parse.quote(value)}", {}, timeout)
    if r.code == 404:
        return "ok", "no data", "", {}
    if r.code != 200:
        return "error", f"HTTP {r.code}", "", r.body or {}
    b = r.body or {}
    details = {k: b.get(k) for k in ("ports", "hostnames", "tags", "vulns", "cpes")}
    verdict = f"{len(b.get('ports') or [])} ports, {len(b.get('vulns') or [])} vulns"
    return "ok", verdict, "", details


def q_abuseipdb(value, _type, key, get, timeout):
    qs = urllib.parse.urlencode({"ipAddress": value, "maxAgeInDays": 90})
    r = get(f"https://api.abuseipdb.com/api/v2/check?{qs}", {"Key": key}, timeout)
    if r.code != 200:
        return "error", f"HTTP {r.code}", "", r.body or {}
    d = (r.body or {}).get("data") or {}
    details = {k: d.get(k) for k in ("totalReports", "countryCode", "isp", "usageType",
                                     "domain", "isTor", "lastReportedAt")}
    score = d.get("abuseConfidenceScore")
    return "ok", f"abuse confidence {score}%", score, details


def q_greynoise(value, _type, key, get, timeout):
    r = get(f"https://api.greynoise.io/v3/community/{urllib.parse.quote(value)}",
            {"key": key}, timeout)
    if r.code == 404:
        return "ok", "not observed by GreyNoise", "", r.body or {}
    if r.code != 200:
        return "error", f"HTTP {r.code}", "", r.body or {}
    b = r.body or {}
    details = {k: b.get(k) for k in ("noise", "riot", "classification", "name", "last_seen")}
    return "ok", b.get("classification") or "unknown", "", details


def _vt_path(value: str, ioc_type: str) -> str:
    if ioc_type == "ip":
        return f"ip_addresses/{value}"
    if ioc_type == "domain":
        return f"domains/{value}"
    if ioc_type == "url":
        return "urls/" + base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")
    return f"files/{value}"


def q_virustotal(value, ioc_type, key, get, timeout):
    r = get(f"https://www.virustotal.com/api/v3/{_vt_path(value, ioc_type)}",
            {"x-apikey": key}, timeout)
    if r.code == 404:
        return "ok", "not in VirusTotal", "", {}
    if r.code != 200:
        return "error", f"HTTP {r.code}", "", r.body or {}
    attrs = ((r.body or {}).get("data") or {}).get("attributes") or {}
    stats = attrs.get("last_analysis_stats") or {}
    malicious = stats.get("malicious", 0)
    verdict = f"{malicious} malicious / {sum(stats.values()) if stats else 0} engines"
    details = {"last_analysis_stats": stats, "reputation": attrs.get("reputation"),
               "tags": attrs.get("tags")}
    return "ok", verdict, malicious, details


ADAPTERS = {"internetdb": q_internetdb, "abuseipdb": q_abuseipdb,
            "greynoise": q_greynoise, "virustotal": q_virustotal}


# ---------------- orchestration ----------------

def load_iocs(paths: list) -> list:
    seen, out = set(), []
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get("iocs", []) if isinstance(data, dict) else data
        for it in items:
            if not isinstance(it, dict):
                continue
            key = (it.get("field_type"), it.get("value"))
            if key[0] and key[1] and key not in seen:
                seen.add(key)
                out.append({"type": key[0], "value": key[1]})
    return out


def non_public_ip(value: str) -> bool:
    try:
        return not ipaddress.ip_address(value).is_global
    except ValueError:
        return False


def _row(ioc, source, status, verdict="", score="", details=None) -> dict:
    return {"ioc": ioc["value"], "type": ioc["type"], "source": source, "status": status,
            "verdict": verdict, "score": score,
            "details": json.dumps(details or {}, sort_keys=True, ensure_ascii=False),
            "queried_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "evidence_tier": "T3"}


def lookup_all(iocs: list, sources: list, get=http_get_json, timeout: float = 20,
               delay: float = 1.0, vt_delay: float = 15.0, sleep=time.sleep) -> list:
    rows = []
    last_call: dict = {}
    for ioc in iocs:
        for source in sources:
            if ioc["type"] not in SOURCE_TYPES[source]:
                continue
            if ioc["type"] == "ip" and non_public_ip(ioc["value"]):
                rows.append(_row(ioc, source, "skipped", "non-public IP, not sent"))
                continue
            env = SOURCE_KEYS.get(source)
            key = os.environ.get(env, "") if env else ""
            if env and not key:
                rows.append(_row(ioc, source, "not configured", f"add a key: ${env}"))
                continue
            wait = (vt_delay if source == "virustotal" else delay) - (
                time.monotonic() - last_call.get(source, -1e9))
            if wait > 0:
                sleep(wait)
            try:
                status, verdict, score, details = ADAPTERS[source](
                    ioc["value"], ioc["type"], key, get, timeout)
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                status, verdict, score, details = "error", f"{type(exc).__name__}: {exc}", "", {}
            last_call[source] = time.monotonic()
            rows.append(_row(ioc, source, status, verdict, score, details))
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Bulk IOC reputation (T3).")
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--sources", default=",".join(ALL_SOURCES))
    ap.add_argument("--types", default="ip,domain,url,file_hash")
    ap.add_argument("--max", type=int, default=200, help="max indicators queried")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--vt-delay", type=float, default=15.0, help="VT public API: 4/min")
    ap.add_argument("--timeout", type=float, default=20.0)
    args = ap.parse_args(argv)

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    unknown = [s for s in sources if s not in ADAPTERS]
    if unknown:
        print(f"ERROR: unknown source(s): {', '.join(unknown)}", file=sys.stderr)
        return 1
    for path in args.inputs:
        if not path.is_file():
            print(f"ERROR: not found: {path}", file=sys.stderr)
            return 1
    try:
        iocs = load_iocs(args.inputs)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: cannot read iocs: {exc}", file=sys.stderr)
        return 1
    wanted = {t.strip() for t in args.types.split(",")}
    iocs = [i for i in iocs if i["type"] in wanted]
    if len(iocs) > args.max:
        print(f"[ioc-reputation] {len(iocs)} indicators; querying the first {args.max} "
              f"(raise --max to query more)", file=sys.stderr)
        iocs = iocs[:args.max]

    rows = lookup_all(iocs, sources, timeout=args.timeout, delay=args.delay,
                      vt_delay=args.vt_delay)
    out = args.out or args.inputs[0].with_name("ioc-reputation.csv")
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    by_status: dict = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    print(f"indicators={len(iocs)} rows={len(rows)} {by_status} -> {out} (all T3)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
