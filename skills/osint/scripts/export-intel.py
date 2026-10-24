#!/usr/bin/env python3
"""export-intel.py -- STIX 2.1 bundle / MISP event JSON / flat CSV from a case folder.

Reads (never writes) the case's working files:
  investigation/targets/*.md                 target profiles (_TEMPLATE.md skipped)
  investigation/findings/*.md                findings (_TEMPLATE.md, CHALLENGE-*, REALITY-CHECK-* skipped)
  investigation/evidence/extracted/*/iocs.json
      either a list of {value, type, ...} or {"iocs": [{value, type, ...}]}

Writes to <case>/output/exports/ (or --out):
  stix  -> intel-stix-<date>.json      STIX 2.1 bundle
  misp  -> intel-misp-<date>.json      MISP event (lightweight, importable)
  csv   -> intel-entities-<date>.csv + intel-findings-<date>.csv

Ported 2026-10-10 from kipi investigations/export/intel_exports.py: the
SQLite reads were replaced by case-file readers; the type maps and object
shapes are kept. Additions: deterministic UUIDv5 ids for STIX cyber observables
(so re-exports dedupe), TLP marking (default AMBER), findings as STIX notes,
evidence IOCs as indicators.

This is an export of what the case files SAY, not a verification of it. A
finding's confidence travels with it (x_q_confidence); T3 material stays T3.
No relationship/graph objects are produced (founder decision: no link analysis).

Usage:
  export-intel.py [stix|misp|csv|all] [--case C | --case-dir PATH] [--out DIR] [--tlp clear|green|amber|red]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

# STIX 2.1 namespace for deterministic SCO ids (spec section 2.9).
SCO_NAMESPACE = uuid.UUID("00abedb4-aa42-466c-9c01-fed23315a9b7")

TLP = {
    "clear": ("marking-definition--613f2e26-407d-48c7-9eca-b8e91df99dc9", "white"),
    "green": ("marking-definition--34098fce-860f-48ae-8e50-ebd3cc5e41da", "green"),
    "amber": ("marking-definition--f88d31f6-486f-44da-b317-01333bde0b82", "amber"),
    "red": ("marking-definition--5e57c739-391a-4eb3-b6be-7d15ca92d5ed", "red"),
}

# Normalised type -> STIX object type (kept from kipi STIX_TYPE_MAP, extended).
STIX_TYPE_MAP = {
    "ip": "ipv4-addr",
    "ipv6": "ipv6-addr",
    "domain": "domain-name",
    "url": "url",
    "email": "email-addr",
    "handle": "user-account",
    "telegram_channel": "user-account",
    "crypto_wallet": "x-crypto-wallet",
    "hash_sha256": "file",
    "hash_sha1": "file",
    "hash_md5": "file",
    "phone": "x-phone-number",
    "person": "identity",
    "organization": "identity",
    "cve": "vulnerability",
}

# Normalised type -> MISP attribute type (kept from kipi export_misp, extended).
MISP_TYPE_MAP = {
    "ip": "ip-dst",
    "ipv6": "ip-dst",
    "domain": "domain",
    "url": "url",
    "email": "email-src",
    "hash_sha256": "sha256",
    "hash_sha1": "sha1",
    "hash_md5": "md5",
    "handle": "text",
    "telegram_channel": "text",
    "crypto_wallet": "btc",
    "phone": "phone-number",
    "person": "text",
    "organization": "text",
    "cve": "vulnerability",
}
NETWORK_TYPES = {"ip", "ipv6", "domain", "url"}

# Aliases seen in iocs.json producers -> normalised type.
TYPE_ALIASES = {
    "ipv4": "ip", "ip-addr": "ip", "ipv4-addr": "ip", "ip_address": "ip",
    "ipv6-addr": "ipv6",
    "fqdn": "domain", "hostname": "domain", "domain-name": "domain", "domain_name": "domain",
    "uri": "url", "link": "url",
    "email-addr": "email", "email_address": "email",
    "sha256": "hash_sha256", "sha1": "hash_sha1", "md5": "hash_md5",
    "username": "handle", "user": "handle", "account": "handle", "social": "handle",
    "telegram": "telegram_channel",
    "wallet": "crypto_wallet", "btc": "crypto_wallet", "eth": "crypto_wallet",
    "bitcoin": "crypto_wallet", "ethereum": "crypto_wallet", "crypto": "crypto_wallet",
    "phone_number": "phone", "tel": "phone",
    "name": "person", "individual": "person", "org": "organization", "company": "organization",
}

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
IPV4_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$", re.I)
PLACEHOLDER_RE = re.compile(r"^(?:|-+|n/?a|none|tbd|unknown|\?+|\[.*\]|_.*_)$", re.I)


def now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def norm_type(raw: str) -> str:
    t = (raw or "").strip().lower().replace(" ", "_")
    return TYPE_ALIASES.get(t, t)


def classify_value(value: str) -> str | None:
    """Best-effort type for a free-text value from a target profile table."""
    v = value.strip()
    if EMAIL_RE.match(v):
        return "email"
    if re.match(r"^https?://", v, re.I):
        return "url"
    if v.lower().startswith(("t.me/", "telegram.me/")):
        return "telegram_channel"
    if IPV4_RE.match(v):
        return "ip"
    if DOMAIN_RE.match(v):
        return "domain"
    if v.startswith("@") and len(v) > 1 and " " not in v:
        return "handle"
    if re.match(r"^\+?[\d\s().-]{7,}$", v):
        return "phone"
    return None


# ---------- readers ----------

def _bullet(text: str, label: str) -> str:
    m = re.search(rf"^\s*-\s*\*\*{re.escape(label)}:?\*\*:?\s*(.*)$", text, re.M | re.I)
    return m.group(1).strip() if m else ""


def _table_rows(text: str, heading: str) -> list[list[str]]:
    """Rows of the first markdown table under `## heading` (header + separator dropped)."""
    m = re.search(rf"^##\s+{re.escape(heading)}\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S | re.I)
    if not m:
        return []
    rows = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.match(r"^:?-{2,}:?$", c) or not c for c in cells):
            continue
        rows.append(cells)
    return rows[1:] if rows else []


def _clean(v: str) -> str:
    v = re.sub(r"[`*]", "", v).strip()
    m = re.match(r"^\[([^\]]+)\]\(([^)]+)\)$", v)  # markdown link -> url
    return m.group(2) if m else v


def read_targets(case_dir: Path) -> tuple[list[dict], list[dict]]:
    """Return (targets, entities) parsed from investigation/targets/*.md."""
    targets, entities = [], []
    tdir = case_dir / "investigation" / "targets"
    for path in sorted(tdir.glob("*.md")) if tdir.is_dir() else []:
        if path.name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^#\s*Target:\s*(.+)$", text, re.M)
        name = (m.group(1).strip() if m else path.stem).strip()
        if PLACEHOLDER_RE.match(name):
            name = path.stem
        rel = str(path.relative_to(case_dir))
        assessment = _bullet(text, "Confidence level")
        targets.append({"name": name, "file": rel, "confidence": assessment})
        entities.append({"value": name, "type": "person", "source": rel, "context": "target profile",
                         "confidence": assessment})
        for alias in re.split(r"[,;]", _bullet(text, "Aliases/handles")):
            alias = _clean(alias)
            if alias and not PLACEHOLDER_RE.match(alias):
                entities.append({"value": alias, "type": classify_value(alias) or "handle",
                                 "source": rel, "context": f"alias of {name}"})
        for row in _table_rows(text, "Digital Footprint"):
            if len(row) < 2:
                continue
            platform, val = _clean(row[0]), _clean(row[1])
            if not val or PLACEHOLDER_RE.match(val):
                continue
            etype = classify_value(val) or ("domain" if "domain" in platform.lower() else "handle")
            entities.append({"value": val, "type": etype, "source": rel,
                             "context": f"{platform} account of {name}", "platform": platform})
    return targets, entities


def read_findings(case_dir: Path) -> list[dict]:
    findings = []
    fdir = case_dir / "investigation" / "findings"
    for path in sorted(fdir.glob("*.md")) if fdir.is_dir() else []:
        if path.name.startswith("_") or re.match(r"^(CHALLENGE|REALITY-CHECK)-", path.name, re.I):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^#\s*Finding:\s*(.+)$", text, re.M) or re.search(r"^#\s+(.+)$", text, re.M)
        title = m.group(1).strip() if m else path.stem
        fid = re.search(r"\bID:\s*(F-[A-Za-z0-9-]+)", text)
        conf = re.search(r"^##\s*Confidence Level\s*$\s*\**\[?([^\]\n*]+)", text, re.M | re.I)
        summ = re.search(r"^##\s*Summary\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S | re.I)
        summary = re.sub(r"\s+", " ", summ.group(1)).strip() if summ else ""
        summary = re.sub(r"^_(.*)_$", r"\1", summary)
        findings.append({
            "id": fid.group(1) if fid else path.stem,
            "title": title,
            "confidence": conf.group(1).strip() if conf else "",
            "summary": summary,
            "file": str(path.relative_to(case_dir)),
            "text": text,
        })
    return findings


def read_iocs(case_dir: Path) -> list[dict]:
    out = []
    edir = case_dir / "investigation" / "evidence" / "extracted"
    for path in sorted(edir.glob("*/iocs.json")) if edir.is_dir() else []:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            print(f"[warn] skipping unreadable {path}: {exc}", file=sys.stderr)
            continue
        items = data.get("iocs", []) if isinstance(data, dict) else data
        rel = str(path.relative_to(case_dir))
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict) or not str(item.get("value", "")).strip():
                continue
            entry = dict(item)
            entry["value"] = str(item["value"]).strip()
            entry["type"] = norm_type(str(item.get("type", ""))) or classify_value(entry["value"]) or "text"
            entry["source"] = rel
            entry["context"] = item.get("context", "") or f"extracted from {path.parent.name}"
            entry["is_ioc"] = True
            out.append(entry)
    return out


