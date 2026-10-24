"""redact-pii.py regex fallback: types, validators, allowlist, presidio-absent note."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _script_loader import load_script  # noqa: E402

rp = load_script("redact-pii.py", "redact_pii")

DOC = ("Emailed jane.roe@example.com on 2026-03-14 from +1 (415) 555-0199.\n"
       "SSN 123-45-6789, card 4111 1111 1111 1111, IBAN GB82 WEST 1234 5698 7654 32.\n"
       "Server 45.11.181.44, invoice 1234567890123, bad IBAN GB00 WEST 1234 5698 7654 32.\n"
       "Office: (212) 555-0100.\n")


def test_regex_redaction(tmp_path, capsys):
    src = tmp_path / "brief.md"
    src.write_text(DOC)
    assert rp.main([str(src), "--engine", "regex", "--json"]) == 0
    summary = json.loads(capsys.readouterr().out)
    out = (tmp_path / "brief.redacted.md").read_text()
    # PHONE_NUMBER 3: two real phones + the digit groups of the mod-97-invalid IBAN,
    # which are phone-shaped. Over-redaction is the safe direction for this tool.
    assert summary["counts"] == {"CREDIT_CARD": 1, "EMAIL_ADDRESS": 1, "IBAN_CODE": 1,
                                 "PHONE_NUMBER": 3, "US_SSN": 1}
    assert "jane.roe@example.com" not in out and "123-45-6789" not in out
    assert "2026-03-14" in out and "45.11.181.44" in out  # dates / IPs are not PII here
    assert "1234567890123" in out  # fails Luhn: kept
    assert "GB00 WEST" in out  # fails mod-97: kept
    assert "Office: [REDACTED:PHONE_NUMBER]." in out
    assert src.read_text() == DOC  # input untouched


def test_allowlist(tmp_path):
    src = tmp_path / "b.md"
    src.write_text(DOC)
    rp.main([str(src), "--engine", "regex", "--allow", "(212) 555-0100"])
    assert "(212) 555-0100" in (tmp_path / "b.redacted.md").read_text()


def test_auto_without_presidio_falls_back(tmp_path, monkeypatch, capsys):
    src = tmp_path / "b.md"
    src.write_text(DOC)
    monkeypatch.setitem(sys.modules, "presidio_analyzer", None)
    assert rp.main([str(src), "--also", "PERSON"]) == 0
    err = capsys.readouterr().err
    assert "using regex fallback" in err and "--also PERSON ignored" in err
