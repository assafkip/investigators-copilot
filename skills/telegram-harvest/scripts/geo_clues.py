#!/usr/bin/env python3
"""Gather geo CLUES from a listing. Never decides the country.

By design, account/actor country is inferred by a human
from (1) the language used, (2) the Telegram account location, and (3) what the
seller says. This module surfaces those clues so the analyst can fill
"Geo of Acc." and "Ecosystem (Geo)" themselves. It does not guess.

Ported 2026-10-10 from assafkip/account-procurement-tools
(account-procurement-pipeline/src/geo_clues.py) into skills/telegram-harvest.
"""

import re
import json
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# Uppercase 2-letter country codes matched case-sensitively against original text.
# Sellers write "US accounts" / "UK acc" in caps; low-noise, high-value clue.
# 'IN' is deliberately excluded (collides with the English word) -- India still
# matches via its name/demonym terms in countries.json.
COUNTRY_CODES = {
    "US": "United States", "UK": "United Kingdom", "RU": "Russia", "ES": "Spain",
    "PE": "Peru", "AR": "Argentina", "VN": "Vietnam", "CN": "China",
    "DE": "Germany", "FR": "France", "BR": "Brazil", "ID": "Indonesia",
    "PH": "Philippines", "TR": "Turkey", "UA": "Ukraine",
}

# Minimal dialing-code -> country map for the phone clue (from tgspyder member CSV).
PHONE_PREFIXES = {
    "1": "United States/Canada", "7": "Russia/Kazakhstan", "34": "Spain",
    "51": "Peru", "54": "Argentina", "44": "United Kingdom", "49": "Germany",
    "33": "France", "55": "Brazil", "91": "India", "62": "Indonesia",
    "63": "Philippines", "90": "Turkey", "380": "Ukraine", "84": "Vietnam",
    "86": "China",
}


def load_countries(path=None):
    path = Path(path) if path else CONFIG_DIR / "countries.json"
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise FileNotFoundError(f"country config not found at {path}")
    except json.JSONDecodeError as error:
        raise ValueError(f"country config at {path} is not valid JSON: {error}")


def _mentions(text_lower, term):
    term_lower = term.lower()
    if len(term_lower) <= 4 and term_lower.isascii():
        return re.search(r"(?<![a-z0-9])" + re.escape(term_lower) + r"(?![a-z0-9])", text_lower) is not None
    return term_lower in text_lower


def find_country_mentions(text, countries):
    """Return every country whose name/demonym/local term appears in the text."""
    text_lower = (text or "").lower()
    found = []
    for country, terms in countries.items():
        if any(_mentions(text_lower, term) for term in terms):
            found.append(country)
    return found


def find_code_mentions(text):
    """Return countries named by an uppercase 2-letter code (case-sensitive)."""
    found = []
    for code, country in COUNTRY_CODES.items():
        if re.search(r"(?<![A-Za-z0-9])" + code + r"(?![A-Za-z0-9])", text or ""):
            found.append(country)
    return found


def phone_country(phone):
    """Best-effort country from a phone dialing prefix. Empty if unknown."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    for length in (3, 2, 1):
        prefix = digits[:length]
        if prefix in PHONE_PREFIXES:
            return PHONE_PREFIXES[prefix]
    return ""


def gather_clues(original_text, english_text, detected_language, countries):
    """Bundle the geo clues for one listing. All fields are clues, not verdicts."""
    mentioned = find_country_mentions(original_text, countries)
    others = (
        find_country_mentions(english_text, countries)
        + find_code_mentions(original_text)
        + find_code_mentions(english_text)
    )
    for country in others:
        if country not in mentioned:
            mentioned.append(country)
    return {
        "language": detected_language or "",
        "country_words": mentioned,
    }
