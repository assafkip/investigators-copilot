#!/usr/bin/env python3
"""reformat_csv.py -- <CASE NAME> leaked-record classification.

Copy this file to investigation/evidence/scripts/reformat_csv.py in the case
folder, fill in the anchors and classify_row() below, then run:

  python3 investigation/evidence/scripts/reformat_csv.py --case <case-folder>

PREREQUISITE (enforced by evidence-pipeline-guard.py): the source CSV must
already be registered and extracted before this script can run --
  bash skills/osint/scripts/ingest-client-document.sh <file> <slug> document --case <case-folder>
  python3 skills/osint/scripts/extract-intake.py --case <case-folder>

This file supplies ONLY the case-specific identity anchors and classification
rules. The shared Maltego-parsing/Excel-writing scaffold lives in
skills/leak-record-classifier/lib/leak_csv.py -- read that
module's docstring before writing classify_row(), especially the note on
checking your own export's section-boundary markers if csv rows look wrong.
"""

import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[5]  # 
sys.path.insert(0, str(WORKSPACE / "skills" / "leak-record-classifier" / "lib"))
import leak_csv  # noqa: E402

# ---------------------------------------------------------------------------
# CASE-SPECIFIC CONFIG -- fill these in from your own recon pass. Do not
# guess anchors; verify each one against the actual extracted CSV first
# (investigation/evidence/extracted/<stem>/text.md), same as both origin
# cases (case-001-example, case-001-example) did.
# ---------------------------------------------------------------------------

TARGET_SSN_DIGITS = ""          # e.g. "459691485" -- digits only, no dashes
TARGET_DOB = ""                 # e.g. "1976-08-16" -- YYYY-MM-DD

CONFIRMED_ADDR_TOKENS = []       # lowercase substrings, e.g. ["6611 lake meadow"]
CONFIRMED_EMAILS = set()         # emails already co-occurring with a confirmed row

DROP_COLUMNS = {"hashed password", "salt", "documentid", "querytype", "password plain"}


def classify_row(row):
    """Return (tier_key, reason). Define your own tier vocabulary -- the two
    origin cases used different sets (confirmed/flagged/excluded/unrelated vs.
    subject_confirmed/subject_flagged/household/excluded/unrelated) because
    their households/subjects differed. Pick whatever tiers this case's data
    actually needs; wire matching entries into TIER_CONFIG and
    CLEANED_TIERS/FILTERED_OUT_TIERS below.

    IMPORTANT precedence lesson (case-039 shipped with this bug initially,
    caught before delivery): check for a genuine SSN-matches-but-DOB-conflicts
    case FIRST, before any weaker confirm signal (address, email) can silently
    absorb it into "confirmed". Leak databases (esp. National Public Data)
    are known to have real record-matching quality issues -- don't let a
    conflict get masked by a later, weaker match.
    """
    name = (row.get("Name", "") or "").strip()
    ssn_digits = leak_csv.norm_digits(row.get("Ssn", ""))
    dob_raw = row.get("Birthdate", "") or ""
    dob_norm = leak_csv.norm_dob(dob_raw)
    address = row.get("Address", "") or ""
    emails = leak_csv.emails_in_field(row.get("Email", ""))

    # Example structure -- replace with this case's real rules:
    if ssn_digits == TARGET_SSN_DIGITS and dob_norm and dob_norm != TARGET_DOB:
        return ("flagged", f"SSN matches but DOB conflicts ({dob_raw!r} vs {TARGET_DOB})")
    if ssn_digits == TARGET_SSN_DIGITS and (dob_norm is None or dob_norm == TARGET_DOB):
        return ("confirmed", "SSN matches subject")
    if dob_norm == TARGET_DOB:
        return ("confirmed", "DOB matches subject")
    if leak_csv.addr_hits(address, CONFIRMED_ADDR_TOKENS):
        return ("confirmed", "Confirmed household address")
    if any(e in CONFIRMED_EMAILS for e in emails):
        return ("confirmed", "Corroborating email")

    return ("unrelated", "No signal")


# Sheets that appear in the Excel deliverable, in order. A tier not listed
# here (typically "unrelated") is still written to the filtered-out CSV audit
# trail but dropped from the client-facing spreadsheet.
TIER_CONFIG = [
    {"key": "confirmed", "sheet_title": "Confirmed", "fill_color": "E2EFDA"},   # light green
    {"key": "flagged",   "sheet_title": "Flagged",   "fill_color": "FFF2CC"},   # light yellow
    {"key": "excluded",  "sheet_title": "Excluded",  "fill_color": "FCE4D6"},   # light red
]

CLEANED_TIERS = {"confirmed", "flagged"}
FILTERED_OUT_TIERS = {"excluded", "unrelated"}

OUTPUT_BASENAME = "case"   # e.g. "example" -> example_cleaned.csv


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Reformat Maltego CSV for this case.")
    parser.add_argument("--case", help="case folder name under investigations/")
    parser.add_argument("--input", help="override input CSV path")
    parser.add_argument("--output-dir", help="override output directory")
    args = parser.parse_args()

    leak_csv.run(
        workspace=WORKSPACE,
        case_arg=args.case,
        input_arg=args.input,
        output_dir_arg=args.output_dir,
        classify_fn=classify_row,
        tier_config=TIER_CONFIG,
        cleaned_tiers=CLEANED_TIERS,
        filtered_out_tiers=FILTERED_OUT_TIERS,
        output_basename=OUTPUT_BASENAME,
        drop_columns=DROP_COLUMNS,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
