"""Port of theia app/lib/*.test.mjs + scripts/harness.mjs invariants to pytest.

No network. Exercises lib/ioc_extract.py, the Python port of theia's deterministic
extractors. Every case below mirrors a theia node:test case one-for-one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))
import ioc_extract as ie  # noqa: E402


def assert_slice_equality(text, items):
    for it in items:
        assert text[it["start"]:it["end"]] == it["source_span"], it["value"]
        assert it["source_span"].strip(), it["value"]


def only(items, ft):
    return [i for i in items if i["field_type"] == ft]


def vals(items, ft):
    return [i["value"] for i in only(items, ft)]


# ---------------- iocExtract.test.mjs ----------------

def test_ip_clean_and_defanged():
    text = "beacon to 8.8.8.8 and 10[.]0[.]0[.]1 seen"
    items = ie.extract_iocs(text)
    assert vals(items, "ip") == ["10.0.0.1", "8.8.8.8"]
    d = next(i for i in only(items, "ip") if i["value"] == "10.0.0.1")
    assert d["source_span"] == "10[.]0[.]0[.]1"
    assert_slice_equality(text, items)


def test_ip_octet_and_version_rejection():
    assert vals(ie.extract_iocs("build v1.2.3.4 shipped"), "ip") == []
    assert vals(ie.extract_iocs("bogus 999.1.1.1 here"), "ip") == []
    assert vals(ie.extract_iocs("version 1.2.3.4"), "ip") == []
    assert vals(ie.extract_iocs("version: 1.2.3.4"), "ip") == []
    assert vals(ie.extract_iocs("ver. 1.2.3.4"), "ip") == []
    assert vals(ie.extract_iocs("callback 8.8.4.4 seen"), "ip") == ["8.8.4.4"]


def test_url_list_does_not_collapse():
    items = ie.extract_iocs("iocs: https://a.com/x,https://b.com/y;https://c.com/z")
    assert sorted(vals(items, "url")) == ["https://a.com/x", "https://b.com/y", "https://c.com/z"]


def test_domain_clean_and_defanged():
    text = "c2 at evil.com and backup hxxps colon removed evil2[.]net"
    items = ie.extract_iocs(text)
    assert "evil.com" in vals(items, "domain")
    assert "evil2.net" in vals(items, "domain")
    assert_slice_equality(text, items)


def test_domain_onion_and_non_tld():
    items = ie.extract_iocs("market at abcdef.onion not file.zzzznotatld")
    assert "abcdef.onion" in vals(items, "domain")
    assert not any("zzzznotatld" in d for d in vals(items, "domain"))


def test_domain_filename_lookalike():
    assert vals(ie.extract_iocs("dropped invoice.zip and sample.mov to disk"), "domain") == []


def test_url_suppresses_inner_domain():
    text = "visit (https://evil.com/a/b). also hxxps://bad[.]net/x"
    items = ie.extract_iocs(text)
    assert sorted(vals(items, "url")) == ["https://bad.net/x", "https://evil.com/a/b"]
    assert "evil.com" not in vals(items, "domain")
    assert_slice_equality(text, items)


def test_url_trailing_punctuation_trimmed():
    u = only(ie.extract_iocs("ref https://evil.com/path, then done"), "url")[0]
    assert u["value"] == "https://evil.com/path"
    assert u["source_span"] == "https://evil.com/path"


def test_email_clean_and_defanged():
    text = "contact bad@evil.com or phish[at]evil2[.]net now"
    items = ie.extract_iocs(text)
    assert "bad@evil.com" in vals(items, "email")
    assert "phish@evil2.net" in vals(items, "email")
    assert "evil.com" not in vals(items, "domain")
    assert_slice_equality(text, items)


MD5 = "d41d8cd98f00b204e9800998ecf8427e"
SHA1 = "da39a3ee5e6b4b0d3255bfef95601890afd80709"
SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_hash_lengths():
    items = ie.extract_iocs(f"hashes {MD5} {SHA1} {SHA256}")
    assert sorted(vals(items, "file_hash")) == sorted([MD5, SHA1, SHA256])


def test_hash_overlength_run():
    assert vals(ie.extract_iocs(f"blob {'a' * 65} end"), "file_hash") == []


def test_hash_wrapped_reassembled():
    wrapped = f"hash:\n{SHA256[:40]}\n    {SHA256[40:]}\nend"
    items = ie.extract_iocs(wrapped)
    h = next(i for i in only(items, "file_hash") if i["value"] == SHA256)
    assert wrapped[h["start"]:h["end"]] == h["source_span"]
    assert "\n" in h["source_span"]


def test_two_md5s_not_joined():
    b = "5d41402abc4b2a76b9719d911017c592"
    items = ie.extract_iocs(f"known-good:\n{MD5}\n{b}\n")
    assert sorted(vals(items, "file_hash")) == sorted([MD5, b])


def test_guid_not_hash():
    assert vals(ie.extract_iocs("id 550e8400-e29b-41d4-a716-446655440000 here"), "file_hash") == []


def test_cve_uppercased():
    assert vals(ie.extract_iocs("exploits cve-2021-44228 aka log4shell"), "cve") == ["CVE-2021-44228"]


def test_dedupe_counts():
    text = "8.8.8.8 then again 8.8.8.8 twice"
    ip = only(ie.extract_iocs(text), "ip")
    assert len(ip) == 1 and ip[0]["count"] == 2 and ip[0]["start"] == text.index("8.8.8.8")


def test_stable_sort():
    order = [i["field_type"] for i in ie.extract_iocs("z.com a.com 1.1.1.1 CVE-2020-0001")]
    assert order == sorted(order)


def test_refang_defang():
    assert ie.refang("hxxps://evil[.]com") == "https://evil.com"
    assert ie.refang("a[dot]b[dot]c") == "a.b.c"
    assert ie.refang("https://evil.com") == "https://evil.com"
    assert ie.defang("https://evil.com") == "hxxps://evil[.]com"


def test_empty_input():
    assert ie.extract_iocs("") == []
    assert ie.extract_iocs(None) == []
    assert ie.extract_iocs("just words, no indicators.") == []


# ---------------- context.test.mjs ----------------

def test_context_sentence():
    text = ("Initial access was gained via phishing. Black Basta affiliates have used "
            "170.130.165[.]73 for command and control. Other infrastructure was rotated.")
    ind = "170.130.165[.]73"
    s = text.index(ind)
    c = ie.sentence_context(text, s, s + len(ind))
    assert text[c["context_start"]:c["context_end"]] == c["context"]
    assert c["context"] == "Black Basta affiliates have used 170.130.165[.]73 for command and control."


def test_context_bare_row_no_fabrication():
    text = "Indicators of compromise:\nevilphishing[.]com\nlogin[.]com\n"
    ind = "evilphishing[.]com"
    s = text.index(ind)
    assert ie.sentence_context(text, s, s + len(ind))["context"] == ind


def test_context_cap():
    text = "word " * 200 + "8.8.8.8" + " more" * 200
    s = text.index("8.8.8.8")
    c = ie.sentence_context(text, s, s + 7, cap=120)
    assert text[c["context_start"]:c["context_end"]] == c["context"]
    assert "8.8.8.8" in c["context"] and len(c["context"]) <= 120


def test_context_table_row():
    text = "45.11.181[.]44\tC2 server\tBlack Basta\n66.42.118[.]54\tC2 server\n"
    s = text.index("45.11.181[.]44")
    assert ie.sentence_context(text, s, s + 14)["context"] == "45.11.181[.]44\tC2 server\tBlack Basta"


# ---------------- section.test.mjs ----------------

def test_section_benign():
    text = "Deconfliction (known-good):\nsandbox 203.0.113.9 used in testing"
    r = ie.section_hint(text, text.index("203.0.113.9"))
    assert r == {"section_hint": "benign", "section_heading": "Deconfliction (known-good):"}


def test_section_threat_wins():
    text = "Benign test infrastructure:\n\nIndicators of Compromise\nevilhost 198.51.100.7 c2"
    assert ie.section_hint(text, text.index("198.51.100.7")) is None


def test_section_no_heading_and_prose():
    t1 = "the beacon reached 198.51.100.7 during the intrusion"
    assert ie.section_hint(t1, t1.index("198.51.100.7")) is None
    t2 = "This indicator is not obviously malicious but was excluded elsewhere in review.\n1.2.3.4"
    assert ie.section_hint(t2, t2.index("1.2.3.4")) is None


def test_section_in_extract_iocs():
    text = f"Known-good hashes (deconfliction):\n{MD5}\n\nMalicious file hashes\n{SHA1}"
    items = ie.extract_iocs(text)
    benign = next(i for i in items if i["value"] == MD5)
    bad = next(i for i in items if i["value"] == SHA1)
    assert benign["section_hint"] == "benign"
    assert benign["section_heading"] == "Known-good hashes (deconfliction):"
    assert "section_hint" not in bad
    assert_slice_equality(text, items)
    ip = ie.extract_iocs("plain beacon to 8.8.8.8 seen")[0]
    assert "section_hint" not in ip and "section_heading" not in ip


# ---------------- attackIds.test.mjs ----------------

MAP = {"T1566": "Phishing", "T1566.002": "Spearphishing Link",
       "T1078": "Valid Accounts", "T1078.004": "Cloud Accounts"}


def test_attack_ids():
    text = "Initial access via T1566; then T1078.004 for persistence."
    out = ie.extract_attack_ids(text, MAP)
    assert [o["id"] for o in out] == ["T1078.004", "T1566"]
    assert out[1]["name"] == "Phishing" and out[0]["name"] == "Cloud Accounts"
    for o in out:
        assert text[o["start"]:o["end"]] == o["source_span"] and o["in_attack"]


def test_attack_unknown_and_fake_sub():
    o = ie.extract_attack_ids("row id T9999 in a table", MAP)[0]
    assert o["in_attack"] is False and o["name"] is None
    o = ie.extract_attack_ids("bogus T1566.999 in a table", MAP)[0]
    assert o["id"] == "T1566.999" and o["in_attack"] is False
    o = ie.extract_attack_ids("saw T1566.002 in logs", MAP)[0]
    assert o["in_attack"] and o["name"] == "Spearphishing Link"


def test_attack_dedupe_and_empty():
    out = ie.extract_attack_ids("T1566 and again T1566 plus T1078", MAP)
    assert [o["id"] for o in out] == ["T1078", "T1566"] and out[1]["count"] == 2
    assert ie.extract_attack_ids("phishing led to valid account abuse", MAP) == []
    assert ie.extract_attack_ids("", MAP) == []
    assert ie.extract_attack_ids("T1566", {}) == [{
        "id": "T1566", "name": None, "in_attack": False, "source_span": "T1566",
        "start": 0, "end": 5, "count": 1, "context": "T1566", "context_start": 0,
        "context_end": 5}]


# ---------------- entities.test.mjs ----------------

GAZ = {
    "actors": [{"name": "APT29", "aliases": ["Cozy Bear", "Nobelium"]},
               {"name": "Scattered Spider", "aliases": ["Octo Tempest"]},
               {"name": "Turla", "aliases": ["Snake"]}],
    "tools": [{"name": "Cobalt Strike", "aliases": ["CS"]}],
    "malware": [{"name": "Emotet", "aliases": ["Geodo"]}],
}
STOP = ["cat", "cs", "menu"]


def test_entities_alias_resolution():
    text = "Intrusion by APT29. Also tracked as Cozy Bear in prior reports."
    apt = next(e for e in ie.detect_entities(text, GAZ, STOP) if e["name"] == "APT29")
    assert apt["kind"] == "actor" and apt["count"] == 2
    for s in apt["spans"]:
        assert text[s["start"]:s["end"]] == s["source_span"]


def test_entities_multiword_and_guards():
    out = ie.detect_entities("Operators deployed Cobalt Strike and Emotet.", GAZ, STOP)
    assert any(e["name"] == "Cobalt Strike" and e["kind"] == "tool" for e in out)
    assert any(e["name"] == "Emotet" and e["kind"] == "malware" for e in out)
    assert ie.detect_entities("The CS team met about menu items.", GAZ, STOP) == []
    short = {"actors": [{"name": "XYZ", "aliases": []}], "tools": [], "malware": []}
    assert ie.detect_entities("XYZ appeared", short, []) == []
    assert ie.detect_entities("The word Turlaish and reTurla are not actors.", GAZ, STOP) == []


def test_entities_boundaries_caps_sort_case():
    t = next(e for e in ie.detect_entities("(Turla) and 'Snake' operated.", GAZ, STOP)
             if e["name"] == "Turla")
    assert t["count"] == 2
    apt = ie.detect_entities("APT29 " * 8, GAZ, STOP)[0]
    assert apt["count"] == 8 and len(apt["spans"]) == 5
    keys = [f"{e['kind']} {e['name']}" for e in
            ie.detect_entities("Emotet Cobalt Strike APT29 Turla", GAZ, STOP)]
    assert keys == sorted(keys)
    apt = next(e for e in ie.detect_entities("apt29 and NOBELIUM active", GAZ, STOP)
               if e["name"] == "APT29")
    assert {s["source_span"] for s in apt["spans"]} == {"apt29", "NOBELIUM"}
    assert ie.detect_entities("", GAZ, STOP) == []


# ---------------- grounding.test.mjs ----------------

def test_grounding_normalization():
    assert ie.span_grounded("devicelogin.microsoft.com",
                            ie.normalize("The actor used devicelogin.microsoft.com to phish."))
    assert not ie.span_grounded("invoice.pdf", ie.normalize("Payload dropped as Invoice.pdf"))
    assert ie.span_grounded("credential harvesting then exfiltration",
                            ie.normalize("credential   harvesting\tthen\nexfiltration"))
    assert ie.span_grounded("api.tele gram.org", ie.normalize("api.tele\u200bgram.org"))
    assert ie.span_grounded("uses command-and-control over HTTPS",
                            ie.normalize("uses command- and-control over HTTPS"))
    assert ie.span_grounded("pre- and post-exploitation", ie.normalize("pre- and post-exploitation"))
    assert ie.span_grounded("the actor's \"device code\" flow - abused",
                            ie.normalize("the actor\u2019s \u201cdevice code\u201d flow \u2014 abused"))
    assert ie.span_grounded("", ie.normalize("anything"))
    assert ie.span_grounded("   ", ie.normalize("anything"))


def test_ground_extraction_drops_fabricated():
    raw = ("Storm-2372 sent phishing links resolving to devicelogin.microsoft.com. "
           "The C2 used login.microsoftonline.com token grants.")
    extraction = {
        "behavioral_patterns": [{"sequence": "x", "observables": [
            {"field_type": "domain", "pattern": "devicelogin.microsoft.com",
             "source_span": "resolving to devicelogin.microsoft.com"},
            {"field_type": "ip", "pattern": "185.220.101.33",
             "source_span": "beaconed to 185.220.101.33 every 60s"}]}],
        "tools": ["curl"], "malware": [],
        "unbound_iocs": [{"field_type": "domain", "pattern": "login.microsoftonline.com",
                          "source_span": "used login.microsoftonline.com token grants"}],
    }
    g = ie.ground_extraction(extraction, raw)
    assert len(g["behavioral_patterns"][0]["observables"]) == 1
    assert len(g["unbound_iocs"]) == 1
    assert [d["pattern"] for d in g["_dropped_ungrounded"]] == ["185.220.101.33"]


# ---------------- harness.mjs: section 2.0 invariant on the vendored gazetteer ----------------

def test_harness_invariant_with_vendored_data():
    text = ("APT28 (Fancy Bear) used Mimikatz and Cobalt Strike against targets. "
            "C2: hxxps://update-check[.]com/gate.php and 45.11.181[.]44 per T1566.001.\n"
            "Hash: " + SHA256 + "\nContact: ops[at]bad-domain[.]xyz \u2014 2026-01-02.")
    r = ie.extract_all(text)
    assert ie.slice_violations(text, r) == []
    assert r["counts"]["iocs"] >= 4
    assert any(a["id"] == "T1566.001" and a["in_attack"] for a in r["attack_ids"])
    names = {e["name"] for g in r["entities"].values() for e in g}
    assert "Mimikatz" in names or "Cobalt Strike" in names