def collect(case_dir: Path) -> dict:
    targets, entities = read_targets(case_dir)
    iocs = read_iocs(case_dir)
    merged: dict[tuple[str, str], dict] = {}
    for e in entities + iocs:
        e["type"] = norm_type(e["type"])
        key = (e["type"], e["value"].lower())
        if key in merged:
            merged[key]["sources"].append(e["source"])
            merged[key]["is_ioc"] = merged[key].get("is_ioc") or e.get("is_ioc", False)
        else:
            merged[key] = {**e, "sources": [e["source"]]}
    return {"case": case_dir.name, "targets": targets, "entities": list(merged.values()),
            "findings": read_findings(case_dir)}


# ---------- STIX 2.1 ----------

def _sco_id(stix_type: str, contributing: dict) -> str:
    canon = json.dumps(contributing, sort_keys=True, separators=(",", ":"))
    return f"{stix_type}--{uuid.uuid5(SCO_NAMESPACE, canon)}"


def _stix_object(entity: dict, now: str, marking: str) -> dict | None:
    etype = entity["type"]
    stix_type = STIX_TYPE_MAP.get(etype)
    if not stix_type:
        return None
    value = entity["value"]
    base = {"type": stix_type, "spec_version": "2.1", "object_marking_refs": [marking]}
    if stix_type in ("ipv4-addr", "ipv6-addr", "domain-name", "url", "email-addr"):
        val = value.lower() if stix_type in ("domain-name", "email-addr") else value
        return {**base, "id": _sco_id(stix_type, {"value": val}), "value": val}
    if stix_type == "user-account":
        user_id = value.lstrip("@")
        account_type = "telegram" if etype == "telegram_channel" or "t.me/" in value else (
            (entity.get("platform") or "social").lower().replace(" ", "-"))
        return {**base, "id": _sco_id(stix_type, {"account_type": account_type, "user_id": user_id}),
                "user_id": user_id, "account_type": account_type}
    if stix_type == "file":
        algo = {"hash_sha256": "SHA-256", "hash_sha1": "SHA-1", "hash_md5": "MD5"}[etype]
        return {**base, "id": _sco_id(stix_type, {"hashes": {algo: value.lower()}}),
                "hashes": {algo: value.lower()}}
    if stix_type in ("x-crypto-wallet", "x-phone-number"):
        return {**base, "id": _sco_id(stix_type, {"value": value}), "value": value}
    if stix_type == "identity":
        return {**base, "id": f"identity--{uuid.uuid4()}", "created": now, "modified": now,
                "name": value, "identity_class": "individual" if etype == "person" else "organization",
                "description": entity.get("context", "")}
    if stix_type == "vulnerability":
        return {**base, "id": f"vulnerability--{uuid.uuid4()}", "created": now, "modified": now,
                "name": value.upper(),
                "external_references": [{"source_name": "cve", "external_id": value.upper()}]}
    return None


