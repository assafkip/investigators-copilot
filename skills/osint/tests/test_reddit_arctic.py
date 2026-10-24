"""reddit_arctic fallback order: arctic -> pullpush -> rss; failure raises."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "lib"))
import reddit_arctic as ra  # noqa: E402

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
 <entry><id>t1_abc</id><title>hello</title><updated>2026-10-01T00:00:00+00:00</updated>
  <author><name>/u/someone</name></author><category term="OSINT"/>
  <link href="https://www.reddit.com/r/OSINT/comments/x1/t/abc/"/>
  <content type="html">&lt;p&gt;body text&lt;/p&gt;</content></entry>
</feed>"""


def _get_factory(fail_hosts):
    calls = []

    def _get(url):
        calls.append(url)
        for host in fail_hosts:
            if host in url:
                raise OSError(f"down: {host}")
        return {"data": [{"id": "p1", "title": "t", "author": "someone", "subreddit": "OSINT",
                          "created_utc": 1700000000, "permalink": "/r/OSINT/comments/p1/t/"}]}
    return _get, calls


def test_user_history_prefers_arctic():
    _get, calls = _get_factory([])
    out = ra.user_history("someone", _get=_get)
    assert out["mirror"] == "arctic"
    assert "author=someone" in calls[0] and "arctic-shift" in calls[0]
    assert out["posts"][0]["author"] == "someone"


def test_user_history_falls_back_to_pullpush():
    _get, calls = _get_factory(["arctic-shift"])
    out = ra.user_history("someone", _get=_get)
    assert out["mirror"] == "pullpush"
    assert out["errors"] and out["errors"][0].startswith("arctic")


def test_user_history_falls_back_to_rss():
    _get, _ = _get_factory(["arctic-shift", "pullpush"])
    out = ra.user_history("u/someone", _get=_get, _get_text=lambda url: RSS)
    assert out["mirror"] == "rss"
    assert out["posts"][0]["subreddit"] == "OSINT"
    assert out["posts"][0]["body"] == "body text"


def test_every_route_down_raises_not_empty():
    _get, _ = _get_factory(["arctic-shift", "pullpush"])

    def bad_rss(url):
        raise OSError("rss down")
    with pytest.raises(ra.RedditFetchFailed):
        ra.user_history("someone", _get=_get, _get_text=bad_rss)


def test_unrecognised_body_is_failure():
    with pytest.raises(ra.RedditFetchFailed):
        ra._items({"error": "x"})
