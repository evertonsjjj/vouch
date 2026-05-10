"""Patchright-backed adapter — drop-in stealth replacement for BrowserAdapter."""

from __future__ import annotations

from .browser import BrowserAdapter

try:
    from patchright.async_api import async_playwright as async_patchright  # type: ignore

    _PATCHRIGHT_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PATCHRIGHT_AVAILABLE = False


class StealthBrowserAdapter(BrowserAdapter):
    behavior = "stealth"

    def __init__(self, **kwargs):
        if not _PATCHRIGHT_AVAILABLE:
            raise ImportError(
                "StealthBrowserAdapter requires patchright. "
                "Install with: pip install 'curio[browser,stealth]'"
            )
        super().__init__(**kwargs)

    # Override the playwright launcher to use patchright's chromium.
    async def _browser(self):  # type: ignore[override]
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _ctx():
            pw = await async_patchright().start()
            browser = await pw.chromium.launch(headless=self.config.headless)
            try:
                yield pw, browser
            finally:
                await browser.close()
                await pw.stop()

        return _ctx()
