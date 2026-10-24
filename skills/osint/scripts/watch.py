#!/usr/bin/env python3
"""watch.py -- register URLs/profiles for change monitoring and poll them (bounded).

Backends:
  changedetection  changedetection.io REST API ($CHANGEDETECTION_URL,
                   $CHANGEDETECTION_API_KEY). The server does the polling; we read
                   each watch's last_changed timestamp and compare with what we saw.
  local            no server: fetch the URL ourselves, hash the normalised body
                   (scripts/styles stripped, whitespace collapsed), compare with the
                   last hash we stored.

Store (append-only, one JSON object per line):
  investigations/<case>/memory/watch.jsonl
    {"event": "add",  "url", "backend", "uuid", "label", "at"}
    {"event": "poll", "url", "status": "new|changed|unchanged|error", "sha256",
     "last_changed", "at", "error"}
    {"event": "remove", "url", "at"}
State is rebuilt by replaying the file, so history is never rewritten.

Usage:
  watch.py add <url> [--case C] [--label TEXT] [--backend auto|local|changedetection]
  watch.py list [--case C] [--json]
  watch.py poll [--case C] [--max N] [--deadline SECONDS] [--capture]
  watch.py remove <url> [--case C]

poll is bounded (loop exits): at most --max watches (default 50) and a total
wall-clock --deadline (default 300 s); each fetch times out at 20 s and reads at
most 5 MB. A "changed" result is a lead, not evidence: --capture routes every
changed URL through capture-evidence.sh --batch so it lands as an EV-NNNN item.

Optional alternative: a self-hosted sosse (https://gitlab.com/biolds/sosse,
AGPL, run as a separate service, never imported) can crawl + diff sites on a
schedule; point it at the same URLs and use its UI/API alongside this store.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

import active_case  # noqa: E402

USER_AGENT = "Mozilla/5.0 (workspace watch.py; change monitor)"
FETCH_TIMEOUT = 20
MAX_BYTES = 5 * 1024 * 1024
CAPTURE_SCRIPT = SCRIPT_DIR / "capture-evidence.sh"


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- store ----------

def store_path(case_dir: Path) -> Path:
    return case_dir / "memory" / "watch.jsonl"


def append_event(case_dir: Path, event: dict) -> None:
    path = store_path(case_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    event.setdefault("at", now_utc())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True) + "\n")


def load_state(case_dir: Path) -> dict[str, dict]:
    """Replay watch.jsonl into {url: state}. Malformed lines are skipped, not fatal."""
    state: dict[str, dict] = {}
    path = store_path(case_dir)
    if not path.is_file():
        return state
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        url = ev.get("url")
        if not url:
            continue
        kind = ev.get("event")
        if kind == "add":
            state[url] = {"url": url, "backend": ev.get("backend", "local"),
                          "uuid": ev.get("uuid", ""), "label": ev.get("label", ""),
                          "added": ev.get("at", ""), "sha256": None,
                          "last_changed": None, "last_status": "new", "last_checked": None}
        elif kind == "remove":
            state.pop(url, None)
        elif kind == "poll" and url in state:
            st = state[url]
            st["last_status"] = ev.get("status", "")
            st["last_checked"] = ev.get("at")
            if ev.get("sha256"):
                st["sha256"] = ev["sha256"]
            if ev.get("last_changed") is not None:
                st["last_changed"] = ev["last_changed"]
    return state


# ---------- local backend ----------

def fetch_url(url: str) -> bytes:
    """Fetch at most MAX_BYTES with a hard timeout. Tests replace this function."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        return resp.read(MAX_BYTES)


def normalise(body: bytes) -> str:
    text = body.decode("utf-8", "replace")
    text = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", text)
    text = re.sub(r"(?s)<!--.*?-->", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def content_hash(body: bytes) -> str:
    return hashlib.sha256(normalise(body).encode("utf-8")).hexdigest()


def poll_local(st: dict) -> dict:
    try:
        body = fetch_url(st["url"])
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"status": "error", "error": str(exc)[:300]}
    if not body.strip():
        return {"status": "error", "error": "empty body (fail-closed: not treated as a change)"}
    digest = content_hash(body)
    if st.get("sha256") is None:
        return {"status": "new", "sha256": digest}
    return {"status": "changed" if digest != st["sha256"] else "unchanged", "sha256": digest}


# ---------- changedetection.io backend ----------

def cd_config() -> tuple[str, str]:
    return os.environ.get("CHANGEDETECTION_URL", "").rstrip("/"), os.environ.get("CHANGEDETECTION_API_KEY", "")


