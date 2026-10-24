#!/usr/bin/env python3
"""render-map.py -- Leaflet HTML map from geo-tagged evidence.

Sources (any combination):
  * every exif.json under investigations/<case>/investigation/evidence/ (EV items and
    extracted/ folders). Accepts exiftool -json output (a list of dicts) or a single
    dict, with GPS as decimal GPSLatitude/GPSLongitude (+ Ref), DMS strings
    ("40 deg 26' 46.30\\" N"), a GPSPosition string, or lat/lon/latitude/longitude keys.
  * --csv FILE: columns lat, lon (or latitude/longitude) and optional label, date, ev,
    source. Repeatable.

Output: <case>/output/exports/map-<date>.html (or --out). The page loads Leaflet 1.9.4
from cdnjs and OpenStreetMap tiles, so VIEWING needs network; the point table under the
map is plain HTML and works offline. Points are EXIF/analyst claims, not verified
locations: EXIF can be stripped, edited or wrong (see skills/geo-sleuth/SKILL.md).

Usage:
  render-map.py [--case C | --case-dir PATH] [--csv FILE ...] [--out DIR] [--title T] [--no-exif]
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

LEAFLET_CSS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"
LEAFLET_JS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"

DMS_RE = re.compile(
    r"(?P<deg>-?\d+(?:\.\d+)?)\s*(?:deg|°)?\s*(?:(?P<min>\d+(?:\.\d+)?)\s*['′])?\s*"
    r"(?:(?P<sec>\d+(?:\.\d+)?)\s*(?:\"|″|''))?\s*(?P<hem>[NSEW])?",
    re.I,
)
EV_RE = re.compile(r"(EV-\d{4})")


def parse_coord(value, ref: str = "") -> float | None:
    """Decimal or DMS string -> signed decimal degrees."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        num = float(value)
    else:
        m = DMS_RE.search(str(value).strip())
        if not m:
            return None
        num = abs(float(m["deg"])) + float(m["min"] or 0) / 60 + float(m["sec"] or 0) / 3600
        if str(value).strip().startswith("-"):
            num = -num
        ref = m["hem"] or ref
    if (ref or "").strip().upper()[:1] in ("S", "W") and num > 0:
        num = -num
    return num


def _get(d: dict, *keys):
    lower = {k.lower().split(":")[-1]: v for k, v in d.items()}
    for k in keys:
        if k.lower() in lower and lower[k.lower()] not in (None, ""):
            return lower[k.lower()]
    return None


def coords_from_exif(d: dict) -> tuple[float, float] | None:
    pos = _get(d, "GPSPosition")
    if isinstance(pos, str) and "," in pos:
        a, b = pos.split(",", 1)
        lat, lon = parse_coord(a), parse_coord(b)
    else:
        lat = parse_coord(_get(d, "GPSLatitude", "latitude", "lat"), str(_get(d, "GPSLatitudeRef") or ""))
        lon = parse_coord(_get(d, "GPSLongitude", "longitude", "lon", "lng"), str(_get(d, "GPSLongitudeRef") or ""))
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    if lat == 0 and lon == 0:
        return None  # null island: almost always a zeroed tag, not a location
    return round(lat, 6), round(lon, 6)


def points_from_exif_files(case_dir: Path) -> list[dict]:
    points = []
    edir = case_dir / "investigation" / "evidence"
    for path in sorted(edir.rglob("exif.json")) if edir.is_dir() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            print(f"[warn] unreadable {path}: {exc}", file=sys.stderr)
            continue
        records = data if isinstance(data, list) else [data]
        rel = str(path.relative_to(case_dir))
        ev = EV_RE.search(rel)
        for rec in records:
            if not isinstance(rec, dict):
                continue
            c = coords_from_exif(rec)
            if not c:
                continue
            points.append({
                "lat": c[0], "lon": c[1],
                "label": str(_get(rec, "FileName", "SourceFile") or path.parent.name),
                "date": str(_get(rec, "DateTimeOriginal", "CreateDate", "GPSDateTime") or ""),
                "ev": ev.group(1) if ev else "",
                "source": rel, "kind": "exif",
            })
    return points


