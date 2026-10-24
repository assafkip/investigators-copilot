"""identity-sweep.py: type detection, adapter selection, merge/dedup, case save. Offline."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS / "lib"))
from enrich.base import Adapter, EnrichmentError, EnrichmentResult  # noqa: E402

spec = importlib.util.spec_from_file_location("identity_sweep", SCRIPTS / "identity-sweep.py")
sweep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sweep)


class FakeA(Adapter):
    slug, watched_types = "fake_a", ("handle",)

    def run(self, query, mode=None, timeout=60):
        return [EnrichmentResult("url", "GitHub: bob", "hit", url="https://github.com/bob/", tier="T3"),
                EnrichmentResult("record", "Some Registry", "rec", tier="T1")]


class FakeB(Adapter):
    slug, watched_types = "fake_b", ("handle", "email")

    def run(self, query, mode=None, timeout=60):
        return [EnrichmentResult("url", "github", "dup", url="http://www.github.com/bob")]


class FakeBroken(Adapter):
    slug, watched_types = "fake_broken", ("handle",)

    def run(self, query, mode=None, timeout=60):
        raise EnrichmentError("upstream 503")


class FakeMissing(Adapter):
    slug, watched_types, env_var = "fake_missing", ("handle",), "FAKE_SWEEP_KEY_UNSET"


class FakePhone(Adapter):
    slug, watched_types = "fake_phone", ("phone",)


@pytest.fixture
def fake_registry(monkeypatch):
    adapters = {c.slug: c for c in (FakeA, FakeB, FakeBroken, FakeMissing, FakePhone)}
    monkeypatch.delenv("FAKE_SWEEP_KEY_UNSET", raising=False)
    monkeypatch.setattr(sweep.registry, "slugs", lambda: sorted(adapters))
    monkeypatch.setattr(sweep.registry, "get_adapter", lambda s: adapters[s]())
    return adapters


@pytest.mark.parametrize("value,expected", [
    ("bob@example.org", "email"), ("+1 415 555 2671", "phone"), ("4155552671", "phone"),
    ("@bob_99", "handle"), ("bob.smith", "handle"), ("12", "handle")])
def test_detect_type(value, expected):
    assert sweep.detect_type(value) == expected


def test_select_skips_missing_and_other_types(fake_registry):
    ready, skipped = sweep.select_adapters("handle", set(), set())
    assert {a.slug for a in ready} == {"fake_a", "fake_b", "fake_broken"}
    assert skipped == {"fake_missing": ["$FAKE_SWEEP_KEY_UNSET"]}
    ready, _ = sweep.select_adapters("handle", {"fake_a"}, set())
    assert [a.slug for a in ready] == ["fake_a"]
    ready, _ = sweep.select_adapters("handle", set(), {"fake_broken"})
    assert "fake_broken" not in {a.slug for a in ready}


def test_merge_dedups_by_url_and_forces_t3(fake_registry):
    outputs, errors = sweep.run_all([FakeA(), FakeB(), FakeBroken()], "bob", 10, 3)
    assert errors == {"fake_broken": "FAILED: upstream 503"}
    merged = sweep.merge(outputs)
    assert len(merged) == 2
    gh = next(r for r in merged if r.get("url"))
    assert gh["sources"] == ["fake_a", "fake_b"]
    record = next(r for r in merged if not r.get("url"))
    assert record["tier"] == "T3" and record["adapter_tier"] == "T1"


def test_main_saves_case_layout(fake_registry, monkeypatch, tmp_path, capsys):
    case_dir = tmp_path / "investigations" / "case-999-test"
    case_dir.mkdir(parents=True)
    monkeypatch.setattr(sweep, "resolve_case_dir", lambda case: (case, tmp_path / "investigations" / case))
    rc = sweep.main(["@bob", "--case", "case-999-test", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["type"] == "handle" and payload["query"] == "bob"
    assert payload["header"].startswith("T3 hypothesis queue only")
    outs = list((case_dir / "investigation" / "evidence" / "raw-collections").iterdir())
    assert len(outs) == 1 and outs[0].name.endswith("-identity-bob")
    assert {p.name for p in outs[0].iterdir()} == {"results.json", "urls.tsv", "summary.md"}
    tsv = (outs[0] / "urls.tsv").read_text().splitlines()
    assert len(tsv) == 1 and tsv[0].startswith("https://github.com/bob/\tidentity-bob-0\tfake_a+fake_b")
    summary = (outs[0] / "summary.md").read_text()
    assert "T3 hypothesis queue only" in summary and "fake_missing" in summary and "upstream 503" in summary


def test_main_exit_codes(fake_registry, capsys):
    assert sweep.main(["bob", "--only", "fake_broken"]) == 1
    assert sweep.main(["nobody@example.org", "--skip", "fake_b"]) == 3
    assert "T3 hypothesis queue only" in capsys.readouterr().out
