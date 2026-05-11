"""Curated site profiles registry.

A *profile* is a bundle of search-config for a single domain:
  - ``search_url_template`` for sites with a stable query URL
  - ``result_selectors`` (CSS) for sites where we already know the markup
  - ``working_tier`` hint (skip HTTP for known-blocked sites)
  - ``rate_limit`` hint
  - language tags, behavior, etc.

Profiles ship with vouch for popular sites (arxiv, github, etc.) and users
can publish/share their own. The community registry will live at
``github.com/everton-evton/vouch-profiles`` and ``vouch profiles update``
pulls the latest.

Public API::

    from vouch.profiles import get_profile, list_profiles, ProfileRegistry

    site = get_profile("arxiv.org")          # → preconfigured Site
    list_profiles()                          # → list[str] of domains
    registry = ProfileRegistry.builtin()     # full registry object
"""

from __future__ import annotations

from .registry import ProfileRegistry, get_profile, list_profiles

__all__ = ["ProfileRegistry", "get_profile", "list_profiles"]
