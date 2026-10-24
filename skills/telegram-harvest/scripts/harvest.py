#!/usr/bin/env python3
"""harvest.py -- Telegram channels -> offline translate -> rule extract -> XLSX with clue columns.

No LLM, no external API at run time (translation models are local Argos packages).
The machine never decides account/actor country: the geo columns stay blank and the
clues (language, country words, TG handles) land in helper columns for the analyst.

Ported 2026-10-10 from assafkip/account-procurement-tools
(account-procurement-pipeline/src/pipeline.py). Changes for workspace:
  * --case writes into investigations/<case>/investigation/evidence/raw-collections/
    <ts>-telegram-harvest/ (workbook, listings.jsonl, urls.tsv for capture-evidence.sh)
  * --from-csv processes an existing tgspyder messages CSV offline (no scrape)
  * --no-translate runs detection-free, keyword-only extraction (no models needed)
  * --keywords / --countries select another rule profile (default: account-procurement)
  * bounded: --max-messages per channel

Usage:
  harvest.py --channels channels.txt [--case C] [--proxy socks5://127.0.0.1:9050]
  harvest.py --from-csv messages.csv --channel @name [--case C] [--no-translate]
Common: [--out FILE.xlsx] [--workdir DIR] [--keywords F] [--countries F] [--max-messages N]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "osint" / "scripts" / "lib"))

import extract  # noqa: E402
import geo_clues  # noqa: E402
import lang_translate  # noqa: E402
import scrape  # noqa: E402

SKILL_ROOT = HERE.parent


def read_channels(path: str) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def score_confidence(fields: dict) -> tuple[str, bool]:
    """Confidence for a listing row, and whether a human must review it."""
    has_type = bool(fields["account_type"])
    has_price = bool(fields["cost"])
    extras = sum(bool(fields[k]) for k in ("verified", "quantity", "payment_attached", "handles"))
    if has_type and has_price and extras >= 1:
        return "high", False
    if has_type and (has_price or extras >= 1):
        return "medium", True
    return "low", True


def message_url(channel: str, message_id: str) -> str:
    handle = channel.lstrip("@").rstrip("/").split("/")[-1]
    if handle and message_id and not handle.startswith("+"):
        return f"https://t.me/{handle}/{message_id}"
    return channel


def build_record(message: dict, channel: str, keywords: dict, countries: dict, run_date: str,
                 translate: bool = True) -> dict | None:
    """Turn one scraped message into a listing record, or None if it is not a listing."""
    original = message.get("text", "") or ""
    if translate:
        language_name, iso = lang_translate.detect_language(original)
        english = lang_translate.translate_to_english(original, iso)
    else:
        language_name, english = "", ""
    combined_lower = (original + "\n" + english).lower()
    if not extract.is_listing(combined_lower, keywords):
        return None
    fields = extract.extract_listing(original, english, keywords)
    clues = geo_clues.gather_clues(original, english, language_name, countries)
    confidence, needs_review = score_confidence(fields)
    return {
        "date_of_finding": run_date,
        "url": message_url(channel, str(message.get("message_id", ""))),
        "vendor_name": channel,
        "account_type": fields["account_type"],
        "details": (english or original)[:500],
        "age": fields["age"],
        "verified": fields["verified"],
        "farmed": fields["farmed"],
        "spend": fields["spend"],
        "payment_attached": fields["payment_attached"],
        "pin": fields["pin"],
        "history": fields["history"],
        "transfer_method": fields["transfer_method"],
        "cost": fields["cost"],
        "quantity": fields["quantity"],
        "payment_method": fields["payment_method"],
        "clue_language": clues["language"],
        "clue_country_words": clues["country_words"],
        "clue_handles": fields["handles"],
        "clue_phone_country": "",
        "confidence": confidence,
        "needs_review": needs_review,
        "source_channel": channel,
        "message_id": message.get("message_id", ""),
        "message_date": message.get("date", ""),
        "text_original": original[:2000],
        "text_english": english[:2000] if english else "",
        "tier": "T3",
    }


def output_paths(args) -> tuple[Path, Path]:
    """(run_dir, workbook path)."""
    if args.out:
        out = Path(args.out)
        return out.parent, out
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if args.case is not None:
        import active_case
        _, case_dir = active_case.resolve_case_dir(args.case)
        run_dir = case_dir / "investigation" / "evidence" / "raw-collections" / f"{stamp}-telegram-harvest"
    else:
        run_dir = SKILL_ROOT / "output" / f"{stamp}-telegram-harvest"
    return run_dir, run_dir / "telegram-harvest.xlsx"


def write_side_files(run_dir: Path, records: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "listings.jsonl").open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with (run_dir / "urls.tsv").open("w", encoding="utf-8") as fh:
        fh.write("# url\tslug\tplatform\taccount\tnote  (feed to capture-evidence.sh --batch)\n")
        for n, r in enumerate(records, start=1):
            if r["url"].startswith("https://t.me/"):
                slug = "tg-" + r["url"].split("t.me/", 1)[1].replace("/", "-").lower()[:50]
                fh.write(f"{r['url']}\t{slug}\ttelegram\t{r['source_channel']}\t"
                         f"telegram-harvest {r['account_type']} conf={r['confidence']}\n")


def collect_messages(args, channel_list: list[str]):
    """Yield (channel, messages, invites) per channel, from a CSV or a live tgspyder run."""
    if args.from_csv:
        yield args.channel or "unknown", scrape.read_messages(args.from_csv), []
        return
    workdir = Path(args.workdir) if args.workdir else SKILL_ROOT / "output" / "scrape"
    for channel in channel_list:
        print(f"[*] scraping {channel}")
        scrape.run_target(channel, workdir, proxy=args.proxy)
        msgs = scrape.read_messages(scrape.newest_csv(workdir, "chats", "messages"))
        inv = scrape.read_invites(scrape.newest_csv(workdir, "crawled_links", "crawled_links"))
        yield channel, msgs, inv


def run(args) -> int:
    run_date = datetime.now().strftime("%Y-%m-%d")
    keywords = extract.load_keywords(args.keywords or None)
    countries = geo_clues.load_countries(args.countries or None)
    translate = not args.no_translate
    if translate:
        ready, missing = lang_translate.ensure_ready()
        if not ready:
            print(f"[FAIL] offline translation not ready. Missing: {', '.join(missing)}", file=sys.stderr)
            print("       Run setup.sh, or pass --no-translate for keyword-only extraction.", file=sys.stderr)
            return 1
    channel_list: list[str] = []
    if not args.from_csv:
        channel_list = read_channels(args.channels)
        if not channel_list:
            print("[FAIL] no channels to scrape. Add targets to the channel list.", file=sys.stderr)
            return 1

    import build_sheet  # openpyxl; imported late so --help works without it

    records, invites = [], []
    for channel, messages, inv in collect_messages(args, channel_list):
        for message in messages[: args.max_messages]:
            rec = build_record(message, channel, keywords, countries, run_date, translate)
            if rec:
                records.append(rec)
        invites += [{"invite_link": link, "source_channel": channel, "first_seen": run_date} for link in inv]
        print(f"    {channel}: {len(messages)} messages, {len(records)} listings so far")

    run_dir, out_path = output_paths(args)
    write_side_files(run_dir, records)
    out = build_sheet.save_sheet(records, out_path, invites=invites)
    review = sum(1 for r in records if r["needs_review"])
    print(f"[OK] {len(records)} listings ({review} need review), {len(invites)} invite links -> {out}")
    print(f"     capture cited messages: bash skills/osint/scripts/capture-evidence.sh "
          f"--batch {run_dir / 'urls.tsv'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Telegram harvest -> XLSX (no LLM).")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--channels", help="file with one @handle / t.me/name / t.me/+invite per line")
    src.add_argument("--from-csv", help="existing tgspyder messages CSV (offline mode)")
    ap.add_argument("--channel", default="", help="channel name for --from-csv rows")
    ap.add_argument("--case", nargs="?", const="", default=None,
                    help="write into the case raw-collections (bare --case = active case)")
    ap.add_argument("--out", default="")
    ap.add_argument("--workdir", default="")
    ap.add_argument("--proxy", default=None, help="SOCKS proxy, e.g. socks5://127.0.0.1:9050")
    ap.add_argument("--keywords", default="", help="keyword profile JSON (default config/keywords.json)")
    ap.add_argument("--countries", default="", help="country clue JSON (default config/countries.json)")
    ap.add_argument("--no-translate", action="store_true")
    ap.add_argument("--max-messages", type=int, default=5000, help="per-channel cap (loop bound)")
    return ap


def main(argv: list[str] | None = None) -> int:
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
