"""validate-citations.py: extraction, EV claim check, dead-link exit code (no network)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _script_loader import load_script  # noqa: E402

vc = load_script("validate-citations.py", "validate_citations")

REPORT = ('On 2026-03-14 the account wrote "the vault is empty" and drew 9243 replies '
          '([post](https://example.com/post)).\n'
          'A second claim of 512 shares is at <https://example.com/post>. '
          'See also https://gone.example.org/x.\n')


def _case(tmp_path):
    item = tmp_path / "case" / "investigation" / "evidence" / "items" / "EV-0001-post"
    item.mkdir(parents=True)
    (item / "source.json").write_text(json.dumps({"ev_id": "EV-0001",
                                                  "source_url": "https://example.com/post"}))
    (item / "content.md").write_text('Posted 2026-03-14: "the vault is empty", 9243 replies.')
    report = tmp_path / "case" / "output" / "brief.md"
    report.parent.mkdir(parents=True)
    report.write_text(REPORT)
    return report


def test_extract_citations_sentences():
    cites = vc.extract_citations(REPORT)
    assert [c["url"] for c in cites] == ["https://example.com/post", "https://example.com/post",
                                         "https://gone.example.org/x"]
    for c in cites:
        assert REPORT[c["start"]:c["end"]] == c["url"]
    assert cites[2]["sentence"] == "See also https://gone.example.org/x."


def test_claim_check_against_ev(tmp_path):
    report = _case(tmp_path)
    index = vc.index_ev_items(vc.find_evidence_dir(report, None, None))
    rows = vc.validate(report, index, network=False, timeout=1, delay=0)
    assert rows[0]["claim_check"] == "ok" and rows[0]["ev_items"] == "EV-0001"
    assert rows[1]["claim_check"] == "missing: 512"
    assert rows[2]["claim_check"] == "no EV item"


def test_dead_link_exit_and_blocked(tmp_path, monkeypatch, capsys):
    report = _case(tmp_path)
    status = {"https://example.com/post": {"status": "blocked", "code": 403, "detail": "GET"},
              "https://gone.example.org/x": {"status": "dead", "code": 404, "detail": "GET"}}
    monkeypatch.setattr(vc, "check_url", lambda url, timeout: status[url])
    real_validate = vc.validate
    monkeypatch.setattr(vc, "validate", lambda *a, **k: real_validate(*a, checker=vc.check_url, **k))
    assert vc.main([str(report), "--delay", "0"]) == 1
    captured = capsys.readouterr()
    assert "BLOCKED" in captured.err and "https://gone.example.org/x" in captured.err


def test_all_ok_exits_zero(tmp_path, monkeypatch):
    report = _case(tmp_path)
    ok = {"status": "ok", "code": 200, "detail": "HEAD"}
    real_validate = vc.validate
    monkeypatch.setattr(vc, "validate",
                        lambda *a, **k: real_validate(*a, checker=lambda u, t: ok, **k))
    assert vc.main([str(report), "--delay", "0"]) == 0
