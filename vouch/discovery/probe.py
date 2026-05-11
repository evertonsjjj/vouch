"""Probe crawl on Site add() — auto-configure a site profile before first real query.

When a user does ``engine.add(Site("foo.com"))`` with ``auto_probe=True``, we run:

  1. A fast HTTP HEAD/GET on the homepage to see if the site responds.
  2. A short list of probe queries (``test``, ``hello``, ``tutorial``) against
     the search-bar (or ``search_url_template`` if provided).
  3. The full extraction pipeline once on the first probe — cache search-bar
     selectors, learn the result tier, optionally infer CSS selectors.
  4. Persist everything in the selector cache so the user's first real query
     uses the learned profile and runs fast.

This is intentionally cheap (1-3 LLM calls + 1-3 page loads) so it doesn't
slow down ``add()`` dramatically.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..catalog import Site
    from ..engine import SearchEngine

log = logging.getLogger("vouch.probe")

_PROBE_QUERIES = ("introduction", "tutorial", "test")


def probe_site(site: Site, engine: SearchEngine, *, max_probes: int = 1) -> dict:
    """Run probe queries to learn a site's profile. Returns a profile summary."""
    summary: dict = {"site": site.url, "probes": [], "errors": []}

    n = max(1, min(max_probes, len(_PROBE_QUERIES)))
    for q in _PROBE_QUERIES[:n]:
        try:
            r = engine.search(q, sites=[site.url], depth=1, max_results=3, timeout=15)
        except Exception as e:
            summary["errors"].append(f"{q!r}: {type(e).__name__}: {e}")
            continue
        summary["probes"].append(
            {
                "query": q,
                "status": r.status,
                "n_chunks": len(r.chunks),
                "first_title": r.chunks[0].title[:60] if r.chunks else None,
            }
        )

    cached = engine.selector_cache.get(site.url) or {}
    summary["working_tier"] = cached.get("working_tier")
    summary["has_result_selectors"] = bool(cached.get("result_selectors"))
    summary["url_pattern"] = cached.get("result_url_contains")
    return summary


__all__ = ["probe_site"]
