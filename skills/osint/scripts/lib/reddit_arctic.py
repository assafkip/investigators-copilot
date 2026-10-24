"""Reddit reads, through the Arctic Shift archive mirror. Self-contained.

VENDORED into Investigators Copilot 2026-10-10 from assafkip/kipi
`investigations/enrich/reddit_arctic.py` (upstream of that: kipi-core
`reddit_arctic/transport.py`). Investigators Copilot additions, marked below: author
(user-history) reads, and a Reddit RSS last resort taken from reddit-build-radar
`collectors.py` for when BOTH mirrors refuse (seen 2026-10-10: Arctic Shift 522
from cloud egress, PullPush 429).

## Why the mirror and not reddit.com

Arctic Shift is a free archive mirror of Reddit. No auth, no app approval, no
rate-limit dance. Every other route was tried and each one closed:

    www.reddit.com/...json     403 from any datacenter IP.
    .rss listing feeds         throttled. 3s pacing returned 429 on 11 of 12
                               requests; 10s ran clean, which is a rate nobody
                               wants to harvest at.
    old.reddit.com HTML        throttled the same way, and it is a scrape.
    the official OAuth API     app creation is gated behind an approval process
                               that did not come through.
    a paid Apify actor         worked, at roughly 60 to 90 seconds per subreddit
                               through a residential proxy, against a run
                               timeout that only fit two or three rooms.

## The one rule worth keeping if you change anything here

A FAILED READ RAISES. It never returns an empty list. An empty list is what a
quiet subreddit looks like, so returning it for a failure makes a dead mirror
and a boring week the same value, and nothing downstream can tell them apart
afterwards. Four separate copies of this code drifted into doing that before
this rule was written down.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.parse
import urllib.request

ARCTIC_BASE = "https://arctic-shift.photon-reddit.com"
PULLPUSH_BASE = "https://api.pullpush.io"

# Identify honestly. The mirror needs no auth and no costume, so there is
# nothing to gain by pretending to be a browser.
USER_AGENT = os.environ.get(
    "REDDIT_UA", "reddit-arctic-reader/1.0 (automated research; contact via repo)")

DEFAULT_TIMEOUT = 45
MAX_LIMIT = 100          # the mirror's own ceiling; asking past it truncates


class RedditFetchFailed(RuntimeError):
    """Every mirror refused. Raised, never returned as an empty list."""


class ReadDeadlineExceeded(Exception):
    """A CALLER ran out of its own time budget. Distinct from a socket timeout,
    which is a host problem and takes the ordinary fallback."""


def _clean_sub(subreddit: str) -> str:
    return (subreddit or "").lstrip("/").removeprefix("r/").strip().rstrip("/")


def _get_json(url: str, timeout: int, _opener=None, _get=None):
    if _get is not None:
        return _get(url)
    opener = _opener or urllib.request.urlopen
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with opener(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _items(payload) -> list:
    """An UNRECOGNISED body is a failure, not an empty room.

    A 200 carrying an error object, an HTML interstitial or a renamed field used
    to read as "no results", which is the same lie as returning [] on a refusal.
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return data
        if data is None and not payload:
            return []
    raise RedditFetchFailed(
        "unrecognised mirror body (%s); refusing to read it as an empty result"
        % type(payload).__name__)


def arctic_url(subreddit: str, limit: int, *, after: str = "",
               before: str = "") -> str:
    q = {"subreddit": _clean_sub(subreddit), "limit": min(limit, MAX_LIMIT),
         "sort": "desc"}
    if after:
        q["after"] = after
    # `before` is the cursor for a DESCENDING page, measured rather than
    # assumed: the last row's created_utc passed as `after` returns rows that
    # OVERLAP the page you already have; passed as `before` it returns strictly
    # older ones.
    if before:
        q["before"] = before
    return f"{ARCTIC_BASE}/api/posts/search?{urllib.parse.urlencode(q)}"


def pullpush_url(subreddit: str, limit: int) -> str:
    q = {"subreddit": _clean_sub(subreddit), "size": min(limit, MAX_LIMIT),
         "sort": "desc"}
    return f"{PULLPUSH_BASE}/reddit/search/submission?{urllib.parse.urlencode(q)}"


def comments_url(link_id: str, limit: int = MAX_LIMIT) -> str:
    q = {"link_id": str(link_id).removeprefix("t3_"),
         "limit": min(limit, MAX_LIMIT), "sort": "asc",
         "fields": "id,created_utc,author,parent_id,body,score"}
    return f"{ARCTIC_BASE}/api/comments/search?{urllib.parse.urlencode(q)}"


def link_id_from_permalink(permalink: str) -> str:
    """`/r/x/comments/<id>/slug/` -> `<id>`. Accepts a bare id and a full url."""
    text = str(permalink or "").strip()
    if "/comments/" in text:
        return text.split("/comments/", 1)[1].split("/", 1)[0].split("?", 1)[0]
    return text.strip("/").split("/")[-1].split("?", 1)[0].removeprefix("t3_")


