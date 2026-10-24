#!/usr/bin/env python3
"""resolve-entities.py -- entity resolution over CSV / JSON records -> same_as candidates.

Reads records (people / accounts / leak rows) with any of: name, email, phone, address,
and emits candidate pairs that may be the same real-world entity, each with a
`match_probability` and the fields that drove it (`match_basis`).

Engines:
  splink   -- splink + DuckDB (lazy import; pip install splink). Fellegi-Sunter model,
              u-probabilities by random sampling, m-probabilities by EM when the data
              supports it. Used automatically when importable; force with --engine.
  fallback -- deterministic, stdlib only: normalized exact email / phone, name
              similarity via difflib, address similarity. Same input, same output.
Address normalization uses libpostal (`postal`, lazy) when installed, else a regex
abbreviation fold.

EVERY candidate is T3 (hypothesis queue only). Per the evidence-tier rule, a name match
alone is 0 crosslinks; `match_basis` says which fields matched so an analyst can see a
name-only pair for what it is. Nothing here writes to findings.

Input formats: .csv / .tsv (header row), .json (a list of objects, or {"records": [...]}),
.jsonl. Works on leak-record-classifier output CSVs (columns are auto-detected; override
with --name-col / --email-col / --phone-col / --address-col / --id-col).

Usage:
  python3 resolve-entities.py records.csv [more.json ...] --out same_as.csv
      [--engine auto|splink|fallback] [--threshold 0.5] [--ftm entities.ftm.jsonl]
      [--ftm-schema Person|LegalEntity|Company]

Output: .csv or .json by --out extension (default: same_as.csv next to the first input).
Exit: 0 ok; 1 input/setup error.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

FIELD_ALIASES = {
    "name": ["name", "full_name", "fullname", "display_name", "displayname", "subject_name",
             "person", "owner", "holder", "account_name", "username_display"],
    "first": ["first_name", "firstname", "given_name", "first"],
    "last": ["last_name", "lastname", "surname", "family_name", "last"],
    "email": ["email", "email_address", "e-mail", "mail", "emails"],
    "phone": ["phone", "phone_number", "telephone", "tel", "mobile", "cell", "msisdn", "phones"],
    "address": ["address", "street_address", "full_address", "addr", "location", "address1"],
    "id": ["id", "record_id", "uid", "unique_id", "row_id"],
}
OUT_COLUMNS = ["id_l", "id_r", "relation", "match_probability", "match_basis", "engine",
               "name_l", "name_r", "email_l", "email_r", "phone_l", "phone_r",
               "address_l", "address_r", "source_l", "source_r", "evidence_tier"]
ADDRESS_ABBREV = {
    "street": "st", "avenue": "ave", "road": "rd", "boulevard": "blvd", "drive": "dr",
    "lane": "ln", "court": "ct", "place": "pl", "square": "sq", "suite": "ste",
    "apartment": "apt", "north": "n", "south": "s", "east": "e", "west": "w",
    "floor": "fl", "highway": "hwy", "parkway": "pkwy", "terrace": "ter",
}


# ---------------- loading ----------------

def load_records(path: Path) -> list:
    suffix = path.suffix.lower()
    if suffix in (".csv", ".tsv"):
        delim = "\t" if suffix == ".tsv" else ","
        with path.open(encoding="utf-8", errors="replace", newline="") as fh:
            return list(csv.DictReader(fh, delimiter=delim))
    if suffix == ".jsonl":
        return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if suffix == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("records") or data.get("entities") or data.get("rows") or []
        if not isinstance(data, list):
            raise ValueError(f"{path}: expected a list of objects")
        return [r for r in data if isinstance(r, dict)]
    raise ValueError(f"{path}: unsupported input type {suffix} (use .csv .tsv .json .jsonl)")


def pick_column(keys: list, field: str, override: str | None) -> str | None:
    if override:
        return override if override in keys else None
    lowered = {k.lower().strip(): k for k in keys}
    for alias in FIELD_ALIASES[field]:
        if alias in lowered:
            return lowered[alias]
    return None


def _cell(row: dict, col: str | None) -> str:
    if not col:
        return ""
    value = row.get(col)
    if isinstance(value, list):
        value = value[0] if value else ""
    return "" if value is None else str(value).strip()


def map_records(rows: list, source: str, overrides: dict) -> list:
    if not rows:
        return []
    keys = list({k for r in rows for k in r.keys()})
    cols = {f: pick_column(keys, f, overrides.get(f)) for f in FIELD_ALIASES}
    mapped = []
    for i, row in enumerate(rows, start=1):
        name = _cell(row, cols["name"]) or " ".join(
            p for p in (_cell(row, cols["first"]), _cell(row, cols["last"])) if p)
        rid = _cell(row, cols["id"]) or f"{source}:{i}"
        mapped.append({"id": rid, "source": source, "name": name,
                       "email": _cell(row, cols["email"]), "phone": _cell(row, cols["phone"]),
                       "address": _cell(row, cols["address"])})
    return mapped


# ---------------- normalization ----------------

def norm_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    tokens = re.findall(r"[^\W_]+", text)
    return " ".join(tokens)


def norm_email(value: str) -> str:
    v = (value or "").strip().lower()
    return v if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v) else ""


def norm_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits[-10:] if len(digits) >= 7 else ""


def _postal_expand():
    try:
        from postal.expand import expand_address
    except ImportError:
        return None
    return expand_address


def norm_address(value: str, expander=None) -> str:
    if not value:
        return ""
    if expander is not None:
        expansions = expander(value)
        if expansions:
            return sorted(expansions)[0]
    tokens = re.findall(r"[^\W_]+", value.lower())
    return " ".join(ADDRESS_ABBREV.get(t, t) for t in tokens)


def normalize_all(records: list) -> str:
    expander = _postal_expand()
    for r in records:
        r["name_norm"] = norm_name(r["name"])
        r["email_norm"] = norm_email(r["email"])
        r["phone_norm"] = norm_phone(r["phone"])
        r["address_norm"] = norm_address(r["address"], expander)
    return "libpostal" if expander else "regex abbreviation fold"


# ---------------- deterministic fallback ----------------

def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _name_sim(a: str, b: str) -> float:
    """Best of raw and token-sorted similarity (handles "Roe Jane" vs "Jane Roe")."""
    sorted_a = " ".join(sorted(a.split()))
    sorted_b = " ".join(sorted(b.split()))
    return max(similarity(a, b), similarity(sorted_a, sorted_b))


def score_pair(a: dict, b: dict) -> tuple:
    basis = []
    name_sim = _name_sim(a["name_norm"], b["name_norm"])
    addr_sim = similarity(a["address_norm"], b["address_norm"])
    email = bool(a["email_norm"]) and a["email_norm"] == b["email_norm"]
    phone = bool(a["phone_norm"]) and a["phone_norm"] == b["phone_norm"]
    if email:
        basis.append("email_exact")
    if phone:
        basis.append("phone_exact")
    if name_sim >= 0.8:
        basis.append(f"name_sim={name_sim:.2f}")
    if addr_sim >= 0.85:
        basis.append(f"address_sim={addr_sim:.2f}")
    if email and phone:
        prob = 0.99
    elif email or phone:
        prob = 0.97 if name_sim >= 0.8 else (0.95 if email else 0.90)
    elif name_sim >= 0.92 and addr_sim >= 0.85:
        prob = 0.85
    elif name_sim >= 0.95:
        prob = 0.60  # name-only: a hypothesis, 0 crosslinks under the evidence-tier rule
    else:
        prob = 0.0
    if basis and all(b_.startswith("name_sim") for b_ in basis):
        basis.append("name_only_not_a_crosslink")
    return prob, ";".join(basis)


def candidate_pairs(records: list):
    """Blocking: shared email, shared phone, or same first-3 of a sorted name token."""
    blocks: dict = {}
    for idx, r in enumerate(records):
        keys = []
        if r["email_norm"]:
            keys.append("e:" + r["email_norm"])
        if r["phone_norm"]:
            keys.append("p:" + r["phone_norm"])
        for tok in r["name_norm"].split():
            if len(tok) >= 3:
                keys.append("n:" + tok[:3])
        for k in keys:
            blocks.setdefault(k, []).append(idx)
    seen = set()
    for members in blocks.values():
        for i, left in enumerate(members):
            for right in members[i + 1:]:
                pair = (min(left, right), max(left, right))
                if pair not in seen:
                    seen.add(pair)
                    yield pair


def resolve_fallback(records: list, threshold: float) -> list:
    out = []
    for i, j in candidate_pairs(records):
        prob, basis = score_pair(records[i], records[j])
        if prob >= threshold and prob > 0:
            out.append(_pair_row(records[i], records[j], prob, basis, "fallback (difflib)"))
    return sorted(out, key=lambda r: (-r["match_probability"], r["id_l"], r["id_r"]))


def _pair_row(a: dict, b: dict, prob: float, basis: str, engine: str) -> dict:
    return {"id_l": a["id"], "id_r": b["id"], "relation": "same_as",
            "match_probability": round(float(prob), 4), "match_basis": basis, "engine": engine,
            "name_l": a["name"], "name_r": b["name"], "email_l": a["email"], "email_r": b["email"],
            "phone_l": a["phone"], "phone_r": b["phone"], "address_l": a["address"],
            "address_r": b["address"], "source_l": a["source"], "source_r": b["source"],
            "evidence_tier": "T3"}


# ---------------- splink ----------------

def _splink_linker(df, settings):
    """Build a Linker on splink 4 (db_api kwarg) or splink 5 (register first)."""
    import inspect

    from splink import Linker
    try:
        from splink import DuckDBAPI
    except ImportError:
        from splink.backends.duckdb import DuckDBAPI
    db_api = DuckDBAPI()
    if "db_api" in inspect.signature(Linker.__init__).parameters:
        return Linker(df, settings, db_api=db_api)
    return Linker(db_api.register(df), settings)


def resolve_splink(records: list, threshold: float) -> tuple:
    import pandas as pd
    import splink.comparison_library as cl
    from splink import SettingsCreator, block_on

    frame = pd.DataFrame([{
        "unique_id": str(i), "name_norm": r["name_norm"] or None,
        "email_norm": r["email_norm"] or None, "phone_norm": r["phone_norm"] or None,
        "address_norm": r["address_norm"] or None} for i, r in enumerate(records)])
    settings = SettingsCreator(
        link_type="dedupe_only",
        comparisons=[cl.JaroWinklerAtThresholds("name_norm", [0.95, 0.88]),
                     cl.ExactMatch("email_norm"), cl.ExactMatch("phone_norm"),
                     cl.JaroWinklerAtThresholds("address_norm", [0.95, 0.85])],
        blocking_rules_to_generate_predictions=[
            block_on("email_norm"), block_on("phone_norm"), block_on("substr(name_norm, 1, 3)")],
        retain_matching_columns=True)
    linker = _splink_linker(frame, settings)
    note = "splink ("
    try:
        linker.training.estimate_probability_two_random_records_match(
            [block_on("email_norm"), block_on("phone_norm")], recall=0.7)
        note += "prior from email/phone rules, "
    except Exception as exc:  # noqa: BLE001 -- e.g. no exact email/phone overlaps at all
        note += "default prior, "
        print(f"[resolve-entities] note: splink prior left at default: {exc}", file=sys.stderr)
    linker.training.estimate_u_using_random_sampling(max_pairs=1e6)
    note += "u by random sampling"
    try:
        linker.training.estimate_parameters_using_expectation_maximisation(
            block_on("substr(name_norm, 1, 3)"))
        note += ", m by EM)"
    except Exception as exc:  # noqa: BLE001 -- small data often cannot train m; say so
        note += f", m left at defaults: EM failed: {type(exc).__name__})"
        print(f"[resolve-entities] note: splink EM training skipped: {exc}", file=sys.stderr)
    pred = linker.inference.predict(threshold_match_probability=threshold).as_pandas_dataframe()
    rows = []
    for _, p in pred.iterrows():
        a, b = records[int(p["unique_id_l"])], records[int(p["unique_id_r"])]
        _, basis = score_pair(a, b)
        rows.append(_pair_row(a, b, p["match_probability"], basis, note))
    return sorted(rows, key=lambda r: (-r["match_probability"], r["id_l"], r["id_r"])), note


def resolve(records: list, engine: str, threshold: float) -> tuple:
    if engine in ("auto", "splink"):
        try:
            import duckdb  # noqa: F401
            import splink  # noqa: F401
        except ImportError as exc:
            if engine == "splink":
                raise SystemExit(f"ERROR: --engine splink but splink/duckdb missing ({exc}): "
                                 "pip install splink")
            print(f"[resolve-entities] splink not installed ({exc}); using deterministic "
                  "fallback. pip install splink for probabilistic linkage.", file=sys.stderr)
        else:
            return resolve_splink(records, threshold)
    return resolve_fallback(records, threshold), "fallback (difflib)"


# ---------------- FollowTheMoney ----------------

def _ftm_id(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


def ftm_entities(records: list, pairs: list, schema: str) -> list:
    try:
        from followthemoney import model
    except ImportError:
        model = None
    ids = {}
    out = []
    for r in records:
        props = {"name": r["name"], "email": r["email"], "phone": r["phone"],
                 "address": r["address"]}
        eid = _ftm_id("record", r["source"], r["id"])
        ids[r["id"]] = eid
        out.append(_ftm_make(model, schema, eid, {k: v for k, v in props.items() if v}))
    for p in pairs:
        summary = f"same_as candidate p={p['match_probability']} basis={p['match_basis']} (T3)"
        eid = _ftm_id("same_as", p["id_l"], p["id_r"])
        out.append(_ftm_make(model, "UnknownLink", eid, {
            "subject": ids[p["id_l"]], "object": ids[p["id_r"]], "role": "same_as",
            "summary": summary}))
    return out


def _ftm_make(model, schema: str, eid: str, props: dict) -> dict:
    if model is None:
        return {"id": eid, "schema": schema, "properties": {k: [v] for k, v in props.items()}}
    proxy = model.make_entity(schema)
    proxy.id = eid
    for key, value in props.items():
        proxy.add(key, value)
    return proxy.to_dict()


# ---------------- output ----------------

def write_pairs(rows: list, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() == ".json":
        out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        return
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Entity resolution -> same_as candidates (T3).")
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--engine", choices=["auto", "splink", "fallback"], default="auto")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--ftm", type=Path, help="also write FollowTheMoney JSONL here")
    ap.add_argument("--ftm-schema", default="Person")
    for field in ("name", "email", "phone", "address", "id"):
        ap.add_argument(f"--{field}-col")
    args = ap.parse_args(argv)

    overrides = {f: getattr(args, f"{f}_col") for f in ("name", "email", "phone", "address", "id")}
    records = []
    for path in args.inputs:
        if not path.is_file():
            print(f"ERROR: input not found: {path}", file=sys.stderr)
            return 1
        try:
            records += map_records(load_records(path), path.name, overrides)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    if len(records) < 2:
        print("ERROR: need at least 2 records to resolve", file=sys.stderr)
        return 1

    addr_mode = normalize_all(records)
    pairs, engine_note = resolve(records, args.engine, args.threshold)
    out = args.out or args.inputs[0].with_name("same_as.csv")
    write_pairs(pairs, out)
    print(f"records={len(records)} candidates={len(pairs)} engine={engine_note} "
          f"address_norm={addr_mode} -> {out}")
    if args.ftm:
        ents = ftm_entities(records, pairs, args.ftm_schema)
        args.ftm.parent.mkdir(parents=True, exist_ok=True)
        args.ftm.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in ents),
                            encoding="utf-8")
        print(f"ftm entities={len(ents)} -> {args.ftm}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
