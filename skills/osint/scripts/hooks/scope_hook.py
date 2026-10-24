#!/usr/bin/env python3
"""PreToolUse hook (OPT-IN): deny investigating entities that are not case targets.

Ported 2026-10-10 from kipi investigations/agent/scope_hook.py. The roster is the
active case's canonical/scope.md Targets section (see scope.py). A denied call is
returned to the model as a PreToolUse permissionDecision "deny" with the reason, so
it records the entity as a LEAD instead of chasing it.

Not wired by default. Enable by adding the JSON snippet from hooks/README.md to
.claude/settings.json. Kill switch: Q_SCOPE_HOOK=0. No active case or an empty
roster means no gate (allow), and any error FAILS OPEN: a scope hook must never be
the thing that breaks a run.

stdin: PreToolUse JSON. stdout: nothing (allow) or the deny JSON. Exit code always 0.
"""

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "lib"))


def _allow() -> None:
    sys.exit(0)


def _roster():
    import active_case
    import scope

    workspace = Path(os.environ["Q_WORKSPACE"]) if os.environ.get("Q_WORKSPACE") else active_case.WORKSPACE
    case = active_case.read_active_case(workspace)
    if not case:
        return set()
    case_dir = workspace / "investigations" / case
    if not case_dir.is_dir():
        return set()
    return scope.load_roster(case_dir, os.environ.get("Q_SCOPE_EXTRA", ""))


def main() -> None:
    if os.environ.get("Q_SCOPE_HOOK", "1") == "0":
        _allow()
    try:
        import scope

        event = json.load(sys.stdin)
        roster = _roster()
        if not roster:
            _allow()
        allow, reason = scope.gate(event.get("tool_name", ""), event.get("tool_input", {}) or {}, roster)
    except Exception:  # noqa: BLE001 -- fail open by design, see docstring
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
