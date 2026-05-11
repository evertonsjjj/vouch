"""SearchEngine — the orchestrator users mostly talk to.

Glue between Catalog, Router, SiteAdapters, and Aggregator. Provides the Level-1
``search()`` shortcut, the Level-2 instance API, and the Level-3 YAML loader.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from ._llm import LLMClient
from .adapters import build_adapter
from .adapters.base import AdapterContext
from .catalog import Catalog, Site
from .config import EngineConfig
from .discovery.cache import SelectorCache
from .exceptions import AdapterError, BlockedError
from .models import CacheStats, Chunk, RouteDecision, SearchResult
from .router import build_router
from .router.base import Router, RoutingContext

log = logging.getLogger("vouch.engine")


class SearchEngine:
    """Top-level orchestrator. Construct once, search many times."""

    def __init__(
        self,
        llm: str | list[str] = "ollama/qwen2.5:14b",
        *,
        router_llm: str | None = None,
        vision_llm: str | None = None,
        api_keys: dict[str, str] | None = None,
        # Routing
        router_strategy: str = "llm",
        router_top_k: int = 3,
        router_explain: bool = False,
        router: Router | None = None,
        # Search
        default_depth: int = 1,
        parallel_sites: int = 3,
        # Browser
        default_behavior: str = "natural",
        humanize: bool = True,
        typing_speed: str = "natural",
        headless: bool = True,
        business_hours_only: bool = False,
        # Caching
        cache_dir: str | Path = "~/.vouch",
        cache_ttl_days: int = 30,
        # Politeness
        respect_robots_txt: bool = True,
        default_rate_limit: str = "2/min",
        user_agent: str | None = None,
        # Captcha
        captcha_min_confidence: float = 0.7,
        captcha_max_attempts: int = 2,
        # Resilience
        auto_resolve_dns: bool = False,
        auto_escalate_adapter: bool = True,
        auto_probe_on_add: bool = False,
        probe_queries: int = 1,
        use_browser_pool: bool = True,
        # Misc
        verbose: bool = False,
        request_timeout: float = 30.0,
        catalog: Catalog | None = None,
        selector_cache: SelectorCache | None = None,
    ):
        self.config = EngineConfig(
            llm=llm,
            router_llm=router_llm,
            vision_llm=vision_llm,
            api_keys=api_keys,
            router_strategy=router_strategy,  # type: ignore[arg-type]
            router_top_k=router_top_k,
            router_explain=router_explain,
            default_depth=default_depth,
            parallel_sites=parallel_sites,
            default_behavior=default_behavior,  # type: ignore[arg-type]
            humanize=humanize,
            typing_speed=typing_speed,  # type: ignore[arg-type]
            headless=headless,
            business_hours_only=business_hours_only,
            cache_dir=cache_dir,  # type: ignore[arg-type]
            cache_ttl_days=cache_ttl_days,
            respect_robots_txt=respect_robots_txt,
            default_rate_limit=default_rate_limit,
            user_agent=user_agent,
            captcha_min_confidence=captcha_min_confidence,
            captcha_max_attempts=captcha_max_attempts,
            auto_resolve_dns=auto_resolve_dns,
            auto_escalate_adapter=auto_escalate_adapter,
            auto_probe_on_add=auto_probe_on_add,
            probe_queries=probe_queries,
            use_browser_pool=use_browser_pool,
            verbose=verbose,
            request_timeout=request_timeout,
        )
        if verbose:
            logging.basicConfig(level=logging.INFO)

        # Persistent storage --------------------------------------------------
        cache_path = self.config.cache_dir
        cache_path.mkdir(parents=True, exist_ok=True)
        self.catalog = catalog or Catalog(cache_path / "catalog.db")
        self.selector_cache = selector_cache or SelectorCache(cache_path / "selectors.db")

        # LLM clients ---------------------------------------------------------
        self._llm = LLMClient(self.config.llm, api_keys=api_keys)
        if router_llm:
            self._router_llm = LLMClient(router_llm, api_keys=api_keys)
        else:
            self._router_llm = self._llm
        self._vision = LLMClient(vision_llm, api_keys=api_keys) if vision_llm else None

        # Router --------------------------------------------------------------
        if router is not None:
            self.router = router
        else:
            kwargs: dict[str, Any] = {}
            if router_strategy == "llm":
                kwargs["llm"] = self._router_llm
            self.router = build_router(router_strategy, **kwargs)

        # Browser pool — lazy. Created on first browser-tier search.
        self._browser_pool: Any = None
        self._stealth_pool: Any = None

    # ------------------------------------------------------------------
    # Browser pool lifecycle
    # ------------------------------------------------------------------

    def _get_browser_pool(self, *, stealth: bool = False):
        """Return the engine's shared :class:`BrowserPool`, creating it lazily.

        Two pools may exist (regular + stealth) since they need different
        Playwright launchers. They share the engine's lifetime and are torn
        down by :meth:`close`.
        """
        if not self.config.use_browser_pool:
            return None
        try:
            from .adapters.browser_pool import BrowserPool
        except ImportError:
            return None  # playwright not installed

        if stealth:
            if self._stealth_pool is None:
                self._stealth_pool = BrowserPool(
                    headless=self.config.headless,
                    user_agent=self.config.user_agent,
                    stealth=True,
                )
            return self._stealth_pool
        if self._browser_pool is None:
            self._browser_pool = BrowserPool(
                headless=self.config.headless,
                user_agent=self.config.user_agent,
                stealth=False,
            )
        return self._browser_pool

    def close(self) -> None:
        """Tear down browser pools. Safe to call multiple times."""
        for pool in (self._browser_pool, self._stealth_pool):
            if pool is not None:
                try:
                    pool.shutdown()
                except Exception as e:
                    log.debug("pool shutdown raised: %s", e)
        self._browser_pool = None
        self._stealth_pool = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # ------------------------------------------------------------------
    # Catalog convenience
    # ------------------------------------------------------------------

    def add(
        self,
        site: Site,
        *,
        replace: bool = False,
        probe: bool | None = None,
    ) -> Site:
        """Add a Site to the catalog. Optionally runs a probe crawl first.

        ``probe`` defaults to ``EngineConfig.auto_probe_on_add``. Pass ``probe=True``
        to force, or ``probe=False`` to skip even if auto-probe is enabled.
        """
        site = self.catalog.add(site, replace=replace, resolve_dns=self.config.auto_resolve_dns)
        run_probe = self.config.auto_probe_on_add if probe is None else probe
        if run_probe:
            try:
                from .discovery.probe import probe_site

                summary = probe_site(site, self, max_probes=self.config.probe_queries)
                log.info("Probe summary for %s: %s", site.url, summary)
            except Exception as e:
                log.warning("Probe crawl for %s raised: %s", site.url, e)
        return site

    def remove(self, url: str) -> bool:
        return self.catalog.remove(url)

    def update(self, url: str, **fields) -> Site:
        return self.catalog.update(url, **fields)

    def list_sites(self, **kwargs) -> list[Site]:
        return self.catalog.list_sites(**kwargs)

    # ------------------------------------------------------------------
    # YAML
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: str | Path, **overrides) -> SearchEngine:
        import yaml

        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        defaults = data.get("defaults") or {}
        engine_kwargs = {**defaults, **overrides}
        engine = cls(**engine_kwargs)
        for raw in data.get("sites") or []:
            engine.catalog.add(Site(**raw), replace=True)
        return engine

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def asearch(self, query: str, **kwargs) -> SearchResult:
        """Async wrapper around :meth:`search` — runs the sync engine in a thread.

        Use this from inside agent frameworks that require an async tool::

            result = await engine.asearch("LLM benchmarks", depth=1)
        """
        import asyncio

        return await asyncio.to_thread(self.search, query, **kwargs)

    def search(
        self,
        query: str,
        *,
        depth: int | None = None,
        sites: list[str] | None = None,
        only_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
        max_results: int = 10,
        timeout: float = 60.0,
    ) -> SearchResult:
        t0 = time.perf_counter()
        depth = self.config.default_depth if depth is None else depth
        candidate_sites = self._select_candidates(sites, only_tags, exclude_tags)
        if not candidate_sites:
            return SearchResult(
                query=query, status="ok", duration_ms=(time.perf_counter() - t0) * 1000
            )

        # Routing
        decisions = self._route(query, candidate_sites, only_tags, exclude_tags)
        chosen_urls = [d.site for d in decisions]
        chosen_sites = [s for s in candidate_sites if s.url in chosen_urls]
        chosen_sites.sort(key=lambda s: chosen_urls.index(s.url))

        # Parallel fetch
        chunks: list[Chunk] = []
        errors: list[str] = []
        sites_searched: list[str] = []
        cache = CacheStats()

        with ThreadPoolExecutor(max_workers=max(1, self.config.parallel_sites)) as pool:
            futures = {
                pool.submit(self._search_site, site, query, depth, max_results, timeout): site
                for site in chosen_sites
            }
            for fut in as_completed(futures):
                site = futures[fut]
                try:
                    site_chunks, hit = fut.result()
                    chunks.extend(site_chunks)
                    sites_searched.append(site.url)
                    if hit:
                        cache.hits += 1
                    else:
                        cache.misses += 1
                except BlockedError as e:
                    errors.append(f"{site.url}: blocked ({e.reason})")
                    log.warning("Site %s blocked: %s", site.url, e)
                except AdapterError as e:
                    errors.append(f"{site.url}: {e}")
                    log.warning("Site %s failed: %s", site.url, e)
                except Exception as e:
                    errors.append(f"{site.url}: unexpected {type(e).__name__}: {e}")
                    log.exception("Site %s raised", site.url)

        # Aggregate / dedup / rank
        chunks = _dedup(chunks)
        chunks = _rerank(chunks, query)[:max_results]

        tokens = (
            self._llm.tokens.add(self._router_llm.tokens)
            if self._router_llm is not self._llm
            else self._llm.tokens
        )
        cost = self._llm.cost_usd + (
            self._router_llm.cost_usd if self._router_llm is not self._llm else 0.0
        )

        # Quality assessment of the final chunk set.
        from .extraction.llm_extract import looks_low_quality

        quality_warning = None
        if chunks and looks_low_quality(chunks):
            quality_warning = (
                "Heuristic + LLM extraction returned chunks that look like nav/category links "
                "rather than real results. The site likely renders results via JavaScript or "
                "blocks scraping. Consider providing a `search_url_template` or installing the "
                "stealth extras: `pip install 'vouch[browser,stealth]'`."
            )

        if errors and chunks:
            status = "low_quality" if quality_warning else "partial"
        elif errors and not chunks:
            status = "blocked"
        elif quality_warning:
            status = "low_quality"
        else:
            status = "ok"

        result = SearchResult(
            query=query,
            chunks=chunks,
            sites_searched=sites_searched,
            routing_decisions=decisions,
            duration_ms=round((time.perf_counter() - t0) * 1000, 2),
            cost_estimate_usd=round(cost, 6),
            tokens_used=tokens,
            cache_stats=cache,
            status=status,
            errors=errors,
            quality_warning=quality_warning,
        )
        return result

    # ------------------------------------------------------------------
    # Cache & utility
    # ------------------------------------------------------------------

    def cache_stats(self) -> dict:
        return self.selector_cache.stats()

    def invalidate_cache(self, url: str) -> int:
        return self.selector_cache.invalidate(url)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _select_candidates(
        self,
        sites: list[str] | None,
        only_tags: list[str] | None,
        exclude_tags: list[str] | None,
    ) -> list[Site]:
        if sites:
            from .catalog import _normalize_domain

            wanted = {_normalize_domain(s) for s in sites}
            in_catalog = {s.url: s for s in self.catalog.list_sites()}
            return [in_catalog[u] for u in wanted if u in in_catalog] + [
                Site(url=u) for u in wanted if u not in in_catalog
            ]
        return (
            self.catalog.list_sites(only_tags=only_tags) if only_tags else self.catalog.list_sites()
        )

    def _route(
        self,
        query: str,
        sites: list[Site],
        only_tags: list[str] | None,
        exclude_tags: list[str] | None,
    ) -> list[RouteDecision]:
        if len(sites) <= self.config.router_top_k:
            return [RouteDecision(site=s.url, score=1.0, reason="under-top-k") for s in sites]
        ctx = RoutingContext(
            query=query,
            sites=sites,
            top_k=self.config.router_top_k,
            only_tags=only_tags,
            exclude_tags=exclude_tags,
            explain=self.config.router_explain,
        )
        return self.router.route(ctx)

    def _search_site(
        self,
        site: Site,
        query: str,
        depth: int,
        max_results: int,
        timeout: float,
    ) -> tuple[list[Chunk], bool]:
        """Try the cheapest adapter that hasn't already failed for this site.

        Escalation ladder, persisted per site in the selector cache:

          1. ``http`` (HTTPAdapter, default for sites with ``search_url_template``)
          2. ``browser`` (Playwright, full JS render)
          3. ``stealth`` (Patchright, fingerprint masking)

        After each search we record the tier used and whether it succeeded; the
        next call starts at the lowest tier that hasn't already failed.
        """
        cache_hit = self.selector_cache.get(site.url) is not None

        if not self.config.auto_escalate_adapter:
            return self._run_with_adapter(
                site, query, depth, max_results, timeout, tier=None
            ), cache_hit

        ladder = self._adapter_ladder(site)
        last_error: Exception | None = None
        best_chunks: list[Chunk] = []
        best_tier: str | None = None
        for tier in ladder:
            try:
                chunks = self._run_with_adapter(site, query, depth, max_results, timeout, tier=tier)
            except (BlockedError, AdapterError) as e:
                log.info("Tier %s failed for %s: %s — escalating", tier, site.url, e)
                last_error = e
                self._record_tier_failure(site.url, tier)
                continue
            if not chunks:
                log.info("Tier %s returned 0 chunks for %s — escalating", tier, site.url)
                self._record_tier_failure(site.url, tier)
                continue
            from .extraction.llm_extract import looks_low_quality

            if not looks_low_quality(chunks):
                self._record_tier_success(site.url, tier)
                return chunks, cache_hit
            # Low-quality — keep latest as fallback (higher tiers tend to render
            # closer to what a real user sees) and try the next tier.
            log.info(
                "Tier %s returned %d low-quality chunks for %s — escalating",
                tier,
                len(chunks),
                site.url,
            )
            best_chunks = chunks
            best_tier = tier
            self._record_tier_failure(site.url, tier)

        if best_chunks:
            # Best we could do — record the tier that produced it as "working" so
            # next call doesn't keep grinding through dead tiers.
            if best_tier is not None:
                self._record_tier_success(site.url, best_tier)
            return best_chunks, cache_hit
        if last_error is not None:
            raise last_error
        return [], cache_hit

    def _run_with_adapter(
        self,
        site: Site,
        query: str,
        depth: int,
        max_results: int,
        timeout: float,
        *,
        tier: str | None,
    ) -> list[Chunk]:
        adapter = self._adapter_for_tier(site, tier)
        try:
            ctx = AdapterContext(
                site=site,
                query=query,
                depth=depth,
                max_results=max_results,
                timeout=timeout,
            )
            if site.pre_search:
                try:
                    site.pre_search(ctx)
                except Exception as e:
                    log.warning("pre_search hook for %s raised: %s", site.url, e)
            chunks = adapter.search(ctx)
            if site.post_extract:
                try:
                    chunks = list(site.post_extract(chunks)) or chunks
                except Exception as e:
                    log.warning("post_extract hook for %s raised: %s", site.url, e)
            return chunks
        finally:
            try:
                adapter.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Adapter tier persistence (stored in the same selector cache row)
    # ------------------------------------------------------------------

    def _adapter_ladder(self, site: Site) -> list[str]:
        """Tiers to try in order. Honors ``working_tier`` first if known.

        Skips ``stealth`` automatically when ``patchright`` isn't installed —
        otherwise we'd re-run the plain BrowserAdapter twice for the same query.
        """
        cached = self.selector_cache.get(site.url) or {}
        all_tiers = ["http", "browser"]
        try:  # only include stealth if it's actually available
            import patchright  # type: ignore  # noqa: F401

            all_tiers.append("stealth")
        except ImportError:
            pass

        working = cached.get("working_tier")
        failed = set(cached.get("failed_tiers") or [])
        if working in all_tiers:
            idx = all_tiers.index(working)
            return [working] + [t for t in all_tiers[idx + 1 :] if t not in failed]
        return [t for t in all_tiers if t not in failed] or all_tiers

    def _record_tier_failure(self, domain: str, tier: str) -> None:
        cached = self.selector_cache.get(domain) or {}
        failed = set(cached.get("failed_tiers") or [])
        if tier in failed:
            return
        failed.add(tier)
        cached["failed_tiers"] = sorted(failed)
        try:
            self.selector_cache.set(domain, cached)
        except Exception:
            pass

    def _record_tier_success(self, domain: str, tier: str) -> None:
        cached = self.selector_cache.get(domain) or {}
        cached["working_tier"] = tier
        # Don't permanently blacklist a tier we're about to use — drop it from
        # the failed list when it becomes the chosen working tier.
        failed = [t for t in (cached.get("failed_tiers") or []) if t != tier]
        if failed:
            cached["failed_tiers"] = failed
        elif "failed_tiers" in cached:
            cached.pop("failed_tiers")
        try:
            self.selector_cache.set(domain, cached)
        except Exception:
            pass

    def _adapter_for_tier(self, site: Site, tier: str | None):
        """Build the adapter for an explicit tier, or default selection if tier is None."""
        if tier is None:
            return build_adapter(
                site,
                self.config,
                llm=self._llm,
                selector_cache=self.selector_cache,
                pool=self._get_browser_pool(stealth=False),
                stealth_pool=self._get_browser_pool(stealth=True)
                if site.behavior == "stealth"
                else None,
            )
        if tier == "http":
            from .adapters.http import HTTPAdapter

            return HTTPAdapter(
                config=self.config, llm=self._llm, selector_cache=self.selector_cache
            )
        if tier == "browser":
            try:
                from .adapters.browser import BrowserAdapter

                return BrowserAdapter(
                    config=self.config,
                    llm=self._llm,
                    selector_cache=self.selector_cache,
                    pool=self._get_browser_pool(stealth=False),
                )
            except ImportError:
                from .adapters.http import HTTPAdapter

                return HTTPAdapter(
                    config=self.config, llm=self._llm, selector_cache=self.selector_cache
                )
        if tier == "stealth":
            try:
                from .adapters.stealth import StealthBrowserAdapter

                return StealthBrowserAdapter(
                    config=self.config,
                    llm=self._llm,
                    selector_cache=self.selector_cache,
                    pool=self._get_browser_pool(stealth=True),
                )
            except ImportError:
                try:
                    from .adapters.browser import BrowserAdapter

                    return BrowserAdapter(
                        config=self.config,
                        llm=self._llm,
                        selector_cache=self.selector_cache,
                        pool=self._get_browser_pool(stealth=False),
                    )
                except ImportError:
                    from .adapters.http import HTTPAdapter

                    return HTTPAdapter(
                        config=self.config, llm=self._llm, selector_cache=self.selector_cache
                    )
        # unknown tier: default
        return build_adapter(site, self.config, llm=self._llm, selector_cache=self.selector_cache)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _dedup(chunks: list[Chunk]) -> list[Chunk]:
    seen: set[str] = set()
    out: list[Chunk] = []
    for c in chunks:
        key = c.source_url.split("#")[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _rerank(chunks: list[Chunk], query: str) -> list[Chunk]:
    """Lightweight lexical re-rank — just enough to put the most relevant first."""
    q_terms = {w.lower() for w in query.split() if len(w) > 2}
    if not q_terms:
        return chunks
    scored = []
    for c in chunks:
        text = (c.title + " " + (c.snippet or "") + " " + (c.content or ""))[:2000].lower()
        overlap = sum(1 for t in q_terms if t in text)
        score = c.relevance_score + 0.05 * overlap
        scored.append(c.model_copy(update={"relevance_score": round(min(1.0, score), 3)}))
    scored.sort(key=lambda c: c.relevance_score, reverse=True)
    return scored


# Back-compat alias: callers used ``engine.list()`` before v0.2.1. Renamed
# to ``list_sites`` to avoid shadowing the ``list`` builtin in class-scope
# type annotations. Kept as an alias for one minor version; will be removed
# in v1.0.
SearchEngine.list = SearchEngine.list_sites  # type: ignore[attr-defined]


# ----------------------------------------------------------------------
# Level-1 one-shot search
# ----------------------------------------------------------------------


def search(
    query: str,
    *,
    sites: Sequence[str | Site],
    llm: str | list[str] = "ollama/qwen2.5:14b",
    depth: int = 1,
    api_keys: dict[str, str] | None = None,
    max_results: int = 10,
    timeout: float = 60.0,
    **engine_kwargs,
) -> SearchResult:
    """One-shot search. Builds an ephemeral in-memory engine and tears it down."""
    engine = SearchEngine(
        llm=llm,
        api_keys=api_keys,
        cache_dir=engine_kwargs.pop("cache_dir", "~/.vouch"),
        **engine_kwargs,
    )
    for s in sites:
        site_obj = s if isinstance(s, Site) else Site(url=s)
        try:
            engine.catalog.add(site_obj, replace=True)
        except Exception as e:
            log.warning("could not add %s: %s", site_obj, e)
    return engine.search(query, depth=depth, max_results=max_results, timeout=timeout)
