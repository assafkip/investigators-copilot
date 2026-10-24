#!/usr/bin/env python3
"""reddit-arctic.py -- keyless Reddit reads for /q-osint reddit.

Routes, in order: Arctic Shift archive -> PullPush -> Reddit RSS. reddit.com
JSON is NOT a route: it returns 403 from any datacenter IP.

Usage:
  reddit-arctic.py user <username>   [--max 100] [--case <case>] [--json]
  reddit-arctic.py sub <subreddit>   [--max 60]  [--case <case>] [--json]
  reddit-arctic.py thread <permalink-or-id>      [--case <case>] [--json]

With --case (or a set .active-case and --save), results are written to
investigations/<case>/investigation/evidence/raw-collections/<ts>-reddit-<kind>-<name>/
as results.json + urls.tsv (feed urls.tsv to capture-evidence.sh --batch).
Everything returned is T3 (automated tool output) until crosslinked.

A failed read exits 1 with every route's error. It never prints an empty
result for a failure.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import reddit_arctic as ra  # noqa: E402
from active_case import resolve_case_dir  # noqa: E402


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in text.lower())[:60]


def save(case_arg: str, kind: str, name: str, payload: dict, rows: list) -> Path:
    case, case_dir = resolve_case_dir(case_arg)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = case_dir / "investigation" / "evidence" / "raw-collections" / f"{ts}-reddit-{kind}-{_slug(name)}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    with open(out / "urls.tsv", "w") as fh:
        for r in rows:
            if r.get("url"):
                fh.write(f"{r['url']}\treddit-{_slug(r.get('id') or name)}\treddit\t{r.get('author', '')}\t{kind} {name}\n")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("kind", choices=["user", "sub", "thread"])
    ap.add_argument("name")
    ap.add_argument("--max", type=int, default=100)
    ap.add_argument("--case", default="")
    ap.add_argument("--save", action="store_true", help="save to the active case even without --case")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        if args.kind == "user":
            payload = ra.user_history(args.name, max_items=args.max)
            rows = payload["posts"] + payload["comments"]
        elif args.kind == "sub":
            rows = ra.recent_with_rss(args.name, max_items=args.max)
            payload = {"subreddit": args.name, "posts": rows, "mirror": rows[0]["mirror"] if rows else "arctic"}
        else:
            link_id = ra.link_id_from_permalink(args.name)
            rows = [dict(ra.normalize(c), url=f"https://www.reddit.com/comments/{link_id}/_/{c.get('id', '')}/")
                    for c in ra.comments(link_id)]
            payload = {"link_id": link_id, "comments": rows, "mirror": "arctic"}
    except ra.RedditFetchFailed as exc:
        print(f"FAIL-STOP: {exc}", file=sys.stderr)
        return 1

    payload["tier"] = "T3"
    payload["fetched_at"] = datetime.now(timezone.utc).isoformat()

    if args.case or args.save:
        out = save(args.case, args.kind, args.name, payload, rows)
        print(f"saved {len(rows)} items -> {out}", file=sys.stderr)

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"[{payload.get('mirror')}] {len(rows)} items")
        for r in rows[: min(len(rows), 25)]:
            when = (r.get("created") or "")[:10]
            title = r.get("title") or (r.get("body") or "")[:100].replace("\n", " ")
            print(f"  {when}  r/{r.get('subreddit', '')}  u/{r.get('author', '')}  {title}  {r.get('url', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
