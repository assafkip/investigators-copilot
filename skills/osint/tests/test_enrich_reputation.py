"""Reputation / feed adapters: all T3, keys enforced, failures raise. Offline."""
import pytest
from _enrich_net import install

from enrich import registry
from enrich.base import EnrichmentError, HTTPStatusError, NotConfiguredError


def run(slug, query, mode=None):
    return registry.get_adapter(slug).run(query, mode=mode)


@pytest.mark.parametrize("slug,env", [("otx", "OTX_API_KEY"), ("greynoise", "GREYNOISE_API_KEY"),
                                      ("abuseipdb", "ABUSEIPDB_API_KEY")])
def test_keyed_adapters_refuse_without_key(monkeypatch, slug, env):
    monkeypatch.delenv(env, raising=False)
    install(monkeypatch, {})
    with pytest.raises(NotConfiguredError):
        run(slug, "1.2.3.4")


def test_urlscan_keyless_search_collects_related_infra(monkeypatch):
    monkeypatch.delenv("URLSCAN_API_KEY", raising=False)
    calls = install(monkeypatch, {"urlscan.io/api/v1/search": {"total": 2, "results": [
        {"page": {"domain": "a.example.com", "ip": "1.2.3.4", "asnname": "AS1"}, "task": {"time": "2026-01-02"}},
        {"page": {"domain": "b.example.com", "ip": "1.2.3.4"}}]}})
    rows = run("urlscan", "https://example.com/x")
    assert "domain%3Aexample.com" in calls[0][0] and calls[0][1] is None
    assert [r.title for r in rows[1:]] == ["a.example.com", "b.example.com", "1.2.3.4"]
    assert all(r.tier == "T3" for r in rows)


def test_otx_general_and_passive_dns(monkeypatch):
    monkeypatch.setenv("OTX_API_KEY", "k")
    install(monkeypatch, {
        "/general": {"pulse_info": {"count": 3, "pulses": [{"name": "APT x", "tags": ["c2"]}]}},
        "/passive_dns": {"passive_dns": [{"address": "5.6.7.8", "record_type": "A"}]}})
    rows = run("otx", "evil.com")
    assert rows[0].raw_json["pulse_count"] == 3 and rows[0].confidence == "high"
    assert rows[1].title == "5.6.7.8"


def test_greynoise_404_means_unseen(monkeypatch):
    monkeypatch.setenv("GREYNOISE_API_KEY", "k")
    install(monkeypatch, {"greynoise": HTTPStatusError("HTTP 404", 404)})
    [row] = run("greynoise", "1.2.3.4")
    assert "unseen" in row.title


def test_abuseipdb_score_and_hostnames(monkeypatch):
    monkeypatch.setenv("ABUSEIPDB_API_KEY", "k")
    calls = install(monkeypatch, {"abuseipdb": {"data": {"abuseConfidenceScore": 90, "totalReports": 12,
                                                         "domain": "bad.example", "hostnames": ["h.bad.example"]}}})
    rows = run("abuseipdb", "1.2.3.4")
    assert calls[0][1] == {"Key": "k"} and rows[0].confidence == "high"
    assert [r.title for r in rows[1:]] == ["bad.example", "h.bad.example"]


def test_sans_isc_bad_shape_raises(monkeypatch):
    install(monkeypatch, {"isc.sans.edu": {"error": "x"}})
    with pytest.raises(EnrichmentError):
        run("sans_isc", "1.2.3.4")


def test_stopforumspam_email_mode(monkeypatch):
    calls = install(monkeypatch, {"stopforumspam": {"success": 1, "email": {"appears": 1, "frequency": 4}}})
    [row] = run("stopforumspam", "a@b.com")
    assert "email=a%40b.com" in calls[0][0] and "reported 4" in row.summary


def test_stopforumspam_failure_raises(monkeypatch):
    install(monkeypatch, {"stopforumspam": {"success": 0, "error": "rate limited"}})
    with pytest.raises(EnrichmentError, match="rate limited"):
        run("stopforumspam", "1.2.3.4")


def test_crypto_abuse_hit_and_moved_feed(monkeypatch):
    install(monkeypatch, {"domains.json": ["scam.example", "other.example"]})
    [row] = run("crypto_abuse", "https://SCAM.example/claim")
    assert row.raw_json["hit"] is True and row.tier == "T3"
    install(monkeypatch, {"address.json": {"moved": True}})
    with pytest.raises(EnrichmentError):
        run("crypto_abuse", "0xabc")


def test_darkweb_extracts_onions_and_rejects_foreign_page(monkeypatch):
    onion = "a" * 56 + ".onion"
    install(monkeypatch, {"ahmia.fi": f"<html>Ahmia results <a>{onion}</a> {onion}</html>"})
    rows = run("darkweb", "acme")
    assert [r.title for r in rows] == [onion]
    install(monkeypatch, {"ahmia.fi": "<html>Just a moment... cloudflare</html>"})
    with pytest.raises(EnrichmentError):
        run("darkweb", "acme")


def test_xposedornot_not_found_is_empty_and_hit_lists_breaches(monkeypatch):
    install(monkeypatch, {"xposedornot": {"Error": "Not found"}})
    assert run("xposedornot", "a@b.com") == []
    install(monkeypatch, {"xposedornot": {"breaches": [["Adobe", "LinkedIn"]]}})
    [row] = run("xposedornot", "a@b.com")
    assert row.raw_json["breaches"] == ["Adobe", "LinkedIn"]


def test_disposable_email_both_fail_raises_single_source_ok(monkeypatch):
    install(monkeypatch, {"debounce": EnrichmentError("down"), "kickbox": EnrichmentError("down")})
    with pytest.raises(EnrichmentError, match="both providers"):
        run("disposable_email", "x@mailinator.com")
    install(monkeypatch, {"debounce": {"disposable": "true"}, "kickbox": EnrichmentError("down")})
    [row] = run("disposable_email", "x@mailinator.com")
    assert "single source" in row.summary and "disposable" in row.summary
