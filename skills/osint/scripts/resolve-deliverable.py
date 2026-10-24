#!/usr/bin/env python3
"""resolve-deliverable: workspace's wrapper around the shared evidence_ledger.

WHY THIS FILE EXISTS (not a fork of evidence_ledger.py -- a thin adapter in front
of it): RCA rca-synthesis-claim-drift-case-001-example.md. A cold second-opinion
review of a finished, gate-passed case synthesis found four factual errors -- a
superseded number quoted after its own correction, an overlap claim not supported
by the record it cited, two entities placed under the wrong upstream in a summary
table, and an external-authority citation tagged as directly verified when it was
a secondhand relay. The fleet already ships a mechanism built for exactly this
(`.q-system/scripts/evidence_ledger.py`, append-only claim ledger + a
`resolve` check that a document's numbers/quotes trace to a verified row) but it
had never been adopted for workspace. This wrapper is that adoption.

WHY A WRAPPER AND NOT A DIRECT CALL: evidence_ledger.py's number-scanner has no
concept of this instance's own citation convention (`F-014`, `EV-0037`). Its
generic regex reads the digits after the hyphen as a bare number, so a synthesis
document that cites its own findings files by ID produces a wall of false
"traces to no ledger row" failures that have nothing to do with unverified
claims. Measured on SYNTHESIS-2026-09-04.md: roughly a third of its reported
"missing" numbers were finding-citation IDs, not measurements. Stripping that
pattern before handing text to the shared resolver is a workspace-specific
convention, not something the shared skeleton script should special-case for
one instance's naming style -- hence a local wrapper, not an edit to the
skeleton copy (`kipi push` is the only sanctioned path to change shared code).

USAGE:
  python3 resolve-deliverable.py <file.md>       # exit 2 on any real unresolved claim
  python3 resolve-deliverable.py <file.md> --show-stripped   # also print what was stripped, for audit

HONEST BOUNDARY: this strips exactly two citation shapes (`F-<digits>`,
`EV-<digits>`) and nothing else. A number embedded in some other convention this
instance adopts later will read as unresolved again until this list is extended.
It does not change what counts as "resolved" -- a real ledger row is still
required for every other number and quoted span, at full strength.
"""
import re
import sys
from pathlib import Path

SKEL_SCRIPTS = Path(__file__).resolve().parents[3] / ".q-system" / "scripts"
sys.path.insert(0, str(SKEL_SCRIPTS))
import evidence_ledger as el  # noqa: E402

CITATION_RE = re.compile(r"\b(?:F|EV)-\d+\b")


def strip_citations(text: str) -> tuple[str, list[str]]:
    stripped = []

    def _sub(m):
        stripped.append(m.group(0))
        return " "

    return CITATION_RE.sub(_sub, text), stripped


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        sys.stderr.write("usage: resolve-deliverable.py <file.md> [--show-stripped]\n")
        return 2
    path = Path(argv[0])
    show = "--show-stripped" in argv

    text = path.read_text(encoding="utf-8", errors="ignore")
    cleaned, stripped = strip_citations(text)

    if not el.adopted(None):
        sys.stderr.write(
            "resolve-deliverable: no evidence ledger adopted for this instance yet "
            "(canonical/evidence.jsonl does not exist). Nothing to "
            "check against -- this is a silent stand-down by evidence_ledger's own "
            "design, not a pass.\n"
        )
        return 0

    nums = el.resolve_numbers(None, cleaned)
    spans = el.resolve_spans(None, cleaned)

    if show:
        print(f"Stripped {len(stripped)} citation-ID tokens before checking: "
              f"{sorted(set(stripped))}")

    if nums or spans:
        sys.stderr.write(f"resolve-deliverable: FAILED for {path}\n")
        for n in nums:
            sys.stderr.write(f"  - number {n} traces to no ledger row\n")
        for s in spans:
            sys.stderr.write(f'  - quote "{s}" traces to no ledger row\n')
        sys.stderr.write(
            "\nEach of these is either a real claim needing a ledger row "
            "(evidence_ledger.py add ...) or a number/quote that does not need "
            "grounding (e.g. a section number, a date fragment) -- but it does not "
            "get to be silently ungrounded. Label it {{UNVERIFIED}} in the text if "
            "it genuinely is one.\n"
        )
        return 2

    print(f"resolve-deliverable: OK ({path}) -- every number and quoted span "
          f"traces to a ledger row, after stripping {len(stripped)} citation-ID tokens.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