def _pattern(obj: dict) -> str | None:
    t = obj["type"]
    esc = lambda s: s.replace("\\", "\\\\").replace("'", "\\'")  # noqa: E731
    if t in ("ipv4-addr", "ipv6-addr", "domain-name", "url", "email-addr"):
        return f"[{t}:value = '{esc(obj['value'])}']"
    if t == "file":
        algo, h = next(iter(obj["hashes"].items()))
        return f"[file:hashes.'{algo}' = '{esc(h)}']"
    return None


def build_stix(data: dict, tlp: str = "amber") -> dict:
    now = now_z()
    marking_id, tlp_name = TLP[tlp]
    marking = {"type": "marking-definition", "spec_version": "2.1", "id": marking_id,
               "created": "2017-01-20T00:00:00.000Z", "definition_type": "tlp",
               "name": f"TLP:{tlp_name.upper()}", "definition": {"tlp": tlp_name}}
    author = {"type": "identity", "spec_version": "2.1", "id": f"identity--{uuid.uuid4()}",
              "created": now, "modified": now, "name": "the investigation practice",
              "identity_class": "organization"}
    objects: list[dict] = [marking, author]
    by_value: dict[str, str] = {}
    for ent in data["entities"]:
        obj = _stix_object(ent, now, marking_id)
        if not obj:
            continue
        if "created" in obj:
            obj["created_by_ref"] = author["id"]
        if obj["id"] in {o["id"] for o in objects}:
            continue
        objects.append(obj)
        by_value[ent["value"].lower()] = obj["id"]
        pattern = _pattern(obj) if ent.get("is_ioc") else None
        if pattern:
            objects.append({
                "type": "indicator", "spec_version": "2.1", "id": f"indicator--{uuid.uuid4()}",
                "created": now, "modified": now, "created_by_ref": author["id"],
                "name": ent["value"], "pattern": pattern, "pattern_type": "stix",
                "valid_from": now, "indicator_types": ["unknown"],
                "description": f"From {', '.join(ent['sources'])}. Tier/confidence per case files; "
                               "not independently re-verified by this export.",
                "object_marking_refs": [marking_id],
            })
    for f in data["findings"]:
        mentioned = [oid for val, oid in by_value.items() if val and val in f["text"].lower()]
        objects.append({
            "type": "note", "spec_version": "2.1", "id": f"note--{uuid.uuid4()}",
            "created": now, "modified": now, "created_by_ref": author["id"],
            "abstract": f"{f['id']}: {f['title']}", "content": f["summary"] or f["title"],
            "authors": ["the investigation practice"],
            "object_refs": sorted(set(mentioned)) or [author["id"]],
            "x_q_finding_id": f["id"], "x_q_confidence": f["confidence"], "x_q_source_file": f["file"],
            "object_marking_refs": [marking_id],
        })
    refs = [o["id"] for o in objects if o["type"] != "marking-definition" and o["id"] != author["id"]]
    objects.append({
        "type": "report", "spec_version": "2.1", "id": f"report--{uuid.uuid4()}",
        "created": now, "modified": now, "created_by_ref": author["id"],
        "name": f"Investigation export: {data['case']}", "published": now,
        "report_types": ["threat-actor"] if data["targets"] else ["indicator"],
        "object_refs": refs or [author["id"]], "object_marking_refs": [marking_id],
    })
    return {"type": "bundle", "id": f"bundle--{uuid.uuid4()}", "objects": objects}


