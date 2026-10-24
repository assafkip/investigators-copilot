#!/usr/bin/env python3
# evidence-pipeline-guard.py -- PostToolUse gate enforcing the evidence-capture
# protocol's ingest-before-process rule.
#
# Scar (2026-07-21, case-001-example): a client CSV was copied straight
# into investigation/intake/ and a bespoke classifier script was written and run
# against it, bypassing ingest-client-document.sh (EV-NNNN registration + chain
# of custody) and extract-intake.py (deterministic verbatim extraction) entirely.
# Both tools already existed. This hook makes that bypass structurally blocked:
# a case's investigation/evidence/scripts/ cannot gain a new script (Write) and
# an existing one cannot be run (Bash) while any file in investigation/intake/
# lacks BOTH (a) a registered EV-NNNN item and (b) a deterministic extraction.
#
# Wired in .claude/settings.json (4_points_consulting instance) as a PostToolUse
# hook on Write/Edit/MultiEdit/Bash. kipi update safety: this script lives under
#  (instance content), not q-system/ (skeleton subtree overwritten
# by `kipi update`), per RULE-2026-06-30-A. .claude/settings.json itself is also
# not touched by `kipi update` (only q-system/ and plugins/ propagate).
#
# Bypass: none by design -- the fix is always to run the two existing tools,
# which takes under a minute. If a case genuinely has no document/CSV intake
# (pure OSINT collection, no client-provided files), this hook is a no-op
# because investigation/intake/ will be empty or absent.
#
# Self-test: python3 evidence-pipeline-guard.py --self-test

import json
import pathlib
import re
import sys
import tempfile

SCOPE_RE = re.compile(
    r"investigations/(?P<case>[^/]+)/investigation/evidence/scripts/"
)


def find_workspace_root(path_str: str) -> pathlib.Path | None:
    """Given any string containing '.../investigations/<case>/...', return the
    workspace workspace root (the directory containing investigations/)."""
    idx = path_str.find("investigations/")
    if idx == -1:
        return None
    prefix = path_str[:idx]
    return pathlib.Path(prefix) if prefix else pathlib.Path(".")


