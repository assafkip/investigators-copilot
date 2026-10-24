"""Port of kipi tests (test_admission.py + test_extractor_pivots.py) for lib/entity_extract.py.

The pivot-template test is not ported (it exercises kipi's analyze module, not the
extractor). Added: offset invariant + org_candidate + escape-offset preservation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))
from entity_extract import extract_all, extract_dicts, is_admissible  # noqa: E402

CASES = [
    # --- JUNK that must be rejected (each a real past recurrence) ---
    ("phone", "164736471", False, "bare affiliate/tracking id typed phone"),
    ("phone", "1042168184", False, "an IP with the dots stripped, typed phone"),
    ("phone", "20260419", False, "a date typed phone"),
    ("phone", "000000000", False, "all-zeros placeholder phone"),
    ("phone", "165309999", False, "bare 9-digit id typed phone"),
    ("domain", "iana.org", False, "registry boilerplate"),
    ("domain", "whois.verisign-grs.com", False, "WHOIS server boilerplate"),
    ("subdomain", "whois.globaldomaingroup.com", False, "WHOIS server boilerplate"),
    ("domain", "krebsonsecurity.com", False, "journalist / reporting outlet"),
    ("url", "https://krebsonsecurity.com/2025/07/scammers-unleash-flood/", False, "reporting URL"),
    ("domain", "phishdestroy.io", False, "phishing-takedown feed, not target infra"),
    ("domain", "phishtank.com", False, "phishing blocklist, not target infra"),
    ("subdomain", "urlhaus.abuse.ch", False, "abuse.ch blocklist feed"),
    ("url", "https://urlscan.io/result/abc-123/", False, "scanner result page, not target infra"),
    ("domain", "verisign-grs.com", False, "registrar/registry boilerplate"),
    ("domain", "lynn.ns.cloudflare.com", False, "shared Cloudflare nameserver"),
    ("domain", "ns-1234.awsdns-56.org", False, "shared AWS nameserver"),
    ("domain", "globaldomaingroup.com", False, "registrar boilerplate"),
    ("person", "20260610", False, "date masquerading as a person"),
    ("domain", "x", False, "too short"),
    ("handle", "", False, "empty"),
    ("other", "@media (max-width: 600px)", False, "CSS fragment"),
    ("phone", "registrar privacy 12345", False, "mis-parse label"),
    # trump-demo live dig, 2026-06-11: regex over JSON-escaped tool output + whois boilerplate
    ("url", "https://trumpstake.us/global/fbq.js\\nconfidence: high", False,
     "literal \\n escape glued the confidence line onto the URL"),
    ("url", "https://trumpfundus.com/'", False, "trailing quote from a quoted string"),
    ("domain", "isnic.is", False, "ccTLD registry (the .is NIC) -- whois boilerplate"),
    ("email", "iana-contact@isnic.is", False, "the registry's own whois contact email"),
    ("phone", "+3545782030", False, "the registry's own whois contact phone (ISNIC)"),
    ("phone", "+1703925", False, "truncated id wearing a '+1' -- NANP needs 11 digits"),
    ("url", "https://crt.sh/?q=trumpfundus.com", False, "the agent's own cert-lookup tool"),
    ("domain", "ip-api.com", False, "the agent's own IP-lookup tool"),
    ("domain", "errors.pydantic.dev", False, "traceback artifact, not an entity"),
    ("url", "https://thereallo.dev/blog/mammoth", False, "kit writeup -- a source, not infra"),
    # --- KNOWN-GOOD that must always pass (never over-reject real intel) ---
    ("ip", "9.9.9.9", True, "real resolver IP -- dot-stripping must not read it as 9999"),
    ("ip", "1.1.1.1", True, "real resolver IP -- not an all-same-digit placeholder"),
    ("ip", "8.8.8.8", True, "real resolver IP"),
    ("phone", "+14805058800", True, "real E.164 phone"),
    ("phone", "(480) 505-8800", True, "real formatted phone"),
    ("domain", "trumpfundus.com", True, "real target domain"),
    ("domain", "alertoscan.io", True, "real target domain"),
    ("url", "https://trumpfundus.com/register", True, "real target URL"),
    ("domain", "scammer-twitter-clone.com", True, "a scammer's own domain"),
    ("handle", "@scam_promoter", True, "a real handle"),
    ("ip", "104.21.68.184", True, "a real IP (CDN is an edge concern, not node admission)"),
    ("affiliate_id", "164736471", True, "the SAME number is fine when typed as affiliate_id"),
    ("wallet", "0x1234567890abcdef1234567890abcdef12345678", True, "a real wallet"),
    ("email", "scam@trumpfundus.com", True, "a real email"),
    ("phone", "+17035551234", True, "real 11-digit NANP phone"),
    ("phone", "+3545781000", True, "a real Icelandic number that is NOT the registry's"),
    ("domain", "gambler-partners.is", True, "a real .is target domain (registry gated, TLD not)"),
]


def _types(text):
    out = {}
    for e in extract_all(text):
        out.setdefault(e.entity_type, []).append(e.canonical)
    return out


def _check(label, cond):
    assert cond, f"FAIL: {label}"
    print(f"  ok  {label}")


CRYPTO = """
GA tag G-ABCD1234XY and GTM-ABC123 and UA-12345678-1 are shared across the cluster.
TRXDrop hardcodes WalletConnect projectId fbf5b42d9006502246e73447f5d50e33.
Solana receiving address 7EYnhQoR9YM3N7UoaKRoA44Uy8JeaZV3qbVbS1NXW4 listed.
XRP wallet with destinationTag rEb8TK3gBgk5auZkwc6sHnwrGVJH8DuaLh.
TRON address TJRyWwFs9wTFGZg3JbrVriFbNfCug5tDeC drains funds.
EVM wallet 0x1111111111111111111111111111111111111111 receives.
Built on Nuxt with connect-wallet and ethers.js.
"""

# Same shapes, but NO chain/service keywords anywhere -> gates must suppress them.
PLAIN = """
The committee reviewed document 7EYnhQoR9YM3N7UoaKRoA44Uy8JeaZV3qbVbS1NXW4 yesterday.
A reference code fbf5b42d9006502246e73447f5d50e33 was noted in the minutes.
Nothing technical was discussed at all during the quarterly meeting.
"""


def test_new_fingerprint_types():
    t = _types(CRYPTO)
    _check("GA/GTM/UA tracking tags extracted",
           {"g-abcd1234xy", "gtm-abc123", "ua-12345678-1"} <= set(t.get("tracking_tag", [])))
    _check("walletconnect_id extracted (gated on projectId)",
           "fbf5b42d9006502246e73447f5d50e33" in t.get("walletconnect_id", []))
    wallets = set(t.get("crypto_wallet", []))
    _check("Solana address extracted", "7EYnhQoR9YM3N7UoaKRoA44Uy8JeaZV3qbVbS1NXW4" in wallets)
    _check("XRP address extracted", "rEb8TK3gBgk5auZkwc6sHnwrGVJH8DuaLh" in wallets)
    _check("TRON address extracted", "TJRyWwFs9wTFGZg3JbrVriFbNfCug5tDeC" in wallets)
    _check("EVM address extracted", "0x1111111111111111111111111111111111111111" in wallets)
    _check("tech_stack fingerprints extracted",
           {"nuxt", "connect-wallet", "ethers.js"} <= set(t.get("tech_stack", [])))


def test_gating_suppresses_false_positives():
    t = _types(PLAIN)
    _check("no base58 wallet false-positive without chain keywords",
           "7EYnhQoR9YM3N7UoaKRoA44Uy8JeaZV3qbVbS1NXW4" not in t.get("crypto_wallet", []))
    _check("32-hex falls to md5 (not walletconnect) without WC keywords",
           "fbf5b42d9006502246e73447f5d50e33" not in t.get("walletconnect_id", []) and
           "fbf5b42d9006502246e73447f5d50e33" in t.get("hash_md5", []))


SAAS_WHOIS = """A live-chat widget (JivoSite, account ID Y0q86ZSjlX) was added to the page.
Registrar: PDR Ltd. d/b/a PublicDomainRegistry.com
Name Server: alan.ns.cloudflare.com
"""


def test_saas_and_whois():
    t = _types(SAAS_WHOIS)
    _check("SaaS service-account id extracted", "Y0q86ZSjlX" in t.get("saas_service_account", []))
    _check("WHOIS registrar extracted",
           any("pdr ltd" in r for r in t.get("registrar", [])))
    _check("WHOIS nameserver extracted", "alan.ns.cloudflare.com" in t.get("nameserver", []))


def test_phone_rejects_bare_numeric_runs():
    # Bare digit runs (counters, transaction IDs, timestamps) are NOT phones --
    # they used to flood the graph as junk nodes. A real phone carries a '+'
    # or formatting separators.
    t = _types("call +1 (415) 555-0199 or 020 7946 0958. ref 000000000 "
               "txid 276516686 counter 019013683.")
    phones = t.get("phone", [])
    _check("junk numeric runs are not phones",
           not any(p in ("000000000", "276516686", "019013683") for p in phones))
    _check("real formatted phone still extracted",
           any("4155550199" in p for p in phones))
    # A bare digit run IS a phone when a phone/tel label sits right before it
    # (structured-scrape "Phone: 4155550199" shape) -- must not be dropped.
    labeled = _types("Phone: 4155550199  tel no: 02079460958 "
                     "mobile phone number: 13105550147")
    lp = labeled.get("phone", [])
    _check("label-prefixed bare phones kept", "4155550199" in lp and "13105550147" in lp)
    # ...but a label-suffix of an unrelated word must NOT count (Hotel/recall).
    decoy = _types("Hotel: 000000001  recall: 000000002")
    _check("word-suffix decoy labels rejected", not decoy.get("phone"))
    # IPv4 + dates are dot/dash-separated digit runs -- PHONE_RE captures them whole and
    # the separator-accept used to pass them, then the canonicalizer stripped the
    # separators leaving bare-digit junk (104.21.68.184 -> 1042168184; 2026-04-19 ->
    # 20260419). They must NEVER be phones.
    infra = _types("resolves to 104.21.68.184 and 172.67.197.209, first seen 2026-04-19, "
                   "dedicated 38.46.220.132")
    ip_phones = infra.get("phone", [])
    _check("an IPv4 is not a phone", not ip_phones)
    _check("a date is not a phone", "20260419" not in ip_phones)
    # IPv4 still extracted as the IP it is (not lost -- just typed correctly).
    _check("IPv4 still extracted as ip", "104.21.68.184" in infra.get("ip", []))


def test_base58_wallet_case_preserved_no_forged_twin():
    # base58 (1.../3...) is case-sensitive -- lowercasing forges an invalid
    # duplicate. EVM/bech32 are case-insensitive and still lowercase (dedupe).
    t = _types("btc 1muskDgU9ZVSYBbyp52iwp5ksugscMfYv "
               "eth 0xAbCdEf0123456789aBcDeF0123456789AbCdEf01 bc1qqu75xepdcu377lr")
    wallets = t.get("crypto_wallet", [])
    _check("base58 case preserved", "1muskDgU9ZVSYBbyp52iwp5ksugscMfYv" in wallets)
    _check("no lowercased base58 twin", "1muskdgu9zvsybbyp52iwp5ksugscmfyv" not in wallets)
    _check("EVM lowercased", "0xabcdef0123456789abcdef0123456789abcdef01" in wallets)
    _check("bech32 (already lowercase) kept", "bc1qqu75xepdcu377lr" in wallets)


def test_uppercase_bech32_matched_and_lowercased():
    # bech32 is valid all-UPPERCASE too (BIP-173 -- QR codes render it that way).
    # Match it and canonicalize to lowercase like the rest of the family.
    # MIXED case is invalid bech32 and must stay rejected.
    t = _types("btc BC1QQU75XEPDCU377LR sent funds")
    wallets = t.get("crypto_wallet", [])
    _check("uppercase bech32 matched + lowercased", "bc1qqu75xepdcu377lr" in wallets)
    mixed = _types("ref Bc1Qqu75xePdcu377lr")
    _check("mixed-case bech32 rejected", not mixed.get("crypto_wallet"))


def test_admission_contract_table():
    failures = [f"{et}:{v!r} expected {want} ({label})" for et, v, want, label in CASES
                if is_admissible(et, v)[0] != want]
    assert not failures, "\n".join(failures)


def test_offsets_are_exact_and_escapes_preserve_them():
    text = 'blob \\nContact: Dr. Jane Roe at jane@target-co.com, +1 (415) 555-0199, ' \
           'Acme Widgets Inc. paid 0x1111111111111111111111111111111111111111 via @payer_x'
    for d in extract_dicts(text):
        assert text[d["start"]:d["end"]] == d["surface"], d
    types = {d["entity_type"] for d in extract_dicts(text)}
    assert {"email", "phone", "crypto_wallet", "handle", "person", "org_candidate"} <= types
    orgs = [d["canonical"] for d in extract_dicts(text) if d["entity_type"] == "org_candidate"]
    assert "Acme Widgets Inc." in orgs
