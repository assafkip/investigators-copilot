#!/usr/bin/env python3
"""PreToolUse hook (OPT-IN): charge one call against the run's tool budget; deny past the cap.

Ported 2026-10-10 from kipi investigations/agent/budget_hook.py. Arm a run with
`budget.py init --cap N`; with no budget file (or cap <= 0) the hook is a no-op.
Kill switch: Q_BUDGET_HOOK=0. Any error FAILS OPEN.

Not wired by default; see hooks/README.md for the settings.json snippet. Scope the
matcher to collection tools (Bash and MCP), or every Read/Edit gets charged too.

stdin: PreToolUse JSON. stdout: nothing (allow) or the deny JSON. Exit code always 0.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _allow() -> None:
    sys.exit(0)


def main() -> None:
    if os.environ.get("Q_BUDGET_HOOK", "1") == "0":
        _allow()
    try:
        import budget

        json.load(sys.stdin)  # consume the event; we charge per call, not per target
        path = budget.default_path()
        if not os.path.exists(path):
            _allow()
        allow, count, cap = budget.check_and_charge(path)
        reason = budget.deny_message(count, cap)
    except BaseException:  # noqa: BLE001 -- includes SystemExit from case resolution; fail open
        _allow()
    if allow:
        _allow()
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