def unresolved_intake_files(case_dir: pathlib.Path) -> list:
    """Return intake filenames that lack either a matching EV-NNNN item or a
    deterministic extraction. Empty list == fully ingested (or no intake)."""
    intake_dir = case_dir / "investigation" / "intake"
    if not intake_dir.is_dir():
        return []

    intake_files = [f for f in intake_dir.iterdir()
                     if f.is_file() and not f.name.startswith(".")]
    if not intake_files:
        return []

    items_dir = case_dir / "investigation" / "evidence" / "items"
    registered_names = set()
    if items_dir.is_dir():
        for ev_dir in items_dir.glob("EV-*"):
            source_json = ev_dir / "source.json"
            if not source_json.is_file():
                continue
            try:
                data = json.loads(source_json.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            name = data.get("original_filename")
            if name:
                registered_names.add(name)

    extracted_dir = case_dir / "investigation" / "evidence" / "extracted"

    unresolved = []
    for f in intake_files:
        has_ev = f.name in registered_names
        # Accept manifest.json (current canonical extract-intake.py) OR
        # text.md/ocr.md (older per-case extraction scripts, predating the
        # manifest.json convention, that already ran and produced real
        # output) -- a file just needs SOME completed extraction on record,
        # not specifically the newest artifact shape. Bug found + fixed
        # 2026-07-21: the manifest.json-only check false-positived on every
        # pre-existing case (e.g. case-020) whose intake was already fully
        # extracted by a now-superseded local script.
        target_dir = extracted_dir / f.stem
        has_extraction = any((target_dir / name).is_file()
                              for name in ("manifest.json", "text.md", "ocr.md"))
        if not (has_ev and has_extraction):
            unresolved.append(f.name)
    return unresolved


def check(path_or_command: str) -> int:
    """Returns 0 (pass) or 2 (block)."""
    match = SCOPE_RE.search(path_or_command)
    if not match:
        return 0

    case = match.group("case")
    workspace = find_workspace_root(path_or_command)
    if workspace is None:
        return 0

    case_dir = workspace / "investigations" / case
    if not case_dir.is_dir():
        return 0

    unresolved = unresolved_intake_files(case_dir)
    if not unresolved:
        return 0

    file_list = "\n".join(f"  - {name}" for name in unresolved)
    print(
        f"\n[evidence-pipeline-guard] BLOCKED: {case}/investigation/intake/ has "
        f"file(s) not yet run through the evidence pipeline:\n{file_list}\n\n"
        f"Run these first (per .claude/rules/evidence-capture-protocol.md):\n\n"
        f"  bash skills/osint/scripts/ingest-client-document.sh \\\n"
        f"    \"investigations/{case}/investigation/intake/<file>\" <slug> document \\\n"
        f"    --case {case} --provided-by \"<who>\"\n\n"
        f"  python3 skills/osint/scripts/extract-intake.py --case {case}\n\n"
        f"Then write/run your classification script.\n",
        file=sys.stderr,
    )
    return 2


def self_test() -> int:
    print("=== evidence-pipeline-guard.py --self-test ===")
    failures = 0

    with tempfile.TemporaryDirectory() as tmp:
        workspace = pathlib.Path(tmp)
        case_dir = workspace / "investigations" / "case-test-selftest"
        intake_dir = case_dir / "investigation" / "intake"
        scripts_dir = case_dir / "investigation" / "evidence" / "scripts"
        items_dir = case_dir / "investigation" / "evidence" / "items"
        extracted_dir = case_dir / "investigation" / "evidence" / "extracted"
        intake_dir.mkdir(parents=True)
        scripts_dir.mkdir(parents=True)

        (intake_dir / "leak.csv").write_text("a,b\n1,2\n")
        script_path = str(scripts_dir / "classify.py")

        # Test 1: block -- intake file present, no EV item, no extraction
        result = check(script_path)
        if result == 2:
            print("PASS Test 1: blocked -- no EV item, no extraction")
        else:
            print(f"FAIL Test 1: expected 2, got {result}", file=sys.stderr)
            failures += 1

        # Test 2: still block -- EV item registered, but no extraction yet
        ev_dir = items_dir / "EV-0001-leak"
        ev_dir.mkdir(parents=True)
        (ev_dir / "source.json").write_text(json.dumps({"original_filename": "leak.csv"}))
        result = check(script_path)
        if result == 2:
            print("PASS Test 2: still blocked -- EV item exists but extraction missing")
        else:
            print(f"FAIL Test 2: expected 2, got {result}", file=sys.stderr)
            failures += 1

        # Test 3: still block -- extraction exists but EV item doesn't (move EV
        # fully OUT of items_dir -- renaming within items_dir would still match
        # the EV-* glob and silently pass, which is not what this test checks)
        ev_dir_parked = workspace / "EV-0001-leak-parked"
        ev_dir.rename(ev_dir_parked)
        (extracted_dir / "leak").mkdir(parents=True)
        (extracted_dir / "leak" / "manifest.json").write_text("{}")
        result = check(script_path)
        if result == 2:
            print("PASS Test 3: still blocked -- extraction exists but EV item missing")
        else:
            print(f"FAIL Test 3: expected 2, got {result}", file=sys.stderr)
            failures += 1
        ev_dir_parked.rename(ev_dir)

        # Test 4: allow -- both EV item and extraction present
        result = check(script_path)
        if result == 0:
            print("PASS Test 4: allowed -- EV item + extraction both present")
        else:
            print(f"FAIL Test 4: expected 0, got {result}", file=sys.stderr)
            failures += 1

        # Test 5: allow -- Bash command referencing the same scoped path
        bash_cmd = f"python3 {script_path} --case case-test-selftest"
        result = check(bash_cmd)
        if result == 0:
            print("PASS Test 5: allowed via Bash-command form once ingested")
        else:
            print(f"FAIL Test 5: expected 0, got {result}", file=sys.stderr)
            failures += 1

        # Test 6: no-op -- out-of-scope path (not under evidence/scripts/)
        other_path = str(case_dir / "investigation" / "findings" / "notes.md")
        result = check(other_path)
        if result == 0:
            print("PASS Test 6: no-op on out-of-scope path")
        else:
            print(f"FAIL Test 6: expected 0, got {result}", file=sys.stderr)
            failures += 1

        # Test 7: no-op -- intake dir empty (nothing to enforce)
        empty_case_dir = workspace / "investigations" / "case-empty-intake"
        (empty_case_dir / "investigation" / "intake").mkdir(parents=True)
        (empty_case_dir / "investigation" / "evidence" / "scripts").mkdir(parents=True)
        empty_script_path = str(empty_case_dir / "investigation" / "evidence" / "scripts" / "x.py")
        result = check(empty_script_path)
        if result == 0:
            print("PASS Test 7: no-op when intake/ is empty")
        else:
            print(f"FAIL Test 7: expected 0, got {result}", file=sys.stderr)
            failures += 1

    if failures:
        print(f"\n=== {failures} SELF-TEST(S) FAILED ===", file=sys.stderr)
        return 1
    print("\n=== ALL SELF-TESTS PASSED ===")
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        return self_test()

    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    if tool_name in ("Write", "Edit", "MultiEdit"):
        file_path = tool_input.get("file_path", "")
        return check(file_path)

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        return check(command)

    return 0


if __name__ == "__main__":
    sys.exit(main())
