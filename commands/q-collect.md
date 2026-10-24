Plan or execute OSINT collection activities.

**Active case:** read the case folder name from the first line of `.active-case` (written by `/q-begin` and `/q-new-case`). Every path below is inside `investigations/<case>/`. If `.active-case` is missing or empty, ask the founder which case to use. Never read or write the legacy root folders `canonical/`, `investigations/<case>/`, `memory/`.

Read `skills/osint/SKILL.md` for full tool catalog, then execute the /q-collect steps from `.q-system/commands.md`.

1. Read `investigations/<case>/canonical/collection-plan.md` for outstanding requirements
2. Read `investigations/<case>/memory/investigation-state.md` for what's been collected
3. Identify highest-priority collection gaps
4. For each gap, suggest: what to collect, platform/source, tool/method, expected yield, Energy tag + Time Est
5. Present as choices, not commands
6. When founder brings back data, process via /q-intake

Available tools:
- OSINT scripts: `bash skills/osint/scripts/<name>.sh`
- TGSpyder: `tgspyder <target> --members --chats`
- Maigret: `maigret <username>`
- GHunt: `ghunt email <address>`

Argument: $ARGUMENTS (optional: specific platform or target to collect on)
