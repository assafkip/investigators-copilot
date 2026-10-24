"""Registry / sanctions / court adapters. Offline."""
import pytest
from _enrich_net import install

from enrich import registry
from enrich.base import EnrichmentError, HTTPStatusError, NotConfiguredError


def run(slug, query, mode=None):
    return registry.get_adapter(slug).run(query, mode=mode)


def test_gleif_name_search_is_t1(monkeypatch):
    install(monkeypatch, {"lei-records?": {"data": [{"attributes": {
        "lei": "5493001KJTIIGC8Y1R12", "entity": {"legalName": {"name": "ACME LTD"}, "jurisdiction": "GB",
                                                   "status": "ACTIVE", "legalAddress": {"city": "London",
                                                                                        "country": "GB"}},
        "registration": {"status": "ISSUED"}}, "relationships": {"direct-parent": {}}}]}})
    [row] = run("gleif", "Acme")
    assert row.title == "ACME LTD" and row.tier == "T1" and "direct-parent" in row.summary


def test_gleif_lei_404_is_empty(monkeypatch):
    install(monkeypatch, {"lei-records/": HTTPStatusError("HTTP 404", 404)})
    assert run("gleif", "5493001KJTIIGC8Y1R12") == []


def test_opencorporates_keyless_refusal_is_not_configured(monkeypatch):
    monkeypatch.delenv("OPENCORPORATES_API_KEY", raising=False)
    install(monkeypatch, {"opencorporates": HTTPStatusError("HTTP 401", 401)})
    with pytest.raises(NotConfiguredError):
        run("opencorporates", "acme")


def test_opencorporates_officers(monkeypatch):
    monkeypatch.setenv("OPENCORPORATES_API_KEY", "k")
    calls = install(monkeypatch, {"officers/search": {"results": {"officers": [{"officer": {
        "name": "JANE DOE", "position": "director", "company": {"name": "ACME LTD"}}}]}}})
    [row] = run("opencorporates", "Jane Doe", "officer")
    assert "api_token=k" in calls[0][0] and "director of ACME LTD" in row.summary


def test_ofac_oracle_sanctioned(monkeypatch):
    calls = install(monkeypatch, {"publicnode": {"jsonrpc": "2.0", "result": "0x" + "0" * 63 + "1"}})
    [row] = run("ofac", "0x" + "ab" * 20)
    assert row.raw_json["sanctioned"] is True and calls[0][2]["method"] == "eth_call"
    assert row.tier == "T1"  # the on-chain oracle read stays T1


def test_ofac_sdn_name_match_uses_cache_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("OSINT_CACHE_DIR", str(tmp_path))
    csv_rows = "".join(f'{i},"FILLER {i}","entity","SDGT"\n' for i in range(1200))
    csv_rows += '9999,"BADGUY, John","individual","CYBER2"\n'
    install(monkeypatch, {"sdn.csv": csv_rows})
    [row] = run("ofac", "badguy")
    assert row.title == "BADGUY, John" and row.raw_json["program"] == "CYBER2"
    assert row.tier == "T3"  # a name substring match is a lead, never T1
    assert (tmp_path / "ofac_sdn.json").exists()


def test_ofac_truncated_list_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("OSINT_CACHE_DIR", str(tmp_path))
    install(monkeypatch, {"sdn.csv": '1,"A","entity","X"\n'})
    with pytest.raises(EnrichmentError, match="truncated"):
        run("ofac", "a")


def test_courtlistener_dockets(monkeypatch):
    monkeypatch.delenv("COURTLISTENER_API_TOKEN", raising=False)
    calls = install(monkeypatch, {"courtlistener.com/api/rest/v4/search": {"count": 1, "results": [
        {"caseName": "US v. Doe", "court": "S.D.N.Y.", "docketNumber": "1:21-cr-1", "dateFiled": "2021-01-01",
         "absolute_url": "/docket/1/us-v-doe/", "recap_documents": [{"x": 1}]}]}})
    [row] = run("courtlistener", '"John Doe"')
    assert "type=r" in calls[0][0] and calls[0][1] is None
    assert row.url == "https://www.courtlistener.com/docket/1/us-v-doe/" and row.tier == "T1"
    assert "recap_documents" not in row.raw_json


def test_courtlistener_anonymous_refusal_is_not_configured(monkeypatch):
    monkeypatch.delenv("COURTLISTENER_API_TOKEN", raising=False)
    install(monkeypatch, {"courtlistener": HTTPStatusError("HTTP 403", 403)})
    with pytest.raises(NotConfiguredError):
        run("courtlistener", "acme")


def test_opensanctions_prefers_local_yente(monkeypatch):
    monkeypatch.delenv("OPENSANCTIONS_API_KEY", raising=False)
    monkeypatch.setenv("YENTE_URL", "http://yente.local:8000")
    calls = install(monkeypatch, {"/healthz": {"status": "ok"}, "yente.local:8000/match/default": {
        "responses": {"q": {"results": [{"id": "NK-1", "caption": "Ivan X", "schema": "Person", "score": 0.97,
                                         "match": True, "datasets": ["us_ofac_sdn"], "properties": {}}]}}}})
    [row] = run("opensanctions", "Ivan X", "person")
    assert calls[1][2]["queries"]["q"]["schema"] == "Person" and row.tier == "T3"
    assert "us_ofac_sdn" in row.summary


def test_opensanctions_no_yente_no_key(monkeypatch):
    monkeypatch.delenv("OPENSANCTIONS_API_KEY", raising=False)
    install(monkeypatch, {"/healthz": EnrichmentError("refused")})
    with pytest.raises(NotConfiguredError):
        run("opensanctions", "acme")


def test_opensanctions_hosted_with_key(monkeypatch):
    monkeypatch.setenv("OPENSANCTIONS_API_KEY", "k")
    calls = install(monkeypatch, {"/healthz": EnrichmentError("refused"),
                                  "api.opensanctions.org/match": {"responses": {"q": {"results": []}}}})
    assert run("opensanctions", "acme") == []
    assert calls[1][1] == {"Authorization": "ApiKey k"}


def test_wikidata_drops_unrelated_hit(monkeypatch):
    install(monkeypatch, {"wbsearchentities": {"search": [{"id": "Q1", "label": "Totally Different"}]}})
    assert run("wikidata", "acme corp") == []
    install(monkeypatch, {"wbsearchentities": {"search": [{"id": "Q2", "label": "Acme Corp"}]},
                          "wbgetentities": {"entities": {"Q2": {"claims": {"P856": [
                              {"mainsnak": {"datavalue": {"value": "https://acme.example"}}}]}}}}})
    [row] = run("wikidata", "acme corp")
    assert row.raw_json["website"] == "https://acme.example" and row.tier == "T3"
