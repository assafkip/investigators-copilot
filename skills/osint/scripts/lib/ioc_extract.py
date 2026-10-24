"""ioc_extract.py -- deterministic, defang-aware IOC + ATT&CK + gazetteer extraction.

Faithful Python port of theia (KTLYST Labs, MIT) `app/lib/`:
  iocExtract.mjs  -> extract_iocs, refang, defang
  grounding.mjs   -> normalize, span_grounded, ground_extraction
  context.mjs     -> sentence_context
  section.mjs     -> section_hint
  attackIds.mjs   -> extract_attack_ids
  entities.mjs    -> detect_entities
Vendored data lives in data/theia/ (see data/theia/NOTICE.md).

No LLM, no network. The core invariant (theia PRD-003 section 2.0): every emitted item's
`source_span` is EXACTLY `text[start:end]` -- the indicator located in place in the
original text, so provenance is verbatim, not a normalized approximation. The
huntable `value` is the deterministic refang of that raw span.

Offset unit: Python str indices (Unicode code points). theia's JS offsets are UTF-16
code units; the two only differ for astral-plane characters (emoji etc.) BEFORE an
indicator. The slice-equality invariant holds in both.

Regex fidelity notes: JS regexes without the `u` flag treat `\\b`, `\\w`, `\\d` as ASCII;
we compile with re.ASCII to match. JS `\\s` is Unicode-aware even without `u`, so it is
spelled out as JS_WS below rather than relying on Python's ASCII `\\s`.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data" / "theia"

# JS `\s` (ECMAScript WhiteSpace + LineTerminator), spelled out so ASCII mode does not
# shrink it.
JS_WS = "\\t\\n\\v\\f\\r \\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000\\ufeff"
_JS_WS_CHARS = ("\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006"
                "\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff")


def _js_trim(s: str) -> str:
    return s.strip(_JS_WS_CHARS)


# ---------------------------------------------------------------------------
# Vendored data
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_tlds() -> frozenset:
    return frozenset(json.loads((DATA_DIR / "tlds.json").read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def load_gazetteer() -> dict:
    return json.loads((DATA_DIR / "gazetteer.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_stoplist() -> tuple:
    data = json.loads((DATA_DIR / "entity-stoplist.json").read_text(encoding="utf-8"))
    return tuple(data.get("stoplist", []))


# ---------------------------------------------------------------------------
# grounding.mjs
# ---------------------------------------------------------------------------

# Pass 1: whitespace run (JS \s + U+200B ZERO WIDTH SPACE) -> single space.
_WHITESPACE_RUN = re.compile(f"[{JS_WS}\\u200b]+")
# Pass 2: PDF hyphenated line-wrap, protecting suspended-compound function words.
_HYPHENATED_WRAP = re.compile(
    r"(?<=[A-Za-z0-9\]])- (?!(?:and|or|nor|but|to|vs)(?:[^\w-]|$))(?=[a-z])", re.ASCII)
# Pass 3: typographic punctuation -> ASCII fold.
_TYPOGRAPHY_FOLD = {
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u2026": "...",
}
_TYPOGRAPHY_RE = re.compile("[\u2018\u2019\u201c\u201d\u2013\u2014\u2026]")


def normalize(s) -> str:
    """Three passes in the v007-critical order: whitespace, hyphen-wrap, typography."""
    out = _js_trim(_WHITESPACE_RUN.sub(" ", "" if s is None else str(s)))
    out = _HYPHENATED_WRAP.sub("-", out)
    return _TYPOGRAPHY_RE.sub(lambda m: _TYPOGRAPHY_FOLD.get(m.group(0), m.group(0)), out)


def span_grounded(source_span, normalized_text: str) -> bool:
    """Case-sensitive containment after normalization. Empty span -> True (nothing to verify)."""
    span = normalize(source_span)
    if not span:
        return True
    return span in normalized_text


def ground_extraction(extraction: dict, raw_text: str) -> dict:
    """Split model-proposed observables into grounded / dropped (never silently shipped)."""
    pdf = normalize(raw_text)
    dropped = []

    def ok(obs, where):
        good = span_grounded(obs.get("source_span"), pdf)
        if not good:
            dropped.append({**obs, "_where": where})
        return good

    patterns = []
    for pattern in extraction.get("behavioral_patterns") or []:
        obs = [o for o in (pattern.get("observables") or []) if ok(o, "behavioral_pattern")]
        patterns.append({**pattern, "observables": obs})
    iocs = [o for o in (extraction.get("unbound_iocs") or []) if ok(o, "unbound_ioc")]
    return {
        "behavioral_patterns": patterns,
        "tools": extraction.get("tools") or [],
        "malware": extraction.get("malware") or [],
        "unbound_iocs": iocs,
        "_dropped_ungrounded": dropped,
    }


# ---------------------------------------------------------------------------
# context.mjs
# ---------------------------------------------------------------------------

_TERMINATORS = {".", "!", "?"}
_CTX_TRIM_RE = re.compile(f"[{JS_WS}\u00b7|]")
_JS_WS_RE = re.compile(f"[{JS_WS}]")


def sentence_context(text, start: int, end: int, max_back: int = 200,
                     max_fwd: int = 200, cap: int = 320) -> dict:
    """Widen [start,end) to its sentence; returns a verbatim slice + bounds."""
    src = "" if text is None else str(text)
    n = len(src)
    start = max(0, min(start, n))
    end = max(start, min(end, n))

    s = start
    back_edge = max(0, start - max_back)
    while s > back_edge:
        prev = src[s - 1]
        if prev in ("\n", "\r"):
            break
        if prev == " " and s - 2 >= 0 and src[s - 2] in _TERMINATORS:
            break
        s -= 1

    e = end
    fwd_edge = min(n, end + max_fwd)
    while e < fwd_edge:
        ch = src[e]
        if ch in ("\n", "\r"):
            break
        e += 1
        if ch in _TERMINATORS:
            after = src[e] if e < n else None
            if after is None or after in (" ", "\n", "\r"):
                break

    while s < start and _CTX_TRIM_RE.match(src[s]):
        s += 1
    while e > end and _CTX_TRIM_RE.match(src[e - 1]):
        e -= 1

    if e - s > cap:
        over = e - s - cap
        cut_front = min(over, start - s)
        s += cut_front
        over -= cut_front
        e -= min(over, e - end)
        while s < start and _JS_WS_RE.match(src[s]):
            s += 1
        while e > end and _JS_WS_RE.match(src[e - 1]):
            e -= 1

    return {"context": src[s:e], "context_start": s, "context_end": e}


# ---------------------------------------------------------------------------
# section.mjs
# ---------------------------------------------------------------------------

_BENIGN = re.compile(
    r"\b(?:deconflict\w*|benign|known[-\s]?good|legitimate|non[-\s]?malicious|"
    r"clean(?:\s+(?:file|hash|sample|indicator)\w*)?|false[-\s]?positives?|whitelist\w*|"
    r"allow[-\s]?list\w*|excluded|testing|"
    r"test\s+(?:infra\w*|indicator\w*|artifact\w*|host\w*|data))\b",
    re.IGNORECASE | re.ASCII)
_THREAT = re.compile(
    r"\b(?:indicators?\s+of\s+compromise|iocs?|network\s+indicators?|host\s+indicators?|"
    r"c2\b|command[-\s]and[-\s]control|malicious|attacker|threat\s+infra\w*)\b",
    re.IGNORECASE | re.ASCII)
_PROSE_MID = re.compile(f"[.!?][{JS_WS}]+[^{JS_WS}]")
_SENT_END = re.compile(r"[.!?]$")


def _js_last_index_of(src: str, sub: str, frm: int) -> int:
    """JS String.prototype.lastIndexOf(sub, frm) semantics (negative frm clamps to 0)."""
    frm = max(0, min(frm, len(src)))
    return src.rfind(sub, 0, frm + len(sub))


def _is_headingish(line: str) -> bool:
    t = _js_trim(line)
    if len(t) < 2 or len(t) > 80:
        return False
    if _PROSE_MID.search(t):
        return False
    if _SENT_END.search(t):
        return False
    return True


def section_hint(text, start: int, max_lines: int = 40, max_back: int = 4000):
    """Benign/deconfliction hint from the nearest heading above `start`, else None."""
    src = "" if text is None else str(text)
    pos = max(0, min(start, len(src)))
    back_edge = max(0, pos - max_back)
    line_end = _js_last_index_of(src, "\n", pos - 1)
    scanned = 0
    while line_end >= back_edge and scanned < max_lines:
        line_start = _js_last_index_of(src, "\n", line_end - 1) + 1
        raw = src[line_start:line_end]
        if _is_headingish(raw):
            if _BENIGN.search(raw):
                return {"section_hint": "benign", "section_heading": _js_trim(raw)}
            if _THREAT.search(raw):
                return None
        scanned += 1
        line_end = line_start - 1
    return None


# ---------------------------------------------------------------------------
# iocExtract.mjs
# ---------------------------------------------------------------------------

# Real IANA TLDs that are ALSO common file extensions (Codex F4): a 2-label
# `name.<ext>` is a filename, not a domain, unless inside a captured URL.
FILENAME_TLDS = frozenset([
    "zip", "mov", "app", "dev", "sh", "py", "js", "css", "json", "md", "doc", "docx",
    "pdf", "exe", "dll", "ps1", "bat", "bin", "dat", "iso", "img", "log", "xml",
    "html", "htm", "php", "jar", "apk", "dmg", "pkg", "deb", "rpm", "gz", "tar",
    "rar", "txt", "csv", "ppt", "xls", "rtf", "ini", "cfg", "yml", "yaml", "go",
])

_DOT = r"(?:\[\.\]|\(\.\)|\{\.\}|\[dot\]|\(dot\)|\{dot\}|\.)"
_SCHEME = r"h(?:tt|xx)ps?"
_COLON = r"(?::|\[:\])"
_AT = r"(?:@|\[@\]|\[at\])"
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_URLCHUNK = f"(?:{_DOT}|\\[:\\]|[^{JS_WS}<>\"'\\[\\]\\(\\)\\{{\\}},;])"
_FLAGS = re.IGNORECASE | re.ASCII

RE = {
    "url": re.compile(f"{_SCHEME}{_COLON}//(?:{_URLCHUNK})+", _FLAGS),
    "email": re.compile(f"\\b[a-z0-9._%+-]+{_AT}(?:{_LABEL}{_DOT})+[a-z]{{2,63}}\\b", _FLAGS),
    "domain": re.compile(f"\\b(?:{_LABEL}{_DOT})+[a-z][a-z0-9-]{{1,62}}\\b", _FLAGS),
    "ipv4": re.compile(f"\\b\\d{{1,3}}{_DOT}\\d{{1,3}}{_DOT}\\d{{1,3}}{_DOT}\\d{{1,3}}\\b", re.ASCII),
    "cve": re.compile(r"\bCVE-\d{4}-\d{4,7}\b", _FLAGS),
    "md5": re.compile(r"\b[a-f0-9]{32}\b", _FLAGS),
    "sha1": re.compile(r"\b[a-f0-9]{40}\b", _FLAGS),
    "sha256": re.compile(r"\b[a-f0-9]{64}\b", _FLAGS),
    "hashWrap": re.compile(r"\b[a-f0-9]+\r?\n[ \t]*[a-f0-9]+\b", _FLAGS),
}

HASH_LENS = {32, 40, 64}

_REFANG_SCHEME = re.compile(r"h(xx)(ps?)", re.IGNORECASE)
_REFANG_DOT = re.compile(f"\\[\\.\\]|\\(\\.\\)|\\{{\\.\\}}|\\[dot\\]|\\(dot\\)|\\{{dot\\}}|[{JS_WS}]+dot[{JS_WS}]+",
                         re.IGNORECASE)
_REFANG_AT = re.compile(f"\\[@\\]|\\[at\\]|[{JS_WS}]+at[{JS_WS}]+", re.IGNORECASE)
_URL_TRAIL = re.compile(r"[).,;:'\"\[\]]+$")
_VERSION_PREFIX = re.compile(f"(?:^|[^a-z])(?:v|ver|version)[{JS_WS}]*[:.]?[{JS_WS}]*$",
                             re.IGNORECASE)
_HASH_SPLIT = re.compile(r"\r?\n[ \t]*")


def refang(s) -> str:
    """Deterministically turn a defanged string into its real form. Idempotent on clean text."""
    out = "" if s is None else str(s)
    out = _REFANG_SCHEME.sub(lambda m: "htt" + m.group(2), out)
    out = _REFANG_DOT.sub(".", out)
    out = _REFANG_AT.sub("@", out)
    out = out.replace("[:]", ":")
    return _js_trim(out)


def defang(s) -> str:
    """Render a real IOC in a safe, non-clickable form."""
    out = "" if s is None else str(s)
    out = re.sub(r"https?:", lambda m: re.sub(r"http", "hxxp", m.group(0), count=1,
                                             flags=re.IGNORECASE), out, flags=re.IGNORECASE)
    return out.replace(".", "[.]")


def _tld_of(host: str) -> str:
    i = host.rfind(".")
    return "" if i == -1 else host[i + 1:].lower()


def _hits(text: str, rx: re.Pattern, field_type: str, refine=None) -> list:
    out = []
    for m in rx.finditer(text):
        start = m.start()
        raw = m.group(0)
        r = refine(raw, start, text) if refine else {"value": refang(raw), "raw": raw}
        if not r:
            continue
        raw = r.get("raw") or raw
        end = start + len(raw)
        source_span = text[start:end]
        if source_span != raw:
            continue  # paranoia: keep the slice-equality invariant
        if not r.get("value"):
            continue
        out.append({"field_type": field_type, "value": r["value"],
                    "source_span": source_span, "start": start, "end": end})
    return out


def _valid_ipv4(raw: str) -> bool:
    parts = refang(raw).split(".")
    if len(parts) != 4:
        return False
    return all(re.fullmatch(r"[0-9]{1,3}", p) and int(p) <= 255 for p in parts)


def extract_iocs(text) -> list:
    """theia extractIocs: url/email/ip/domain/cve/file_hash with verbatim spans."""
    src = "" if text is None else str(text)
    tlds = load_tlds()
    items: list = []

    def url_refine(raw, _start, _t):
        trimmed = _URL_TRAIL.sub("", raw)
        return {"raw": trimmed, "value": refang(trimmed)}

    def ip_refine(raw, start, t):
        if not _valid_ipv4(raw):
            return None
        before = t[max(0, start - 12):start]
        if _VERSION_PREFIX.search(before):
            return None
        return {"raw": raw, "value": refang(raw)}

    def domain_refine(raw, _start, _t):
        host = refang(raw).lower()
        tld = _tld_of(host)
        if f".{tld}" not in tlds:
            return None
        if len(host.split(".")) == 2 and tld in FILENAME_TLDS:
            return None
        return {"raw": raw, "value": host}

    def wrap_refine(raw, _start, _t):
        parts = _HASH_SPLIT.split(raw)
        if len(parts) != 2:
            return None
        f1, f2 = parts
        if len(f1) + len(f2) not in HASH_LENS:
            return None
        if len(f1) in HASH_LENS and len(f2) in HASH_LENS:
            return None  # two adjacent hashes, not a wrap: never invent a merged IOC
        return {"raw": raw, "value": (f1 + f2).lower()}

    def lower_refine(raw, _s, _t):
        return {"raw": raw, "value": raw.lower()}

    items += _hits(src, RE["url"], "url", url_refine)
    items += _hits(src, RE["email"], "email",
                   lambda raw, _s, _t: {"raw": raw, "value": refang(raw).lower()})
    items += _hits(src, RE["ipv4"], "ip", ip_refine)
    items += _hits(src, RE["domain"], "domain", domain_refine)
    items += _hits(src, RE["cve"], "cve", lambda raw, _s, _t: {"raw": raw, "value": raw.upper()})

    wrapped = _hits(src, RE["hashWrap"], "file_hash", wrap_refine)
    wrap_spans = [(i["start"], i["end"]) for i in wrapped]
    items += wrapped
    items += _hits(src, RE["sha256"], "file_hash", lower_refine)
    items += _hits(src, RE["sha1"], "file_hash", lower_refine)
    items += _hits(src, RE["md5"], "file_hash", lower_refine)

    def keep_hash(i):
        if i["field_type"] != "file_hash":
            return True
        if any(i["start"] == s and i["end"] == e for s, e in wrap_spans):
            return True
        return not any(i["start"] >= s and i["end"] <= e for s, e in wrap_spans)

    items = [i for i in items if keep_hash(i)]

    containers = [(i["start"], i["end"]) for i in items if i["field_type"] in ("url", "email")]

    def contained(i):
        return any(i["start"] >= s and i["end"] <= e for s, e in containers)

    items = [i for i in items
             if not (i["field_type"] in ("domain", "ip") and contained(i))]

    by_key: dict = {}
    for it in items:
        key = f"{it['field_type']} {normalize(it['value'])}"
        prev = by_key.get(key)
        if prev:
            prev["count"] += 1
            if it["start"] < prev["start"]:
                prev.update(start=it["start"], end=it["end"], source_span=it["source_span"])
        else:
            by_key[key] = {**it, "count": 1}

    out = []
    for it in sorted(by_key.values(), key=lambda i: (i["field_type"], i["value"])):
        rec = {**it, **sentence_context(src, it["start"], it["end"])}
        hint = section_hint(src, it["start"])
        if hint:
            rec.update(hint)
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# attackIds.mjs
# ---------------------------------------------------------------------------

_ATTACK_RE = re.compile(r"\bT\d{4}(?:\.\d{3})?\b", re.ASCII)


def extract_attack_ids(text, technique_map: dict | None = None) -> list:
    """Printed T#### / T####.### ids; in_attack only on an EXACT snapshot hit."""
    src = "" if text is None else str(text)
    tmap = technique_map or {}
    by_id: dict = {}
    for m in _ATTACK_RE.finditer(src):
        tid = m.group(0)
        if tid in by_id:
            by_id[tid]["count"] += 1
            continue
        start = m.start()
        end = start + len(tid)
        known = tid in tmap
        by_id[tid] = {"id": tid, "name": tmap[tid] if known else None, "in_attack": known,
                      "source_span": src[start:end], "start": start, "end": end, "count": 1}
    return [{**it, **sentence_context(src, it["start"], it["end"])}
            for it in sorted(by_id.values(), key=lambda i: i["id"])]


