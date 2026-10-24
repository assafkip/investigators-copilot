"""long_pass.sh + preflight_control.py + plausibility_band.py.

The gate half of rca-c1-agent-process-case-001-example: a long pass may not start
until its known-answer control passes. Every test runs in tmp_path with fake controls
and a harmless fake pass; nothing here reads or writes case data.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(os.environ.get("LONG_PASS_SCRIPTS_DIR",
                              Path(__file__).resolve().parents[1] / "scripts"))
LAUNCHER = SCRIPTS / "long_pass.sh"
CONTROL = SCRIPTS / "preflight_control.py"
BAND = SCRIPTS / "plausibility_band.py"
RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{6}$")


def _write(path, text):
    path.write_text(text)
    path.chmod(0o755)
    return path


@pytest.fixture
def work(tmp_path):
    wd = tmp_path / "wd"
    wd.mkdir()
    # A fake control prints its verdict from a file, so one fixture serves every case.
    _write(wd / "control.sh", '#!/bin/bash\ncat "$(dirname "$0")/verdict.txt"\nexit "$(cat "$(dirname "$0")/rc.txt")"\n')
    # The fake pass leaves a marker carrying its run id, then lives briefly.
    _write(wd / "pass.sh", '#!/bin/bash\necho "$LONG_PASS_RUN_ID" >> "$(dirname "$0")/STARTED"\nsleep 2\n')
    return wd


def _verdict(wd, stdout, rc=0):
    (wd / "verdict.txt").write_text(stdout)
    (wd / "rc.txt").write_text(str(rc))


def _launch(wd, name="pass"):
    pre = f"python3 {CONTROL} -- bash {wd / 'control.sh'}"
    return subprocess.run(
        ["bash", str(LAUNCHER), "--name", name, "--workdir", str(wd),
         "--preflight", pre, "--", "bash", str(wd / "pass.sh")],
        capture_output=True, text=True, timeout=30)


def _wait_for(path, seconds=5.0):
    end = time.time() + seconds
    while time.time() < end:
        if path.exists():
            return True
        time.sleep(0.05)
    return path.exists()


# (a) a failing control refuses the launch and writes nothing
def test_control_ok_false_refuses_and_starts_nothing(work):
    _verdict(work, '{"ok": false, "controls": {"a": "missed"}}')
    before = sorted(p.name for p in work.iterdir())
    proc = _launch(work)
    assert proc.returncode == 2, proc.stderr
    assert "NOT started" in proc.stderr
    assert '"ok": false' in proc.stderr  # the preflight output is shown
    time.sleep(0.5)  # give a wrongly started child time to leave its marker
    assert not (work / "STARTED").exists()
    assert sorted(p.name for p in work.iterdir()) == before  # no run.json, status, log


# (b) a passing control launches the pass and records a run id
def test_control_ok_true_launches_and_writes_run_json(work):
    _verdict(work, '{"ok": true, "controls": {"a": "found"}}')
    proc = _launch(work)
    assert proc.returncode == 0, proc.stderr
    rec = json.loads((work / "pass.run.json").read_text())
    assert RUN_ID_RE.match(rec["run_id"])
    assert rec["preflight_exit"] == 0
    assert '"ok": true' in rec["preflight_output_tail"]
    assert rec["command"][0] == "bash"
    assert isinstance(rec["pid"], int) and rec["pid"] > 0
    assert _wait_for(work / "STARTED")
    assert (work / "STARTED").read_text().strip() == rec["run_id"]
    status = work / f"pass.status.{rec['run_id']}.json"
    assert json.loads(status.read_text()) == rec
    assert (work / "pass.status.latest").read_text().strip() == rec["run_id"]


# (c) a second launch never overwrites the first run's status
def test_second_launch_keeps_first_status(work):
    _verdict(work, '{"ok": true}')
    assert _launch(work).returncode == 0
    first = json.loads((work / "pass.run.json").read_text())
    first_status = work / f"pass.status.{first['run_id']}.json"
    first_bytes = first_status.read_bytes()
    assert _launch(work).returncode == 0
    second = json.loads((work / "pass.run.json").read_text())
    assert second["run_id"] != first["run_id"]
    assert first_status.read_bytes() == first_bytes
    assert (work / f"pass.status.{second['run_id']}.json").exists()
    assert (work / "pass.status.latest").read_text().strip() == second["run_id"]


# (d) bad JSON, missing "ok", truthy-but-not-true, and nonzero exit all fail
@pytest.mark.parametrize("stdout,rc", [
    ("not json at all", 0),
    ('{"controls": {}}', 0),
    ('{"ok": "true"}', 0),
    ('{"ok": 1}', 0),
    ('["ok", true]', 0),
    ("", 0),
    ('{"ok": true}', 1),
])
def test_preflight_control_refuses(work, stdout, rc):
    _verdict(work, stdout, rc)
    proc = subprocess.run([sys.executable, str(CONTROL), "--", "bash", str(work / "control.sh")],
                          capture_output=True, text=True)
    assert proc.returncode == 2, (stdout, proc.stdout, proc.stderr)
    assert "PREFLIGHT_CONTROL FAIL" in proc.stderr


def test_preflight_control_bad_json_also_blocks_the_launch(work):
    _verdict(work, "{not json")
    assert _launch(work).returncode == 2
    time.sleep(0.5)
    assert not (work / "STARTED").exists()
    assert not (work / "pass.run.json").exists()


def test_preflight_control_passes_and_reprints(work):
    _verdict(work, 'progress line\n{"ok": true, "controls": {"x": 1}}\n')
    proc = subprocess.run([sys.executable, str(CONTROL), "--", "bash", str(work / "control.sh")],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout) == {"ok": True, "controls": {"x": 1}}


def test_preflight_control_usage_is_not_a_refusal():
    proc = subprocess.run([sys.executable, str(CONTROL)], capture_output=True, text=True)
    assert proc.returncode == 64


def test_launcher_usage_error_is_64_not_2(work):
    proc = subprocess.run(["bash", str(LAUNCHER), "--name", "x"], capture_output=True, text=True)
    assert proc.returncode == 64


@pytest.mark.parametrize("args,rc", [
    (["--measured", "0.55", "--baseline", "0.58", "--tolerance", "0.10"], 0),
    (["--measured", "0.02", "--baseline", "0.58", "--tolerance", "0.10"], 2),
    (["--measured", "0.70", "--baseline", "0.58", "--tolerance", "0.25", "--relative"], 0),
    (["--measured", "0.80", "--baseline", "0.58", "--tolerance", "0.25", "--relative"], 2),
    (["--measured", "abc", "--baseline", "0.58", "--tolerance", "0.1"], 64),
    (["--measured", "0.5", "--baseline", "0.58", "--tolerance", "-1"], 64),
])
def test_plausibility_band(args, rc):
    proc = subprocess.run([sys.executable, str(BAND)] + args, capture_output=True, text=True)
    assert proc.returncode == rc, proc.stderr


def test_band_as_second_preflight_stage_blocks_launch(work):
    _verdict(work, '{"ok": true}')
    pre = (f"python3 {CONTROL} -- bash {work / 'control.sh'} && "
           f"python3 {BAND} --measured 0.02 --baseline 0.58 --tolerance 0.10")
    proc = subprocess.run(
        ["bash", str(LAUNCHER), "--name", "pass", "--workdir", str(work),
         "--preflight", pre, "--", "bash", str(work / "pass.sh")],
        capture_output=True, text=True, timeout=30)
    assert proc.returncode == 2
    assert "PLAUSIBILITY FAIL" in proc.stderr
    time.sleep(0.5)
    assert not (work / "STARTED").exists()
