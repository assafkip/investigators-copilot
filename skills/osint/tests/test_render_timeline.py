"""render-timeline.py: tolerant master-timeline parsing, self-contained HTML, Timesketch CSV."""
import csv
import importlib.util
import json
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS / "lib"))
_spec = importlib.util.spec_from_file_location("render_timeline", SCRIPTS / "render-timeline.py")
rt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rt)

TIMELINE = """# Master Timeline

## Phase 1

| Date | Event | Source | Confidence |
|------|-------|--------|------------|
| 2026-03-14 02:46 | @ohmstone posts "9243 reasons" [EV-0014] | X | confirmed |
| 2026-03-10 | Domain **roe-corp.com** registered | RDAP [EV-0002] | high |
| TBD | undated row | - | - |

## Notes

- 2026-02-01: account created
- **2026-01-15** -- first sighting on Telegram
- 2026-04 - month-precision event
* 2026-03-14T10:00:00+02:00 | tz-shifted event
- no date here 42
- plain bullet without digits
"""


def test_parse_tables_and_bullets_sorted():
    events, skipped = rt.parse_timeline(TIMELINE)
    msgs = [e["message"] for e in events]
    assert msgs == [
        "first sighting on Telegram",
        "account created",
        "Domain roe-corp.com registered",
        '@ohmstone posts "9243 reasons" [EV-0014]',
        "tz-shifted event",
        "month-precision event",
    ]
    assert skipped == 2  # "TBD" row + the bullet with digits but no date
    by_msg = {e["message"]: e for e in events}
    assert by_msg["tz-shifted event"]["start"] == "2026-03-14T08:00:00Z"
    assert by_msg["month-precision event"]["precision"] == "month"
    tweet = by_msg['@ohmstone posts "9243 reasons" [EV-0014]']
    assert tweet["precision"] == "time" and tweet["confidence"] == "confirmed"
    assert tweet["evidence"] == ["EV-0014"] and tweet["source"] == "X"
    assert by_msg["Domain roe-corp.com registered"]["evidence"] == ["EV-0002"]


def test_html_is_self_contained_and_escaped():
    events, skipped = rt.parse_timeline(TIMELINE + "\n- 2026-05-01: </script><b>x</b>\n")
    page = rt.render_html(events, "Timeline <case>", skipped, use_vis=False)
    assert "<title>Timeline &lt;case&gt;</title>" in page
    assert not re.search(r"<script[^>]+src=", page)
    assert not re.search(r"""(?:src|href)=["']?https?://""", page)  # nothing fetched at view time
    data = re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S).group(1)
    parsed = json.loads(data.replace("<\\/", "</"))
    assert len(parsed) == len(events)
    assert "</script><b>" not in data  # breakout neutralised


def test_vis_mode_pins_version():
    events, _ = rt.parse_timeline(TIMELINE)
    page = rt.render_html(events, "t", 0, use_vis=True)
    assert "vis-timeline@7.7.3" in page and 'id="vis"' in page


def test_timesketch_csv(tmp_path):
    events, _ = rt.parse_timeline(TIMELINE)
    out = tmp_path / "ts.csv"
    rt.write_timesketch(events, out)
    rows = list(csv.DictReader(out.open()))
    assert list(rows[0])[:3] == ["message", "datetime", "timestamp_desc"]
    assert rows[0]["datetime"] == "2026-01-15T00:00:00+00:00"
    assert rows[0]["timestamp_desc"] == "Event Date"
    assert int(rows[0]["timestamp"]) == 1768435200 * 1_000_000


def test_main_with_case_dir(tmp_path):
    case = tmp_path / "case-999-test"
    (case / "investigation" / "timelines").mkdir(parents=True)
    (case / "investigation" / "timelines" / "master-timeline.md").write_text(TIMELINE)
    assert rt.main(["--case-dir", str(case), "--timesketch"]) == 0
    outs = sorted(p.name for p in (case / "output" / "exports").iterdir())
    assert len(outs) == 2 and outs[0].endswith(".html") and outs[1].endswith(".timesketch.csv")
