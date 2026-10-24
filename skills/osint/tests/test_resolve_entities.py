"""resolve-entities.py: deterministic fallback, splink path (if installed), FtM output."""
import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _script_loader import load_script  # noqa: E402

re_mod = load_script("resolve-entities.py", "resolve_entities")

ROWS = [
    {"id": "r1", "full_name": "Jane Roe", "email": "Jane.Roe@Example.com",
     "phone": "+1 (415) 555-0199", "address": "12 Main Street"},
    {"id": "r2", "full_name": "Roe Jane", "email": "jane.roe@example.com"},
    {"id": "r3", "full_name": "John Smith", "phone": "415-555-0199"},
    {"id": "r4", "full_name": "Alice Wonder", "email": "alice@w.net"},
    {"id": "r5", "full_name": "Jane Roe", "address": "12 Main St"},
]


def _write_csv(path):
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "full_name", "email", "phone", "address"])
        w.writeheader()
        w.writerows(ROWS)


def _pairs(path):
    with path.open() as fh:
        return {(r["id_l"], r["id_r"]): r for r in csv.DictReader(fh)}


def test_fallback_pairs_and_basis(tmp_path):
    src = tmp_path / "leak.csv"
    _write_csv(src)
    out = tmp_path / "same_as.csv"
    assert re_mod.main([str(src), "--engine", "fallback", "--out", str(out)]) == 0
    pairs = _pairs(out)
    assert float(pairs[("r1", "r2")]["match_probability"]) == 0.97
    assert "email_exact" in pairs[("r1", "r2")]["match_basis"]
    assert "phone_exact" in pairs[("r1", "r3")]["match_basis"]
    assert "address_sim" in pairs[("r1", "r5")]["match_basis"]
    assert "name_only_not_a_crosslink" in pairs[("r2", "r5")]["match_basis"]
    assert not any("r4" in k for k in pairs)
    assert all(r["evidence_tier"] == "T3" and r["relation"] == "same_as" for r in pairs.values())


def test_json_input_and_ftm(tmp_path):
    src = tmp_path / "recs.json"
    src.write_text(json.dumps({"records": ROWS}))
    out = tmp_path / "same_as.json"
    ftm = tmp_path / "ents.ftm.jsonl"
    assert re_mod.main([str(src), "--engine", "fallback", "--out", str(out),
                        "--ftm", str(ftm)]) == 0
    pairs = json.loads(out.read_text())
    ents = [json.loads(ln) for ln in ftm.read_text().splitlines()]
    persons = [e for e in ents if e["schema"] == "Person"]
    links = [e for e in ents if e["schema"] == "UnknownLink"]
    assert len(persons) == 5 and len(links) == len(pairs)
    ids = {e["id"] for e in persons}
    assert all(link["properties"]["subject"][0] in ids for link in links)


def test_auto_without_splink_falls_back(tmp_path, monkeypatch, capsys):
    src = tmp_path / "leak.csv"
    _write_csv(src)
    monkeypatch.setitem(sys.modules, "splink", None)
    assert re_mod.main([str(src), "--out", str(tmp_path / "o.csv")]) == 0
    assert "deterministic fallback" in capsys.readouterr().err


def test_forced_splink_missing_is_explicit(tmp_path, monkeypatch):
    src = tmp_path / "leak.csv"
    _write_csv(src)
    monkeypatch.setitem(sys.modules, "splink", None)
    with pytest.raises(SystemExit, match="pip install splink"):
        re_mod.main([str(src), "--engine", "splink", "--out", str(tmp_path / "o.csv")])


def test_bad_input_errors(tmp_path):
    bad = tmp_path / "x.xml"
    bad.write_text("<a/>")
    assert re_mod.main([str(bad)]) == 1


def test_splink_engine_runs_when_installed(tmp_path):
    pytest.importorskip("splink")
    pytest.importorskip("duckdb")
    src = tmp_path / "leak.csv"
    _write_csv(src)
    out = tmp_path / "s.csv"
    assert re_mod.main([str(src), "--engine", "splink", "--out", str(out)]) == 0
    for row in _pairs(out).values():
        assert row["engine"].startswith("splink") and 0 <= float(row["match_probability"]) <= 1
