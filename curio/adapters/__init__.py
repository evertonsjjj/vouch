"""Per-site search executors."""

from __future__ import annotations

from .base import AdapterContext, SiteAdapter
from .http import HTTPAdapter

__all__ = ["AdapterContext", "HTTPAdapter", "SiteAdapter", "build_adapter"]


def build_adapter(site, config, *, llm=None, selector_cache=None) -> SiteAdapter:
    """Pick an adapter for a site based on its declared behavior + capabilities.

    Order of preference:
      1. ``behavior="external"`` → HTTPAdapter (commercial-bypass plug point).
      2. Has ``search_url_template`` and not stealth → HTTPAdapter (10x faster, no Chromium).
      3. ``behavior="stealth"`` → patchright BrowserAdapter.
      4. Default → playwright BrowserAdapter, falling back to HTTP if not installed.
    """
    behavior = site.behavior
    if behavior == "external":
        return HTTPAdapter(config=config, llm=llm, selector_cache=selector_cache)
    if site.search_url_template and behavior != "stealth":
        return HTTPAdapter(config=config, llm=llm, selector_cache=selector_cache)
    if behavior == "stealth":
        try:
            from .stealth import StealthBrowserAdapter

            return StealthBrowserAdapter(config=config, llm=llm, selector_cache=selector_cache)
        except ImportError:
            pass
    try:
        from .browser import BrowserAdapter

        return BrowserAdapter(config=config, llm=llm, selector_cache=selector_cache)
    except ImportError:
        return HTTPAdapter(config=config)
