"""export-intel.py: case files -> STIX 2.1 / MISP / CSV, output shape checks (no network)."""
import csv
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS / "lib"))
_spec = importlib.util.spec_from_file_location("export_intel", SCRIPTS / "export-intel.py")
ei = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ei)

STIX_ID = re.compile(r"^[a-z0-9-]+--[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

TARGET = """# Target: Jane Roe

> Created: 2026-10-01 | Last updated: 2026-10-02

## Identity

- **Full name:** Jane Roe
- **Aliases/handles:** @janer, jr@example.org
- **DOB:**

## Digital Footprint

| Platform | Handle/URL | Status | Last Collected |
|----------|-----------|--------|----------------|
| X/Twitter | @janer_x | active | 2026-10-01 |
| Email | jane@roe-corp.com | | |
| Domain(s) | roe-corp.com | | |
| LinkedIn | | | |

## Assessment

- **Confidence level:** moderate
"""

FINDING = """# Finding: Shared registrant across roe-corp.com

> ID: F-007 | Created: 2026-10-02 | Last updated: 2026-10-02

## Summary

roe-corp.com and 203.0.113.9 share a registrant email.

## Confidence Level

**[Moderate]**
"""


@pytest.fixture
def case_dir(tmp_path):
    d = tmp_path / "case-999-test"
    (d / "investigation" / "targets").mkdir(parents=True)
    (d / "investigation" / "findings").mkdir(parents=True)
    (d / "investigation" / "targets" / "jane-roe.md").write_text(TARGET)
    (d / "investigation" / "targets" / "_TEMPLATE.md").write_text("# Target: [NAME]\n")
    (d / "investigation" / "findings" / "F-007-registrant.md").write_text(FINDING)
    (d / "investigation" / "findings" / "CHALLENGE-2026-10-02.md").write_text("# Challenge\n")
    ex = d / "investigation" / "evidence" / "extracted"
    (ex / "doc1").mkdir(parents=True)
    (ex / "doc1" / "iocs.json").write_text(json.dumps({"iocs": [
        {"value": "203.0.113.9", "type": "ipv4"},
        {"value": "ROE-CORP.com", "type": "domain"},
        {"value": "d41d8cd98f00b204e9800998ecf8427e", "type": "md5"},
        {"value": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh", "type": "btc"},
    ]}))
    (ex / "doc2").mkdir()
    (ex / "doc2" / "iocs.json").write_text(json.dumps([{"value": "http://bad.example/x", "type": "url"}]))
    (ex / "doc3").mkdir()
    (ex / "doc3" / "iocs.json").write_text("{broken")
    return d


def test_collect_parses_targets_findings_iocs(case_dir):
    data = ei.collect(case_dir)
    vals = {(e["type"], e["value"].lower()) for e in data["entities"]}
    assert ("person", "jane roe") in vals
    assert ("handle", "@janer") in vals and ("handle", "@janer_x") in vals
    assert ("email", "jr@example.org") in vals and ("email", "jane@roe-corp.com") in vals
    assert ("domain", "roe-corp.com") in vals
    assert ("ip", "203.0.113.9") in vals and ("url", "http://bad.example/x") in vals
    # template, challenge and placeholder rows are skipped
    assert not any("[name]" in v for _, v in vals)
    assert [f["id"] for f in data["findings"]] == ["F-007"]
    assert data["findings"][0]["confidence"] == "Moderate"
    # domain from target and iocs.json merged into one entity with both sources, flagged IOC
    dom = [e for e in data["entities"] if e["type"] == "domain"]
    assert len(dom) == 1 and len(dom[0]["sources"]) == 2 and dom[0]["is_ioc"]


def test_stix_bundle_shape(case_dir):
    bundle = ei.build_stix(ei.collect(case_dir), "amber")
    assert bundle["type"] == "bundle" and STIX_ID.match(bundle["id"])
    ids = [o["id"] for o in bundle["objects"]]
    assert len(ids) == len(set(ids))
    for o in bundle["objects"]:
        assert STIX_ID.match(o["id"]), o
        assert o["spec_version"] == "2.1"
        assert o["id"].split("--")[0] == o["type"]
        if o["type"] in ("identity", "note", "report", "indicator", "vulnerability"):
            assert o["created"].endswith("Z") and o["modified"].endswith("Z")
    by_type = {}
    for o in bundle["objects"]:
        by_type.setdefault(o["type"], []).append(o)
    assert {"marking-definition", "identity", "domain-name", "ipv4-addr", "email-addr",
            "user-account", "file", "url", "indicator", "note", "report"} <= set(by_type)
    assert by_type["marking-definition"][0]["definition"] == {"tlp": "amber"}
    # indicators only for evidence IOCs with a STIX pattern
    patterns = {i["pattern"] for i in by_type["indicator"]}
    assert "[ipv4-addr:value = '203.0.113.9']" in patterns
    assert "[file:hashes.'MD5' = 'd41d8cd98f00b204e9800998ecf8427e']" in patterns
    assert all(i["pattern_type"] == "stix" and i["valid_from"] for i in by_type["indicator"])
    # finding note references the observables it mentions
    note = by_type["note"][0]
    refs = set(note["object_refs"])
    dom_id = by_type["domain-name"][0]["id"]
    ip_id = by_type["ipv4-addr"][0]["id"]
    assert {dom_id, ip_id} <= refs
    assert note["x_q_finding_id"] == "F-007"
    # every report ref resolves inside the bundle
    report = by_type["report"][0]
    assert set(report["object_refs"]) <= set(ids)
    # no relationship / graph objects (founder decision)
    assert "relationship" not in by_type


def test_sco_ids_are_deterministic(case_dir):
    a = ei.build_stix(ei.collect(case_dir))
    b = ei.build_stix(ei.collect(case_dir))
    sco = lambda bun: sorted(o["id"] for o in bun["objects"]  # noqa: E731
                             if o["type"] in ("domain-name", "ipv4-addr", "url", "email-addr", "file"))
    assert sco(a) == sco(b)


def test_stix_validates_with_stix2_library_if_installed(case_dir):
    stix2 = pytest.importorskip("stix2")
    bundle = ei.build_stix(ei.collect(case_dir))
    parsed = stix2.parse(json.dumps(bundle), allow_custom=True)
    assert len(parsed.objects) == len(bundle["objects"])


def test_misp_event_shape(case_dir):
    ev = ei.build_misp(ei.collect(case_dir), "red")["Event"]
    assert ev["info"].endswith("case-999-test")
    assert ev["published"] is False and ev["Tag"] == [{"name": "tlp:red"}]
    attrs = ev["Attribute"]
    by_val = {a["value"]: a for a in attrs}
    assert by_val["203.0.113.9"]["type"] == "ip-dst" and by_val["203.0.113.9"]["to_ids"] is True
    assert by_val["@janer"]["to_ids"] is False  # handles are never IDS signatures
    assert by_val["bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"]["type"] == "btc"
    assert any(a["type"] == "comment" and a["value"].startswith("F-007") for a in attrs)
    for a in attrs:
        assert {"uuid", "type", "category", "value", "to_ids"} <= set(a)


def test_run_all_writes_files_and_csv(case_dir, tmp_path):
    out = tmp_path / "exports"
    written = ei.run("all", case_dir, out, "green")
    names = sorted(p.name.split("-2")[0] for p in written)
    assert names == ["intel-entities", "intel-findings", "intel-misp", "intel-stix"]
    ent_csv = next(p for p in written if p.name.startswith("intel-entities"))
    rows = list(csv.DictReader(ent_csv.open()))
    assert rows and {"value", "type", "is_ioc", "context", "sources"} == set(rows[0])
    assert json.loads(next(p for p in written if "stix" in p.name).read_text())["type"] == "bundle"


def test_empty_case_still_valid(tmp_path):
    d = tmp_path / "case-empty"
    d.mkdir()
    bundle = ei.build_stix(ei.collect(d))
    assert [o["type"] for o in bundle["objects"]][-1] == "report"
    assert bundle["objects"][-1]["object_refs"]  # never empty (spec requires >= 1)