# ---------- MISP ----------

def build_misp(data: dict, tlp: str = "amber") -> dict:
    attributes = []
    for ent in data["entities"]:
        misp_type = MISP_TYPE_MAP.get(ent["type"])
        if not misp_type:
            continue
        attributes.append({
            "uuid": str(uuid.uuid4()),
            "type": misp_type,
            "category": "Network activity" if ent["type"] in NETWORK_TYPES else (
                "Financial fraud" if ent["type"] == "crypto_wallet" else "Other"),
            "value": ent["value"],
            "to_ids": bool(ent.get("is_ioc")) and ent["type"] in NETWORK_TYPES | {"hash_sha256", "hash_sha1", "hash_md5"},
            "comment": f"{ent.get('context', '')} [{', '.join(ent['sources'])}]".strip()[:1000],
        })
    for f in data["findings"]:
        attributes.append({
            "uuid": str(uuid.uuid4()), "type": "comment", "category": "Other",
            "value": f"{f['id']}: {f['title']} -- {f['summary']}"[:4000], "to_ids": False,
            "comment": f"confidence={f['confidence'] or 'unstated'} file={f['file']}",
        })
    ts = datetime.now(timezone.utc)
    return {"Event": {
        "uuid": str(uuid.uuid4()),
        "info": f"Investigators Copilot investigation: {data['case']}",
        "date": ts.strftime("%Y-%m-%d"),
        "timestamp": str(int(ts.timestamp())),
        "distribution": "0",
        "threat_level_id": "2",
        "analysis": "1",
        "published": False,
        "Tag": [{"name": f"tlp:{'clear' if tlp == 'clear' else TLP[tlp][1]}"}],
        "Attribute": attributes,
    }}


