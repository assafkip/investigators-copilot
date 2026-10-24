"""Phase 3 identity adapters: parsing + failure contract, all offline (monkeypatched)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))
from enrich import registry  # noqa: E402
from enrich import (email_intel, ghunt, git_osint, github_user, gitlab_user, gitrecon,  # noqa: E402
                    gravatar, hackernews_user, holehe, maigret, npm_user, phone, sherlock,
                    telegram_phone, user_scanner, username)
from enrich._identity_common import BinAdapter  # noqa: E402
from enrich.base import EnrichmentError, NotConfiguredError  # noqa: E402

IDENTITY_SLUGS = {"username", "email_intel", "phone", "gravatar", "git_osint", "github_user",
                  "gitlab_user", "hackernews_user", "npm_user", "maigret", "sherlock", "user_scanner",
                  "holehe", "ghunt", "gitrecon", "telegram_phone"}


def _fake_fetch(table):
    """fetch() stand-in: match on a URL substring -> (status, body)."""
    def fake(url, **_):
        for needle, answer in table.items():
            if needle in url:
                return answer
        raise EnrichmentError(f"unexpected url {url}")
    return fake


def test_all_identity_adapters_register_without_import_errors():
    slugs = set(registry.slugs())
    assert IDENTITY_SLUGS <= slugs
    bad = {m: e for m, e in registry.IMPORT_ERRORS.items() if m in IDENTITY_SLUGS}
    assert not bad
    for slug in IDENTITY_SLUGS:
        assert registry.get_adapter(slug).tier == "T3"


# -- username -----------------------------------------------------------------

def test_wmn_dataset_is_vendored_full():
    data = json.loads(username.WMN_PATH.read_text())
    assert len(data["sites"]) > 500
    assert "CC BY-SA" in " ".join(data["license"]) or "Attribution-ShareAlike" in " ".join(data["license"])
    assert (username.WMN_PATH.parent / "NOTICE.md").is_file()
    assert len(username.load_wmn(include_protected=True)) > len(username.load_wmn())


def test_wmn_verdict_contract():
    site = {"e_code": 200, "e_string": "profile-card", "m_code": 404, "m_string": "Not Found"}
    assert username.wmn_verdict(site, 200, "<div class=profile-card>") is True
    assert username.wmn_verdict(site, 404, "Not Found") is False
    assert username.wmn_verdict(site, 200, "login wall") is None
    assert username.wmn_verdict(site, 503, "") is None


def test_username_sweep_found_and_fail_closed(monkeypatch):
    sites = [{"name": "Alpha", "uri_check": "https://alpha.test/{account}", "e_code": 200,
              "e_string": "HIT", "m_code": 404, "m_string": ""},
             {"name": "Beta", "uri_check": "https://beta.test/u/{account}", "e_code": 200,
              "e_string": "HIT", "m_code": 404, "m_string": ""}]
    monkeypatch.setattr(username, "CURATED", [])
    monkeypatch.setattr(username, "load_wmn", lambda include_protected=False: sites)
    monkeypatch.setattr(username, "fetch", _fake_fetch({"alpha.test": (200, "HIT"), "beta.test": (404, "")}))
    out = username.UsernameAdapter().run("@someone")
    assert out[0].result_type == "document" and "1/2" in out[0].title
    assert [r.url for r in out[1:]] == ["https://alpha.test/someone"]
    assert all(r.tier == "T3" for r in out)

    def down(url, **_):
        raise EnrichmentError("network down")
    monkeypatch.setattr(username, "fetch", down)
    with pytest.raises(EnrichmentError, match="indeterminate"):
        username.UsernameAdapter().run("someone")


def test_username_reddit_uses_arctic_history(monkeypatch):
    class FakeArctic:
        @staticmethod
        def user_history(name, **_):
            return {"posts": [{"id": "x"}], "comments": []}
    monkeypatch.setattr(username, "reddit_arctic_module", lambda: FakeArctic)
    row = username.check_curated(("Reddit", "", ("reddit",), "https://www.reddit.com/user/{u}"), "spez")
    assert row["present"] is True and row["url"] == "https://www.reddit.com/user/spez"


def test_username_rejects_bad_handle():
    with pytest.raises(EnrichmentError):
        username.UsernameAdapter().run("two words")


# -- email_intel --------------------------------------------------------------

def test_email_triage_via_doh(monkeypatch):
    answers = {("example.org", "MX"): ["10 aspmx.l.google.com.", "20 alt1.aspmx.l.google.com."],
               ("example.org", "TXT"): ['"v=spf1 include:_spf.google.com ~all"'],
               ("_dmarc.example.org", "TXT"): ['"v=DMARC1; p=reject"']}
    monkeypatch.setattr(email_intel, "doh_query", lambda n, t, timeout=10: answers.get((n, t), []))
    out = email_intel.EmailIntelAdapter().run("Bob@Example.org")
    facts = out[0].raw_json
    assert facts["provider"] == "Google Workspace" and facts["dmarc_policy"] == "reject"
    assert facts["spf"].startswith("v=spf1") and [r.title for r in out[1:]][0] == "aspmx.l.google.com"


def test_email_doh_failure_raises(monkeypatch):
    def boom(url, **_):
        raise EnrichmentError("HTTP 503")
    monkeypatch.setattr(email_intel, "http_json", boom)
    with pytest.raises(EnrichmentError, match="DoH"):
        email_intel.EmailIntelAdapter().run("a@example.org")


def test_email_headers_received_chain():
    raw = ("Received: from mx.google.com (mx.google.com [142.250.1.1]) by relay\n"
           "Received: from sender (unknown [203.0.113.9]) by smtp.evil.test ([8.8.4.4])\n"
           "Received: from laptop (10.0.0.5)\nFrom: x@y.test\nSubject: hi\n\nbody 1.2.3.4")
    out = email_intel.EmailIntelAdapter().run(raw)
    chain = out[0].raw_json
    assert chain["origin_ip"] == "8.8.4.4"   # bottom-most PUBLIC ip; 203.0.113.9 is TEST-NET, 10.x private
    assert {r.title for r in out[1:]} == {"142.250.1.1", "8.8.4.4"}


# -- phone ----------------------------------------------------------------------

def test_phone_missing_dependency_is_not_configured(monkeypatch):
    def missing():
        raise NotConfiguredError("phone: python package phonenumbers missing")
    monkeypatch.setattr(phone, "_import_phonenumbers", missing)
    with pytest.raises(NotConfiguredError):
        phone.PhoneAdapter().run("+14155552671")


def test_phone_parses_when_library_present():
    pytest.importorskip("phonenumbers")
    out = phone.PhoneAdapter().run("+14155552671")
    assert out[0].raw_json["e164"] == "+14155552671" and out[0].raw_json["country"] == "US"


# -- gravatar / github / gitlab / hn / npm -----------------------------------------

def test_gravatar_profile_and_404(monkeypatch):
    body = json.dumps({"entry": [{"displayName": "Bob", "profileUrl": "https://gravatar.com/bob",
                                  "accounts": [{"shortname": "github", "url": "https://github.com/bob",
                                                "username": "bob"}, {"url": "javascript:x"}]}]})
    monkeypatch.setattr(gravatar, "fetch", _fake_fetch({"gravatar.com": (200, body)}))
    out = gravatar.GravatarAdapter().run("bob@example.org")
    assert out[0].result_type == "profile" and [r.url for r in out[1:]] == ["https://github.com/bob"]
    monkeypatch.setattr(gravatar, "fetch", _fake_fetch({"gravatar.com": (404, "")}))
    assert "no profile" in gravatar.GravatarAdapter().run("bob@example.org")[0].title
    monkeypatch.setattr(gravatar, "fetch", _fake_fetch({"gravatar.com": (500, "")}))
    with pytest.raises(EnrichmentError):
        gravatar.GravatarAdapter().run("bob@example.org")


def test_github_user_pivots_and_login_guard(monkeypatch):
    user = {"login": "Octo", "name": "Octo Cat", "company": "@github", "blog": "octo.dev",
            "email": "octo@example.org", "twitter_username": "octo", "html_url": "https://github.com/Octo"}
    monkeypatch.setattr(github_user, "fetch", _fake_fetch({"api.github.com": (200, json.dumps(user))}))
    out = github_user.GithubUserAdapter().run("octo")
    urls = {r.url for r in out if r.url}
    assert {"https://github.com/Octo", "https://octo.dev", "https://x.com/octo"} <= urls
    assert any(r.title == "octo@example.org" for r in out)
    with pytest.raises(EnrichmentError, match="does not match"):
        github_user.GithubUserAdapter().run("someoneelse")
    monkeypatch.setattr(github_user, "fetch", _fake_fetch({"api.github.com": (403, "")}))
    with pytest.raises(EnrichmentError, match="rate limit"):
        github_user.GithubUserAdapter().run("octo")


def test_gitlab_user_match_guard(monkeypatch):
    body = json.dumps([{"username": "other"}, {"username": "Dev", "name": "D", "public_email": "d@x.org",
                                               "web_url": "https://gitlab.com/Dev"}])
    monkeypatch.setattr(gitlab_user, "fetch", _fake_fetch({"gitlab.com": (200, body)}))
    out = gitlab_user.GitlabUserAdapter().run("dev")
    assert out[0].url == "https://gitlab.com/Dev" and out[1].title == "d@x.org"
    monkeypatch.setattr(gitlab_user, "fetch", _fake_fetch({"gitlab.com": (200, "[]")}))
    assert "no public user" in gitlab_user.GitlabUserAdapter().run("dev")[0].title


def test_hackernews_user_bio_pivots(monkeypatch):
    body = json.dumps({"id": "pg", "karma": 1, "created": 1160418092,
                       "about": "site: <a href=\"https://paulgraham.com\">x</a> mail pg@example.org"})
    monkeypatch.setattr(hackernews_user, "fetch", _fake_fetch({"firebaseio": (200, body)}))
    out = hackernews_user.HackernewsUserAdapter().run("pg")
    assert out[0].raw_json["created"] == "2006-10-09"
    assert any(r.url == "https://paulgraham.com" for r in out) and any(r.title == "pg@example.org" for r in out)
    monkeypatch.setattr(hackernews_user, "fetch", _fake_fetch({"firebaseio": (200, "null")}))
    assert "no such user" in hackernews_user.HackernewsUserAdapter().run("pg")[0].title


def test_npm_user_only_own_publisher_email(monkeypatch):
    body = json.dumps({"objects": [
        {"package": {"name": "@sc/pkg", "links": {"repository": "git+https://github.com/a/b.git"},
                     "publisher": {"username": "alice", "email": "alice@example.org"}}},
        {"package": {"name": "other", "publisher": {"username": "bob", "email": "bob@example.org"}}}]})
    monkeypatch.setattr(npm_user, "fetch", _fake_fetch({"registry.npmjs.org": (200, body)}))
    out = npm_user.NpmUserAdapter().run("alice")
    titles = [r.title for r in out]
    assert "alice@example.org" in titles and "bob@example.org" not in titles
    assert any(r.url == "https://www.npmjs.com/package/@sc/pkg" for r in out)
    assert any(r.url == "https://github.com/a/b" for r in out)


# -- git_osint ------------------------------------------------------------------

def test_git_osint_parse_log_and_handle(monkeypatch):
    assert git_osint.parse_log("A@X.org|A\nnoreply@github.com|B\na@x.org|A2\n") == [("a@x.org", "A")]
    repos = json.dumps([{"clone_url": "https://github.com/u/fork.git", "fork": True},
                        {"clone_url": "https://github.com/u/own.git", "fork": False}])
    monkeypatch.setattr(git_osint, "fetch", _fake_fetch({"api.github.com": (200, repos)}))
    monkeypatch.setattr(git_osint, "mine_repo", lambda url, timeout=90: [("dev@x.org", "Dev")])
    out = git_osint.GitOsintAdapter().run("u")
    assert out[0].raw_json["repo"] == "https://github.com/u/own.git" and out[1].title == "dev@x.org"


# -- subprocess wrappers --------------------------------------------------------------

def _proc(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


@pytest.mark.parametrize("cls", [maigret.MaigretAdapter, sherlock.SherlockAdapter, holehe.HoleheAdapter,
                                 ghunt.GhuntAdapter, gitrecon.GitreconAdapter, user_scanner.UserScannerAdapter])
def test_missing_binary_raises_not_configured_with_setup_hint(cls, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    query = "a@example.org" if "email" in cls.watched_types and "handle" not in cls.watched_types else "someone"
    with pytest.raises(NotConfiguredError, match="setup-tools.sh --only"):
        cls().run(query)
    assert cls().missing() and cls.license_note


def _write_then(path_from_cmd, content):
    """exec_tool stand-in that writes `content` where the command asked for output."""
    def fake(self, cmd, **kwargs):
        target = path_from_cmd(cmd, kwargs)
        target.write_text(content)
        return _proc()
    return fake


def test_maigret_parses_simple_report(monkeypatch):
    report = {"GitHub": {"url_user": "https://github.com/bob", "status": {"status": "Claimed", "tags": ["coding"]}},
              "Foo": {"url_user": "https://foo.test/bob", "status": {"status": "Available"}}}
    monkeypatch.setattr(BinAdapter, "exec_tool", _write_then(
        lambda cmd, kw: Path(cmd[cmd.index("--folderoutput") + 1]) / "report_bob_simple.json", json.dumps(report)))
    out = maigret.MaigretAdapter().run("bob")
    assert [r.url for r in out[1:]] == ["https://github.com/bob"]


def test_sherlock_csv_and_stdout(monkeypatch):
    csv_text = "username,name,url_main,url_user,exists,http_status,response_time_s\n" \
               "bob,GitHub,https://github.com,https://github.com/bob,Claimed,200,0.1\n" \
               "bob,Foo,https://foo.test,https://foo.test/bob,Available,404,0.1\n"
    monkeypatch.setattr(BinAdapter, "exec_tool", _write_then(
        lambda cmd, kw: Path(cmd[cmd.index("--folderoutput") + 1]) / "bob.csv", csv_text))
    assert [r.url for r in sherlock.SherlockAdapter().run("bob")[1:]] == ["https://github.com/bob"]
    assert sherlock.parse_stdout("[+] GitHub: https://github.com/bob\n[*] done") == [
        {"site": "GitHub", "url": "https://github.com/bob"}]


def test_user_scanner_report(monkeypatch):
    rows = [{"status": "Found", "site_name": "GitHub", "url": "https://github.com/bob"},
            {"status": "Not Found", "site_name": "X", "url": "https://x.com/bob"}]
    monkeypatch.setattr(BinAdapter, "exec_tool", _write_then(
        lambda cmd, kw: Path(cmd[cmd.index("-o") + 1]), json.dumps(rows)))
    out = user_scanner.UserScannerAdapter().run("bob")
    assert [r.url for r in out[1:]] == ["https://github.com/bob"]


def test_holehe_output_parse_and_failure(monkeypatch):
    text = "[+] Email used, [-] Email not used, [x] Rate limit\n[+] instagram.com\n[-] x.com\n[+] spotify.com\n"
    assert holehe.parse_output(text) == ["instagram.com", "spotify.com"]
    monkeypatch.setattr(BinAdapter, "exec_tool", lambda self, cmd, **kw: _proc(text))
    assert len(holehe.HoleheAdapter().run("a@example.org")) == 3
    monkeypatch.setattr(BinAdapter, "exec_tool", lambda self, cmd, **kw: _proc("", 1, "Traceback"))
    with pytest.raises(EnrichmentError):
        holehe.HoleheAdapter().run("a@example.org")


def test_ghunt_extract_and_login_error(monkeypatch):
    data = {"PROFILE_CONTAINER": {"profile": {"personId": "1234", "names": {"PROFILE": {"fullname": "Jo Do"}},
                                              "profilePhotos": {"PROFILE": {"url": "https://lh3.test/p.jpg"}}}}}
    info = ghunt.extract(data)
    assert info == {"ids": ["1234"], "names": ["Jo Do"], "urls": ["https://lh3.test/p.jpg"]}
    monkeypatch.setattr(BinAdapter, "exec_tool", lambda self, cmd, **kw: _proc("Please run ghunt login", 1))
    with pytest.raises(NotConfiguredError, match="ghunt login"):
        ghunt.GhuntAdapter().run("a@gmail.com")


def test_gitrecon_parse():
    text = (" [+] Username: bob\n [+] Name: Bob B\n [+] Leaked email: Bob@Example.org\n"
            " [+] Id: 1\n [+] Key: ssh-ed25519 AAAA\n")
    parsed = gitrecon.parse_output(text)
    assert parsed["emails"] == ["bob@example.org"] and parsed["ssh_keys"] == ["ssh-ed25519 AAAA"]
    assert parsed["fields"]["name"] == "Bob B"


def test_telegram_phone_env_gate_and_parse(monkeypatch, tmp_path):
    for var in telegram_phone.REQUIRED_ENV:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr("shutil.which", lambda name: "/bin/true")
    with pytest.raises(NotConfiguredError, match="API_ID"):
        telegram_phone.TelegramPhoneAdapter().run("+14155552671")
    for var in telegram_phone.REQUIRED_ENV:
        monkeypatch.setenv(var, "x")
    monkeypatch.setenv("TELEGRAM_SESSION_DIR", str(tmp_path / "tg"))
    result = {"+14155552671": {"id": 42, "username": "jdoe", "first_name": "J", "last_name": "Doe"}}
    monkeypatch.setattr(BinAdapter, "exec_tool", _write_then(
        lambda cmd, kw: Path(cmd[cmd.index("--output") + 1]), json.dumps(result)))
    out = telegram_phone.TelegramPhoneAdapter().run("+1 415 555 2671")
    assert out[0].url == "https://t.me/jdoe" and out[0].tier == "T3"
