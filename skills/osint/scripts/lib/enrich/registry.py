"""Adapter registry: discovers every Adapter subclass in this package.

No central import list to edit. A module that fails to import (missing optional
dependency) is recorded in IMPORT_ERRORS and skipped, never silently dropped:
`osint-tool.py --list` and diagnose.sh print those errors.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil

from . import base

_ADAPTERS: dict[str, type[base.Adapter]] = {}
IMPORT_ERRORS: dict[str, str] = {}
_LOADED = False

_SKIP = {"base", "registry", "__init__"}


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    pkg = importlib.import_module(__package__)
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name in _SKIP or info.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"{__package__}.{info.name}")
        except Exception as exc:  # recorded, surfaced by --list
            IMPORT_ERRORS[info.name] = f"{type(exc).__name__}: {exc}"
            continue
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, base.Adapter) and obj is not base.Adapter and obj.slug:
                if obj.slug in _ADAPTERS and _ADAPTERS[obj.slug] is not obj:
                    raise RuntimeError(f"duplicate adapter slug {obj.slug!r} in {info.name}")
                _ADAPTERS[obj.slug] = obj
    _LOADED = True


def slugs() -> list[str]:
    _load()
    return sorted(_ADAPTERS)


def get_adapter(slug: str) -> base.Adapter:
    _load()
    if slug not in _ADAPTERS:
        raise KeyError(slug)
    return _ADAPTERS[slug]()


def describe_all() -> list[dict]:
    _load()
    return [get_adapter(s).describe() for s in slugs()]