# ---------- CSV ----------

def write_csv(data: dict, out_dir: Path, stamp: str) -> list[Path]:
    ent_path = out_dir / f"intel-entities-{stamp}.csv"
    with ent_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["value", "type", "is_ioc", "context", "sources"])
        for e in sorted(data["entities"], key=lambda e: (e["type"], e["value"].lower())):
            w.writerow([e["value"], e["type"], "yes" if e.get("is_ioc") else "", e.get("context", ""),
                        " | ".join(e["sources"])])
    fnd_path = out_dir / f"intel-findings-{stamp}.csv"
    with fnd_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "title", "confidence", "file", "summary"])
        for f in data["findings"]:
            w.writerow([f["id"], f["title"], f["confidence"], f["file"], f["summary"]])
    return [ent_path, fnd_path]


def run(fmt: str, case_dir: Path, out_dir: Path, tlp: str) -> list[Path]:
    data = collect(case_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    written: list[Path] = []
    if fmt in ("stix", "all"):
        p = out_dir / f"intel-stix-{stamp}.json"
        p.write_text(json.dumps(build_stix(data, tlp), indent=2), encoding="utf-8")
        written.append(p)
    if fmt in ("misp", "all"):
        p = out_dir / f"intel-misp-{stamp}.json"
        p.write_text(json.dumps(build_misp(data, tlp), indent=2), encoding="utf-8")
        written.append(p)
    if fmt in ("csv", "all"):
        written += write_csv(data, out_dir, stamp)
    print(f"[export-intel] {len(data['entities'])} entities, {len(data['findings'])} findings, "
          f"{len(data['targets'])} targets", file=sys.stderr)
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export a case to STIX 2.1 / MISP / CSV.")
    ap.add_argument("format", nargs="?", default="all", choices=["stix", "misp", "csv", "all"])
    ap.add_argument("--case", default="")
    ap.add_argument("--case-dir", default="", help="explicit case folder (bypasses .active-case)")
    ap.add_argument("--out", default="")
    ap.add_argument("--tlp", default="amber", choices=sorted(TLP))
    args = ap.parse_args(argv)
    if args.case_dir:
        case_dir = Path(args.case_dir).resolve()
        if not case_dir.is_dir():
            sys.exit(f"ERROR: case directory not found: {case_dir}")
    else:
        import active_case
        _, case_dir = active_case.resolve_case_dir(args.case)
    out_dir = Path(args.out) if args.out else case_dir / "output" / "exports"
    for p in run(args.format, case_dir, out_dir, args.tlp):
        print(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
