#!/usr/bin/env python3
"""Deterministic in-flight tool-call budget for a collection run ("cap the function, not the time").

Ported 2026-10-10 from kipi investigations/agent/budget.py. A budget file is one JSON
object {"cap": int, "count": int}; every gated tool call charges 1, and calls are
denied once count exceeds cap. cap <= 0 or no file means unbudgeted (allow).

Default file: investigations/<active case>/memory/tool-budget.json, or $Q_BUDGET_FILE.

CLI (to arm / inspect / disarm a run):
  budget.py init --cap 40 [--case C] [--file PATH]
  budget.py status [--case C] [--file PATH]
  budget.py clear [--case C] [--file PATH]

Pure + stdlib-only so the hook subprocess can import it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def read_state(path: str) -> tuple[int, int]:
    """(cap, count); (0, 0) if unreadable -> caller treats cap 0 as unbudgeted (fail open)."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return int(data.get("cap", 0)), int(data.get("count", 0))
    except (OSError, ValueError, TypeError, AttributeError):
        return 0, 0


def check_and_charge(path: str) -> tuple[bool, int, int]:
    """Charge one call; return (allow, count, cap). Single writer per run: calls are
    sequential, so a read-modify-write with an atomic replace is race-free enough here."""
    cap, count = read_state(path)
    if cap <= 0:
        return True, count, cap
    count += 1
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"cap": cap, "count": count}, f)
        os.replace(tmp, path)
    except OSError:
        return True, count, cap  # cannot persist the charge: fail open, never wedge the run
    return count <= cap, count, cap


def deny_message(count: int, cap: int) -> str:
    return (f"tool budget exhausted: {count} of {cap} collection calls used this run. STOP collecting "
            "and write up what you have now. List entities you did not reach as LEADS; the founder "
            "decides whether to extend the budget (budget.py init --cap N).")


def write_budget(path: str, cap: int) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"cap": int(cap), "count": 0}, f)


def default_path(case: str = "") -> str:
    if os.environ.get("Q_BUDGET_FILE"):
        return os.environ["Q_BUDGET_FILE"]
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
    import active_case

    workspace = Path(os.environ["Q_WORKSPACE"]) if os.environ.get("Q_WORKSPACE") else active_case.WORKSPACE
    _, case_dir = active_case.resolve_case_dir(case, workspace)
    return str(case_dir / "memory" / "tool-budget.json")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Arm / inspect / clear the tool-call budget.")
    ap.add_argument("action", choices=["init", "status", "clear"])
    ap.add_argument("--cap", type=int, default=40)
    ap.add_argument("--case", default="")
    ap.add_argument("--file", default="")
    args = ap.parse_args(argv)
    path = args.file or default_path(args.case)
    if args.action == "init":
        write_budget(path, args.cap)
        print(f"budget armed: cap {args.cap} -> {path}")
    elif args.action == "status":
        cap, count = read_state(path)
        print(f"{count}/{cap} used ({path})" if cap > 0 else f"unbudgeted ({path})")
    else:
        try:
            os.remove(path)
            print(f"budget cleared: {path}")
        except FileNotFoundError:
            print(f"no budget file: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
