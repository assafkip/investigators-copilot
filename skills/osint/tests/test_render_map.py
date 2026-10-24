"""render-map.py: GPS parsing from exiftool-style JSON and CSV, safe HTML output."""
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS / "lib"))
_spec = importlib.util.spec_from_file_location("render_map", SCRIPTS / "render-map.py")
rm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rm)


@pytest.mark.parametrize("value,ref,expected", [
    (40.446, "", 40.446),
    ("40 deg 26' 46.30\" N", "", 40.446194),
    ("79 deg 58' 56.00\" W", "", -79.982222),
    ("33.5", "S", -33.5),
    ("-12.25", "", -12.25),
    ("garbage", "", None),
])
def test_parse_coord(value, ref, expected):
    got = rm.parse_coord(value, ref)
    assert (got is None and expected is None) or abs(got - expected) < 1e-5


def test_exif_variants_and_null_island():
    assert rm.coords_from_exif({"GPSPosition": "40 deg 26' 46.30\" N, 79 deg 58' 56.00\" W"}) == (40.446194, -79.982222)
    assert rm.coords_from_exif({"EXIF:GPSLatitude": 51.5, "EXIF:GPSLongitude": 0.12, "GPSLongitudeRef": "West"}) == (51.5, -0.12)
    assert rm.coords_from_exif({"lat": 0, "lon": 0}) is None
    assert rm.coords_from_exif({"lat": 95, "lon": 10}) is None
    assert rm.coords_from_exif({"Make": "Canon"}) is None


def test_main_collects_exif_and_csv(tmp_path):
    case = tmp_path / "case-999-test"
    item = case / "investigation" / "evidence" / "items" / "EV-0007-photo"
    item.mkdir(parents=True)
    (item / "exif.json").write_text(json.dumps([{"SourceFile": "original.jpg", "GPSLatitude": 48.8584,
                                                "GPSLongitude": 2.2945, "DateTimeOriginal": "2026:03:01 10:00:00"}]))
    nogps = case / "investigation" / "evidence" / "extracted" / "doc"
    nogps.mkdir(parents=True)
    (nogps / "exif.json").write_text(json.dumps({"Make": "Canon"}))
    csv_path = tmp_path / "pts.csv"
    csv_path.write_text("lat,lon,label,ev\n35.6586,139.7454,<b>tower</b>,EV-0009\nbad,row,x,\n")
    assert rm.main(["--case-dir", str(case), "--csv", str(csv_path), "--out", str(tmp_path / "o")]) == 0
    page = next((tmp_path / "o").glob("map-*.html")).read_text()
    data = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', page, re.S)
                      .group(1).replace("<\\/", "</"))
    assert {(p["ev"], p["kind"]) for p in data} == {("EV-0007", "exif"), ("EV-0009", "csv")}
    assert "<b>tower</b>" not in page.split('<script id="data"')[0]  # escaped in table
    assert "leaflet/1.9.4" in page


def test_no_points_exits(tmp_path):
    (tmp_path / "c").mkdir()
    with pytest.raises(SystemExit):
        rm.main(["--case-dir", str(tmp_path / "c")])
