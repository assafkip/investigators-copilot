"""Subprocess-wrapped tools (GPL/AGPL never imported): theHarvester, bbot, SpiderFoot,
wappalyzer/httpx. run_bin is faked; missing binaries raise NotConfiguredError."""
import json
from pathlib import Path

import pytest
from _enrich_net import install

from enrich import base, registry
from enrich.base import EnrichmentError, NotConfiguredError


def run(slug, query, mode=None):
    return registry.get_adapter(slug).run(query, mode=mode)


@pytest.mark.parametrize("slug", ["theharvester", "bbot", "spiderfoot", "wappalyzer"])
def test_missing_binary_is_not_configured(monkeypatch, slug):
    monkeypatch.delenv("SPIDERFOOT_URL", raising=False)
    monkeypatch.delenv("PD_HTTPX_BIN", raising=False)
    install(monkeypatch, {})
    with pytest.raises(NotConfiguredError):
        run(slug, "example.com")


def test_theharvester_reads_json_file(monkeypatch):
    install(monkeypatch, {}, bins=("theHarvester",))

    def fake_run_bin(cmd, *, timeout=300):
        stem = cmd[cmd.index("-f") + 1]
        Path(f"{stem}.json").write_text(json.dumps({"emails": ["a@example.com"], "hosts": ["www.example.com:1.2.3.4"]}))
        return "done"
    monkeypatch.setattr(base, "run_bin", fake_run_bin)
    rows = run("theharvester", "example.com")
    assert [r.title for r in rows[1:]] == ["a@example.com", "www.example.com"]
    assert registry.get_adapter("theharvester").license_note.startswith("GPL")


def test_theharvester_no_output_raises(monkeypatch):
    install(monkeypatch, {"theHarvester": "error: bad source"}, bins=("theHarvester",))
    with pytest.raises(EnrichmentError, match="no JSON"):
        run("theharvester", "example.com")


def test_bbot_passive_preset_and_event_parse(monkeypatch):
    events = "\n".join(json.dumps(e) for e in [
        {"type": "SCAN", "data": "x"}, {"type": "DNS_NAME", "data": "a.example.com"},
        {"type": "IP_ADDRESS", "data": "1.2.3.4"}, {"type": "DNS_NAME", "data": "a.example.com"}])
    calls = install(monkeypatch, {"bbot -t example.com": "[INFO] banner\n" + events}, bins=("bbot",))
    rows = run("bbot", "example.com")
    assert "-rf passive" in calls[0]
    assert [r.title for r in rows[1:]] == ["a.example.com", "1.2.3.4"]


def test_spiderfoot_cli_json(monkeypatch):
    out = json.dumps([{"type": "ROOT", "data": "example.com"},
                      {"type": "IP Address", "data": "1.2.3.4", "module": "sfp_dnsresolve"}])
    calls = install(monkeypatch, {"sf.py -s example.com -u passive": out}, bins=("sf.py",))
    rows = run("spiderfoot", "example.com")
    assert rows[1].title == "1.2.3.4" and rows[0].raw_json["events"] == {"IP Address": ["1.2.3.4"]}
    assert calls


def test_spiderfoot_rest_results(monkeypatch):
    monkeypatch.setenv("SPIDERFOOT_URL", "http://sf.local:5001")
    install(monkeypatch, {"sf.local:5001/scaneventresults": [
        ["2026-01-01", "evil.example", "example.com", "sfp_x", "", "", "", "", "", "", "AFFILIATE_INTERNET_NAME"]]})
    rows = run("spiderfoot", "SCANID", "results")
    assert rows[1].title == "evil.example"


def test_wappalyzer_cli_json(monkeypatch):
    install(monkeypatch, {"wappalyzer https://example.com": json.dumps(
        {"technologies": [{"name": "Nginx", "version": "1.25", "categories": [{"name": "Web servers"}]}]})},
        bins=("wappalyzer",))
    [row] = run("wappalyzer", "example.com")
    assert "Nginx 1.25" in row.summary and row.tier == "T3"


def test_wappalyzer_bad_output_raises(monkeypatch):
    install(monkeypatch, {"wappalyzer": "not json"}, bins=("wappalyzer",))
    with pytest.raises(EnrichmentError):
        run("wappalyzer", "example.com")
