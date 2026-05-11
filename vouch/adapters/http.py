"""HTTP-only adapter — fast, cheap, depth=0 surveys.

If a Site declares ``search_url_template``, this adapter can also handle
basic depth=1 by hitting the template URL and parsing snippets out of the
returned HTML. For real interactive search, use BrowserAdapter.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

import httpx
import trafilatura
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from ..config import EngineConfig
from ..exceptions import AdapterError
from ..models import Chunk
from .base import AdapterContext, SiteAdapter

log = logging.getLogger("vouch.adapter.http")

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/132.0.0.0 Safari/537.36"
)


class HTTPAdapter(SiteAdapter):
    def __init__(self, config: EngineConfig | None = None, *, llm=None, selector_cache=None):
        self.config = config or EngineConfig()
        self.llm = llm
        self.cache = selector_cache
        self._client = httpx.Client(
            timeout=self.config.request_timeout,
            follow_redirects=True,
            headers={"User-Agent": self.config.user_agent or _DEFAULT_UA},
        )

    def close(self) -> None:
        self._client.close()

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=0.5, max=4), reraise=True
    )
    def _fetch(self, url: str, *, accept_language: str | None = None) -> httpx.Response:
        headers = {"Accept-Language": accept_language} if accept_language else None
        resp = self._client.get(url, headers=headers)
        resp.raise_for_status()
        return resp

    def search(self, ctx: AdapterContext) -> list[Chunk]:
        site = ctx.site
        if site.search_url_template:
            return self._search_via_template(ctx)
        if ctx.depth == 0:
            return self._homepage_chunks(ctx)
        # Last-resort fallback: just dump the homepage.
        log.info(
            "HTTP adapter cannot perform interactive search on %s; serving homepage.", site.url
        )
        return self._homepage_chunks(ctx)

    def _homepage_chunks(self, ctx: AdapterContext) -> list[Chunk]:
        url = ctx.site.homepage
        try:
            resp = self._fetch(url)
        except Exception as e:
            raise AdapterError(f"GET {url} failed: {e}") from e
        chunk = _extract_chunk(resp.text, source_url=url, site=ctx.site)
        return [chunk] if chunk else []

    def _search_via_template(self, ctx: AdapterContext) -> list[Chunk]:
        tpl = ctx.site.search_url_template or ""
        if "{query}" not in tpl:
            raise AdapterError(f"search_url_template for {ctx.site.url} must contain '{{query}}'")
        from urllib.parse import quote_plus

        from .._lang import accept_language_for
        from ..extraction.trafilatura import to_chunks

        path = tpl.format(query=quote_plus(ctx.query))
        url = path if path.startswith("http") else urljoin(ctx.site.homepage, path)
        accept_lang = accept_language_for(ctx.query)
        try:
            resp = self._fetch(url, accept_language=accept_lang)
        except Exception as e:
            raise AdapterError(f"GET {url} failed: {e}") from e
        chunks = to_chunks(
            resp.text,
            source_url=url,
            site=ctx.site,
            max_results=ctx.max_results,
            llm=self.llm,
            query=ctx.query,
            cache=self.cache,
        )
        if ctx.depth >= 2:
            chunks = self._fetch_full(chunks, ctx)
        return chunks[: ctx.max_results]

    def _fetch_full(self, chunks: list[Chunk], ctx: AdapterContext) -> list[Chunk]:
        out: list[Chunk] = []
        for c in chunks[: ctx.max_results]:
            try:
                resp = self._fetch(c.source_url)
                full = trafilatura.extract(resp.text, include_links=False) or ""
                if full:
                    c = c.model_copy(update={"content": full})
            except Exception as e:
                log.debug("full-fetch failed for %s: %s", c.source_url, e)
            out.append(c)
        return out


# --- HTML helpers -----------------------------------------------------------

_HREF = re.compile(r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def _strip(html: str) -> str:
    return _WHITESPACE.sub(" ", _TAG.sub(" ", html)).strip()


def _extract_chunk(html: str, *, source_url: str, site) -> Chunk | None:
    txt = trafilatura.extract(html, include_links=False)
    title = _extract_title(html) or site.url
    if not txt:
        return None
    return Chunk(
        source_url=source_url,
        site=site.url,
        site_category=site.category,
        title=title,
        snippet=txt[:200],
        content=None,
        relevance_score=0.5,
        metadata={"adapter": "http"},
    )


def _extract_title(html: str) -> str | None:
    m = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return _strip(m.group(1)) if m else None


def _split_into_result_chunks(
    html: str, *, source_url: str, site, max_results: int = 10
) -> list[Chunk]:
    """Heuristic: pull out <a> tags pointing at the same domain, treat them as result rows."""
    chunks: list[Chunk] = []
    seen: set[str] = set()
    base = site.homepage
    domain = site.url
    for m in _HREF.finditer(html):
        href, body = m.group(1), m.group(2)
        text = _strip(body)
        if not text or len(text) < 8:
            continue
        url = href if href.startswith("http") else urljoin(base, href)
        if domain not in url:
            continue
        if url in seen:
            continue
        seen.add(url)
        chunks.append(
            Chunk(
                source_url=url,
                site=site.url,
                site_category=site.category,
                title=text[:160],
                snippet="",
                relevance_score=0.5,
                metadata={"adapter": "http", "source": "result-page"},
            )
        )
        if len(chunks) >= max_results * 2:
            break
    return chunks
