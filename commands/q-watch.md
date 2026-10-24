Monitor case URLs and profiles for changes, and route every change into the evidence chain.

**Active case:** read the case folder name from the first line of `.active-case` (written by `/q-begin` and `/q-new-case`). The watch store lives at `investigations/<case>/memory/watch.jsonl` (append-only). If `.active-case` is missing or empty, ask the founder which case to use.

**Backends (auto-selected):**
- `changedetection` -- when `CHANGEDETECTION_URL` and `CHANGEDETECTION_API_KEY` are set, URLs are registered in a self-hosted changedetection.io (tagged with the case name) and its `last_changed` is read on each poll. Start one with `docker run -d -p 5000:5000 --name changedetection dgtlmoon/changedetection.io`, then Settings > API for the key.
- `local` -- no server needed: `watch.py` fetches each URL itself and compares a SHA-256 of the normalised body (scripts/styles stripped). An empty body is an error, never a "change".
- Optional: a self-hosted **sosse** (AGPL, separate service, never imported) can crawl and diff whole sites on a schedule; use it alongside this store, not instead of the EV capture step.

**Steps:**
1. Parse `$ARGUMENTS`: `add <url> [label]`, `remove <url>`, `list`, or `poll [--capture]`. Default is `list`.
2. Run the matching command:
   ```bash
   python3 skills/osint/scripts/watch.py add "<url>" --label "<label>"
   python3 skills/osint/scripts/watch.py list
   python3 skills/osint/scripts/watch.py poll                # report only
   python3 skills/osint/scripts/watch.py poll --capture      # changed URLs -> capture-evidence.sh --batch
   python3 skills/osint/scripts/watch.py remove "<url>"
   ```
3. `poll` is bounded: `--max 50` watches and `--deadline 300` seconds per run by default. If it reports watches left over, say so; do not loop it.
4. A `changed` result is a LEAD (T3). Only the EV-NNNN item created by `--capture` (through `capture-evidence.sh`) may be cited. If the batch capture fail-stops (INCOMPLETE item), stop and tell the founder which URL and why (`.claude/rules/evidence-capture-protocol.md`).
5. For a social profile, prefer `capture-evidence.sh <url> <slug> --social` on the changed URL so media lands in the same EV item.
6. Report: watches polled, changed (with the new EV IDs), errors (URL + error), and anything not polled this run.

**Rules:**
- Never edit `watch.jsonl` by hand; it is an append-only history.
- Login walls / challenge pages / 403s on poll are blocked extractions: stop and tell the founder (`.claude/rules/q-investigation.md`).

Argument: $ARGUMENTS (optional: `add <url> [label]` | `remove <url>` | `list` | `poll [--capture]`)