def points_from_csv(path: Path) -> list[dict]:
    points = []
    with path.open(encoding="utf-8", newline="") as fh:
        for n, row in enumerate(csv.DictReader(fh), start=2):
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
            lat = parse_coord(row.get("lat") or row.get("latitude"))
            lon = parse_coord(row.get("lon") or row.get("lng") or row.get("longitude"))
            if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                print(f"[warn] {path.name}:{n}: no usable lat/lon, skipped", file=sys.stderr)
                continue
            points.append({"lat": round(lat, 6), "lon": round(lon, 6), "label": row.get("label", ""),
                           "date": row.get("date", ""), "ev": row.get("ev", ""),
                           "source": row.get("source", "") or path.name, "kind": "csv"})
    return points


def render_html(points: list[dict], title: str) -> str:
    data = json.dumps(points, ensure_ascii=False).replace("</", "<\\/")
    rows = "\n".join(
        f"<tr><td>{p['lat']}</td><td>{p['lon']}</td><td>{html.escape(p['label'])}</td>"
        f"<td>{html.escape(p['date'])}</td><td>{html.escape(p['ev'])}</td><td>{html.escape(p['source'])}</td></tr>"
        for p in points)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="{LEAFLET_CSS}">
<style>
:root{{--bg:#fbfaf7;--fg:#1d1f21;--muted:#6b6f76;--line:#d9d6cf}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16181b;--fg:#e7e5e0;--muted:#9aa0a6;--line:#33373c}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}}
header,section{{max-width:1100px;margin:auto;padding:16px}}h1{{font-size:22px;margin:0}}.meta{{color:var(--muted);font-size:13px}}
#map{{height:60vh;min-height:320px;max-width:1100px;margin:auto;border:1px solid var(--line)}}
.wrap{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:13px}}td,th{{border-bottom:1px solid var(--line);padding:4px 8px;text-align:left}}
</style></head><body>
<header><h1>{html.escape(title)}</h1>
<div class="meta">{len(points)} points &middot; generated {generated} &middot; EXIF/analyst coordinates, not verified locations</div></header>
<div id="map"></div>
<section><div class="wrap"><table><thead><tr><th>lat</th><th>lon</th><th>label</th><th>date</th><th>EV</th><th>source</th></tr></thead>
<tbody>{rows}</tbody></table></div></section>
<script id="data" type="application/json">{data}</script>
<script src="{LEAFLET_JS}"></script>
<script>
const PTS = JSON.parse(document.getElementById('data').textContent);
if (window.L && PTS.length) {{
  const map = L.map('map');
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors'}}).addTo(map);
  const group = L.featureGroup();
  PTS.forEach(p => {{
    const div = document.createElement('div');
    [p.label, p.date, p.ev, p.source, p.lat + ', ' + p.lon].filter(Boolean).forEach(t => {{
      const line = document.createElement('div'); line.textContent = t; div.appendChild(line); }});
    L.marker([p.lat, p.lon]).bindPopup(div).addTo(group);
  }});
  group.addTo(map);
  map.fitBounds(group.getBounds().pad(0.2), {{maxZoom: 15}});
}} else {{
  document.getElementById('map').textContent = 'Map library unavailable offline; see the table below.';
}}
</script>
</body></html>
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Leaflet map of geo-tagged evidence.")
    ap.add_argument("--case", default="")
    ap.add_argument("--case-dir", default="")
    ap.add_argument("--csv", action="append", default=[])
    ap.add_argument("--out", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--no-exif", action="store_true")
    args = ap.parse_args(argv)

    case_dir = None
    if args.case_dir:
        case_dir = Path(args.case_dir).resolve()
    elif not (args.csv and args.no_exif):
        import active_case
        _, case_dir = active_case.resolve_case_dir(args.case)
    points = [] if (args.no_exif or case_dir is None) else points_from_exif_files(case_dir)
    for c in args.csv:
        points += points_from_csv(Path(c))
    if not points:
        sys.exit("ERROR: no geo-tagged points found (no GPS in exif.json files and no usable CSV rows)")
    out_dir = Path(args.out) if args.out else (case_dir / "output" / "exports" if case_dir else Path.cwd())
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = args.title or f"Evidence map: {case_dir.name if case_dir else 'points'}"
    path = out_dir / f"map-{stamp}.html"
    path.write_text(render_html(points, title), encoding="utf-8")
    print(path)
    print(f"[render-map] {len(points)} points", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
