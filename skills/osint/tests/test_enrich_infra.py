"""Infra adapters: RDAP/WHOIS, DoH, SPF/DMARC, ASN, RIPEstat, ipwho.is, reverse IP,
Cert Spotter, Shodan, typosquat. Offline: base.http_json/http_get/run_bin are faked."""
import sys

import pytest
from _enrich_net import doh_answer, install

from enrich import registry
from enrich.base import EnrichmentError, HTTPStatusError, NotConfiguredError

RDAP = {"ldhName": "EXAMPLE.COM", "events": [{"eventAction": "registration", "eventDate": "1995-08-14"}],
        "status": ["active"], "nameservers": [{"ldhName": "A.IANA-SERVERS.NET"}],
        "entities": [{"roles": ["registrar"], "vcardArray": ["vcard", [["fn", {}, "text", "RESERVED-IANA"]]]}],
        "links": [{"rel": "self", "href": "https://rdap.verisign.com/com/v1/domain/EXAMPLE.COM"}]}


def run(slug, query, mode=None):
    return registry.get_adapter(slug).run(query, mode=mode)


def test_rdap_renders_registration_and_is_t1(monkeypatch):
    install(monkeypatch, {"rdap.org/domain/example.com": RDAP})
    [row] = run("rdap", "https://example.com/path")
    assert row.tier == "T1" and "registration: 1995-08-14" in row.summary
    assert "registrar: RESERVED-IANA" in row.summary and row.url.startswith("https://rdap.verisign")


def test_infra_whois_supplements_redacted_registrant_with_raw_whois(monkeypatch):
    install(monkeypatch, {"rdap.org": RDAP, "whois example.com": "Registrant Name: Jane Doe\nfoo: bar\n"},
            bins=("whois",))
    [row] = run("infra", "example.com")
    assert "[RDAP+whois]" in row.summary and "Registrant Name: Jane Doe" in row.summary


def test_infra_whois_failure_raises_not_empty(monkeypatch):
    install(monkeypatch, {"rdap.org": HTTPStatusError("HTTP 500 from rdap.org", 500)})
    with pytest.raises(EnrichmentError):
        run("infra", "example.com", "whois")


def test_infra_dns_uses_doh_without_dig(monkeypatch):
    install(monkeypatch, {"type=AAAA": {"Status": 0}, "type=A": doh_answer(1, "93.184.215.14"), "type=MX": doh_answer(15, "0 ."),
                          "type=": {"Status": 0}})
    [row] = run("infra", "example.com", "dns")
    assert row.raw_json["records"]["A"] == ["93.184.215.14"] and "AAAA" not in row.raw_json["records"]


def test_infra_reverse_via_doh_ptr(monkeypatch):
    calls = install(monkeypatch, {"8.8.8.8.in-addr.arpa": doh_answer(12, "dns.google.")})
    [row] = run("infra", "8.8.8.8")
    assert row.raw_json["ptr"] == ["dns.google"] and "in-addr.arpa" in calls[0][0]


def test_doh_servfail_raises(monkeypatch):
    install(monkeypatch, {"dns.google": {"Status": 2}})
    with pytest.raises(EnrichmentError, match="status 2"):
        run("doh", "example.com", "A")


def test_doh_nxdomain_is_an_answer(monkeypatch):
    install(monkeypatch, {"dns.google": {"Status": 3}})
    [row] = run("doh", "nope.example", "A")
    assert "NXDOMAIN" in row.summary


def test_dns_deep_parses_spf_and_dmarc(monkeypatch):
    install(monkeypatch, {
        "_dmarc.example.com": doh_answer(16, '"v=DMARC1; p=reject; rua=mailto:r@dmarc.agari.com"'),
        "type=TXT": doh_answer(16, '"v=spf1 include:_spf.google.com ip4:203.0.113.5/32 -all"'),
        "type=MX": doh_answer(15, "1 aspmx.l.google.com.")})
    rows = run("dns_deep", "example.com")
    head = rows[0].raw_json
    assert head["mail_provider"] == "Google Workspace" and head["dmarc_policy"] == "reject"
    titles = {r.title for r in rows[1:]}
    assert {"_spf.google.com", "203.0.113.5", "dmarc.agari.com"} <= titles


