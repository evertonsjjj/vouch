"""Playwright-backed adapter — discovers a search interface on first visit, replays from cache thereafter."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager
from typing import Any

import trafilatura

from ..config import EngineConfig
from ..exceptions import AdapterError, BlockedError
from ..models import Chunk
from .base import AdapterContext, SiteAdapter

log = logging.getLogger("farol.adapter.browser")

_PLAYWRIGHT_AVAILABLE = True
try:
    from playwright.async_api import (  # type: ignore
        Browser,
        Page,
        Playwright,
        async_playwright,
    )
    from playwright.async_api import (
        TimeoutError as PWTimeout,
    )
except ImportError:  # pragma: no cover
    _PLAYWRIGHT_AVAILABLE = False


# Process-wide cap on simultaneous Chromium launches.
# Each launch is ~250 MB resident; capping prevents the OS from killing the
# parent on memory pressure (especially on Windows in CI / dev sandboxes).
_MAX_PARALLEL_BROWSERS = int(os.environ.get("FAROL_MAX_BROWSERS", "1"))
_LAUNCH_LOCK = threading.Semaphore(_MAX_PARALLEL_BROWSERS)


class BrowserAdapter(SiteAdapter):
    """Discovers selectors via LLM the first time, caches them per (domain, dom-fingerprint)."""

    behavior: str = "natural"

    def __init__(
        self,
        *,
        config: EngineConfig | None = None,
        llm: Any = None,
        selector_cache: Any = None,
    ):
        if not _PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "BrowserAdapter requires playwright. Install with: pip install 'farol[browser]' "
                "and run: farol install-browser"
            )
        self.config = config or EngineConfig()
        self.llm = llm
        self.cache = selector_cache  # SelectorCache or None
        self._loop: asyncio.AbstractEventLoop | None = None

    # Sync facade -- runs the async pipeline on a private loop.
    def search(self, ctx: AdapterContext) -> list[Chunk]:
        # Gate launches so we never exceed the global concurrency budget.
        with _LAUNCH_LOCK:
            return _run_sync(self._search_async(ctx))

    def close(self) -> None:
        pass  # Each search uses a fresh playwright lifecycle.

    # --- async pipeline -------------------------------------------------

    async def _search_async(self, ctx: AdapterContext) -> list[Chunk]:
        async with self._browser() as (_pw, browser):
            page = await self._new_page(browser)
            try:
                return await self._do_search(page, ctx)
            finally:
                await page.context.close()

    @asynccontextmanager
    async def _browser(self):
        pw: Playwright = await async_playwright().start()
        browser = None
        try:
            browser = await self._launch(pw)
            yield pw, browser
        finally:
            # Each cleanup is independent — a failure in one shouldn't prevent
            # the others. Otherwise a half-killed Chromium becomes a zombie.
            if browser is not None:
                try:
                    await browser.close()
                except Exception as e:
                    log.debug("browser.close() raised: %s", e)
            try:
                await pw.stop()
            except Exception as e:
                log.debug("pw.stop() raised: %s", e)

    async def _launch(self, pw):
        # Headless launch with extra-stable flags for low-memory hosts.
        return await pw.chromium.launch(
            headless=self.config.headless,
            args=[
                "--disable-dev-shm-usage",  # use /tmp instead of shared mem
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )

    async def _new_page(self, browser: Browser) -> Page:
        ctx = await browser.new_context(
            user_agent=self.config.user_agent,
            viewport={"width": 1366, "height": 900},
        )
        return await ctx.new_page()

    async def _do_search(self, page: Page, ctx: AdapterContext) -> list[Chunk]:
        site = ctx.site
        await _safe_goto(page, site.homepage, timeout_ms=int(ctx.timeout * 1000))
        if await _is_blocked(page):
            raise BlockedError(f"{site.url} appears to block automated access", reason="bot_check")

        if ctx.depth == 0:
            # depth=0 contract: homepage skim, no search interaction, no LLM discovery.
            from ..extraction.trafilatura import to_chunks

            html = await page.content()
            return to_chunks(html, source_url=page.url, site=site)[: ctx.max_results]

        if site.search_url_template:
            return await self._template_path(page, ctx)
        return await self._discovery_path(page, ctx)

    async def _template_path(self, page: Page, ctx: AdapterContext) -> list[Chunk]:
        from urllib.parse import quote_plus, urljoin

        url = ctx.site.search_url_template.format(query=quote_plus(ctx.query))
        if not url.startswith("http"):
            url = urljoin(ctx.site.homepage, url)
        await _safe_goto(page, url, timeout_ms=int(ctx.timeout * 1000))
        # Many sites render results via XHR after DOMContentLoaded; wait for the
        # network to go idle (capped) so we capture the post-hydration HTML.
        try:
            await page.wait_for_load_state(
                "networkidle", timeout=min(8000, int(ctx.timeout * 1000))
            )
        except PWTimeout:
            pass
        return await _scrape_results(page, ctx, llm=self.llm, cache=self.cache)

    async def _discovery_path(self, page: Page, ctx: AdapterContext) -> list[Chunk]:
        site = ctx.site
        cached = self.cache.get(site.url) if self.cache else None
        selectors = cached
        if not cached:
            selectors = await self._discover_selectors(page, site, ctx.query)
            if self.cache and selectors:
                self.cache.set(site.url, selectors)
        if not selectors:
            from ..extraction.trafilatura import to_chunks

            html = await page.content()
            return to_chunks(
                html,
                source_url=page.url,
                site=site,
                llm=self.llm,
                query=ctx.query,
                cache=self.cache,
            )[: ctx.max_results]
        await self._execute(page, selectors, ctx)
        return await _scrape_results(page, ctx, llm=self.llm, cache=self.cache)

    async def _discover_selectors(self, page: Page, site, query: str) -> dict | None:
        if self.llm is None:
            return None
        from ..discovery.search_bar import discover_selectors

        try:
            return await discover_selectors(page, query, llm=self.llm, site=site)
        except Exception as e:
            log.warning("Search-bar discovery failed for %s: %s", site.url, e)
            return None

    async def _execute(self, page: Page, selectors: dict, ctx: AdapterContext) -> None:
        from ..discovery.humanize import type_humanlike

        input_sel = selectors.get("input")
        submit_sel = selectors.get("submit")
        if not input_sel:
            raise AdapterError(f"No input selector for {ctx.site.url}")
        try:
            box = page.locator(input_sel).first
            await box.click(timeout=8000)
            if self.config.humanize:
                await type_humanlike(box, ctx.query, speed=self.config.typing_speed)
            else:
                await box.fill(ctx.query)
            if submit_sel:
                await page.locator(submit_sel).first.click(timeout=8000)
            else:
                await box.press("Enter")
            await page.wait_for_load_state("networkidle", timeout=int(ctx.timeout * 1000))
        except PWTimeout as e:
            raise AdapterError(f"Search execution timed out on {ctx.site.url}: {e}") from e


# --- shared helpers ---------------------------------------------------------


async def _safe_goto(page: Page, url: str, *, timeout_ms: int) -> None:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
    except PWTimeout as e:
        raise AdapterError(f"goto({url}) timed out: {e}") from e


async def _is_blocked(page: Page) -> bool:
    title = (await page.title() or "").lower()
    body = (await page.content())[:2000].lower()
    needles = [
        "just a moment",
        "checking your browser",
        "captcha",
        "access denied",
        "are you human",
    ]
    return any(n in title or n in body for n in needles)


async def _scrape_results(page: Page, ctx: AdapterContext, *, llm=None, cache=None) -> list[Chunk]:
    from ..extraction.trafilatura import to_chunks

    html = await page.content()
    chunks = to_chunks(
        html,
        source_url=page.url,
        site=ctx.site,
        llm=llm,
        query=ctx.query,
        cache=cache,
    )
    if ctx.depth >= 2:
        chunks = await _extract_full(page, chunks[: ctx.max_results])
    return chunks[: ctx.max_results]


async def _extract_full(page: Page, chunks: list[Chunk]) -> list[Chunk]:
    out: list[Chunk] = []
    for c in chunks:
        try:
            await page.goto(c.source_url, wait_until="domcontentloaded", timeout=20000)
            html = await page.content()
            full = trafilatura.extract(html, include_links=False) or ""
            if full:
                c = c.model_copy(update={"content": full})
        except Exception as e:
            log.debug("full-fetch in browser failed for %s: %s", c.source_url, e)
        out.append(c)
    return out


def _run_sync(coro):
    """Bridge async pipeline to sync API. Re-uses a thread-local loop."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already inside an async context — execute on a new loop in another thread.
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
    except RuntimeError:
        pass
    return asyncio.run(coro)
