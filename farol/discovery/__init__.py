"""Search-bar discovery, selector caching, and human-like behavior."""

from __future__ import annotations

from .cache import SelectorCache
from .humanize import type_humanlike
from .search_bar import discover_selectors

__all__ = ["SelectorCache", "discover_selectors", "type_humanlike"]
