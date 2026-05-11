"""vouch — curated AI search for agents.

Public API:
    search          — one-shot search function (Level 1)
    SearchEngine    — orchestrator with persistent catalog (Level 2/3)
    Site            — declarative source descriptor
    Catalog         — SQLite-backed registry of sites
    Monitor         — change tracking (optional)

See README.md for the full guide.
"""

from __future__ import annotations

from .catalog import Catalog, Site
from .engine import SearchEngine, search
from .exceptions import (
    AdapterError,
    BlockedError,
    CatalogError,
    CurioError,  # back-compat alias (deprecated, will be removed in v1.0)
    DiscoveryError,
    RouterError,
    VouchError,
)
from .models import Chunk, RouteDecision, SearchResult
from .profiles import ProfileRegistry, get_profile, list_profiles

__version__ = "0.2.0"

__all__ = [
    "AdapterError",
    "BlockedError",
    "Catalog",
    "CatalogError",
    "Chunk",
    "CurioError",
    "DiscoveryError",
    "ProfileRegistry",
    "RouteDecision",
    "RouterError",
    "SearchEngine",
    "SearchResult",
    "Site",
    "VouchError",
    "__version__",
    "get_profile",
    "list_profiles",
    "search",
]


def __getattr__(name: str):
    # Lazy import for optional Monitor (requires apscheduler).
    if name == "Monitor":
        from .monitor.watcher import Monitor

        return Monitor
    raise AttributeError(f"module 'vouch' has no attribute {name!r}")
