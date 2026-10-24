"""Offline network fakes for enrichment adapter tests (no sockets, ever).

`install(monkeypatch, routes)` patches base.http_json / base.http_get / base.run_bin.
`routes` maps a URL (or argv) substring to a value: a dict/list (JSON body), bytes/str
(raw body), or an Exception instance to raise. First matching substring wins; an
unmatched call fails the test loudly so a forgotten route never hits the network.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))
from enrich import base  # noqa: E402


def _lookup(routes, key, calls):
    calls.append(key)
    for frag, value in routes.items():
        if frag in key:
            if isinstance(value, Exception):
                raise value
            return value
    raise AssertionError(f"unrouted network call in test: {key}")


def install(monkeypatch, routes, bins=()):
    calls = []

    def http_json(url, *, headers=None, timeout=30, data=None):
        value = _lookup(routes, url, calls)
        calls[-1] = (url, headers, data)
        return json.loads(value) if isinstance(value, (str, bytes)) else value

    def http_get(url, *, headers=None, timeout=30):
        value = _lookup(routes, url, calls)
        return value.encode() if isinstance(value, str) else value if isinstance(value, bytes) \
            else json.dumps(value).encode()

    def run_bin(cmd, *, timeout=300):
        return _lookup(routes, " ".join(cmd), calls)

    monkeypatch.setattr(base, "http_json", http_json)
    monkeypatch.setattr(base, "http_get", http_get)
    monkeypatch.setattr(base, "run_bin", run_bin)
    from enrich import _common
    monkeypatch.setattr(_common, "which", lambda *names: next((f"/bin/{n}" for n in names if n in bins), None))
    return calls


def doh_answer(rtype_code, *values, status=0):
    return {"Status": status, "Answer": [{"type": rtype_code, "data": v} for v in values]}
