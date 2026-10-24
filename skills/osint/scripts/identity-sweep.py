#!/usr/bin/env python3
"""identity-sweep.py -- run every ready identity adapter on one handle/email/phone.

Usage:
  identity-sweep.py <handle|email|phone> [--type auto|handle|email|phone]
                    [--case <case>|--save] [--json] [--only a,b] [--skip a,b]
                    [--timeout N] [--workers N]

Auto-detects the value type, runs every READY enrichment adapter whose
watched_types include it (adapters missing a key/binary are skipped and listed),
merges and dedups the results by URL (else by title), and tags everything T3.

With --case/--save it writes
  investigations/<case>/investigation/evidence/raw-collections/<ts>-identity-<value>/
    results.json  urls.tsv  summary.md
(urls.tsv feeds capture-evidence.sh --batch; same layout as osint-tool.py).

Exit: 0 = at least one adapter answered; 1 = every adapter that ran failed;
3 = no adapter was ready for this value type.
"""

import argparse
import json
import re
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from active_case import resolve_case_dir  # noqa: E402
from enrich import registry  # noqa: E402
from enrich.base import EnrichmentError, NotConfiguredError  # noqa: E402

T3_HEADER = ("T3 hypothesis queue only -- attribution needs 2 independent T1/T2 crosslinks "
             "(.claude/rules/q-investigation.md)")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_RE = re.compile(r"^\+?[0-9][0-9 ()./-]{5,20}$")


def detect_type(value: str) -> str:
    value = value.strip()
    if EMAIL_RE.match(value):
        return "email"
    digits = re.sub(r"\D", "", value)
    if PHONE_RE.match(value) and 7 <= len(digits) <= 15:
        return "phone"
    return "handle"


def normalize_value(value: str, value_type: str) -> str:
    value = value.strip()
    if value_type == "handle":
        return value.lstrip("@")
    if value_type == "email":
        return value.lower()
    return re.sub(r"[ ()./-]", "", value)


def _csv(text: str) -> set:
    return {s.strip() for s in (text or "").split(",") if s.strip()}


def select_adapters(value_type: str, only: set, skip: set) -> tuple[list, dict]:
    """(ready adapters, {slug: missing-list}) for this value type."""
    ready, skipped = [], {}
    for slug in registry.slugs():
        adapter = registry.get_adapter(slug)
        if value_type not in adapter.watched_types or slug in skip or (only and slug not in only):
            continue
        gaps = adapter.missing()
        if gaps:
            skipped[slug] = gaps
        else:
            ready.append(adapter)
    return ready, skipped


def run_one(adapter, value: str, timeout: int) -> tuple[str, list, str | None]:
    try:
        results = adapter.run(value, timeout=timeout)
    except NotConfiguredError as exc:
        return adapter.slug, [], f"NOT CONFIGURED: {exc}"
    except EnrichmentError as exc:
        return adapter.slug, [], f"FAILED: {exc}"
    except Exception as exc:  # an adapter bug must not sink the whole sweep; it is reported
        return adapter.slug, [], f"CRASHED: {type(exc).__name__}: {exc}"
    return adapter.slug, results, None


def run_all(adapters: list, value: str, timeout: int, workers: int) -> tuple[dict, dict]:
    outputs, errors = {}, {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(adapters)))) as pool:
        for slug, results, error in pool.map(lambda a: run_one(a, value, timeout), adapters):
            if error:
                errors[slug] = error
            else:
                outputs[slug] = results
    return outputs, errors


def dedup_key(item: dict) -> str:
    url = item.get("url")
    if url:
        parts = urllib.parse.urlsplit(url.strip())
        host = parts.netloc.lower().removeprefix("www.")
        return f"url:{host}{parts.path.rstrip('/').lower()}" + (f"?{parts.query}" if parts.query else "")
    return f"{item.get('result_type')}:{str(item.get('title', '')).strip().lower()}"