def fetch_posts(subreddit: str, *, limit: int = MAX_LIMIT, after: str = "",
                before: str = "", timeout: int = DEFAULT_TIMEOUT,
                _opener=None, _get=None):
    """Arctic Shift first, PullPush second. Returns (raw posts, which mirror).

    The fallback is a DIFFERENT HOST, which is what makes it a fallback rather
    than a retry of the thing that just failed.
    """
    try:
        return _items(_get_json(arctic_url(subreddit, limit, after=after,
                                           before=before),
                                timeout, _opener, _get)), "arctic"
    except ReadDeadlineExceeded:
        raise
    except Exception as arctic_exc:
        try:
            return _items(_get_json(pullpush_url(subreddit, limit),
                                    timeout, _opener, _get)), "pullpush"
        except ReadDeadlineExceeded:
            raise
        except Exception as pullpush_exc:
            raise RedditFetchFailed(
                "both mirrors refused r/%s: arctic=%s: %s; pullpush=%s: %s"
                % (_clean_sub(subreddit), type(arctic_exc).__name__, arctic_exc,
                   type(pullpush_exc).__name__, pullpush_exc))


def comments(link_id: str, *, limit: int = MAX_LIMIT,
             timeout: int = DEFAULT_TIMEOUT, _opener=None, _get=None) -> list:
    """Every comment on one thread, oldest first. Raises on a refused read: an
    empty list is a QUIET thread and must never be a broken fetch wearing one."""
    try:
        return _items(_get_json(comments_url(link_id, limit), timeout,
                                _opener, _get))
    except ReadDeadlineExceeded:
        raise
    except RedditFetchFailed:
        raise
    except Exception as exc:
        raise RedditFetchFailed("mirror refused comments for %s: %s: %s"
                                % (link_id, type(exc).__name__, exc))


def normalize(record: dict, subreddit: str = "", term: str = "") -> dict:
    """One shape for every consumer, using Reddit's OWN field names.

    Bodies are always carried: the useful signal is in bodies, not titles.
    `created` is emitted as an ISO string because the mirror hands back a unix
    float and every consumer wants the string.
    """
    created = record.get("created_utc") or record.get("created")
    if isinstance(created, (int, float)):
        created = dt.datetime.fromtimestamp(created, dt.timezone.utc).isoformat()
    permalink = record.get("permalink") or ""
    return {
        "id": record.get("id") or "",
        "subreddit": record.get("subreddit") or _clean_sub(subreddit),
        "matched_term": term,
        "title": (record.get("title") or "").strip(),
        "body": record.get("selftext") or record.get("body") or "",
        "url": (record.get("url")
                if str(record.get("url", "")).startswith("https://www.reddit.com")
                else ("https://www.reddit.com" + permalink if permalink
                      else record.get("url") or "")),
        "permalink": permalink,
        "created": created or "",
        "score": record.get("score") if record.get("score") is not None else 0,
        "num_comments": record.get("num_comments") or 0,
        "author": record.get("author") or "",
    }


def recent(subreddit: str, *, max_items: int = 60,
           timeout: int = DEFAULT_TIMEOUT, _opener=None, _get=None,
           **_ignored) -> list:
    """One room's recent posts, normalized, newest first.

    A thin result here is a QUIET ROOM and can be trusted as one. Pages past the
    mirror's 100 ceiling rather than silently handing back the ceiling.

    `**_ignored` swallows arguments the retired Apify path needed (`token`,
    `with_counts`). The mirror needs no auth and returns comment counts free, so
    they are accepted and unused rather than removed, and a caller still passing
    them does not crash.
    """
    raw, mirror = fetch_posts(subreddit, limit=min(max_items, MAX_LIMIT),
                              timeout=timeout, _opener=_opener, _get=_get)
    if max_items > MAX_LIMIT and len(raw) >= MAX_LIMIT:
        seen = {r.get("id") for r in raw}
        cursor = None
        for _ in range(20):                 # a real ceiling, not a while True
            last = raw[-1].get("created_utc")
            nxt = (last + 1) if isinstance(last, (int, float)) else None
            if nxt is None or nxt == cursor:
                break
            cursor = nxt
            page, _m = fetch_posts(subreddit, limit=MAX_LIMIT,
                                   before=str(cursor), timeout=timeout,
                                   _opener=_opener, _get=_get)
            fresh = [r for r in page if r.get("id") not in seen]
            seen.update(r.get("id") for r in fresh)
            raw.extend(fresh)
            if len(raw) >= max_items or len(page) < MAX_LIMIT:
                break
        raw = raw[:max_items]
    out = []
    for record in raw:
        post = normalize(record, subreddit, "")
        post["mirror"] = mirror
        out.append(post)
    return out


# ---------------------------------------------------------------------------
# Investigators Copilot additions: user history + RSS last resort
# ---------------------------------------------------------------------------

def _clean_user(username: str) -> str:
    return (username or "").strip().lstrip("/").removeprefix("u/").removeprefix("user/").strip("/")


