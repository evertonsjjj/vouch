"""Persistent Playwright pool — one browser per process, many searches.

Why this exists
---------------
The plain :class:`farol.adapters.browser.BrowserAdapter` launches and tears
down a fresh Chromium process for **every** search. That's the worst case for:

* **Throughput** — Chromium boot is ~3-8 s on cold cache, 1-2 s warm. For a
  catalog of 10 sites and 20 queries, that's 200+ launches.
* **Stability** — repeatedly fork/exec'ing Chromium on Windows is the
  scenario that triggered process hangs during our v0.2 benchmark.
* **Resource use** — each launch allocates ~250 MB RSS. A dev box runs out
  of memory long before a real catalog finishes.

This module gives the engine a single, long-lived Chromium that all searches
share. The pool is created on first use, lives for the engine's lifetime, and
is torn down on :meth:`shutdown` / process exit.

Architecture
------------
Playwright async objects are bound to the event loop that created them, so
you cannot share a single ``Playwright`` instance across the multiple loops
that ``asyncio.run`` creates in the engine's ``ThreadPoolExecutor``. The pool
sidesteps this by running its own background thread with a dedicated
event loop:

* :class:`BrowserPool` owns one ``threading.Thread`` running an
  ``asyncio.new_event_loop()`` for the engine's lifetime.
* Adapters submit coroutines via :meth:`run_coro`, which uses
  ``asyncio.run_coroutine_threadsafe`` to dispatch onto the pool thread and
  blocks the caller until the result is ready (or it times out).
* All Playwright objects (the ``Playwright`` handle, the ``Browser``, every
  ``BrowserContext`` we open) live on that single loop and are reused.

For ``BrowserAdapter.search()`` the contract becomes::

    chunks = run_coro(adapter._search_async(ctx), timeout=ctx.timeout * 3 + 30)

instead of ``asyncio.run(adapter._search_async(ctx))``. Same code, but the
adapter receives a freshly-created ``BrowserContext`` from the pool rather
than spinning up a new ``Playwright`` + ``Browser`` every call.

The pool is opt-in via ``EngineConfig.use_browser_pool=True`` (default in
v0.2). Set it to False to keep the legacy "fresh browser per search"
behaviour, which is more isolated but much slower.
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import threading
from concurrent.futures import Future
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

log = logging.getLogger("farol.browser_pool")

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page, Playwright


class BrowserPool:
    """Process-wide pool of a single shared Chromium browser.

    Construct one per :class:`farol.engine.SearchEngine`. Call
    :meth:`shutdown` when the engine is no longer needed; otherwise the pool
    cleans up on interpreter exit via :func:`atexit`.
    """

    def __init__(
        self,
        *,
        headless: bool = True,
        user_agent: str | None = None,
        stealth: bool = False,
    ):
        self.headless = headless
        self.user_agent = user_agent
        self.stealth = stealth

        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stopping = threading.Event()
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._launch_lock = threading.Lock()

        atexit.register(self.shutdown)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _ensure_started(self) -> None:
        """Lazy-start the background loop + browser on first use."""
        if self._loop is not None and self._thread is not None and self._thread.is_alive():
            return
        with self._launch_lock:
            if self._loop is not None and self._thread is not None and self._thread.is_alive():
                return

            self._loop = asyncio.new_event_loop()
            self._ready.clear()
            self._thread = threading.Thread(
                target=self._run_loop_forever,
                name="farol-browser-pool",
                daemon=True,
            )
            self._thread.start()
            # Block until the loop is actually serving callbacks.
            if not self._ready.wait(timeout=10):
                raise RuntimeError("Browser pool thread did not start within 10 s")

            # Launch the shared Playwright + Browser on the pool's loop.
            fut = asyncio.run_coroutine_threadsafe(self._async_launch(), self._loop)
            fut.result(timeout=60)

    def _run_loop_forever(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._loop.call_soon(self._ready.set)
        try:
            self._loop.run_forever()
        finally:
            try:
                self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            except Exception:
                pass
            self._loop.close()

    async def _async_launch(self) -> None:
        if self.stealth:
            try:
                from patchright.async_api import async_playwright  # type: ignore
            except ImportError:
                log.info("patchright not installed, falling back to playwright")
                from playwright.async_api import async_playwright
        else:
            from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        log.info("BrowserPool ready (stealth=%s, headless=%s)", self.stealth, self.headless)

    # ------------------------------------------------------------------
    # Public dispatch
    # ------------------------------------------------------------------

    def run_coro(self, coro, *, timeout: float | None = None) -> Any:
        """Run *coro* on the pool's loop, blocking until it returns or raises."""
        self._ensure_started()
        assert self._loop is not None
        fut: Future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return fut.result(timeout=timeout)
        except Exception:
            fut.cancel()
            raise

    @asynccontextmanager
    async def page(self, *, user_agent: str | None = None):
        """Yield a fresh :class:`Page` from a new :class:`BrowserContext`.

        The context is torn down on exit. Each call gets isolation (cookies
        don't leak between calls) but the underlying browser is shared.
        """
        self._ensure_started()
        # We're already inside the pool's loop when called via run_coro;
        # otherwise the caller has misused this API.
        assert self._browser is not None
        ctx_kwargs: dict[str, Any] = {"viewport": {"width": 1366, "height": 900}}
        ua = user_agent or self.user_agent
        if ua:
            ctx_kwargs["user_agent"] = ua
        ctx: BrowserContext = await self._browser.new_context(**ctx_kwargs)
        page: Page = await ctx.new_page()
        try:
            yield page
        finally:
            try:
                await ctx.close()
            except Exception as e:
                log.debug("ctx.close raised: %s", e)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Tear down the browser, stop the loop, join the thread.

        Safe to call multiple times.
        """
        if self._stopping.is_set():
            return
        self._stopping.set()
        if self._loop is None:
            return

        async def _cleanup():
            try:
                if self._browser is not None:
                    await self._browser.close()
            except Exception as e:
                log.debug("browser.close raised: %s", e)
            try:
                if self._pw is not None:
                    await self._pw.stop()
            except Exception as e:
                log.debug("pw.stop raised: %s", e)

        try:
            fut = asyncio.run_coroutine_threadsafe(_cleanup(), self._loop)
            fut.result(timeout=10)
        except Exception as e:
            log.debug("pool cleanup raised: %s", e)
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5)

        self._pw = None
        self._browser = None
        self._loop = None
        self._thread = None


__all__ = ["BrowserPool"]