def test_asn_from_ip_via_doh(monkeypatch):
    # Force the DoH branch: with dnspython installed the adapter would otherwise make a
    # real DNS query and this test would depend on the network.
    monkeypatch.setitem(sys.modules, "dns", None)
    monkeypatch.setitem(sys.modules, "dns.resolver", None)
    install(monkeypatch, {
        "8.8.8.8.origin.asn.cymru.com": doh_answer(16, '"15169 | 8.8.8.0/24 | US | arin | 2023-12-28"'),
        "AS15169.asn.cymru.com": doh_answer(16, '"15169 | US | arin | 2000-03-30 | GOOGLE, US"')})
    rows = run("asn", "8.8.8.8")
    assert rows[0].raw_json["prefix"] == "8.8.8.0/24" and rows[0].raw_json["as_owner"] == "GOOGLE, US"
    assert rows[1].title == "AS15169" and all(r.tier == "T3" for r in rows)


def test_asn_rejects_garbage():
    with pytest.raises(EnrichmentError):
        run("asn", "not-an-ip")


def test_ripestat(monkeypatch):
    install(monkeypatch, {"stat.ripe.net": {"data": {"asns": ["15169"], "prefix": "8.8.8.0/24"}}})
    rows = run("ripestat", "8.8.8.8")
    assert rows[1].title == "AS15169" and "8.8.8.0/24" in rows[0].summary


def test_ipwhois_success_false_raises(monkeypatch):
    install(monkeypatch, {"ipwho.is": {"success": False, "message": "Reserved range"}})
    with pytest.raises(EnrichmentError, match="Reserved"):
        run("ipwhois", "10.0.0.1")


def test_reverse_ip_quota_body_raises_and_list_parses(monkeypatch):
    install(monkeypatch, {"hackertarget": "API count exceeded - Increase Quota"})
    with pytest.raises(EnrichmentError):
        run("reverse_ip", "1.2.3.4")
    install(monkeypatch, {"hackertarget": "a.example.com\nb.example.org\n"})
    rows = run("reverse_ip", "1.2.3.4")
    assert [r.title for r in rows[1:]] == ["a.example.com", "b.example.org"] and rows[0].tier == "T3"


def test_certspotter_scopes_to_queried_domain(monkeypatch):
    install(monkeypatch, {"certspotter": [{"id": "1", "not_before": "2026-01-01",
                                            "dns_names": ["*.example.com", "www.example.com", "evil.net"],
                                            "issuer": {"friendly_name": "Let's Encrypt"}}]})
    titles = [r.title for r in run("certspotter", "example.com")]
    assert titles == ["example.com", "www.example.com"]


def test_certspotter_404_is_empty_other_errors_raise(monkeypatch):
    install(monkeypatch, {"certspotter": HTTPStatusError("HTTP 404", 404)})
    assert run("certspotter", "example.com") == []
    install(monkeypatch, {"certspotter": HTTPStatusError("HTTP 429", 429)})
    with pytest.raises(EnrichmentError):
        run("certspotter", "example.com")


def test_shodan_keyless_internetdb(monkeypatch):
    monkeypatch.delenv("SHODAN_API_KEY", raising=False)
    install(monkeypatch, {"internetdb.shodan.io/1.2.3.4": {"ports": [22, 443], "hostnames": ["h.example.com"],
                                                            "cpes": [], "tags": [], "vulns": ["CVE-2024-1"]}})
    rows = run("shodan", "1.2.3.4")
    assert "CVE-2024-1" in rows[0].summary and rows[1].title == "h.example.com"
    assert registry.get_adapter("shodan").missing() == []


def test_shodan_host_mode_without_key_is_not_configured(monkeypatch):
    monkeypatch.delenv("SHODAN_API_KEY", raising=False)
    with pytest.raises(NotConfiguredError):
        run("shodan", "1.2.3.4", "host")


def test_typosquat_not_configured_without_dnstwist(monkeypatch):
    install(monkeypatch, {})
    monkeypatch.setitem(__import__("sys").modules, "dnstwist", None)
    with pytest.raises(NotConfiguredError):
        run("typosquat", "example.com")


def test_typosquat_binary_path(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "dnstwist", None)
    install(monkeypatch, {"dnstwist --registered": '[{"fuzzer": "*original", "domain": "example.com"},'
                                                    '{"fuzzer": "homoglyph", "domain": "examp1e.com", "dns_a": ["1.1.1.1"]}]'},
            bins=("dnstwist",))
    rows = run("typosquat", "example.com")
    assert [r.title for r in rows[1:]] == ["examp1e.com"] and all(r.tier == "T3" for r in rows)
