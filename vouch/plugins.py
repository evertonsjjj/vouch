"""Plugin discovery via setuptools ``entry_points``.

vouch picks up three plugin groups installed in the user's Python environment:

* ``vouch.adapters`` — per-site or per-pattern adapters. Each entry's value
  is a callable returning an instance that implements :class:`SiteAdapter`
  (or a class that can be instantiated as such).
* ``vouch.routers`` — alternative :class:`Router` strategies.
* ``vouch.profiles`` — community-published profile registries. Each entry
  resolves to a function returning a :class:`ProfileRegistry`, which is
  merged into the default registry on import.

Convention for adapter plugins
------------------------------
The entry point **name** is a domain pattern. It can be:

  - an exact host: ``arxiv.org``
  - a wildcard suffix: ``*.gov.br``
  - or ``*`` for a fallback that wants to handle every site (rare; prefer
    targeted plugins).

The first matching plugin wins. Order: exact match → most specific suffix →
``*``. Internal adapters (HTTPAdapter, BrowserAdapter) are still the last
resort if no plugin claims the site.

Distribution example
--------------------
A third-party plugin ``vouch-adapter-arxiv`` declares in its pyproject.toml::

    [project.entry-points."vouch.adapters"]
    "arxiv.org" = "vouch_adapter_arxiv:make"

Where ``make`` is::

    def make(*, config, llm=None, selector_cache=None, pool=None, **kw):
        return ArxivAdapter(config=config, llm=llm, selector_cache=selector_cache)

That's it — ``pip install vouch-adapter-arxiv`` and the next ``SearchEngine``
in any user's project picks it up automatically.
"""

from __future__ import annotations

import logging
from importlib.metadata import EntryPoint, entry_points
from typing import Any

log = logging.getLogger("vouch.plugins")


# ----------------------------------------------------------------------
# Generic loader
# ----------------------------------------------------------------------


def _load(group: str) -> list[EntryPoint]:
    """Return all entry points in ``group`` installed in this environment."""
    return list(entry_points(group=group))


# ----------------------------------------------------------------------
# Adapter plugins
# ----------------------------------------------------------------------


def find_adapter_factory(host: str) -> Any | None:
    """Find a plugin willing to handle ``host``. Returns the loaded callable.

    Match precedence:
      1. exact host (``arxiv.org``)
      2. most-specific suffix wildcard (``*.gov.br`` beats ``*.br``)
      3. universal fallback (``*``)
    """
    host = host.lower()
    exact: Any | None = None
    suffixes: list[tuple[int, EntryPoint]] = []
    wildcard: Any | None = None

    for ep in _load("vouch.adapters"):
        name = ep.name.lower()
        if name == host:
            exact = ep
            break
        if name == "*":
            wildcard = ep
            continue
        if name.startswith("*.") and host.endswith(name[1:]):
            suffixes.append((len(name), ep))

    chosen: EntryPoint | None = exact
    if chosen is None and suffixes:
        # Longest suffix first — most specific match wins.
        suffixes.sort(key=lambda t: t[0], reverse=True)
        chosen = suffixes[0][1]
    if chosen is None and wildcard is not None:
        chosen = wildcard
    if chosen is None:
        return None

    try:
        return chosen.load()
    except Exception as e:
        log.warning("Failed to load adapter plugin %r: %s", chosen.name, e)
        return None


def list_adapter_plugins() -> list[str]:
    """Return the names (host patterns) of all installed adapter plugins."""
    return sorted(ep.name for ep in _load("vouch.adapters"))


# ----------------------------------------------------------------------
# Router plugins
# ----------------------------------------------------------------------


def list_router_plugins() -> list[str]:
    return sorted(ep.name for ep in _load("vouch.routers"))


def find_router_factory(name: str) -> Any | None:
    for ep in _load("vouch.routers"):
        if ep.name == name:
            try:
                return ep.load()
            except Exception as e:
                log.warning("Failed to load router plugin %r: %s", name, e)
                return None
    return None


# ----------------------------------------------------------------------
# Profile plugins
# ----------------------------------------------------------------------


def list_profile_plugins() -> list[str]:
    return sorted(ep.name for ep in _load("vouch.profiles"))


def load_profile_plugins() -> list[Any]:
    """Load every ``vouch.profiles`` plugin and return their registries.

    Each entry point should be a callable returning a ``ProfileRegistry``.
    """
    out: list[Any] = []
    for ep in _load("vouch.profiles"):
        try:
            factory = ep.load()
            reg = factory() if callable(factory) else factory
            out.append(reg)
        except Exception as e:
            log.warning("Failed to load profile plugin %r: %s", ep.name, e)
    return out


__all__ = [
    "find_adapter_factory",
    "find_router_factory",
    "list_adapter_plugins",
    "list_profile_plugins",
    "list_router_plugins",
    "load_profile_plugins",
]
