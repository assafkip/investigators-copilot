"""active_case.{sh,py}: a case is a folder name under investigations/, or a path
to an existing case folder anywhere (ASK-2617). Runs in temp dirs only."""
import subprocess
import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[1] / "scripts" / "lib"
sys.path.insert(0, str(LIB))
import active_case  # noqa: E402


@pytest.fixture
def tree(tmp_path):
    ws = tmp_path / "workspace"
    (ws / "investigations" / "case-001-example").mkdir(parents=True)
    ext = tmp_path / "infohawk" / "007-b"
    ext.mkdir(parents=True)
    return ws, ext


def sh_resolve(ws, arg, cwd):
    out = subprocess.run(
        ["bash", "-c", f'. "{LIB}/active_case.sh"; resolve_case_dir "$1" && printf "%s\\t%s" "$CASE" "$CASE_DIR"', "_", arg],
        env={"WORKSPACE": str(ws), "PATH": "/usr/bin:/bin"}, cwd=cwd, capture_output=True, text=True)
    return out.returncode, out.stdout


def test_name_resolves_under_investigations(tree):
    ws, _ = tree
    assert active_case.resolve_case_dir("case-001-example", ws) == ("case-001-example", ws / "investigations" / "case-001-example")
    assert sh_resolve(ws, "case-001-example", ws) == (0, f"case-001-example\t{ws}/investigations/case-001-example")


def test_absolute_path_outside_investigations(tree):
    ws, ext = tree
    assert active_case.resolve_case_dir(str(ext), ws) == ("007-b", ext.resolve())
    assert sh_resolve(ws, str(ext), ws) == (0, f"007-b\t{ext.resolve()}")


def test_relative_path_from_cwd(tree):
    ws, ext = tree
    assert sh_resolve(ws, "infohawk/007-b", ext.parent.parent) == (0, f"007-b\t{ext.resolve()}")


def test_missing_path_still_fails(tree):
    ws, _ = tree
    code, _ = sh_resolve(ws, "infohawk/nope", ws.parent)
    assert code == 1
    with pytest.raises(SystemExit):
        active_case.resolve_case_dir("no-such-case", ws)


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _copy_scripts(tmp_path):
    """Copy the real scripts into a throwaway skills/osint/scripts so
    WORKSPACE (derived from the script path) is a temp dir, never the live repo."""
    import shutil
    dst = tmp_path / "workspace" / "skills" / "osint" / "scripts"
    dst.mkdir(parents=True)
    for name in ("next-ev-id.sh", "ingest-client-document.sh"):
        shutil.copy2(SCRIPTS / name, dst / name)
    shutil.copytree(SCRIPTS / "lib", dst / "lib", ignore=shutil.ignore_patterns("enrich", "__pycache__"))
    (tmp_path / "workspace" / "investigations").mkdir()
    return dst


def test_ingest_into_case_outside_investigations(tmp_path):
    # Codex P1 on PR #5: the nested next-ev-id.sh call must get the case folder
    # path, not its bare name, or it resolves under investigations/ and fails.
    dst = _copy_scripts(tmp_path)
    ext = tmp_path / "infohawk" / "007-b"
    ext.mkdir(parents=True)
    doc = tmp_path / "doc.txt"
    doc.write_text("hello")
    out = subprocess.run(
        ["bash", str(dst / "ingest-client-document.sh"), str(doc), "sample", "document",
         "--case", str(ext), "--provided-by", "Example Client"],
        capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    items = list((ext / "investigation" / "evidence" / "items").glob("EV-0001-sample"))
    assert items and (items[0] / "source.json").is_file()