# ---------------------------------------------------------------------------
# entities.mjs
# ---------------------------------------------------------------------------

MIN_TERM_LEN = 4
MAX_SPANS = 5
_ALNUM_RUN = re.compile(r"[^\W_]+")  # Unicode letters + numbers (\p{L}\p{N} approximation)


def _term_regex(term: str) -> re.Pattern:
    return re.compile(f"(?<![^\\W_]){re.escape(term)}(?![^\\W_])", re.IGNORECASE)


def detect_entities(text, gazetteer: dict | None, stoplist=()) -> list:
    """Curated whole-token gazetteer matching (actors / tools / malware)."""
    src = "" if text is None else str(text)
    lower = src.lower()
    stop = {str(s).lower() for s in (stoplist or [])}
    doc_tokens = set(_ALNUM_RUN.findall(lower))

    def first_token(t):
        m = _ALNUM_RUN.search(t.lower())
        return m.group(0) if m else None

    gaz = gazetteer or {}
    groups = [("actor", gaz.get("actors") or []), ("tool", gaz.get("tools") or []),
              ("malware", gaz.get("malware") or [])]
    results: dict = {}
    for kind, entries in groups:
        for entry in entries:
            name = (entry or {}).get("name")
            if not name:
                continue
            rec = {"kind": kind, "name": name, "matched": None, "spans": [], "count": 0}
            for term in [name, *(entry.get("aliases") or [])]:
                t = str(term)
                if len(t) < MIN_TERM_LEN or t.lower() in stop:
                    continue
                ft = first_token(t)
                if not ft or ft not in doc_tokens or t.lower() not in lower:
                    continue
                for m in _term_regex(t).finditer(src):
                    start, end = m.start(), m.end()
                    span = src[start:end]
                    if not span.strip():
                        continue
                    rec["count"] += 1
                    if rec["matched"] is None:
                        rec["matched"] = span
                    if len(rec["spans"]) < MAX_SPANS:
                        rec["spans"].append({"source_span": span, "start": start, "end": end})
            if rec["count"] > 0:
                results[f"{kind} {name}"] = rec
    return sorted(results.values(), key=lambda e: (e["kind"], e["name"]))


