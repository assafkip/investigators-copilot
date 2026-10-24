#!/usr/bin/env python3
"""dead-hooks-lint.py -- flag hook commands in .claude/settings.json whose script does not exist.

Why: most hooks here are wired as `test -f X && python3 X` (or `if [ -f X ]; then ...`).
That guard makes a moved or deleted script a SILENT no-op: the hook "runs", exits 0,
and enforces nothing. This lint resolves every script path referenced by every hook
command and reports the ones that are missing, split into:

  SILENT  missing and guarded (test -f / [ -f ] / `|| true` / 2>/dev/null): the gate is
          off and nobody is told
  LOUD    missing and unguarded: the hook errors on every matching event

Paths containing variables other than $CLAUDE_PROJECT_DIR (e.g. ${CLAUDE_PLUGIN_ROOT},
$R inside a for-loop) cannot be resolved statically; loop items that are literal paths
are still checked. Unresolvable references are listed with --verbose, never failed.

Usage:
  dead-hooks-lint.py [SETTINGS_JSON ...] [--project-dir DIR] [--json] [--verbose]
Default: <repo>/.claude/settings.json (+ settings.local.json when present).
Exit: 0 all resolvable scripts exist, 1 at least one missing, 2 unreadable settings.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_TOKEN = re.compile(r"""["']?([~$\w{}./-]*?[\w}]+\.(?:py|sh|js|mjs|cjs|ts|rb|pl))["']?(?=$|[\s;|&)"'])""")
GUARD_RE = re.compile(r"(\btest\s+-[fex]\b|\[\s+-[fex]\s|\|\|\s*true\b|2>\s*/dev/null)")


def iter_hook_commands(settings: dict):
    for event, groups in (settings.get("hooks") or {}).items():
        for group in groups or []:
            for hook in group.get("hooks") or []:
                cmd = hook.get("command")
                if hook.get("type", "command") == "command" and cmd:
                    yield event, group.get("matcher") or "*", cmd


def resolve(token: str, project_dir: Path) -> Path | None:
    t = token.replace("${CLAUDE_PROJECT_DIR}", str(project_dir)).replace("$CLAUDE_PROJECT_DIR", str(project_dir))
    if "$" in t or "{" in t:
        return None
    t = os.path.expanduser(t)
    p = Path(t)
    return p if p.is_absolute() else project_dir / p


def scan(settings_path: Path, project_dir: Path) -> tuple[list[dict], list[dict]]:
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    missing, unresolved = [], []
    for event, matcher, cmd in iter_hook_commands(settings):
        guarded = bool(GUARD_RE.search(cmd))
        seen = set()
        for token in SCRIPT_TOKEN.findall(cmd):
            if token in seen or token.startswith(("http:", "https:")):
                continue
            seen.add(token)
            path = resolve(token, project_dir)
            row = {"settings": str(settings_path), "event": event, "matcher": matcher,
                   "script": token, "command": cmd}
            if path is None:
                unresolved.append(row)
            elif not path.exists():
                missing.append({**row, "resolved": str(path), "kind": "SILENT" if guarded else "LOUD"})
    return missing, unresolved


def default_settings(project_dir: Path) -> list[Path]:
    out = [project_dir / ".claude" / "settings.json"]
    local = project_dir / ".claude" / "settings.local.json"
    if local.is_file():
        out.append(local)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Find hook commands whose script path does not exist.")
    ap.add_argument("settings", nargs="*")
    ap.add_argument("--project-dir", default="")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    project_dir = Path(args.project_dir or os.environ.get("CLAUDE_PROJECT_DIR") or REPO_ROOT).resolve()
    files = [Path(s) for s in args.settings] or default_settings(project_dir)
    all_missing, all_unresolved = [], []
    for f in files:
        try:
            m, u = scan(f, project_dir)
        except (OSError, ValueError) as exc:
            print(f"ERROR: cannot read {f}: {exc}", file=sys.stderr)
            return 2
        all_missing += m
        all_unresolved += u

    if args.json:
        print(json.dumps({"missing": all_missing, "unresolved": all_unresolved}, indent=2))
    else:
        for row in all_missing:
            print(f"{row['kind']:<6} {row['event']}/{row['matcher']}: {row['script']} -> {row['resolved']} (missing)")
        if args.verbose:
            for row in all_unresolved:
                print(f"SKIP   {row['event']}/{row['matcher']}: {row['script']} (cannot resolve statically)")
        silent = sum(1 for r in all_missing if r["kind"] == "SILENT")
        print(f"dead-hooks-lint: {len(all_missing)} missing ({silent} silent, {len(all_missing) - silent} loud), "
              f"{len(all_unresolved)} unresolvable, across {len(files)} settings file(s)")
    return 1 if all_missing else 0


if __name__ == "__main__":
    sys.exit(main())
