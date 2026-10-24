"""Phone intel: region / original carrier / line type, fully offline. Keyless, T3.

Ported from assafkip/kipi investigations/enrich/phone.py. Uses Google's
libphonenumber metadata (`phonenumbers`, imported lazily). Missing library ->
NotConfiguredError (install: pip install phonenumbers).

Carrier is the ORIGINAL allocation from the numbering plan; number porting is not
reflected. This parses a number, it does not tie it to a person: a phone used as
an identity anchor needs an independent second source (q-investigation.md).
"""
from __future__ import annotations

import importlib.util

from ._identity_common import SETUP_HINT, T3_NOTE, lead
from .base import Adapter, EnrichmentError, NotConfiguredError

LINE_TYPES = {0: "FIXED_LINE", 1: "MOBILE", 2: "FIXED_LINE_OR_MOBILE", 3: "TOLL_FREE",
              4: "PREMIUM_RATE", 5: "SHARED_COST", 6: "VOIP", 7: "PERSONAL_NUMBER",
              8: "PAGER", 9: "UAN", 10: "VOICEMAIL", 27: "UNKNOWN"}


def _import_phonenumbers():
    try:
        import phonenumbers
        from phonenumbers import carrier, geocoder
    except ImportError as exc:
        raise NotConfiguredError("phone: python package phonenumbers missing (pip install phonenumbers; "
                                 + SETUP_HINT.format(name="phonenumbers") + ")") from exc
    return phonenumbers, carrier, geocoder


def describe_number(raw: str) -> dict:
    phonenumbers, carrier, geocoder = _import_phonenumbers()
    try:
        parsed = phonenumbers.parse(raw, None)
    except phonenumbers.NumberParseException as exc:
        raise EnrichmentError(f"phone: cannot parse {raw!r} ({exc}); use E.164 (+<cc>...)") from exc
    if not phonenumbers.is_valid_number(parsed):
        return {"input": raw, "valid": False}
    return {"input": raw, "valid": True,
            "e164": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
            "international": phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL),
            "country": phonenumbers.region_code_for_number(parsed) or "",
            "region": geocoder.description_for_number(parsed, "en") or "",
            "carrier": carrier.name_for_number(parsed, "en") or "",
            "line_type": LINE_TYPES.get(phonenumbers.number_type(parsed), "UNKNOWN")}


class PhoneAdapter(Adapter):
    slug = "phone"
    display_name = "Phone intel (libphonenumber, offline)"
    category = "identity"
    tier = "T3"
    watched_types = ("phone",)

    def missing(self):
        gaps = super().missing()
        if importlib.util.find_spec("phonenumbers") is None:
            gaps.append("py:phonenumbers")
        return gaps

    def run(self, query, mode=None, timeout=10):
        raw = (query or "").strip()
        if not raw:
            raise EnrichmentError("phone: empty number")
        info = describe_number(raw)
        if not info["valid"]:
            return [lead(f"phone: {raw} -- invalid", "Not a valid number per libphonenumber metadata.",
                         raw=info, rtype="document", confidence="low")]
        voip = "\nVoIP line: a common disposable/fraud signal." if info["line_type"] == "VOIP" else ""
        summary = (f"E.164: {info['e164']}\ncountry: {info['country']}\nregion: {info['region']}\n"
                   f"carrier (original allocation): {info['carrier'] or 'unknown'}\n"
                   f"line type: {info['line_type']}{voip}\n{T3_NOTE}")
        rows = [lead(f"phone: {info['e164']} -- {info['region'] or info['country']}, {info['line_type']}",
                     summary, raw=info, rtype="document", confidence="high")]
        if info["carrier"]:
            rows.append(lead(info["carrier"], f"Original carrier for {info['e164']} ({info['line_type']}).",
                             rtype="record", confidence="medium"))
        return rows