# ---------------------------------------------------------------------------
# Composite (theia extractLoop deterministic half)
# ---------------------------------------------------------------------------

def extract_all(text, gazetteer: dict | None = None, stoplist=None) -> dict:
    """Run every deterministic extractor. Uses the vendored gazetteer by default."""
    gaz = load_gazetteer() if gazetteer is None else gazetteer
    stop = load_stoplist() if stoplist is None else stoplist
    iocs = extract_iocs(text)
    attack_ids = extract_attack_ids(text, gaz.get("techniques") or {})
    flat = detect_entities(text, gaz, stop)
    entities = {
        "actors": [e for e in flat if e["kind"] == "actor"],
        "tools": [e for e in flat if e["kind"] == "tool"],
        "malware": [e for e in flat if e["kind"] == "malware"],
    }
    return {
        "iocs": iocs,
        "attack_ids": attack_ids,
        "entities": entities,
        "counts": {"iocs": len(iocs), "attack_ids": len(attack_ids),
                   "actors": len(entities["actors"]), "tools": len(entities["tools"]),
                   "malware": len(entities["malware"])},
    }


def slice_violations(text: str, result: dict) -> list:
    """theia harness section 2.0 check: every span must equal text[start:end] and be non-empty."""
    bad = []

    def chk(o, label):
        if text[o["start"]:o["end"]] != o["source_span"] or not o["source_span"].strip():
            bad.append(label)

    for i in result.get("iocs", []):
        chk(i, f"ioc:{i['value']}")
    for a in result.get("attack_ids", []):
        chk(a, f"attack:{a['id']}")
    for group in (result.get("entities") or {}).values():
        for e in group:
            for s in e["spans"]:
                chk(s, f"entity:{e['name']}")
    return bad