def author_url(kind: str, username: str, limit: int, *, before: str = "") -> str:
    """kind is "posts" or "comments". Arctic Shift supports author= on both."""
    q = {"author": _clean_user(username), "limit": min(limit, MAX_LIMIT), "sort": "desc"}
    if before:
        q["before"] = before
    return f"{ARCTIC_BASE}/api/{kind}/search?{urllib.parse.urlencode(q)}"


def pullpush_author_url(kind: str, username: str, limit: int) -> str:
    path = "submission" if kind == "posts" else "comment"
    q = {"author": _clean_user(username), "size": min(limit, MAX_LIMIT), "sort": "desc"}
    return f"{PULLPUSH_BASE}/reddit/search/{path}?{urllib.parse.urlencode(q)}"


def rss_url(*, subreddit: str = "", username: str = "") -> str:
    if username:
        return f"https://www.reddit.com/user/{urllib.parse.quote(_clean_user(username))}/.rss"
    return f"https://www.reddit.com/r/{urllib.parse.quote(_clean_sub(subreddit))}/new/.rss"


def _fetch_text(url: str, timeout: int, _opener=None, _get_text=None) -> str:
    if _get_text is not None:
        return _get_text(url)
    opener = _opener or urllib.request.urlopen
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with opener(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def rss_records(text: str) -> list:
    """Parse a Reddit Atom feed into normalized-ish records.

    RSS carries no score or comment count, and bodies are HTML. Each record is
    marked mirror="rss" so a consumer can tell a degraded read from a full one.
    An unparseable feed RAISES, same rule as the mirrors.
    """
    import html as _html
    import re as _re
    from xml.etree import ElementTree
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise RedditFetchFailed(f"unparseable RSS body: {exc}")
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    out = []
    for entry in root.findall("atom:entry", ns):
        link = entry.find("atom:link", ns)
        url = link.get("href", "") if link is not None else ""
        author = entry.findtext("atom:author/atom:name", default="", namespaces=ns)
        cat = entry.find("atom:category", ns)
        content = entry.findtext("atom:content", default="", namespaces=ns)
        body = _re.sub(r"<[^>]+>", " ", _html.unescape(content))
        out.append({
            "id": (entry.findtext("atom:id", default="", namespaces=ns) or "").removeprefix("t3_").removeprefix("t1_"),
            "subreddit": cat.get("term", "") if cat is not None else "",
            "matched_term": "",
            "title": (entry.findtext("atom:title", default="", namespaces=ns) or "").strip(),
            "body": _re.sub(r"\s+", " ", body).strip(),
            "url": url,
            "permalink": url.replace("https://www.reddit.com", ""),
            "created": entry.findtext("atom:updated", default="", namespaces=ns) or "",
            "score": None,
            "num_comments": None,
            "author": author.removeprefix("/u/"),
            "mirror": "rss",
        })
    return out


def user_history(username: str, *, max_items: int = 100,
                 timeout: int = DEFAULT_TIMEOUT, _opener=None, _get=None,
                 _get_text=None) -> dict:
    """Posts + comments by one author. Arctic, then PullPush, then RSS.

    Returns {"posts": [...], "comments": [...], "mirror": str, "errors": [...]}.
    Raises RedditFetchFailed only when every route refused. An empty result
    from a route that ANSWERED is a real "no public activity".
    """
    errors = []
    for mirror, build in (("arctic", author_url), ("pullpush", pullpush_author_url)):
        try:
            posts = _items(_get_json(build("posts", username, max_items), timeout, _opener, _get))
            comments_ = _items(_get_json(build("comments", username, max_items), timeout, _opener, _get))
        except ReadDeadlineExceeded:
            raise
        except Exception as exc:
            errors.append(f"{mirror}: {type(exc).__name__}: {exc}")
            continue
        norm = lambda r: dict(normalize(r), mirror=mirror)  # noqa: E731
        return {"posts": [norm(r) for r in posts], "comments": [norm(r) for r in comments_],
                "mirror": mirror, "errors": errors}
    try:
        items = rss_records(_fetch_text(rss_url(username=username), timeout, _opener, _get_text))
    except Exception as exc:
        errors.append(f"rss: {type(exc).__name__}: {exc}")
        raise RedditFetchFailed("every route refused u/%s: %s" % (_clean_user(username), "; ".join(errors)))
    return {"posts": items, "comments": [], "mirror": "rss", "errors": errors,
            "note": "RSS fallback: posts and comments mixed, no scores, latest ~25 only"}


def recent_with_rss(subreddit: str, *, max_items: int = 60, timeout: int = DEFAULT_TIMEOUT,
                    _opener=None, _get=None, _get_text=None) -> list:
    """recent() with the RSS feed as a third route."""
    try:
        return recent(subreddit, max_items=max_items, timeout=timeout, _opener=_opener, _get=_get)
    except RedditFetchFailed as mirrors_exc:
        try:
            return rss_records(_fetch_text(rss_url(subreddit=subreddit), timeout, _opener, _get_text))[:max_items]
        except Exception as rss_exc:
            raise RedditFetchFailed(f"{mirrors_exc}; rss={type(rss_exc).__name__}: {rss_exc}")
