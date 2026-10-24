# Opt-in collection hooks (scope + budget)

Not wired by default. Ported 2026-10-10 from kipi `investigations/agent/`.

| File | Role |
|---|---|
| `scope.py` | pure gate: roster from the active case's `canonical/scope.md` Targets section; deny out-of-roster targets and network enumeration (lead, not chase) |
| `scope_hook.py` | PreToolUse wrapper; kill switch `Q_SCOPE_HOOK=0`; fails open |
| `budget.py` | budget file + CLI: `budget.py init --cap 40`, `status`, `clear` |
| `budget_hook.py` | PreToolUse wrapper; no budget file = no-op; kill switch `Q_BUDGET_HOOK=0`; fails open |

Enable by merging into `.claude/settings.json` (`hooks.PreToolUse`):

```json
{
  "matcher": "Bash|mcp__.*",
  "hooks": [
    {"type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/skills/osint/scripts/hooks/scope_hook.py\"", "timeout": 5},
    {"type": "command", "command": "python3 \"$CLAUDE_PROJECT_DIR/skills/osint/scripts/hooks/budget_hook.py\"", "timeout": 5}
  ]
}
```

Do not use the `test -f X && python3 X` form: a moved script then skips silently
(`scripts/dead-hooks-lint.py` flags that pattern when the file is missing).

Optional env: `Q_SCOPE_EXTRA=<file>` (extra in-scope entities, one per line),
`Q_BUDGET_FILE=<path>` (default `investigations/<case>/memory/tool-budget.json`),
`Q_WORKSPACE=<workspace dir>` (tests / alternate checkouts).
Tests: `tests/test_scope_hook.py`.
