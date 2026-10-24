#!/usr/bin/env python3
"""render-timeline.py -- /q-export timeline-html: master-timeline.md -> self-contained HTML (+ Timesketch CSV).

Input (tolerant parser), default investigations/<case>/investigation/timelines/master-timeline.md:
  * markdown tables whose header has a Date-like column ("Date", "When", "Date/Time")
    and any of Event / Description / What / Activity, plus optional Source / Evidence /
    Confidence / Actor columns
  * bullets:  "- 2026-03-14: text"   "- 2026-03-14 02:46 -- text"   "- **2026-03-14** text"
    "* 2026-03 - text" (month precision)   "- 2026-03-14T02:46:00Z | text"
Undated lines are ignored and counted.

Output, default <case>/output/exports/:
  timeline-<date>.html   one file, no network needed (inline CSS + JS, data embedded as
                         JSON). --vis instead loads vis-timeline 7.7.3 pinned from
                         jsdelivr for an interactive zoomable band (needs network to view).
  --timesketch           also writes timeline-<date>.timesketch.csv with the Timesketch
                         import columns: message, datetime, timestamp_desc (+ timestamp,
                         source, evidence, confidence).

Usage:
  render-timeline.py [--case C | --case-dir PATH | --input FILE] [--out DIR] [--title T]
                     [--vis] [--timesketch]
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

VIS_JS = "https://cdn.jsdelivr.net/npm/vis-timeline@7.7.3/standalone/umd/vis-timeline-graph2d.min.js"
VIS_CSS = "https://cdn.jsdelivr.net/npm/vis-timeline@7.7.3/styles/vis-timeline-graph2d.min.css"

DATE_RE = re.compile(
    r"(?P<y>(?:19|20)\d{2})-(?P<m>\d{2})(?:-(?P<d>\d{2}))?"
    r"(?:[T ](?P<H>\d{1,2}):(?P<M>\d{2})(?::(?P<S>\d{2}))?)?\s*(?P<tz>Z|UTC|[+-]\d{2}:?\d{2})?"
)
BULLET_RE = re.compile(r"^\s*[-*+]\s+(?P<body>.+)$")
EV_RE = re.compile(r"\[?(EV-\d{4})\]?")

DATE_COLS = ("date", "when", "date/time", "datetime", "time", "timestamp")
EVENT_COLS = ("event", "description", "what", "activity", "summary", "detail", "details")


def parse_date(text: str) -> tuple[str, str] | None:
    """(iso_utc, precision) from the first date in text, or None."""
    m = DATE_RE.search(text or "")
    if not m:
        return None
    y, mo = int(m["y"]), int(m["m"])
    d = int(m["d"]) if m["d"] else 1
    hh = int(m["H"]) if m["H"] else 0
    mi = int(m["M"]) if m["M"] else 0
    ss = int(m["S"]) if m["S"] else 0
    try:
        dt = datetime(y, mo, d, hh, mi, ss)
    except ValueError:
        return None
    tz = m["tz"] or ""
    if tz and tz not in ("Z", "UTC"):
        sign = 1 if tz[0] == "+" else -1
        digits = tz[1:].replace(":", "")
        offset_min = sign * (int(digits[:2]) * 60 + int(digits[2:4]))
        from datetime import timedelta
        dt = dt - timedelta(minutes=offset_min)
    precision = "time" if m["H"] else ("day" if m["d"] else "month")
    return dt.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), precision


def _strip_md(s: str) -> str:
    s = re.sub(r"\*\*|__|`", "", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", s)
    return s.strip()


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_sep(cells: list[str]) -> bool:
    return all(re.match(r"^:?-{2,}:?$", c) or not c for c in cells)


def parse_timeline(text: str) -> tuple[list[dict], int]:
    events: list[dict] = []
    skipped = 0
    lines = text.splitlines()
    i = 0
    section = ""
    while i < len(lines):
        line = lines[i]
        if line.startswith("#"):
            section = line.lstrip("#").strip()
        if line.strip().startswith("|") and i + 1 < len(lines) and _is_sep(_cells(lines[i + 1])):
            header = [h.lower() for h in _cells(line)]
            i += 2
            dcol = next((n for n, h in enumerate(header) if h in DATE_COLS or h.startswith("date")), None)
            ecol = next((n for n, h in enumerate(header) if h in EVENT_COLS), None)
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = _cells(lines[i])
                i += 1
                if dcol is None or dcol >= len(row):
                    skipped += 1
                    continue
                parsed = parse_date(row[dcol])
                if not parsed:
                    skipped += 1
                    continue
                if ecol is not None and ecol < len(row):
                    msg = row[ecol]
                else:
                    msg = " | ".join(c for n, c in enumerate(row) if n != dcol and c)
                extras = {h: row[n] for n, h in enumerate(header) if n < len(row) and n not in (dcol, ecol)}
                events.append(_event(parsed, msg, extras, section))
            continue
        b = BULLET_RE.match(line)
        if b:
            body = b["body"]
            parsed = parse_date(body)
            if parsed:
                msg = DATE_RE.sub("", body, count=1)
                msg = re.sub("^[\\s*_:|,.\\-\u2013\u2014]+", "", msg).strip()
                events.append(_event(parsed, msg, {}, section))
            elif re.search(r"\d", body):
                skipped += 1
        i += 1
    events.sort(key=lambda e: e["start"])
    return events, skipped


def _event(parsed: tuple[str, str], msg: str, extras: dict, section: str) -> dict:
    iso, precision = parsed
    msg = _strip_md(msg) or "(no description)"
    source = _strip_md(extras.get("source", "") or extras.get("sources", ""))
    evidence = sorted(set(EV_RE.findall(msg + " " + " ".join(extras.values()))))
    return {
        "start": iso,
        "precision": precision,
        "message": msg,
        "source": source,
        "evidence": evidence,
        "confidence": _strip_md(extras.get("confidence", "")),
        "actor": _strip_md(extras.get("actor", "") or extras.get("target", "") or extras.get("who", "")),
        "section": section,
    }


# ---------- HTML ----------

_CSS = """
:root{--bg:#fbfaf7;--fg:#1d1f21;--muted:#6b6f76;--line:#d9d6cf;--accent:#1f5f8b;--chip:#eef2f5}
@media (prefers-color-scheme:dark){:root{--bg:#16181b;--fg:#e7e5e0;--muted:#9aa0a6;--line:#33373c;--accent:#7fb3d9;--chip:#22272c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
header{padding:24px 16px 8px;max-width:960px;margin:auto}h1{font-size:22px;margin:0 0 4px}
.meta{color:var(--muted);font-size:13px}main{max-width:960px;margin:auto;padding:0 16px 48px}
.strip{width:100%;height:46px;margin:12px 0 4px;display:block}
.controls{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 16px}
input[type=search]{flex:1;min-width:180px;padding:8px 10px;border:1px solid var(--line);border-radius:6px;background:transparent;color:var(--fg);font:inherit}
.year{font-weight:600;color:var(--accent);margin:22px 0 6px;border-bottom:1px solid var(--line);padding-bottom:2px}
.ev{display:grid;grid-template-columns:150px 1fr;gap:12px;padding:8px 0;border-bottom:1px dashed var(--line)}
.ev time{color:var(--muted);font-variant-numeric:tabular-nums;font-size:13px}
.chips{margin-top:4px;display:flex;gap:6px;flex-wrap:wrap}.chip{background:var(--chip);border-radius:4px;padding:1px 6px;font-size:12px;color:var(--muted)}
.hidden{display:none}#vis{margin:12px 0;border:1px solid var(--line)}
@media (max-width:560px){.ev{grid-template-columns:1fr;gap:2px}}
footer{color:var(--muted);font-size:12px;max-width:960px;margin:auto;padding:0 16px 24px}
"""

_JS = """
const EVENTS = JSON.parse(document.getElementById('data').textContent);
const list = document.getElementById('list');
function fmt(e){const d=e.start; if(e.precision==='month')return d.slice(0,7); if(e.precision==='day')return d.slice(0,10); return d.slice(0,16).replace('T',' ')+' UTC';}
function el(tag,cls,text){const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=text; return n;}
let lastYear=null;
EVENTS.forEach((e,i)=>{const y=e.start.slice(0,4); if(y!==lastYear){list.appendChild(el('div','year',y)); lastYear=y;}
  const row=el('div','ev'); row.dataset.i=i; const t=el('time','',fmt(e)); t.setAttribute('datetime',e.start);
  const body=el('div'); body.appendChild(el('div','',e.message)); const chips=el('div','chips');
  [e.actor,e.confidence&&('confidence: '+e.confidence),e.source&&('source: '+e.source)].concat(e.evidence).filter(Boolean).forEach(c=>chips.appendChild(el('span','chip',c)));
  if(chips.childNodes.length)body.appendChild(chips); row.appendChild(t); row.appendChild(body); list.appendChild(row);});
document.getElementById('q').addEventListener('input',ev=>{const q=ev.target.value.toLowerCase();
  list.querySelectorAll('.ev').forEach(r=>{const e=EVENTS[r.dataset.i]; const hay=(e.message+' '+e.source+' '+e.actor+' '+e.evidence.join(' ')).toLowerCase(); r.classList.toggle('hidden',q&&!hay.includes(q));});});
(function strip(){const svg=document.getElementById('strip'); if(!EVENTS.length)return; const ts=EVENTS.map(e=>Date.parse(e.start));
  const lo=Math.min(...ts), hi=Math.max(...ts), span=Math.max(hi-lo,1), W=1000, H=46; svg.setAttribute('viewBox','0 0 '+W+' '+H);
  const ns='http://www.w3.org/2000/svg'; const axis=document.createElementNS(ns,'line'); axis.setAttribute('x1',0);axis.setAttribute('x2',W);axis.setAttribute('y1',30);axis.setAttribute('y2',30);axis.setAttribute('stroke','currentColor');axis.setAttribute('opacity','.3'); svg.appendChild(axis);
  ts.forEach((t,i)=>{const x=10+(W-20)*(t-lo)/span; const c=document.createElementNS(ns,'circle'); c.setAttribute('cx',x);c.setAttribute('cy',30);c.setAttribute('r',4);c.setAttribute('fill','var(--accent)');c.setAttribute('opacity','.7');
    const ti=document.createElementNS(ns,'title'); ti.textContent=fmt(EVENTS[i])+' '+EVENTS[i].message; c.appendChild(ti); svg.appendChild(c);});
  [[lo,'start'],[hi,'end']].forEach(([t,a])=>{const tx=document.createElementNS(ns,'text'); tx.setAttribute('x',a==='start'?10:W-10); tx.setAttribute('y',14); tx.setAttribute('text-anchor',a); tx.setAttribute('font-size','12'); tx.setAttribute('fill','currentColor'); tx.textContent=new Date(t).toISOString().slice(0,10); svg.appendChild(tx);});})();
"""

_VIS_JS = """
if (window.vis) { new vis.Timeline(document.getElementById('vis'), new vis.DataSet(EVENTS.map((e,i)=>({id:i,start:e.start,content:e.message.length>60?e.message.slice(0,57)+'...':e.message,title:e.message}))), {stack:true,zoomable:true}); }
"""


def render_html(events: list[dict], title: str, skipped: int, use_vis: bool) -> str:
    data = json.dumps(events, ensure_ascii=False).replace("</", "<\\/")
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    head_extra = (f'<link rel="stylesheet" href="{VIS_CSS}">\n<script src="{VIS_JS}"></script>' if use_vis else "")
    vis_div = '<div id="vis"></div>' if use_vis else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>{_CSS}</style>
{head_extra}
</head><body>
<header><h1>{html.escape(title)}</h1>
<div class="meta">{len(events)} dated events &middot; generated {generated}{f" &middot; {skipped} undated lines skipped" if skipped else ""}</div></header>
<main>
<svg id="strip" class="strip" role="img" aria-label="Event density over time"></svg>
{vis_div}
<div class="controls"><input id="q" type="search" placeholder="Filter by text, source, actor or EV id"></div>
<div id="list"></div>
</main>
<footer>Times are UTC. Each entry is only as strong as its cited source; EV ids refer to the case evidence items.</footer>
<script id="data" type="application/json">{data}</script>
<script>{_JS}{_VIS_JS if use_vis else ""}</script>
</body></html>
"""


def write_timesketch(events: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["message", "datetime", "timestamp_desc", "timestamp", "source", "evidence", "confidence"])
        for e in events:
            dt = datetime.strptime(e["start"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            desc = {"time": "Event Time", "day": "Event Date", "month": "Event Month"}[e["precision"]]
            w.writerow([e["message"], dt.isoformat(), desc, int(dt.timestamp() * 1_000_000),
                        e["source"], " ".join(e["evidence"]), e["confidence"]])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render master-timeline.md to HTML (+ Timesketch CSV).")
    ap.add_argument("--case", default="")
    ap.add_argument("--case-dir", default="")
    ap.add_argument("--input", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--vis", action="store_true", help="use vis-timeline 7.7.3 from jsdelivr (needs network)")
    ap.add_argument("--timesketch", action="store_true")
    args = ap.parse_args(argv)

    case_dir = None
    if args.case_dir:
        case_dir = Path(args.case_dir).resolve()
    elif not args.input:
        import active_case
        _, case_dir = active_case.resolve_case_dir(args.case)
    src = Path(args.input) if args.input else case_dir / "investigation" / "timelines" / "master-timeline.md"
    if not src.is_file():
        sys.exit(f"ERROR: timeline not found: {src} (build it with /q-timeline)")
    events, skipped = parse_timeline(src.read_text(encoding="utf-8", errors="replace"))
    if not events:
        sys.exit(f"ERROR: no dated events parsed from {src}")
    out_dir = Path(args.out) if args.out else (case_dir / "output" / "exports" if case_dir else src.parent)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = args.title or f"Timeline: {case_dir.name if case_dir else src.stem}"
    html_path = out_dir / f"timeline-{stamp}.html"
    html_path.write_text(render_html(events, title, skipped, args.vis), encoding="utf-8")
    print(html_path)
    if args.timesketch:
        ts_path = out_dir / f"timeline-{stamp}.timesketch.csv"
        write_timesketch(events, ts_path)
        print(ts_path)
    print(f"[render-timeline] {len(events)} events, {skipped} undated lines skipped", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
