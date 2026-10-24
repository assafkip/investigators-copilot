"""extract-intake.py side files (iocs.json / entities.json / exif.json / ner.json),
Telegram JSON + XLSX handlers. Temp dirs only, no network, no client data.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location("extract_intake", SCRIPTS / "extract-intake.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ei = _load()

REPORT = (
    "# Notes\n\nOn 2026-03-14 the operator @payer_x used hxxps://drop-zone[.]xyz/gate.php "
    "and 45.11.181[.]44 (T1566.001). Contact ops@bad-domain.xyz or +1 (415) 555-0199.\n"
    "Funds went to 0x1111111111111111111111111111111111111111. Dr. Jane Roe of "
    "Acme Widgets Inc. denied it.\n"
)


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    case_dir = tmp_path / "investigations" / "case-999-test"
    (case_dir / "investigation" / "intake").mkdir(parents=True)
    monkeypatch.setattr(ei, "WORKSPACE", tmp_path)
    return case_dir


def _run(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["extract-intake.py", "--case", "case-999-test", *argv])
    return ei.main()


def _out(case_dir, stem):
    return case_dir / "investigation" / "evidence" / "extracted" / stem


def test_md_side_files_with_exact_offsets(workspace, monkeypatch):
    (workspace / "investigation" / "intake" / "report.md").write_text(REPORT, encoding="utf-8")
    assert _run(monkeypatch) == 0
    out = _out(workspace, "report")
    text = (out / "text.md").read_text(encoding="utf-8")
    assert REPORT.rstrip() in text  # verbatim text unchanged
    iocs = json.loads((out / "iocs.json").read_text(encoding="utf-8"))
    ents = json.loads((out / "entities.json").read_text(encoding="utf-8"))
    values = {i["value"] for i in iocs["iocs"]}
    assert {"https://drop-zone.xyz/gate.php", "45.11.181.44", "ops@bad-domain.xyz"} <= values
    assert any(a["id"] == "T1566.001" for a in iocs["attack_ids"])
    for item in iocs["iocs"] + iocs["attack_ids"]:
        src = (out / item["source_file"]).read_text(encoding="utf-8")
        assert src[item["start"]:item["end"]] == item["source_span"]
    types = {e["entity_type"] for e in ents["entities"]}
    assert {"handle", "email", "phone", "crypto_wallet", "person", "org_candidate"} <= types
    for e in ents["entities"]:
        src = (out / e["source_file"]).read_text(encoding="utf-8")
        assert src[e["start"]:e["end"]] == e["surface"]
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["iocs"] == len(iocs["iocs"]) and manifest["entities"] == len(ents["entities"])
    assert not (out / "exif.json").exists()  # no images -> no exif side file
    assert not (out / "ner.json").exists()  # no --ner -> no ner side file


def test_telegram_json_handler(workspace, monkeypatch):
    export = {"name": "ord403", "messages": [
        {"date": "2026-01-02T03:04:05", "from": "unydigma",
         "text": ["leak at ", {"type": "link", "text": "https://evil.example.com/x"}]},
        {"date": "2026-01-03", "from": "cutdead", "text": "ping @handle_two"}]}
    (workspace / "investigation" / "intake" / "result.json").write_text(json.dumps(export))
    assert _run(monkeypatch) == 0
    out = _out(workspace, "result")
    text = (out / "text.md").read_text(encoding="utf-8")
    assert "# Channel: ord403" in text
    assert "[date=2026-01-02T03:04:05 from=unydigma] leak at https://evil.example.com/x" in text
    assert json.loads((out / "manifest.json").read_text())["messages"] == 2
    ents = json.loads((out / "entities.json").read_text())["entities"]
    assert any(e["canonical"] == "@handle_two" for e in ents)


def test_xlsx_handler(workspace, monkeypatch):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Leak"
    ws.append(["name", "email"])
    ws.append(["Jane Roe", "jane@target-co.com"])
    ws.append([None, None])
    wb.save(workspace / "investigation" / "intake" / "leak.xlsx")
    assert _run(monkeypatch) == 0
    out = _out(workspace, "leak")
    text = (out / "text.md").read_text(encoding="utf-8")
    assert "## Sheet: Leak" in text and "**email:** jane@target-co.com" in text
    assert json.loads((out / "manifest.json").read_text())["rows"] == 1


def test_xlsx_missing_openpyxl_is_clear_fail(workspace, monkeypatch, capsys):
    (workspace / "investigation" / "intake" / "x.xlsx").write_bytes(b"PK")
    monkeypatch.setitem(sys.modules, "openpyxl", None)  # simulate absent library
    assert _run(monkeypatch) == 2
    assert "pip install openpyxl" in capsys.readouterr().err


def test_ner_missing_library_never_crashes(workspace, monkeypatch):
    (workspace / "investigation" / "intake" / "report.md").write_text(REPORT, encoding="utf-8")
    monkeypatch.setitem(sys.modules, "spacy", None)
    assert _run(monkeypatch, "--ner", "spacy") == 0
    ner = json.loads((_out(workspace, "report") / "ner.json").read_text())
    assert ner["status"] == "unavailable" and "pip install spacy" in ner["note"]
    assert (_out(workspace, "report") / "iocs.json").exists()


def test_ner_langextract_without_key_is_skipped(workspace, monkeypatch):
    (workspace / "investigation" / "intake" / "report.md").write_text(REPORT, encoding="utf-8")
    monkeypatch.delenv("LANGEXTRACT_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert _run(monkeypatch, "--ner", "langextract") == 0
    ner = json.loads((_out(workspace, "report") / "ner.json").read_text())
    assert ner["status"] == "skipped"


def test_ner_drops_misaligned_spans(tmp_path, monkeypatch):
    out = tmp_path / "x"
    out.mkdir()
    monkeypatch.setattr(ei, "_run_ner_backend", lambda b, t: (
        [{"label": "person", "start": 0, "end": 4, "text": "Jane"},
         {"label": "person", "start": 0, "end": 4, "text": "Fake"}], "stub"))
    stats = ei.write_ner(out, {"text.md": "Jane Roe"}, "gliner")
    rec = json.loads((out / "ner.json").read_text())
    assert stats["ner_entities"] == 1 and rec["dropped_misaligned"] == 1


def test_exif_pillow_reads_gps_and_skips_generated(tmp_path, monkeypatch):
    image_mod = pytest.importorskip("PIL.Image")
    out = tmp_path / "doc"
    (out / "images").mkdir(parents=True)
    img = image_mod.new("RGB", (8, 8))
    exif = img.getexif()
    exif[0x010F] = "TestCam"  # Make
    exif[0x8825] = {1: "N", 2: (40.0, 26.0, 46.0)}
    img.save(out / "images" / "image_001.jpg", exif=exif)
    img.save(out / "images" / "page-1.png")  # pdftoppm render lookalike
    img.save(out / "images" / "image_001.up4x.png")
    monkeypatch.setattr(ei.shutil, "which", lambda name: None)  # force Pillow path
    stats = ei.write_exif(out, ".pdf")
    data = json.loads((out / "exif.json").read_text())
    assert data["tool"] == "pillow" and stats["exif_images"] == 1
    rec = data["exif"]["images/image_001.jpg"]
    assert rec["Make"] == "TestCam" and rec["GPSInfo"]["GPSLatitudeRef"] == "N"


def test_exif_unavailable_is_recorded(tmp_path, monkeypatch):
    out = tmp_path / "doc"
    (out / "images").mkdir(parents=True)
    (out / "images" / "a.png").write_bytes(b"\x89PNG")
    monkeypatch.setattr(ei.shutil, "which", lambda name: None)
    monkeypatch.setitem(sys.modules, "PIL", None)
    stats = ei.write_exif(out, ".png")
    assert stats["exif"].startswith("exif: unavailable")
