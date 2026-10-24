# Investigation claims get a ledger too, not just raw evidence (ADVISORY)

`evidence-capture-protocol.md`'s EV-NNNN system and the evidence ledger
(`evidence-ledger.md`) answer two different questions and this instance had
only ever adopted one of them.

| System | Answers | Lives at |
|---|---|---|
| EV-NNNN chain-of-custody | Do we have a tamper-evident copy of this **external** page/document? | `investigation/evidence/items/EV-NNNN-*/` |
| Evidence ledger | Does this **derived, computed** claim (a percentage, a count, an attribution, a confidence tag) trace to a command that was actually run, and does a later document quoting it still match the current, corrected value? | `canonical/evidence.jsonl` |

A page can be perfectly chain-of-custody-captured and a finding built from it
can still be wrong three re-summarization hops later, because nothing checked
the LATER document against the FIRST one, or against a correction that
happened after the first was written. That is exactly what happened in
case-043: RCA `q-system/output/rca/rca-synthesis-claim-drift-case-001-example.md`.
Four errors, all in the direction of a stronger claim than the evidence
supported, all caught by an outside cold review rather than by anything
mechanical in this instance.

## The rule

Any deliverable-tier document for an investigation (a synthesis, a brief, a
report meant to leave the case folder) records its load-bearing claims in the
evidence ledger as they are established, and gets checked before it is
reported as finished:

```bash
python3 .q-system/scripts/evidence_ledger.py add \
  --claim "what the number/attribution actually is" \
  --source "the finding file it comes from" \
  --command "what was actually run to get it" \
  --result "the actual output"

python3 skills/osint/scripts/resolve-deliverable.py <the deliverable file>
```

The second command is a thin, workspace-specific wrapper around
`evidence_ledger.py resolve` — it strips this instance's own `F-NNN`/`EV-NNNN`
citation IDs before checking, because the shared script's generic number-scanner
otherwise reads "F-014" as the number 14 and produces false failures unrelated
to whether any claim is actually ungrounded. See the wrapper's own docstring for
why this is a local adapter and not an edit to the shared skeleton script.

**Exit 2 means a real number or quoted span in the document has no ledger row
behind it.** Fix it one of two ways, in order: verify it and add the row, or
mark it `{{UNVERIFIED}}` in the text if it is genuinely an inference rather
than a measurement. Neither is optional; silently ungrounded is the failure
mode this exists to remove.

## Why this is labeled ADVISORY, not ENFORCED

The script works and is callable today — proven against `SYNTHESIS-2026-09-04.md`
this session. But nothing in `.claude/settings.json` wires it as a PostToolUse
hook, so no write to a deliverable-tier file triggers it automatically. Calling
it ENFORCED without that wiring is exactly the kind of overclaim this rule
exists to prevent (`skill-hook-pairing.md`'s decision rule: a script that isn't
actually wired to fire gets DETECTED or ADVISORY, never ENFORCED). Wiring an
automatic hook is a real next step, not done here — it would need scoping
(which paths count as "deliverable-tier") and a decision on whether it blocks
or only warns, both judgment calls left to the founder rather than assumed.

## What this does not retroactively fix

Case-043's `SYNTHESIS-2026-09-04.md` was NOT fully backfilled against this
ledger — only the specific facts the cold review found wrong were entered as
rows (the corrected live-domain percentage, the ColocaTel maintainer record,
the direct Spamhaus fetch, the BGP tie). Running `resolve-deliverable.py`
against that document today still fails on dozens of older, never-disputed
numbers that were never entered. That is a stated gap, not a silent one:
full retroactive backfill of an already-finished document is disproportionate
to what this rule is for. **The rule binds forward** — the next deliverable
this or any future investigation produces should be ledger-checked before
it is called done, not the ones that already shipped.

## Does not apply

Internal working notes, session logs, raw collection dumps. This is for
documents that leave the case folder as a stated conclusion — a brief, a
synthesis, a report to a client, founder, or outside party.

## Cross-references

`evidence-capture-protocol.md` (the EV-NNNN half) · `evidence-ledger.md` (the
shared mechanism this adopts) · `skill-hook-pairing.md` (why this is a script
and a rule pointing at it, not a paragraph asking nicely).

```json
[
  {
    "clause": "Investigation claims get a ledger too, not just raw evidence",
    "status": "ADVISORY",
    "exec": "skills/osint/scripts/resolve-deliverable.py",
    "config": "none -- not wired as an automatic hook",
    "note": "script exists, tested, callable; no PostToolUse hook triggers it automatically yet, so it is a manual step, not an enforced gate",
    "directives": 1
  }
]
```
