"""Single resolver for the active investigation case (Python side).

Mirror of active_case.sh: explicit case argument, else the first line of
.active-case. Returns (case, case_dir) or raises SystemExit
with a clear message.
"""

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[4]  # 


def read_active_case(workspace: Path = WORKSPACE) -> str:
    pointer = workspace / ".active-case"
    if not pointer.is_file():
        return ""
    lines = pointer.read_text().splitlines()
    return lines[0].strip() if lines else ""


def resolve_case_dir(case: str = "", workspace: Path = WORKSPACE) -> tuple[str, Path]:
    case = (case or read_active_case(workspace)).strip()
    if not case:
        sys.exit("ERROR: no active case set and no case argument given")
    # Mirror of active_case.sh: a value containing "/" that is an existing
    # directory is the case folder itself (a case outside investigations/).
    if "/" in case and Path(case).is_dir():
        case_dir = Path(case).resolve()
        return case_dir.name, case_dir
    case_dir = workspace / "investigations" / case
    if not case_dir.is_dir():
        sys.exit(f"ERROR: case directory not found: {case_dir}")
    return case, case_dir


if __name__ == "__main__":
    c, d = resolve_case_dir(sys.argv[1] if len(sys.argv) > 1 else "")
    print(f"{c}\t{d}")