def merge(outputs: dict) -> list[dict]:
    """Dedup by URL (else type+title); every merged row lists all adapters that produced it."""
    merged: dict[str, dict] = {}
    for slug in sorted(outputs):
        for result in outputs[slug]:
            item = result.to_dict()
            item["adapter_tier"], item["tier"], item["source"] = item.get("tier"), "T3", slug
            key = dedup_key(item)
            if key in merged:
                if slug not in merged[key]["sources"]:
                    merged[key]["sources"].append(slug)
                continue
            item["sources"] = [slug]
            merged[key] = item
    return list(merged.values())


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "-" for c in text.lower())[:60]


def summary_markdown(payload: dict) -> str:
    lines = [f"# Identity sweep: {payload['query']} ({payload['type']})", "", f"**{T3_HEADER}**", "",
             f"- fetched: {payload['fetched_at']}",
             f"- adapters answered: {', '.join(payload['adapters_answered']) or 'none'}",
             f"- results after dedup: {len(payload['results'])}", "", "## Skipped (not configured)", ""]
    lines += [f"- {s}: missing {', '.join(m)}" for s, m in payload["skipped"].items()] or ["- none"]
    lines += ["", "## Errors", ""]
    lines += [f"- {s}: {e}" for s, e in payload["errors"].items()] or ["- none"]
    lines += ["", "## URLs (T3 leads)", ""]
    lines += [f"- [{', '.join(r['sources'])}] {r['title']} <{r['url']}>" for r in payload["results"] if r.get("url")]
    return "\n".join(lines) + "\n"


def save(case_arg: str, payload: dict) -> Path:
    _, case_dir = resolve_case_dir(case_arg)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = f"identity-{_slug(payload['query'])}"
    out = case_dir / "investigation" / "evidence" / "raw-collections" / f"{ts}-{tag}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    (out / "summary.md").write_text(summary_markdown(payload))
    with open(out / "urls.tsv", "w") as fh:
        for i, r in enumerate(r for r in payload["results"] if r.get("url")):
            fh.write(f"{r['url']}\t{tag}-{i}\t{'+'.join(r['sources'])}\t\tT3 {r['title'][:80]}\n")
    return out


def print_human(payload: dict) -> None:
    print(T3_HEADER)
    print(f"[identity-sweep] {payload['query']} ({payload['type']}): {len(payload['results'])} merged results "
          f"from {len(payload['adapters_answered'])} adapter(s)")
    for slug, gaps in payload["skipped"].items():
        print(f"  skipped {slug}: missing {', '.join(gaps)}")
    for slug, err in payload["errors"].items():
        print(f"  error   {slug}: {err}")
    for r in payload["results"]:
        print(f"  T3 [{','.join(r['sources'])}] {r['title']}  {r.get('url') or ''}")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("value")
    ap.add_argument("--type", default="auto", choices=["auto", "handle", "email", "phone"])
    ap.add_argument("--case", default="")
    ap.add_argument("--save", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--skip", default="")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--workers", type=int, default=6)
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    value_type = detect_type(args.value) if args.type == "auto" else args.type
    value = normalize_value(args.value, value_type)
    adapters, skipped = select_adapters(value_type, _csv(args.only), _csv(args.skip))
    outputs, errors = run_all(adapters, value, args.timeout, args.workers) if adapters else ({}, {})
    payload = {"query": value, "type": value_type, "header": T3_HEADER,
               "fetched_at": datetime.now(timezone.utc).isoformat(),
               "adapters_answered": sorted(outputs), "skipped": skipped, "errors": errors,
               "results": merge(outputs)}
    if args.case or args.save:
        print(f"saved {len(payload['results'])} results -> {save(args.case, payload)}", file=sys.stderr)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print_human(payload)
    if not adapters:
        print(f"ERROR: no ready adapter for type {value_type}", file=sys.stderr)
        return 3
    return 0 if outputs else 1


if __name__ == "__main__":
    sys.exit(main())
