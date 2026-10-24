"""ioc-reputation.py with a stubbed HTTP layer (no network, no keys needed)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _script_loader import load_script  # noqa: E402

rep = load_script("ioc-reputation.py", "ioc_reputation")

IOCS = {"iocs": [
    {"field_type": "ip", "value": "45.11.181.44"},
    {"field_type": "ip", "value": "10.0.0.1"},
    {"field_type": "domain", "value": "evil.example"},
    {"field_type": "file_hash", "value": "d41d8cd98f00b204e9800998ecf8427e"},
    {"field_type": "cve", "value": "CVE-2021-44228"},
]}


def fake_get(url, headers, timeout):
    if "internetdb" in url:
        return rep.HttpResult(200, {"ports": [22, 443], "vulns": ["CVE-1"], "hostnames": []})
    if "abuseipdb" in url:
        assert headers["Key"] == "k1"
        return rep.HttpResult(200, {"data": {"abuseConfidenceScore": 87, "totalReports": 5}})
    if "greynoise" in url:
        return rep.HttpResult(404, {"message": "IP not observed"})
    if "virustotal" in url:
        return rep.HttpResult(200, {"data": {"attributes": {
            "last_analysis_stats": {"malicious": 3, "harmless": 60}}}})
    raise AssertionError(url)


def test_lookup_all_rows(monkeypatch, tmp_path):
    src = tmp_path / "iocs.json"
    src.write_text(json.dumps(IOCS))
    monkeypatch.setenv("ABUSEIPDB_API_KEY", "k1")
    monkeypatch.delenv("GREYNOISE_API_KEY", raising=False)
    monkeypatch.setenv("VT_API_KEY", "k3")
    rows = rep.lookup_all(rep.load_iocs([src]), rep.ALL_SOURCES, get=fake_get,
                          delay=0, vt_delay=0, sleep=lambda s: None)
    by = {(r["ioc"], r["source"]): r for r in rows}
    assert by[("45.11.181.44", "internetdb")]["verdict"] == "2 ports, 1 vulns"
    assert by[("45.11.181.44", "abuseipdb")]["score"] == 87
    assert by[("45.11.181.44", "greynoise")]["status"] == "not configured"
    assert by[("10.0.0.1", "internetdb")]["status"] == "skipped"
    assert by[("evil.example", "virustotal")]["verdict"] == "3 malicious / 63 engines"
    assert ("d41d8cd98f00b204e9800998ecf8427e", "virustotal") in by
    assert not any(r["type"] == "cve" for r in rows)
    assert all(r["evidence_tier"] == "T3" for r in rows)


def test_vt_url_id_is_unpadded_base64():
    assert rep._vt_path("http://a.b/", "url") == "urls/aHR0cDovL2EuYi8"


def test_main_writes_csv(monkeypatch, tmp_path):
    src = tmp_path / "iocs.json"
    src.write_text(json.dumps(IOCS))
    for env in ("ABUSEIPDB_API_KEY", "GREYNOISE_API_KEY", "VT_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setattr(rep, "http_get_json", fake_get)
    monkeypatch.setattr(rep, "lookup_all", lambda iocs, sources, **k: rep.__dict__[
        "_orig_lookup"](iocs, sources, get=fake_get, delay=0, vt_delay=0, sleep=lambda s: None))
    rep._orig_lookup = LOOKUP
    out = tmp_path / "rep.csv"
    assert rep.main([str(src), "--out", str(out), "--sources", "internetdb,virustotal"]) == 0
    text = out.read_text()
    assert "internetdb" in text and "not configured" in text


LOOKUP = rep.lookup_all
