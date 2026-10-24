#!/usr/bin/env python3
"""Rule-based extraction of account-sale listings from Telegram message text.

Pure stdlib. No LLM, no network. Deterministic and unit-tested. This is the
programmatic replacement for the LLM parsing step: it reads keyword
dictionaries from config/keywords.json and pulls structured fields out of a
raw (or translated) marketplace post.

It deliberately does NOT decide account/actor country. That is a human
judgment call (see geo_clues.py for the clues it surfaces instead).

Ported 2026-10-10 from assafkip/account-procurement-tools
(account-procurement-pipeline/src/extract.py) into skills/telegram-harvest.
"""

import re
import json
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

# Currency amounts: symbol-first ($50, ₽1 000) or number-first (50$, 50 usd, 300 руб).
PRICE_RE = re.compile(
    r"(?:[$€£₽¥₫]\s?\d[\d.,\s]*\d|\b\d[\d.,\s]*\d?\s?(?:[$€£₽¥₫]|usd|eur|gbp|rub|руб|dong|vnd|rmb|cny|元))",
    re.IGNORECASE,
)
HANDLE_RE = re.compile(r"@[A-Za-z0-9_]{4,32}")
TME_RE = re.compile(r"(?:https?://)?t\.me/(?:joinchat/|\+)?[A-Za-z0-9_/+-]+", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19[9]\d|20[0-2]\d)\b")


def load_keywords(path=None):
    """Load the keyword dictionaries. Raises with a clear message if missing."""
    path = Path(path) if path else CONFIG_DIR / "keywords.json"
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise FileNotFoundError(f"keyword config not found at {path}")
    except json.JSONDecodeError as error:
        raise ValueError(f"keyword config at {path} is not valid JSON: {error}")


def _match_term(text_lower, term):
    """Match one term. Short/ascii terms need word boundaries; long or CJK use substring."""
    term_lower = term.lower()
    if len(term_lower) <= 4 and term_lower.isascii():
        return re.search(r"(?<![a-z0-9])" + re.escape(term_lower) + r"(?![a-z0-9])", text_lower) is not None
    return term_lower in text_lower


def _first_matching_term(text_lower, terms):
    """Return the most specific matched term (longest first), or empty string."""
    for term in sorted(terms, key=len, reverse=True):
        if _match_term(text_lower, term):
            return term
    return ""


def detect_account_type(text_lower, keywords):
    """Return the display label of the first account type found, or empty string."""
    for label, terms in keywords["account_types"].items():
        if _first_matching_term(text_lower, terms):
            return label
    return ""


def detect_flags(text_lower, keywords):
    """Return {flag_label: matched_term} for every flag present."""
    found = {}
    for label, terms in keywords["flags"].items():
        matched = _first_matching_term(text_lower, terms)
        if matched:
            found[label] = matched
    return found


def extract_prices(text):
    """Return every price-like token, whitespace-normalised."""
    return [re.sub(r"\s+", " ", match).strip() for match in PRICE_RE.findall(text)]


def extract_handles(text):
    """Return unique @usernames in first-seen order."""
    return _dedupe(HANDLE_RE.findall(text))


def extract_links(text):
    """Return unique t.me and http(s) links in first-seen order."""
    links = TME_RE.findall(text) + URL_RE.findall(text)
    return _dedupe(link.rstrip(".,)") for link in links)


def extract_quantity(text_lower, keywords):
    """Return a number sitting next to a stock/quantity word, or empty string."""
    for term in keywords["quantity_terms"]:
        if not _match_term(text_lower, term):
            continue
        window = re.escape(term.lower())
        near = re.search(window + r"[^\d]{0,8}(\d{1,6})", text_lower) or \
            re.search(r"(\d{1,6})[^\d]{0,8}" + window, text_lower)
        if near:
            return near.group(1)
    return ""


def extract_first_term(text_lower, keywords, key):
    """Return the first matched term for a simple term-list config key."""
    return _first_matching_term(text_lower, keywords.get(key, []))


def extract_year(text):
    """Return the first plausible account-age year, or empty string."""
    match = YEAR_RE.search(text)
    return match.group(1) if match else ""


def is_listing(text_lower, keywords):
    """A message is a candidate listing only if it names one of the target account types."""
    return bool(detect_account_type(text_lower, keywords))


def extract_listing(original_text, english_text, keywords):
    """Pull all structured fields from one message.

    Matches keywords against original + translated text so local-language and
    English terms both hit. Returns a flat dict of column values.
    """
    combined = ((original_text or "") + "\n" + (english_text or "")).lower()
    flags = detect_flags(combined, keywords)
    prices = extract_prices((original_text or "") + " " + (english_text or ""))

    return {
        "account_type": detect_account_type(combined, keywords),
        "verified": flags.get("Verified", ""),
        "farmed": flags.get("Farmed", ""),
        "payment_attached": flags.get("Payment Attached", ""),
        "pin": flags.get("PIN", ""),
        "cost": prices[0] if prices else "",
        "all_prices": prices,
        "quantity": extract_quantity(combined, keywords),
        "payment_method": extract_first_term(combined, keywords, "payment_methods"),
        "transfer_method": extract_first_term(combined, keywords, "transfer_terms"),
        "spend": extract_first_term(combined, keywords, "spend_terms"),
        "history": extract_first_term(combined, keywords, "history_terms"),
        "age": extract_first_term(combined, keywords, "age_terms") or extract_year(original_text or ""),
        "handles": extract_handles((original_text or "") + " " + (english_text or "")),
        "links": extract_links((original_text or "") + " " + (english_text or "")),
    }


def _dedupe(items):
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
