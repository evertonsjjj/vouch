"""curio — curated AI search for agents.

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
    CurioError,
    DiscoveryError,
    RouterError,
)
from .models import Chunk, RouteDecision, SearchResult

__version__ = "0.1.0"

__all__ = [
    "Catalog",
    "Chunk",
    "CurioError",
    "AdapterError",
    "BlockedError",
    "CatalogError",
    "DiscoveryError",
    "RouterError",
    "RouteDecision",
    "SearchEngine",
    "SearchResult",
    "Site",
    "search",
    "__version__",
]


def __getattr__(name: str):
    # Lazy import for optional Monitor (requires apscheduler).
    if name == "Monitor":
        from .monitor.watcher import Monitor

        return Monitor
    raise AttributeError(f"module 'curio' has no attribute {name!r}")
