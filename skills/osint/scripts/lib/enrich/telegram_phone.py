"""Bellingcat telegram-phone-number-checker wrapper: phone -> Telegram account. T3.

Runs `telegram-phone-number-checker --phone-numbers <e164> --output <tmp>/r.json`
from TELEGRAM_SESSION_DIR (the Telethon session file lives there). Needs
API_ID, API_HASH (https://my.telegram.org) and PHONE_NUMBER (your own account),
plus a one-time interactive login run in that directory. stdin is closed, so a
missing session fails fast instead of waiting for a code.
The check imports the number as a contact and deletes it again: it is an ACTIVE
lookup that the target's privacy settings can defeat. Install:
pipx install telegram-phone-number-checker.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from ._identity_common import T3_NOTE, BinAdapter, lead
from .base import EnrichmentError, NotConfiguredError

REQUIRED_ENV = ("API_ID", "API_HASH", "PHONE_NUMBER")
PHONE_RE = re.compile(r"^\+?[0-9][0-9 ()./-]{5,20}$")


def session_dir() -> Path:
    return Path(os.environ.get("TELEGRAM_SESSION_DIR", "~/.config/copilot/telegram")).expanduser()


def result_rows(phone: str, entry: dict) -> list:
    if entry.get("error"):
        return [lead(f"Telegram: {phone} -- no account found", str(entry["error"])[:300],
                     raw=entry, rtype="document")]
    name = " ".join(x for x in (entry.get("first_name"), entry.get("last_name")) if x)
    username = entry.get("username")
    summary = (f"id: {entry.get('id')}\nusername: {username}\nname: {name}\n"
               f"last seen: {entry.get('user_was_online')}\n{T3_NOTE}")
    return [lead(f"Telegram: {phone} -> {username or entry.get('id')}" + (f" ({name})" if name else ""), summary,
                 url=f"https://t.me/{username}" if username else None, raw=entry, rtype="profile",
                 confidence="medium")]


class TelegramPhoneAdapter(BinAdapter):
    slug = "telegram_phone"
    display_name = "Telegram phone-number checker (bellingcat, subprocess)"
    requires_bin = ("telegram-phone-number-checker",)
    install_name = "telegram-phone-number-checker"
    env_var = "API_ID"
    signup_url = "https://my.telegram.org (API_ID, API_HASH) + PHONE_NUMBER"
    keyless = False
    watched_types = ("phone",)
    license_note = "MIT; invoked as a subprocess"

    def missing(self):
        gaps = super().missing()
        return gaps + [f"${v}" for v in REQUIRED_ENV[1:] if not os.environ.get(v, "").strip()]

    def run(self, query, mode=None, timeout=120):
        phone = re.sub(r"[ ()./-]", "", (query or "").strip())
        if not PHONE_RE.match(phone):
            raise EnrichmentError(f"telegram_phone: not a phone number: {query!r}")
        absent = [v for v in REQUIRED_ENV if not os.environ.get(v, "").strip()]
        if absent:
            raise NotConfiguredError(f"telegram_phone: set {', '.join('$' + v for v in absent)} ({self.signup_url})")
        workdir = session_dir()
        workdir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "r.json"
            proc = self.exec_tool(["telegram-phone-number-checker", "--phone-numbers", phone,
                                   "--output", str(out)], timeout=timeout, cwd=str(workdir))
            if not out.is_file():
                raise self.fail(proc, "no results file (session not logged in? run the tool once by hand "
                                      f"in {workdir})")
            try:
                data = json.loads(out.read_text())
            except json.JSONDecodeError as exc:
                raise EnrichmentError("telegram_phone: unreadable results file") from exc
        entry = next(iter(data.values()), None) if isinstance(data, dict) else None
        if not isinstance(entry, dict):
            raise EnrichmentError("telegram_phone: unexpected results shape")
        return result_rows(phone, entry)
