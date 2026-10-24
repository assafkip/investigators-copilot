#!/usr/bin/env python3
"""redact-pii.py -- redact PII from a markdown / text deliverable before it leaves the case.

Writes <dir>/<stem>.redacted.md next to the input and prints per-type counts. The input
file is never modified.

Engines:
  presidio -- Microsoft Presidio analyzer + anonymizer (lazy import; pip install
              presidio-analyzer presidio-anonymizer, plus a spaCy model such as
              python -m spacy download en_core_web_lg). Used automatically when it loads.
  regex    -- deterministic stdlib fallback: emails, phones, US SSNs, IBANs (mod-97
              checked) and payment cards (Luhn checked). Used when Presidio is absent or
              fails to initialise; the reason is printed, never hidden.

Replacement token: [REDACTED:<TYPE>], e.g. [REDACTED:EMAIL_ADDRESS].

Usage:
  python3 redact-pii.py <file.md> [--engine auto|presidio|regex] [--also PERSON,LOCATION]
                        [--allow VALUE ...] [--out path] [--json]
    --also   extra Presidio entity types (PERSON, LOCATION, IP_ADDRESS, CRYPTO, ...);
             ignored by the regex engine (it has no NER), which says so.
    --allow  exact strings never redacted (e.g. the firm's own published phone).

Exit: 0 ok; 1 input/setup error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import entity_extract  # noqa: E402

BASE_ENTITIES = ["EMAIL_ADDRESS", "PHONE_NUMBER", "US_SSN", "IBAN_CODE", "CREDIT_CARD"]

SSN_RE = re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")
CARD_RE = re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")
IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
    return total % 10 == 0


def iban_ok(value: str) -> bool:
    compact = value.replace(" ", "")
    if not 15 <= len(compact) <= 34:
        return False
    rearranged = compact[4:] + compact[:4]
    numeric = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(numeric) % 97 == 1


def _phone_ok(match) -> bool:
    return (entity_extract._looks_like_phone(match)
            and entity_extract.is_real_phone(match.group(0)))


REGEX_RULES = [
    ("US_SSN", SSN_RE, None),
    ("IBAN_CODE", IBAN_RE, lambda m: iban_ok(m.group(0))),
    ("CREDIT_CARD", CARD_RE,
     lambda m: 13 <= len(re.sub(r"\D", "", m.group(0))) <= 19
     and luhn_ok(re.sub(r"\D", "", m.group(0)))),
    ("EMAIL_ADDRESS", EMAIL_RE, None),
    ("PHONE_NUMBER", entity_extract.PHONE_RE, _phone_ok),
]


def regex_spans(text: str) -> list:
    """(start, end, type) for every regex hit; earlier rules claim overlapping spans."""
    spans: list = []
    for label, rx, valid in REGEX_RULES:
        for m in rx.finditer(text):
            if valid and not valid(m):
                continue
            start, end = m.start(), m.end()
            # PHONE_RE starts at a digit, so "(212) 555-0100" matches without its "(".
            if label == "PHONE_NUMBER" and start > 0 and text[start - 1] == "(" \
                    and ")" in m.group(0):
                start -= 1
            if any(start < e and s < end for s, e, _ in spans):
                continue
            spans.append((start, end, label))
    return spans


def presidio_spans(text: str, entities: list) -> list:
    from presidio_analyzer import AnalyzerEngine
    analyzer = AnalyzerEngine()
    results = analyzer.analyze(text=text, entities=entities, language="en")
    spans: list = []
    for r in sorted(results, key=lambda r: (-r.score, r.start)):
        if any(r.start < e and s < r.end for s, e, _ in spans):
            continue
        spans.append((r.start, r.end, r.entity_type))
    return spans


def apply_redactions(text: str, spans: list, allow: set) -> tuple:
    counts: Counter = Counter()
    out = text
    for start, end, label in sorted(spans, key=lambda s: s[0], reverse=True):
        if text[start:end] in allow:
            continue
        out = out[:start] + f"[REDACTED:{label}]" + out[end:]
        counts[label] += 1
    return out, counts


def pick_spans(text: str, engine: str, also: list) -> tuple:
    if engine in ("auto", "presidio"):
        try:
            return presidio_spans(text, BASE_ENTITIES + also), "presidio"
        except ImportError as exc:
            reason = f"presidio not installed ({exc}): pip install presidio-analyzer"
        except Exception as exc:  # noqa: BLE001 -- e.g. spaCy model missing; reported below
            reason = f"presidio failed to initialise: {type(exc).__name__}: {exc}"
        if engine == "presidio":
            raise SystemExit(f"ERROR: --engine presidio but {reason}")
        print(f"[redact-pii] {reason}; using regex fallback", file=sys.stderr)
    if also:
        print(f"[redact-pii] regex engine has no NER; --also {','.join(also)} ignored",
              file=sys.stderr)
    return regex_spans(text), "regex"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Redact PII from a deliverable.")
    ap.add_argument("file", type=Path)
    ap.add_argument("--engine", choices=["auto", "presidio", "regex"], default="auto")
    ap.add_argument("--also", default="", help="extra Presidio entity types, comma-separated")
    ap.add_argument("--allow", action="append", default=[], help="exact value to keep")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--json", action="store_true", help="print counts as JSON")
    args = ap.parse_args(argv)

    if not args.file.is_file():
        print(f"ERROR: not found: {args.file}", file=sys.stderr)
        return 1
    text = args.file.read_text(encoding="utf-8")
    also = [a.strip().upper() for a in args.also.split(",") if a.strip()]
    spans, engine = pick_spans(text, args.engine, also)
    redacted, counts = apply_redactions(text, spans, set(args.allow))
    out = args.out or args.file.with_name(f"{args.file.stem}.redacted.md")
    out.write_text(redacted, encoding="utf-8")
    summary = {"engine": engine, "input": str(args.file), "output": str(out),
               "total": sum(counts.values()), "counts": dict(sorted(counts.items()))}
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"engine={engine} redacted={summary['total']} -> {out}")
        for label, n in summary["counts"].items():
            print(f"  {label}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
