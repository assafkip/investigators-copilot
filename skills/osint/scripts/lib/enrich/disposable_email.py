"""Disposable / throwaway email check, cross-checked across debounce.io and Kickbox. Keyless, T3.

Ported from hydra src/osint/disposable-email.ts. One provider failing is tolerated
(the verdict says "single source"); both failing raises.
"""
from __future__ import annotations

import urllib.parse

from . import _common as c
from .base import Adapter, EnrichmentError

_DEBOUNCE = "https://disposable.debounce.io/?email="
_KICKBOX = "https://open.kickbox.com/v1/disposable/"


def _as_bool(v):
    return v if isinstance(v, bool) else {"true": True, "false": False}.get(str(v).lower())


def _probe(url: str, timeout: int):
    try:
        body = c.get_json(url, timeout=timeout)
    except EnrichmentError as exc:
        return None, str(exc)
    return _as_bool((body or {}).get("disposable")), ""


class DisposableEmailAdapter(Adapter):
    slug = "disposable_email"
    display_name = "Disposable email check (debounce + kickbox)"
    category = "identity"
    tier = "T3"
    watched_types = ("email", "domain")

    def run(self, query, mode=None, timeout=20):
        addr = (query or "").strip().lower()
        if "@" not in addr and not c.DOMAIN_RE.match(addr):
            raise EnrichmentError(f"disposable_email: {query!r} is not an email or domain")
        email = addr if "@" in addr else f"probe@{addr}"
        deb, deb_err = _probe(_DEBOUNCE + urllib.parse.quote(email), timeout)
        kick, kick_err = _probe(_KICKBOX + urllib.parse.quote(email.split("@")[1]), timeout)
        if deb is None and kick is None:
            raise EnrichmentError(f"disposable_email: both providers failed ({deb_err}; {kick_err})")
        label = lambda v: "unknown" if v is None else ("disposable" if v else "not disposable")  # noqa: E731
        if deb is not None and kick is not None:
            verdict = f"both agree: {label(deb)}" if deb == kick else \
                f"DISAGREE: debounce={label(deb)}, kickbox={label(kick)} (inconclusive)"
        else:
            verdict = f"single source only: debounce={label(deb)}, kickbox={label(kick)}"
        return [c.res(self, "document", f"disposable check: {addr}", verdict,
                      raw_json={"debounce": deb, "kickbox": kick, "errors": [e for e in (deb_err, kick_err) if e]},
                      confidence="medium" if deb is not None and deb == kick else "low")]