def cd_request(method: str, path: str, payload: dict | None = None) -> dict:
    base, key = cd_config()
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(f"{base}/api/v1{path}", data=data, method=method,
                                 headers={"x-api-key": key, "Content-Type": "application/json",
                                          "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        raw = resp.read(MAX_BYTES).decode("utf-8", "replace")
    try:
        return json.loads(raw) if raw.strip() else {}
    except ValueError:
        return {"raw": raw}


def cd_add(url: str, label: str, tag: str) -> str:
    body = {"url": url, "title": label or url, "tag": tag}
    resp = cd_request("POST", "/watch", body)
    return str(resp.get("uuid") or resp.get("id") or resp.get("raw", "")).strip()


def poll_changedetection(st: dict) -> dict:
    if not st.get("uuid"):
        return {"status": "error", "error": "no changedetection uuid recorded"}
    try:
        info = cd_request("GET", f"/watch/{st['uuid']}")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {"status": "error", "error": str(exc)[:300]}
    last_changed = info.get("last_changed") or 0
    if st.get("last_changed") is None:
        return {"status": "new", "last_changed": last_changed}
    status = "changed" if last_changed and last_changed != st["last_changed"] else "unchanged"
    return {"status": status, "last_changed": last_changed}


# ---------- commands ----------

def choose_backend(requested: str) -> str:
    base, key = cd_config()
    if requested == "changedetection":
        if not (base and key):
            sys.exit("NotConfigured: set CHANGEDETECTION_URL and CHANGEDETECTION_API_KEY "
                     "(changedetection.io Settings > API)")
        return "changedetection"
    if requested == "local":
        return "local"
    return "changedetection" if base and key else "local"


def cmd_add(case: str, case_dir: Path, url: str, label: str, backend: str) -> int:
    if not re.match(r"^https?://", url):
        sys.exit("ERROR: url must start with http(s)://")
    if url in load_state(case_dir):
        print(f"already watching: {url}")
        return 0
    backend = choose_backend(backend)
    uuid = ""
    if backend == "changedetection":
        try:
            uuid = cd_add(url, label, case)
        except (urllib.error.URLError, OSError) as exc:
            sys.exit(f"ERROR: changedetection add failed: {exc}")
        if not uuid:
            sys.exit("ERROR: changedetection returned no uuid")
    append_event(case_dir, {"event": "add", "url": url, "backend": backend, "uuid": uuid, "label": label})
    print(f"watching ({backend}): {url}")
    return 0


def cmd_remove(case_dir: Path, url: str) -> int:
    if url not in load_state(case_dir):
        print(f"not watched: {url}")
        return 1
    append_event(case_dir, {"event": "remove", "url": url})
    print(f"removed: {url}")
    return 0


def cmd_list(case_dir: Path, as_json: bool) -> int:
    state = load_state(case_dir)
    if as_json:
        print(json.dumps(list(state.values()), indent=2))
        return 0
    if not state:
        print("(no watches)")
        return 0
    for st in state.values():
        print(f"{st['last_status']:<10} {st['backend']:<16} {st['last_checked'] or '-':<21} {st['url']}")
    return 0


def slug_for(url: str) -> str:
    s = re.sub(r"^https?://", "", url)
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return ("watch-" + s)[:60].rstrip("-")


def route_to_capture(case: str, changed: list[str]) -> int:
    """Write a capture batch TSV and run capture-evidence.sh --batch (fail-stop inside)."""
    fd, tsv = tempfile.mkstemp(prefix="watch-capture-", suffix=".tsv")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        for url in changed:
            fh.write(f"{url}\t{slug_for(url)}\t\t\twatch.py change detected {now_utc()}\n")
    print(f"[capture] {len(changed)} changed URL(s) -> capture-evidence.sh --batch {tsv}")
    return subprocess.call(["bash", str(CAPTURE_SCRIPT), "--batch", tsv, "--case", case])


def cmd_poll(case: str, case_dir: Path, max_items: int, deadline: float, capture: bool) -> int:
    state = load_state(case_dir)
    started = time.monotonic()
    changed: list[str] = []
    polled = 0
    for st in list(state.values())[:max_items]:
        if time.monotonic() - started > deadline:
            print(f"[poll] deadline {deadline:.0f}s reached; {len(state) - polled} watch(es) left for next run")
            break
        result = poll_changedetection(st) if st["backend"] == "changedetection" else poll_local(st)
        append_event(case_dir, {"event": "poll", "url": st["url"], **result})
        polled += 1
        print(f"{result['status']:<10} {st['url']}" + (f"  ({result['error']})" if result.get("error") else ""))
        if result["status"] == "changed":
            changed.append(st["url"])
    if len(state) > max_items:
        print(f"[poll] --max {max_items} reached; {len(state) - max_items} watch(es) not polled this run")
    print(f"[poll] polled {polled}, changed {len(changed)}")
    if capture and changed:
        return route_to_capture(case, changed)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Change monitoring for case URLs (changedetection.io or local).")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("url")
    a.add_argument("--label", default="")
    a.add_argument("--backend", choices=["auto", "local", "changedetection"], default="auto")
    r = sub.add_parser("remove")
    r.add_argument("url")
    li = sub.add_parser("list")
    li.add_argument("--json", action="store_true")
    po = sub.add_parser("poll")
    po.add_argument("--max", type=int, default=50)
    po.add_argument("--deadline", type=float, default=300.0)
    po.add_argument("--capture", action="store_true")
    for sp in (a, r, li, po):
        sp.add_argument("--case", default="")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    case, case_dir = active_case.resolve_case_dir(args.case)
    if args.cmd == "add":
        return cmd_add(case, case_dir, args.url, args.label, args.backend)
    if args.cmd == "remove":
        return cmd_remove(case_dir, args.url)
    if args.cmd == "list":
        return cmd_list(case_dir, args.json)
    return cmd_poll(case, case_dir, max(1, args.max), args.deadline, args.capture)


if __name__ == "__main__":
    sys.exit(main())
