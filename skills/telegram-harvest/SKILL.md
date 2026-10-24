---
name: telegram-harvest
description: >
  Programmatic, no-LLM Telegram channel harvest: tgspyder scrape -> offline language
  detection + translation (Argos) -> rule-based field extraction -> XLSX with clue
  columns, plus listings.jsonl and a capture batch for EV evidence. Built for
  marketplace / account-sale / fraud-vendor channels. Use when: "harvest these
  telegram channels", "scrape telegram listings into a spreadsheet", "telegram
  marketplace sweep", "account procurement sheet".
  NOT for: private groups the case has no lawful access to, or identifying a person
  behind a channel (clues only; attribution needs T1/T2 crosslinks).
---

# telegram-harvest

Port of the founder's `assafkip/account-procurement-tools` pipeline (see `NOTICE.md`).
Deterministic: keyword dictionaries + regexes, no LLM, no external API at run time.

```
channels.txt -> tgspyder (scrape + invite links) -> lingua detect -> Argos translate (offline)
             -> extract.py rules (type, price, PIN, verified, qty, handles, links)
             -> geo_clues.py (clues only, never a country verdict)
             -> telegram-harvest.xlsx + listings.jsonl + urls.tsv
```

## Setup (once per machine)

```bash
bash skills/telegram-harvest/setup.sh        # venv, deps, tgspyder, Argos models
# tgspyder is not vendored: TGSPYDER_SRC=<checkout> bash .../setup.sh if it is elsewhere
skills/telegram-harvest/.venv/bin/tgspyder @somechannel --chats   # one interactive login
```

Telegram login uses a real account session: founder decision per case. Sessions are
secrets; never commit them.

## Run

```bash
PY=skills/telegram-harvest/.venv/bin/python
H=skills/telegram-harvest/scripts/harvest.py

# live scrape into the active case (raw-collections/<ts>-telegram-harvest/)
$PY $H --channels <case>/investigation/evidence/telegram-channels.txt --case
# via SOCKS proxy
$PY $H --channels channels.txt --case --proxy socks5://127.0.0.1:9050
# offline: re-process an existing tgspyder messages CSV, no models needed
python3 $H --from-csv messages_x.csv --channel @x --case --no-translate
# a different rule profile (copy config/keywords.json and edit the terms)
$PY $H --channels channels.txt --case --keywords path/to/keywords.json
```

Bounded: `--max-messages` per channel (default 5000).

## Output columns

The sheet keeps the 23 template columns in order (Date of Finding ... Screenshot 4),
then helper columns prefixed `»`: Confidence (high/medium/low), Needs Review, Clue:
Language, Clue: Country Words, Clue: Phone Country, Clue: TG Handles, Source Channel,
Message ID, Message Date, Original Text, English Text. `Vendor Type`, `Ecosystem (Geo)`
and `Geo of Acc.` are left blank and highlighted: **a human makes the country call**.

## Evidence routing (required before citing)

- Every row is **T3** (automated extraction). The workbook is working material.
- Capture each message you will cite as an EV item:
  `bash skills/osint/scripts/capture-evidence.sh --batch <run-dir>/urls.tsv --case <case>`
  (trim urls.tsv to the rows you need first; add `--social` per line for media).
- If the workbook itself goes to a client, register it:
  `ingest-client-document.sh <run-dir>/telegram-harvest.xlsx <slug> document --provided-by "telegram-harvest run <ts>"`.
- Handles, phone prefixes and country words are clues. A shared handle across
  channels is not the same operator without a crosslink (`.claude/rules/q-investigation.md`).

## Extending the rules

- `config/keywords.json`: account types, flags, quantity/payment/transfer/spend/history/age
  terms, in any language. Short Latin terms match on word boundaries; longer or CJK
  terms match as substrings.
- `config/countries.json`: country names, demonyms and local terms for the clue column.

## Tests

`python3 -m pytest skills/osint/tests/test_telegram_harvest.py -q`
(offline: extraction, clues, confidence, workbook columns, CSV mode).
