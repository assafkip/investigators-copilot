#!/usr/bin/env python3
"""Offline language detection + translation. No external API, no LLM.

Detection: lingua (accurate on short marketplace posts).
Translation: Argos Translate (CTranslate2 engine); models are installed locally
by setup.sh and run fully offline.

Heavy libraries are imported lazily so the rest of the pipeline and the unit
tests run without the models installed. Call ensure_ready() before a real run.

Ported 2026-10-10 from assafkip/account-procurement-tools
(account-procurement-pipeline/src/lang_translate.py) into skills/telegram-harvest.
"""

# Languages we expect on these marketplaces. Detection is limited to this set
# for speed and short-text accuracy.
EXPECTED_LANGUAGES = [
    "ENGLISH", "RUSSIAN", "CHINESE", "VIETNAMESE", "SPANISH", "PORTUGUESE",
    "TURKISH", "UKRAINIAN", "GERMAN", "FRENCH", "INDONESIAN",
]

_detector = None


def _build_detector():
    """Build (once) a lingua detector limited to EXPECTED_LANGUAGES."""
    global _detector
    if _detector is not None:
        return _detector
    from lingua import Language, LanguageDetectorBuilder
    languages = [getattr(Language, name) for name in EXPECTED_LANGUAGES]
    _detector = LanguageDetectorBuilder.from_languages(*languages).build()
    return _detector


def detect_language(text):
    """Return (language_name, iso_639_1) for the text. Falls back to English."""
    if not text or not text.strip():
        return ("", "en")
    language = _build_detector().detect_language_of(text)
    if language is None:
        return ("", "en")
    return (language.name.capitalize(), language.iso_code_639_1.name.lower())


def translate_to_english(text, src_iso):
    """Translate text to English via Argos. Returns text unchanged if already English."""
    if not text or not text.strip() or src_iso == "en":
        return text
    import argostranslate.translate
    try:
        return argostranslate.translate.translate(text, src_iso, "en")
    except Exception:  # noqa: BLE001 -- missing model / unsupported pair: keep original
        return text


def ensure_ready():
    """Return (ok, missing[]) so the runner can fail loudly before scraping."""
    missing = []
    try:
        import lingua  # noqa: F401
    except ImportError:
        missing.append("lingua-language-detector")
    try:
        import argostranslate.translate  # noqa: F401
    except ImportError:
        missing.append("argostranslate")
    return (not missing, missing)
