#!/usr/bin/env python3
"""osint-tool.py -- run any enrichment adapter from the shell (the bash belt).

Usage:
  osint-tool.py --list                         # every provider, its tier, what is missing
  osint-tool.py <slug> <query> [--mode M] [--json] [--case <case>|--save]

With --case/--save, results go to
  investigations/<case>/investigation/evidence/raw-collections/<ts>-<slug>-<query>/
as results.json + urls.tsv (feed urls.tsv to capture-evidence.sh --batch).
Each result carries its evidence tier (T1 record or T3 tool output). A failed
provider call exits 1 with the reason; it never prints an empty result instead.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from active_case import resolve_case_dir  # noqa: E402
from enrich import registry  # noqa: E402
from enrich.base import EnrichmentError, NotConfiguredError  # noqa: E402


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in text.lower())[:60]


def list_providers(as_json: bool) -> int:
    rows = registry.describe_all()
    if as_json:
        print(json.dumps({"providers": rows, "import_errors": registry.IMPORT_ERRORS}, indent=2))
        return 0
    for r in rows:
        state = "ready" if not r["missing"] else "missing " + ", ".join(r["missing"])
        print(f"{r['slug']:<22} {r['tier']}  {r['category']:<10} {state}")
    for mod, err in registry.IMPORT_ERRORS.items():
        print(f"{mod:<22} IMPORT ERROR: {err}")
    return 0


def save(case_arg: str, slug: str, query: str, payload: dict) -> Path:
    _, case_dir = resolve_case_dir(case_arg)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = case_dir / "investigation" / "evidence" / "raw-collections" / f"{ts}-{slug}-{_slug(query)}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    with open(out / "urls.tsv", "w") as fh:
        for i, r in enumerate(payload["results"]):
            if r.get("url"):
                fh.write(f"{r['url']}\t{slug}-{_slug(query)}-{i}\t{slug}\t\t{r['tier']} {r['title'][:80]}\n")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", nargs="?")
    ap.add_argument("query", nargs="?")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--mode", default=None)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--case", default="")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--timeout", type=int, default=60)
    args = ap.parse_args()

    if args.list or not args.slug:
        return list_providers(args.json)
    if not args.query:
        ap.error("query is required")
    try:
        adapter = registry.get_adapter(args.slug)
    except KeyError:
        print(f"ERROR: unknown provider {args.slug!r} (see --list)", file=sys.stderr)
        return 2
    try:
        results = adapter.run(args.query, mode=args.mode, timeout=args.timeout)
    except NotConfiguredError as exc:
        print(f"NOT CONFIGURED: {exc}", file=sys.stderr)
        return 3
    except EnrichmentError as exc:
        print(f"FAIL-STOP ({args.slug}): {exc}", file=sys.stderr)
        return 1
    for r in results:
        r.source = args.slug
    payload = {"provider": args.slug, "query": args.query, "mode": args.mode,
               "fetched_at": datetime.now(timezone.utc).isoformat(),
               "results": [r.to_dict() for r in results]}
    if args.case or args.save:
        out = save(args.case, args.slug, args.query, payload)
        print(f"saved {len(results)} results -> {out}", file=sys.stderr)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    print(f"[{args.slug}] {len(results)} results")
    for r in results:
        print(f"  {r.tier} {r.confidence:<6} {r.title}  {r.url or ''}")
        if r.summary:
            print(f"         {r.summary[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
