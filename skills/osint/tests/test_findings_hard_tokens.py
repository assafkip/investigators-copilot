"""findings-verify-hook.py hard-token check: self-test + PostToolUse stdin contract."""
import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "scripts" / "findings-verify-hook.py"


def test_self_test_passes():
    result = subprocess.run([sys.executable, str(HOOK), "--self-test"],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "Test 12" in result.stdout


def _case(tmp_path):
    case = tmp_path / "workspace" / "investigations" / "case-x"
    (case / "canonical").mkdir(parents=True)
    (case / "investigation" / "findings").mkdir(parents=True)
    ev = case / "investigation" / "evidence" / "extracted" / "doc"
    ev.mkdir(parents=True)
    (ev / "iocs.json").write_text(json.dumps({"iocs": [{"value": "198.51.100.7"}]}))
    return case


def _hook(payload):
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, check=False)


def test_write_payload_blocks_unbacked_and_passes_backed(tmp_path):
    case = _case(tmp_path)
    path = str(case / "investigation" / "findings" / "F-001.md")
    bad = _hook({"tool_name": "Write", "tool_input": {
        "file_path": path, "content": "CONFIRMED: C2 at 203.0.113.9 and 198.51.100.7"}})
    assert bad.returncode == 2 and "203.0.113.9" in bad.stderr and "198.51.100.7" not in bad.stderr
    ok = _hook({"tool_name": "Edit", "tool_input": {
        "file_path": path, "new_string": "HIGH CONFIDENCE: C2 at 198.51.100.7"}})
    assert ok.returncode == 0, ok.stderr


def test_non_findings_path_is_ignored(tmp_path):
    case = _case(tmp_path)
    res = _hook({"tool_name": "Write", "tool_input": {
        "file_path": str(case / "output" / "brief.md"), "content": "CONFIRMED 203.0.113.9"}})
    assert res.returncode == 0
