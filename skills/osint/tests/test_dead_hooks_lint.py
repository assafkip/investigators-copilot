"""dead-hooks-lint.py: missing hook scripts are reported, guarded ones as SILENT, exit 1."""
import importlib.util
import json
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
_spec = importlib.util.spec_from_file_location("dead_hooks_lint", SCRIPTS / "dead-hooks-lint.py")
dhl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dhl)


def _settings(tmp_path, hooks):
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / "scripts").mkdir()
    (proj / "scripts" / "present.py").write_text("print()\n")
    path = proj / ".claude" / "settings.json"
    path.write_text(json.dumps({"hooks": hooks}))
    return proj, path


def _hook(cmd, matcher="Bash"):
    return {"matcher": matcher, "hooks": [{"type": "command", "command": cmd}]}


def test_detects_silent_and_loud(tmp_path, capsys):
    proj, path = _settings(tmp_path, {
        "PostToolUse": [
            _hook('test -f "$CLAUDE_PROJECT_DIR/scripts/gone.py" && python3 "$CLAUDE_PROJECT_DIR/scripts/gone.py"'),
            _hook('if [ -f "$CLAUDE_PROJECT_DIR/scripts/present.py" ]; then python3 "$CLAUDE_PROJECT_DIR/scripts/present.py"; fi'),
            _hook('python3 "${CLAUDE_PROJECT_DIR}/scripts/also-gone.py"'),
        ],
        "Stop": [_hook('bash "$CLAUDE_PROJECT_DIR/hooks/stop.sh" 2>/dev/null || true', None)],
    })
    rc = dhl.main([str(path), "--project-dir", str(proj)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "SILENT PostToolUse/Bash: $CLAUDE_PROJECT_DIR/scripts/gone.py" in out
    assert "LOUD   PostToolUse/Bash: ${CLAUDE_PROJECT_DIR}/scripts/also-gone.py" in out
    assert "SILENT Stop/*: $CLAUDE_PROJECT_DIR/hooks/stop.sh" in out
    assert "present.py" not in out.split("dead-hooks-lint:")[0]
    assert "3 missing (2 silent, 1 loud)" in out


def test_for_loop_literals_checked_and_vars_skipped(tmp_path, capsys):
    proj, path = _settings(tmp_path, {"PostToolUse": [
        _hook('for R in scripts/present.py scripts/loopgone.py; do [ -f "$CLAUDE_PROJECT_DIR/$R" ] && python3 "$CLAUDE_PROJECT_DIR/$R"; done'),
        _hook('python3 "${CLAUDE_PLUGIN_ROOT}/x.py"'),
    ]})
    rc = dhl.main([str(path), "--project-dir", str(proj), "--json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert [m["script"] for m in data["missing"]] == ["scripts/loopgone.py"]
    assert {u["script"] for u in data["unresolved"]} >= {"${CLAUDE_PLUGIN_ROOT}/x.py"}


def test_clean_settings_exit_zero(tmp_path):
    proj, path = _settings(tmp_path, {"PreToolUse": [_hook('python3 "$CLAUDE_PROJECT_DIR/scripts/present.py"')]})
    assert dhl.main([str(path), "--project-dir", str(proj)]) == 0


def test_unreadable_settings_exit_two(tmp_path):
    bad = tmp_path / "settings.json"
    bad.write_text("{not json")
    assert dhl.main([str(bad), "--project-dir", str(tmp_path)]) == 2
