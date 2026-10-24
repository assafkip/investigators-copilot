#!/usr/bin/env python3
"""Drive the vendored tgspyder CLI per target. No LLM, subprocess only.

tgspyder writes CSVs under '<workdir>/TGSpyder Output/'. We run it once per
target and read back the message + invite CSVs it produced.

Auth note: tgspyder authenticates interactively on first use and persists a
session. Run it once by hand (e.g. `tgspyder @somechannel --chats`) to log in
before batch runs, otherwise a fresh run will block waiting for a login code.

Ported 2026-10-10 from assafkip/account-procurement-tools
(account-procurement-pipeline/src/scrape.py) into skills/telegram-harvest.
"""

import csv
import subprocess
import sys
from pathlib import Path


def run_target(target, workdir, proxy=None, chats=True, invites=True, members=False):
    """Run tgspyder against one target. Returns the CompletedProcess."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    command = _base_command(target)
    if chats:
        command.append("--chats")
    if invites:
        command.append("--crawl-invites")
    if members:
        command.append("--members")
    if proxy:
        command += ["--proxy", proxy]

    return subprocess.run(command, cwd=str(workdir), check=False)


def _base_command(target):
    """Prefer the installed console script; fall back to `python -m tgspyder.cli`."""
    from shutil import which
    if which("tgspyder"):
        return ["tgspyder", target]
    return [sys.executable, "-m", "tgspyder.cli", target]


def newest_csv(workdir, subdir, prefix):
    """Return the most recently modified CSV matching prefix under the output subdir."""
    folder = Path(workdir) / "TGSpyder Output" / subdir
    if not folder.is_dir():
        return None
    candidates = sorted(folder.glob(f"{prefix}_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def read_messages(csv_path):
    """Read a tgspyder messages CSV into dicts: message_id, date, sender, text."""
    if not csv_path or not Path(csv_path).is_file():
        return []
    with open(csv_path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_invites(csv_path):
    """Read a tgspyder crawled_links CSV into a list of invite link strings."""
    if not csv_path or not Path(csv_path).is_file():
        return []
    with open(csv_path, newline="", encoding="utf-8") as handle:
        return [row["invite_link"] for row in csv.DictReader(handle) if row.get("invite_link")]
