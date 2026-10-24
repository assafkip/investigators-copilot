"""watch.py: append-only store, local-hash change detection, bounded poll, capture routing."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS / "lib"))
_spec = importlib.util.spec_from_file_location("watch", SCRIPTS / "watch.py")
watch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(watch)


@pytest.fixture
def case_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("CHANGEDETECTION_URL", raising=False)
    monkeypatch.delenv("CHANGEDETECTION_API_KEY", raising=False)
    d = tmp_path / "investigations" / "case-999-test"
    (d / "memory").mkdir(parents=True)
    return d


def _pages(mapping):
    def _fetch(url):
        val = mapping[url]
        if isinstance(val, Exception):
            raise val
        return val
    return _fetch


def test_add_is_idempotent_and_list_replays(case_dir, capsys):
    watch.cmd_add("case-999-test", case_dir, "https://a.example/", "A", "auto")
    watch.cmd_add("case-999-test", case_dir, "https://a.example/", "A", "auto")
    lines = watch.store_path(case_dir).read_text().splitlines()
    assert len(lines) == 1
    state = watch.load_state(case_dir)
    assert state["https://a.example/"]["backend"] == "local"
    assert state["https://a.example/"]["last_status"] == "new"


def test_poll_new_then_unchanged_then_changed(case_dir, monkeypatch):
    url = "https://a.example/"
    watch.cmd_add("c", case_dir, url, "", "local")
    pages = {url: b"<html><script>var t=1</script><p>hello</p></html>"}
    monkeypatch.setattr(watch, "fetch_url", _pages(pages))
    watch.cmd_poll("c", case_dir, 50, 60, False)
    assert watch.load_state(case_dir)[url]["last_status"] == "new"
    # script-only churn is normalised away
    pages[url] = b"<html><script>var t=2</script><p>hello</p></html>"
    watch.cmd_poll("c", case_dir, 50, 60, False)
    assert watch.load_state(case_dir)[url]["last_status"] == "unchanged"
    pages[url] = b"<html><p>hello world</p></html>"
    watch.cmd_poll("c", case_dir, 50, 60, False)
    assert watch.load_state(case_dir)[url]["last_status"] == "changed"


def test_empty_body_and_errors_are_not_changes(case_dir, monkeypatch):
    url = "https://a.example/"
    watch.cmd_add("c", case_dir, url, "", "local")
    monkeypatch.setattr(watch, "fetch_url", _pages({url: b"<p>x</p>"}))
    watch.cmd_poll("c", case_dir, 50, 60, False)
    monkeypatch.setattr(watch, "fetch_url", _pages({url: b"   "}))
    watch.cmd_poll("c", case_dir, 50, 60, False)
    st = watch.load_state(case_dir)[url]
    assert st["last_status"] == "error"
    assert st["sha256"] == watch.content_hash(b"<p>x</p>")  # baseline kept
    monkeypatch.setattr(watch, "fetch_url", _pages({url: OSError("down")}))
    watch.cmd_poll("c", case_dir, 50, 60, False)
    assert watch.load_state(case_dir)[url]["last_status"] == "error"


def test_poll_is_bounded_by_max(case_dir, monkeypatch, capsys):
    urls = [f"https://s{i}.example/" for i in range(5)]
    for u in urls:
        watch.cmd_add("c", case_dir, u, "", "local")
    calls = []

    def _fetch(url):
        calls.append(url)
        return b"<p>x</p>"
    monkeypatch.setattr(watch, "fetch_url", _fetch)
    watch.cmd_poll("c", case_dir, 2, 60, False)
    assert len(calls) == 2
    assert "not polled this run" in capsys.readouterr().out


def test_poll_is_bounded_by_deadline(case_dir, monkeypatch):
    for i in range(3):
        watch.cmd_add("c", case_dir, f"https://s{i}.example/", "", "local")
    calls = []
    monkeypatch.setattr(watch, "fetch_url", lambda u: calls.append(u) or b"<p>x</p>")
    watch.cmd_poll("c", case_dir, 50, -1, False)  # deadline already passed
    assert calls == []


def test_capture_routes_only_changed_urls(case_dir, monkeypatch):
    a, b = "https://a.example/", "https://b.example/"
    for u in (a, b):
        watch.cmd_add("c", case_dir, u, "", "local")
    pages = {a: b"<p>1</p>", b: b"<p>1</p>"}
    monkeypatch.setattr(watch, "fetch_url", _pages(pages))
    watch.cmd_poll("c", case_dir, 50, 60, False)
    pages[a] = b"<p>2</p>"
    seen = {}

    def _call(cmd):
        seen["cmd"] = cmd
        seen["tsv"] = Path(cmd[3]).read_text()
        return 0
    monkeypatch.setattr(watch.subprocess, "call", _call)
    assert watch.cmd_poll("c", case_dir, 50, 60, True) == 0
    assert seen["cmd"][2] == "--batch" and seen["cmd"][4:] == ["--case", "c"]
    rows = [r.split("\t") for r in seen["tsv"].splitlines()]
    assert [r[0] for r in rows] == [a]
    assert rows[0][1].startswith("watch-a-example")


def test_remove_and_malformed_lines(case_dir):
    url = "https://a.example/"
    watch.cmd_add("c", case_dir, url, "", "local")
    with watch.store_path(case_dir).open("a") as fh:
        fh.write("not json\n")
    assert url in watch.load_state(case_dir)
    watch.cmd_remove(case_dir, url)
    assert watch.load_state(case_dir) == {}
    events = [json.loads(line)["event"] for line in watch.store_path(case_dir).read_text().splitlines()
              if line.startswith("{")]
    assert events == ["add", "remove"]


def test_changedetection_backend(case_dir, monkeypatch):
    monkeypatch.setenv("CHANGEDETECTION_URL", "http://cd.local")
    monkeypatch.setenv("CHANGEDETECTION_API_KEY", "k")
    stamps = {"v": 100}

    def _req(method, path, payload=None):
        if method == "POST":
            assert payload["tag"] == "c"
            return {"uuid": "u-1"}
        return {"last_changed": stamps["v"]}
    monkeypatch.setattr(watch, "cd_request", _req)
    url = "https://a.example/"
    watch.cmd_add("c", case_dir, url, "", "auto")
    st = watch.load_state(case_dir)[url]
    assert st["backend"] == "changedetection" and st["uuid"] == "u-1"
    watch.cmd_poll("c", case_dir, 50, 60, False)
    assert watch.load_state(case_dir)[url]["last_status"] == "new"
    watch.cmd_poll("c", case_dir, 50, 60, False)
    assert watch.load_state(case_dir)[url]["last_status"] == "unchanged"
    stamps["v"] = 200
    watch.cmd_poll("c", case_dir, 50, 60, False)
    assert watch.load_state(case_dir)[url]["last_status"] == "changed"


def test_changedetection_requested_without_config_exits(case_dir):
    with pytest.raises(SystemExit):
        watch.cmd_add("c", case_dir, "https://a.example/", "", "changedetection")
