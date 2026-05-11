"""Fast HTML→text + result-row extraction backed by trafilatura."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import trafilatura

from ..catalog import Site
from ..models import Chunk

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def extract_main_text(html: str) -> str:
    return trafilatura.extract(html, include_links=False, include_comments=False) or ""


def _strip(html: str) -> str:
    return _WS.sub(" ", _TAG.sub(" ", html)).strip()


_CARD_PATTERNS = [
    # ordered from most-specific to most-permissive
    re.compile(
        r"<(?P<tag>article|li|div)[^>]*>\s*"
        r"(?:[^<]*<[^>]*>)*?"
        r"<a[^>]*href=[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<title>[^<]+)</a>"
        r".*?</(?P=tag)>",
        re.IGNORECASE | re.DOTALL,
    ),
]


_RESULT_HREF = re.compile(
    r'<a[^>]*href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<body>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


# Common nav/UI anchors to filter out of result extraction.
_NAV_PATTERNS = re.compile(
    r"^(skip to|jump to|menu|search|sign in|sign up|log in|home|contact|about|"
    r"privacy|terms|cookie|subscribe|next page|previous page|back to top|"
    r"github|twitter|facebook|linkedin|youtube|rss|share|tweet|toggle|"
    r"client challenge|just a moment|access denied|please verify)\b",
    re.IGNORECASE,
)


_NAV_PATH_LEAF = {
    "pricing",
    "plans",
    "about",
    "contact",
    "careers",
    "jobs",
    "press",
    "login",
    "logout",
    "signin",
    "signup",
    "register",
    "terms",
    "privacy",
    "cookies",
    "support",
    "help",
    "faq",
    "docs",
    "blog",
    "newsletter",
    "rss",
    "sitemap",
    "settings",
    "account",
    "profile",
    "tags",
    "topics",
    "trending",
    "explore",
    "community",
    "events",
    "downloads",
    "download",
}


def _is_nav_anchor(text: str, url: str) -> bool:
    if not text:
        return True
    text = text.strip()
    if _NAV_PATTERNS.match(text):
        return True
    if url.endswith(("#main-container", "#main", "#content", "#header", "#footer")):
        return True
    if "#" in url and url.split("#", 1)[1] in {"main", "content", "header", "footer"}:
        return True
    from urllib.parse import urlparse

    p = urlparse(url)
    path = (p.path or "").rstrip("/")
    # Site root or root-ish (logos, brand links).
    if not path or path in {"/", "/en", "/pt", "/index.html"}:
        if "?" not in url and not p.fragment:
            return True
    # Single-segment leaf path matching a known nav slug.
    segments = [s for s in path.split("/") if s]
    if len(segments) == 1 and segments[0].lower() in _NAV_PATH_LEAF:
        return True
    return False


def to_chunks(
    html: str,
    *,
    source_url: str,
    site: Site,
    max_results: int = 25,
    llm: Any | None = None,
    query: str | None = None,
    cache: Any | None = None,
) -> list[Chunk]:
    """Best-effort extraction of result rows from any results page.

    Heuristic chain:
      1) Card pattern (article/li/div with a primary <a>)
      2) Bare <a> tags pointing at the same host (subdomain-aware)
      3) Single chunk from trafilatura main extraction
      4) **LLM fallback**: if the heuristic looks weak and an ``llm`` + ``query``
         are available, ask the model to pick real result links and cache the
         learned URL pattern on the next pass.

    Pass ``cache`` (a ``SelectorCache``) to persist what the LLM learns so the
    next call can replay without paying for another LLM roundtrip.
    """
    chunks: list[Chunk] = []
    seen: set[str] = set()
    base = source_url

    for pat in _CARD_PATTERNS:
        for m in pat.finditer(html):
            href = m.group("href")
            title = _strip(m.group("title"))
            if not href or not title or len(title) < 6:
                continue
            url = href if href.startswith("http") else urljoin(base, href)
            from urllib.parse import urlparse

            host = urlparse(url).netloc.lower().lstrip("www.")
            if host and host != site.url and not host.endswith("." + site.url):
                continue
            if url in seen or _is_nav_anchor(title, url):
                continue
            seen.add(url)
            chunks.append(
                Chunk(
                    source_url=url,
                    site=site.url,
                    site_category=site.category,
                    title=title[:160],
                    snippet=_neighbor_text(html, m.start()),
                    relevance_score=0.6,
                    metadata={"adapter": "browser", "source": "card"},
                )
            )
            if len(chunks) >= max_results:
                return chunks

    if not chunks:
        for m in _RESULT_HREF.finditer(html):
            href = m.group("href")
            body = _strip(m.group("body"))
            if not body or len(body) < 8:
                continue
            url = href if href.startswith("http") else urljoin(base, href)
            # Match the exact host (subdomain-aware) — github.com !== gist.github.com.
            from urllib.parse import urlparse

            host = urlparse(url).netloc.lower().lstrip("www.")
            if host != site.url and not host.endswith("." + site.url):
                continue
            if url in seen or _is_nav_anchor(body, url):
                continue
            seen.add(url)
            chunks.append(
                Chunk(
                    source_url=url,
                    site=site.url,
                    site_category=site.category,
                    title=body[:160],
                    relevance_score=0.5,
                    metadata={"adapter": "browser", "source": "anchor"},
                )
            )
            if len(chunks) >= max_results:
                return chunks

    if not chunks:
        body = extract_main_text(html)
        if body:
            chunks.append(
                Chunk(
                    source_url=source_url,
                    site=site.url,
                    site_category=site.category,
                    title=site.url,
                    snippet=body[:200],
                    content=body,
                    relevance_score=0.4,
                    metadata={"adapter": "browser", "source": "trafilatura"},
                )
            )

    # 4) LLM fallback: heuristic returned little/garbage AND we have an LLM.
    if llm is not None and query:
        from .llm_extract import extract_with_llm_fallback, looks_low_quality

        if looks_low_quality(chunks, source_url=source_url, html=html):
            llm_chunks = extract_with_llm_fallback(
                html,
                source_url=source_url,
                site=site,
                query=query,
                llm=llm,
                cache=cache,
                max_results=max_results,
            )
            if llm_chunks:
                return llm_chunks

    return chunks


def _neighbor_text(html: str, idx: int, *, span: int = 600) -> str:
    chunk = html[idx : idx + span]
    return _strip(chunk)[:200]


__all__ = ["extract_main_text", "to_chunks"]
