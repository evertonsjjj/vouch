"""Per-site search executors."""

from __future__ import annotations

from .base import AdapterContext, SiteAdapter
from .http import HTTPAdapter

__all__ = ["AdapterContext", "HTTPAdapter", "SiteAdapter", "build_adapter"]


def build_adapter(
    site, config, *, llm=None, selector_cache=None, pool=None, stealth_pool=None
) -> SiteAdapter:
    """Pick an adapter for a site based on its declared behavior + capabilities.

    Order of preference:
      0. Third-party plugin registered for this domain via ``farol.adapters``
         entry points (e.g. ``farol-adapter-arxiv`` published on PyPI).
      1. ``behavior="external"`` → HTTPAdapter (commercial-bypass plug point).
      2. Has ``search_url_template`` and not stealth → HTTPAdapter (10x faster, no Chromium).
      3. ``behavior="stealth"`` → patchright BrowserAdapter.
      4. Default → playwright BrowserAdapter, falling back to HTTP if not installed.

    The engine passes its shared ``pool`` (and optionally ``stealth_pool``) so
    every BrowserAdapter the engine constructs reuses a single Chromium
    instance instead of launching one per call.
    """
    # Tier 0: check for a third-party plugin registered for this host.
    try:
        from ..plugins import find_adapter_factory

        factory = find_adapter_factory(site.url)
        if factory is not None:
            try:
                return factory(
                    site=site,
                    config=config,
                    llm=llm,
                    selector_cache=selector_cache,
                    pool=pool,
                    stealth_pool=stealth_pool,
                )
            except TypeError:
                # Older plugins may not accept all kwargs — be permissive.
                return factory(config=config, llm=llm, selector_cache=selector_cache)
    except Exception:
        pass  # plugin path is best-effort; never block on it

    behavior = site.behavior
    if behavior == "external":
        return HTTPAdapter(config=config, llm=llm, selector_cache=selector_cache)
    if site.search_url_template and behavior != "stealth":
        return HTTPAdapter(config=config, llm=llm, selector_cache=selector_cache)
    if behavior == "stealth":
        try:
            from .stealth import StealthBrowserAdapter

            return StealthBrowserAdapter(
                config=config, llm=llm, selector_cache=selector_cache, pool=stealth_pool
            )
        except ImportError:
            pass
    try:
        from .browser import BrowserAdapter

        return BrowserAdapter(config=config, llm=llm, selector_cache=selector_cache, pool=pool)
    except ImportError:
        return HTTPAdapter(config=config)
