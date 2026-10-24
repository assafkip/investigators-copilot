"""entity_extract.py -- standalone regex entity extraction (emails, handles, phones,
wallets, people / org candidates) with exact source offsets. No DB, no LLM.

Port of kipi `investigations/ingest/extractor.py` (extract_all), `admission.py`
(is_admissible, the single entity-admission contract) and `noise.py` (noise domain /
phone rules). Differences from kipi, all deliberate:
  - No `investigations.*` imports; admission + noise are inlined below.
  - Every item carries `start`/`end` (Python str indices) with
    `text[start:end] == surface`, so a caller can prove where it came from.
  - kipi decodes literal JSON escapes (`\\n`, `\\r`, `\\t`) to ONE space, which
    shifts offsets; here each 2-char escape becomes TWO spaces so offsets into
    the original file stay exact.
  - Adds `org_candidate` (proper-name run ending in a legal-entity suffix). kipi
    has no org regex; this is a candidate list for analyst review, never a fact.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

# --------------------------------------------------------------------------
# noise.py (kipi)
# --------------------------------------------------------------------------

_BOILERPLATE_DOMAINS = {
    "iana.org", "icann.org", "verisign-grs.com", "verisign.com", "pir.org",
    "publicinterestregistry.org", "internic.net", "afilias.net", "identitydigital.com",
    "centralnic.com", "markmonitor.com", "cscglobal.com", "csc.com", "registry.google",
    "gandi.net", "namecheap.com", "godaddy.com", "publicdomainregistry.com",
    "tucows.com", "enom.com", "key-systems.net", "namesilo.com", "dynadot.com",
    "isnic.is", "globaldomaingroup.com", "name-services.com", "registrar-servers.com",
}
_LOOKUP_TOOL_DOMAINS = {"crt.sh", "ip-api.com", "pydantic.dev"}
_REFERENCE_DOMAINS = {
    "krebsonsecurity.com", "bleepingcomputer.com", "thehackernews.com", "therecord.media",
    "scamadviser.com", "scamwatch.gov.au", "ic3.gov", "ftc.gov", "securityweek.com",
    "darkreading.com", "welivesecurity.com", "malwarebytes.com", "trendmicro.com",
    "kaspersky.com", "sophos.com", "wikipedia.org",
    "phishdestroy.io", "phishtank.com", "phishtank.org", "openphish.com",
    "abuse.ch", "urlhaus.abuse.ch", "threatfox.abuse.ch", "urlscan.io",
    "virustotal.com", "spamhaus.org", "thereallo.dev", "fullcoll.edu",
}
_NOISE_DOMAINS = _BOILERPLATE_DOMAINS | _REFERENCE_DOMAINS | _LOOKUP_TOOL_DOMAINS
_BOILERPLATE_PHONE_DIGITS = {"3545782030"}
_NAMESERVER_MARKERS = (
    "ns.cloudflare.com", "awsdns", "nsone.net", "dnsmadeeasy.com", "googledomains.com",
    "azure-dns.", "domaincontrol.com", "registrar-servers.com", "name-services.com",
    "dns.he.net", "ns.namecheap.com",
)


def _host(value: str) -> str:
    s = (value or "").strip().lower()
    s = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", s)
    s = s.split("/")[0].split("?")[0].split("#")[0]
    s = s.split("@")[-1]
    s = s.split(":")[0]
    s = s.strip(".")
    return re.sub(r"^www\.", "", s)


def _registrable(host: str) -> str:
    parts = [p for p in host.split(".") if p]
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def is_noise_domain(value: str) -> bool:
    """Registry / WHOIS / lookup-tool / threat-reporting domain: not target infra."""
    host = _host(value)
    if not host:
        return False
    if host.startswith("whois.") or ".whois-servers." in host:
        return True
    if any(m in host for m in _NAMESERVER_MARKERS):
        return True
    return host in _NOISE_DOMAINS or _registrable(host) in _NOISE_DOMAINS


def is_real_phone(value: str) -> bool:
    s = (value or "").strip()
    digits = re.sub(r"[\s().+\-]", "", s)
    if not digits.isdigit() or not (7 <= len(digits) <= 15):
        return False
    if s.startswith("+1") and len(digits) != 11:
        return False
    return s.startswith("+") or bool(re.search(r"[\s().\-]", s))


def is_boilerplate_phone(value: str) -> bool:
    return re.sub(r"[\s().+\-]", "", value or "") in _BOILERPLATE_PHONE_DIGITS


# --------------------------------------------------------------------------
# admission.py (kipi) -- the single entity-admission contract
# --------------------------------------------------------------------------

_CSS_AT_RE = re.compile(
    r"^@(media|import|keyframes|font-face|charset|supports|namespace|page)\b", re.I)
_MISPARSE_PHRASES = (
    "report date", "registrar privacy", "privacy-proxy", "privacy proxy",
    "whois privacy", "mis-parsed", "misparsed", "parser glitch", "ocr artifact",
)
_DOMAINISH = {"domain", "subdomain", "url"}
_OPAQUE_VALUE_TYPES = {"affiliate_id", "wallet", "crypto_wallet", "hash_sha256", "hash_md5",
                       "asn", "indicator", "fingerprint"}
_DOTTED_QUAD_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def _is_dotted_quad(value: str) -> bool:
    if not _DOTTED_QUAD_RE.match(value):
        return False
    return all(int(octet) <= 255 for octet in value.split("."))


def _is_universal_junk(value: str) -> bool:
    low = value.lower()
    if _CSS_AT_RE.match(value):
        return True
    if any(ch in value for ch in "\n\r\t") or re.search(r"\\[nrt]", value):
        return True
    if any(p in low for p in _MISPARSE_PHRASES):
        return True
    if _is_dotted_quad(value):
        return False
    digits = re.sub(r"[\s().+\-]", "", value)
    if digits.isdigit():
        if len(set(digits)) <= 1:
            return True
        if len(digits) == 8:
            y, mo, d = int(digits[:4]), int(digits[4:6]), int(digits[6:8])
            if 2000 <= y <= 2099 and 1 <= mo <= 12 and 1 <= d <= 31:
                return True
    return False


def is_admissible(entity_type, value, *, phone_prevalidated: bool = False) -> tuple:
    """(True, "") if a real entity of this type; (False, reason) if noise / junk."""
    et = (entity_type or "").strip().lower()
    v = (value or "").strip()
    if not v:
        return False, "empty value"
    if len(v) <= 2:
        return False, "too short to be a real entity"
    if et not in _OPAQUE_VALUE_TYPES and _is_universal_junk(v):
        return False, "mis-parsed / placeholder / date -- not an entity"
    if et == "phone" and is_boilerplate_phone(v):
        return False, "a registry's own whois contact number -- boilerplate"
    if et == "phone" and not phone_prevalidated and not is_real_phone(v):
        return False, "not a phone number -- a bare id / tracking number"
    if et in _DOMAINISH and v[-1] in "'\"":
        return False, "trailing quote -- a quoted-string fragment"
    if et in _DOMAINISH and is_noise_domain(v):
        return False, "registry / WHOIS / reference boilerplate -- not target infrastructure"
    if et == "email" and is_noise_domain(v):
        return False, "a registry / reference domain's contact address -- whois boilerplate"
    return True, ""


# --------------------------------------------------------------------------
# extractor.py (kipi)
# --------------------------------------------------------------------------

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
URL_RE = re.compile(r"https?://[^\s<>\")'\\]+")
_BARE_URL_RE = re.compile(r"^https?://[^/]+/?$")
HANDLE_RE = re.compile(r"(?<![\w@])@[A-Za-z0-9_]{2,32}\b")
TELEGRAM_RE = re.compile(r"\b(?:t\.me|telegram\.me)/(?:joinchat/)?([A-Za-z0-9_-]{3,})",
                         re.IGNORECASE)
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")
MD5_RE = re.compile(r"\b[a-fA-F0-9]{32}\b")
IPV4_RE = re.compile(
    r"\b(?:25[0-5]|2[0-4]\d|[01]?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|[01]?\d?\d)){3}\b")
WALLET_RE = re.compile(
    r"\b(?:0x[a-fA-F0-9]{40}|bc1[ac-hj-np-z02-9]{6,87}|BC1[AC-HJ-NP-Z02-9]{6,87}|"
    r"[13][a-km-zA-HJ-NP-Z1-9]{25,34})\b")
_TLD_LEGACY = "com net org info biz name pro mobi tel asia cat jobs aero coop museum"
_TLD_GTLD = ("io ai co me tv cc ws app dev cloud tech space world life today news blog "
             "email link click media network agency solutions services group team plus "
             "run now one zone fyi studio photos pics host press website digital center "
             "support online site live shop store work")
_TLD_ABUSE = ("xyz top club icu cyou sbs cfd quest bond beauty hair makeup skin cam wiki "
              "monster buzz lol mom fun vip rest autos boats motorcycles gdn stream "
              "download loan win bid trade date review country kim science party "
              "gq tk ml ga cf pw su")
_TLD_CC = ("us uk ca au nz de fr es it nl be ch at se no fi dk pt pl gr cz hu ro bg ie "
           "ru cn hk tw jp kr sg in br mx ar cl za ng ke eg tr ua by kz ge il sa ae ir "
           "pk id th vn my ph is im li lu ee lv lt si hr sk onion")
DOMAIN_TLDS = frozenset(f"{_TLD_LEGACY} {_TLD_GTLD} {_TLD_ABUSE} {_TLD_CC}".split())
DOMAIN_RE = re.compile(r"\b(?!www\.)(?:[a-zA-Z0-9-]+\.)+([a-zA-Z]{2,24})\b")
PERSON_HINT_RE = re.compile(
    r"\b(?:Mr\.?|Mrs\.?|Ms\.?|Dr\.?|Prof\.?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})")
PROPER_NAME_RE = re.compile(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){1,3})\b")
ORG_RE = re.compile(
    r"\b((?:[A-Z][A-Za-z0-9&'-]+\s+){1,5}(?:Inc|LLC|L\.L\.C|Ltd|Limited|Corp|Corporation|"
    r"Company|Co|GmbH|AG|S\.A|SA|SARL|BV|B\.V|PLC|LLP|LP|Pty|Holdings|Group|Foundation|"
    r"Bank|Trust)\.?)(?![A-Za-z])")
TRACKING_TAG_RE = re.compile(
    r"\b(?:UA-\d{4,10}-\d{1,4}|G-[A-Z0-9]{8,12}|GTM-[A-Z0-9]{6,8}|AW-\d{9,11})\b")
TRON_RE = re.compile(r"\bT[1-9A-HJ-NP-Za-km-z]{33}\b")
WALLETCONNECT_RE = re.compile(r"\b[0-9a-f]{32}\b")
SOL_RE = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")
XRP_RE = re.compile(r"\br[1-9A-HJ-NP-Za-km-z]{24,34}\b")
GATE_WALLETCONNECT = ("walletconnect", "projectid", "project id", "web3modal", "wagmi", "reown")
GATE_SOL = ("solana", "sol ", "phantom", "spl", "$sol", "sol/")
GATE_XRP = ("xrp", "ripple", "xrpl", "destinationtag", "destination tag")
TECH_STACK_RE = re.compile(
    r"\b(__NUXT__|ethers\.js|web3\.js|@?walletconnect|window\.ethereum|connect-wallet|"
    r"next\.js|nuxt)\b", re.IGNORECASE)
SAAS_ACCOUNT_RE = re.compile(
    r"(?i)\b(?:jivosite|jivo|intercom|tawk\.to|tawk|crisp|tidio|livechat|zendesk|drift)\b"
    r"[^\n]{0,25}?\b(?:account[ _]?id|widget[ _]?id|app[ _]?id|site[ _]?id|id)\b[:#\s]*"
    r"([A-Za-z0-9]{8,24})\b")
REGISTRAR_RE = re.compile(r"(?im)^\s*Registrar:\s*(.+?)\s*$")
NAMESERVER_RE = re.compile(r"(?im)^\s*Name\s*Server:\s*(.+?)\s*$")

CONTEXT_WINDOW = 120
GATE_WINDOW = 60
_PHONE_LABEL_RE = re.compile(r"\b(phone|tel|mobile|cell|fax|whatsapp|msisdn)\b", re.IGNORECASE)
_DATE_SHAPE_RE = re.compile(r"\d{4}[-.]\d{1,2}[-.]\d{1,2}|\d{1,2}[-.]\d{1,2}[-.]\d{4}")


@dataclass
class Extracted:
    surface: str
    entity_type: str
    canonical: str
    context: str
    offset: int
    end: int

    def to_dict(self) -> dict:
        d = asdict(self)
        d["start"] = d.pop("offset")
        return d


def _ctx(text: str, start: int, end: int) -> str:
    s = max(0, start - CONTEXT_WINDOW)
    e = min(len(text), end + CONTEXT_WINDOW)
    return text[s:e].replace("\n", " ").strip()


def _emit(text, m, entity_type, canonical_fn):
    surface = m.group(0)
    canonical = canonical_fn(m) if canonical_fn else surface.lower().strip()
    return Extracted(surface=surface, entity_type=entity_type, canonical=canonical,
                     context=_ctx(text, m.start(), m.end()), offset=m.start(), end=m.end())


def _scan(text, pattern, entity_type, canonical_fn=None, claimed=None, predicate=None):
    seen: set = set()
    for m in pattern.finditer(text):
        if m.start() in seen or (claimed is not None and m.start() in claimed):
            continue
        if predicate is not None and not predicate(m):
            continue
        seen.add(m.start())
        if claimed is not None:
            claimed.add(m.start())
        yield _emit(text, m, entity_type, canonical_fn)


def _scan_gated(text, pattern, entity_type, gates, canonical_fn=None, claimed=None):
    low = text.lower()
    seen: set = set()
    for m in pattern.finditer(text):
        if m.start() in seen or (claimed is not None and m.start() in claimed):
            continue
        s = max(0, m.start() - GATE_WINDOW)
        e = min(len(low), m.end() + GATE_WINDOW)
        if not any(g in low[s:e] for g in gates):
            continue
        seen.add(m.start())
        if claimed is not None:
            claimed.add(m.start())
        yield _emit(text, m, entity_type, canonical_fn)


def _looks_like_phone(m) -> bool:
    s = m.group(0)
    stripped = s.strip()
    if IPV4_RE.fullmatch(stripped) or _DATE_SHAPE_RE.fullmatch(stripped):
        return False
    if "+" in s or re.search(r"[\s().-]", s):
        return True
    return bool(_PHONE_LABEL_RE.search(m.string, max(0, m.start() - 24), m.start()))


def _wallet_canonical(m) -> str:
    s = m.group(0)
    low = s.lower()
    return low if (low.startswith("0x") or low.startswith("bc1")) else s


def _decode_escapes_keep_offsets(text: str) -> str:
    """Literal `\\n`/`\\r`/`\\t` escapes -> two spaces (same length, offsets preserved)."""
    return re.sub(r"\\[nrt]", "  ", text or "")


def _identity_scans(text: str) -> list:
    out = list(_scan(text, EMAIL_RE, "email"))
    out += [e for e in _scan(text, URL_RE, "url") if not _BARE_URL_RE.match(e.surface.strip())]
    out += _scan(text, HANDLE_RE, "handle")
    out += _scan(text, TELEGRAM_RE, "telegram_channel",
                 canonical_fn=lambda m: f"t.me/{m.group(1).lower()}")
    out += _scan(text, PHONE_RE, "phone", predicate=_looks_like_phone,
                 canonical_fn=lambda m: re.sub(r"[\s().-]", "", m.group(0)))
    return out


def _crypto_scans(text: str) -> list:
    claimed: set = set()
    out = list(_scan(text, TRACKING_TAG_RE, "tracking_tag", claimed=claimed))
    out += _scan_gated(text, WALLETCONNECT_RE, "walletconnect_id", GATE_WALLETCONNECT,
                       canonical_fn=lambda m: m.group(0).lower(), claimed=claimed)
    out += _scan(text, SHA256_RE, "hash_sha256", canonical_fn=lambda m: m.group(0).lower(),
                 claimed=claimed)
    out += _scan(text, MD5_RE, "hash_md5", canonical_fn=lambda m: m.group(0).lower(),
                 claimed=claimed)
    out += _scan(text, WALLET_RE, "crypto_wallet", claimed=claimed,
                 canonical_fn=_wallet_canonical)
    out += _scan(text, TRON_RE, "crypto_wallet", canonical_fn=lambda m: m.group(0),
                 claimed=claimed)
    out += _scan_gated(text, SOL_RE, "crypto_wallet", GATE_SOL,
                       canonical_fn=lambda m: m.group(0), claimed=claimed)
    out += _scan_gated(text, XRP_RE, "crypto_wallet", GATE_XRP,
                       canonical_fn=lambda m: m.group(0), claimed=claimed)
    return out


def _infra_and_name_scans(text: str) -> list:
    out = list(_scan(text, IPV4_RE, "ip"))
    out += _scan(text, DOMAIN_RE, "domain", canonical_fn=lambda m: m.group(0).lower(),
                 predicate=lambda m: m.group(1).lower() in DOMAIN_TLDS)
    out += _scan(text, TECH_STACK_RE, "tech_stack", canonical_fn=lambda m: m.group(0).lower())
    out += _scan(text, SAAS_ACCOUNT_RE, "saas_service_account", canonical_fn=lambda m: m.group(1))
    out += _scan(text, REGISTRAR_RE, "registrar",
                 canonical_fn=lambda m: m.group(1).strip().lower())
    out += _scan(text, NAMESERVER_RE, "nameserver",
                 canonical_fn=lambda m: m.group(1).strip().lower())
    out += _scan(text, PERSON_HINT_RE, "person", canonical_fn=lambda m: m.group(1))
    out += _scan(text, ORG_RE, "org_candidate", canonical_fn=lambda m: m.group(1).strip())
    out += _scan(text, PROPER_NAME_RE, "person_candidate", canonical_fn=lambda m: m.group(1))
    return out


def extract_all(text: str) -> list:
    """All regex extractors, admission-gated and deduped by (canonical, type).

    The FIRST occurrence's offsets are kept; `count` is not tracked here (kipi parity).
    """
    text = _decode_escapes_keep_offsets(text)
    out = _identity_scans(text) + _crypto_scans(text) + _infra_and_name_scans(text)
    seen: set = set()
    deduped: list = []
    for e in out:
        key = (e.canonical, e.entity_type)
        if key in seen:
            continue
        seen.add(key)
        if not is_admissible(e.entity_type, e.canonical, phone_prevalidated=True)[0]:
            continue
        deduped.append(e)
    return deduped


def extract_dicts(text: str) -> list:
    """extract_all as JSON-ready dicts with `start`/`end` offsets."""
    return [e.to_dict() for e in extract_all(text)]


def infer_relationships(text: str, entities: list, proximity_chars: int = 200) -> list:
    """Naive proximity co-occurrence (kipi parity)."""
    rels = []
    by_offset = sorted(entities, key=lambda e: e.offset)
    for i, a in enumerate(by_offset):
        for b in by_offset[i + 1:]:
            if b.offset - a.offset > proximity_chars:
                break
            if a.canonical != b.canonical:
                rels.append((a, b, "co_mentioned"))
    return rels
