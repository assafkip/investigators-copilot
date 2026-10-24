#!/usr/bin/env python3
"""validate-citations.py -- are a report's links alive, and does the captured page back the claim?

For a markdown report:
  1. Extract every cited URL (markdown links, <autolinks>, bare http(s) URLs) and the
     sentence that cites it (verbatim slice, via lib/ioc_extract.sentence_context).
  2. HEAD each unique URL (GET fallback when HEAD is refused), polite UA, timeout,
     a delay between requests. Status: ok / dead / blocked (401/403/429: a login wall,
     bot block or rate limit -- capture by hand, per the Blocked Extraction rule).
  3. If a captured EV item exists for the URL (investigation/evidence/items/EV-*/
     source.json `source_url`), check the citing sentence's key tokens (hard facts:
     dates / IPs / emails / wallets, numbers of 2+ digits, "quoted spans") appear in
     that item's text files (content.md, *.txt, *.md, *.json, *.html).

Prints a markdown table; --json / --csv write machine-readable copies.
Exit: 0 all links alive; 1 one or more dead links (or setup error).
A claim-token miss is reported in the table but does not change the exit code: it is a
prompt to re-read the source, not proof the claim is false.

Usage:
  python3 validate-citations.py report.md [--case <case-folder> | --evidence-dir DIR]
      [--timeout 15] [--delay 0.5] [--no-network] [--json out.json] [--csv out.csv]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import ioc_extract  # noqa: E402

USER_AGENT = "Mozilla/5.0 (compatible; copilot-citation-check/1.0; +manual-review)"
MD_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^\s)]+)(?:\s+\"[^\"]*\")?\)")
AUTOLINK_RE = re.compile(r"<(https?://[^>\s]+)>")
BARE_URL_RE = re.compile(r"https?://[^\s<>\"'\)\]]+")
URL_TRAIL_RE = re.compile(r"[.,;:!?]+$")
HARD_TOKEN_RES = (
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    re.compile(r"\b[a-z0-9][a-z0-9._%+-]*@[a-z0-9.-]+\.[a-z]{2,}\b", re.I),
    re.compile(r"\b0x[a-fA-F0-9]{40}\b"),
    re.compile(r"\b(?:bc1[ac-hj-np-z02-9]{6,87}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b"),
)
NUMBER_RE = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?%?(?![\w])")
QUOTED_RE = re.compile(r"[\"\u201c]([^\"\u201d]{4,200})[\"\u201d]")
BLOCKED_CODES = {401, 403, 429}
EV_TEXT_SUFFIXES = {".md", ".txt", ".json", ".html", ".htm", ".csv"}


# ---------------- extraction ----------------

def extract_citations(text: str) -> list:
    """[{url, start, end, sentence}] for every URL occurrence, in document order."""
    found = []
    taken = []
    for rx in (MD_LINK_RE, AUTOLINK_RE, BARE_URL_RE):
        for m in rx.finditer(text):
            group = 1 if rx.groups else 0
            url = URL_TRAIL_RE.sub("", m.group(group))
            start = m.start(group)
            end = start + len(url)
            if any(start < e and s < end for s, e in taken):
                continue
            taken.append((start, end))
            ctx = ioc_extract.sentence_context(text, m.start(), m.end())
            found.append({"url": url, "start": start, "end": end, "sentence": ctx["context"]})
    return sorted(found, key=lambda c: c["start"])


def key_tokens(sentence: str, url: str) -> list:
    """Load-bearing tokens of a citing sentence (URLs themselves excluded)."""
    body = sentence
    for u in BARE_URL_RE.findall(sentence):
        body = body.replace(u, " ")
    tokens = set()
    for rx in HARD_TOKEN_RES:
        tokens |= {m.group(0) for m in rx.finditer(body)}
    for m in NUMBER_RE.finditer(body):
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) >= 2 and not any(m.group(0) in t for t in tokens):
            tokens.add(m.group(0))
    tokens |= {m.group(1).strip() for m in QUOTED_RE.finditer(body)}
    return sorted(t for t in tokens if t and t not in url)


# ---------------- network ----------------

def _request(url: str, method: str, timeout: float) -> int:
    req = urllib.request.Request(url, method=method, headers={
        "User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if method == "GET":
            resp.read(65536)
        return resp.status


def check_url(url: str, timeout: float) -> dict:
    """{status: ok|dead|blocked, code, detail}. HEAD first, GET when HEAD is refused."""
    code, detail = None, ""
    for method in ("HEAD", "GET"):
        try:
            code = _request(url, method, timeout)
            detail = method
            break
        except urllib.error.HTTPError as exc:
            code, detail = exc.code, f"{method} HTTP {exc.code}"
            if method == "HEAD" and exc.code in (400, 403, 404, 405, 429, 500, 501):
                continue  # many servers mishandle HEAD; confirm with GET
            break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            code, detail = None, f"{method} {type(exc).__name__}: {getattr(exc, 'reason', exc)}"
            if method == "HEAD":
                continue
    if code is not None and 200 <= code < 400:
        status = "ok"
    elif code in BLOCKED_CODES:
        status = "blocked"
    else:
        status = "dead"
    return {"status": status, "code": code, "detail": detail}


# ---------------- EV items ----------------

def find_evidence_dir(report: Path, case: str | None, evidence_dir: Path | None) -> Path | None:
    if evidence_dir:
        return evidence_dir
    if case:
        from active_case import resolve_case_dir
        _, case_dir = resolve_case_dir(case)
        return case_dir / "investigation" / "evidence" / "items"
    for parent in report.resolve().parents:
        items = parent / "investigation" / "evidence" / "items"
        if items.is_dir():
            return items
    return None


def _norm_url(url: str) -> str:
    return url.rstrip("/").lower()


def index_ev_items(items_dir: Path | None) -> dict:
    """normalized url -> list of EV item dirs."""
    index: dict = {}
    if not items_dir or not items_dir.is_dir():
        return index
    for src in sorted(items_dir.glob("EV-*/source.json")):
        try:
            meta = json.loads(src.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[validate-citations] WARN: unreadable {src}: {exc}", file=sys.stderr)
            continue
        url = meta.get("source_url") or meta.get("url")
        if url:
            index.setdefault(_norm_url(url), []).append(src.parent)
    return index


def ev_text(item_dir: Path) -> str:
    parts = []
    for p in sorted(item_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in EV_TEXT_SUFFIXES:
            parts.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def claim_check(cite: dict, ev_index: dict) -> tuple:
    items = ev_index.get(_norm_url(cite["url"]), [])
    if not items:
        return "", "no EV item"
    corpus = "\n".join(ev_text(d) for d in items).lower()
    tokens = key_tokens(cite["sentence"], cite["url"])
    ev_ids = ",".join(d.name.split("-")[0] + "-" + d.name.split("-")[1] for d in items)
    if not tokens:
        return ev_ids, "no key tokens to check"
    missing = [t for t in tokens if t.lower() not in corpus]
    return ev_ids, ("ok" if not missing else "missing: " + "; ".join(missing))


# ---------------- main ----------------

def validate(report: Path, ev_index: dict, network: bool, timeout: float, delay: float,
             checker=check_url) -> list:
    text = report.read_text(encoding="utf-8")
    cites = extract_citations(text)
    status_cache: dict = {}
    rows = []
    for cite in cites:
        if cite["url"] not in status_cache:
            if network:
                if status_cache:
                    time.sleep(delay)
                status_cache[cite["url"]] = checker(cite["url"], timeout)
            else:
                status_cache[cite["url"]] = {"status": "unchecked", "code": None,
                                             "detail": "--no-network"}
        ev_ids, claim = claim_check(cite, ev_index)
        st = status_cache[cite["url"]]
        rows.append({"url": cite["url"], "status": st["status"], "code": st["code"],
                     "detail": st["detail"], "ev_items": ev_ids, "claim_check": claim,
                     "sentence": cite["sentence"]})
    return rows


def _cell(value) -> str:
    return str("" if value is None else value).replace("|", "\\|").replace("\n", " ")


def print_table(rows: list) -> None:
    print("| # | Status | Code | URL | EV | Claim check | Citing sentence |")
    print("|---|--------|------|-----|----|-------------|-----------------|")
    for i, r in enumerate(rows, start=1):
        sentence = r["sentence"] if len(r["sentence"]) <= 140 else r["sentence"][:137] + "..."
        print(f"| {i} | {r['status']} | {_cell(r['code'])} | {_cell(r['url'])} | "
              f"{_cell(r['ev_items'])} | {_cell(r['claim_check'])} | {_cell(sentence)} |")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validate report citations.")
    ap.add_argument("report", type=Path)
    ap.add_argument("--case")
    ap.add_argument("--evidence-dir", type=Path)
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--no-network", action="store_true")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--csv", type=Path)
    args = ap.parse_args(argv)
    if not args.report.is_file():
        print(f"ERROR: report not found: {args.report}", file=sys.stderr)
        return 1

    ev_index = index_ev_items(find_evidence_dir(args.report, args.case, args.evidence_dir))
    rows = validate(args.report, ev_index, not args.no_network, args.timeout, args.delay)
    print_table(rows)
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.csv:
        with args.csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["url"])
            writer.writeheader()
            writer.writerows(rows)

    dead = sorted({r["url"] for r in rows if r["status"] == "dead"})
    blocked = sorted({r["url"] for r in rows if r["status"] == "blocked"})
    print(f"\ncitations={len(rows)} unique_urls={len({r['url'] for r in rows})} "
          f"dead={len(dead)} blocked={len(blocked)}")
    if blocked:
        print("BLOCKED (login wall / bot block / rate limit): open and capture by hand:",
              file=sys.stderr)
        for url in blocked:
            print(f"  {url}", file=sys.stderr)
    if dead:
        print("DEAD LINKS:", file=sys.stderr)
        for url in dead:
            print(f"  {url}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
