"""LLM-assisted result extraction — fallback when the heuristic gives garbage.

Strategy: same "discover-then-cache" loop vouch uses for search bars.

  1. Run the static heuristic first (cheap, $0).
  2. If results look weak (mostly nav-like, very short titles, no chunks),
     hand a *compact* representation of all candidate <a> tags to the LLM
     and ask "which of these are real search results for query Q?".
  3. From the LLM's pick, learn a URL-pattern fingerprint (substring like
     ``/abs/``, ``/models/``) and store it on the site's selector cache.
  4. Next time the same site is queried, replay: filter heuristic
     candidates by the cached URL pattern, no LLM needed.

This keeps the LLM call to **at most once per (site, dom_fingerprint)**.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

from ..models import Chunk

if TYPE_CHECKING:
    from .._llm import LLMClient
    from ..catalog import Site
    from ..discovery.cache import SelectorCache

log = logging.getLogger("vouch.extract.llm")

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_HREF = re.compile(
    r'<a[^>]*href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<body>.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)


def _strip(s: str) -> str:
    return _WS.sub(" ", _TAG.sub(" ", s)).strip()


# ----------------------------------------------------------------------
# Quality signal — tells callers when the heuristic deserves a 2nd opinion.
# ----------------------------------------------------------------------


def looks_low_quality(
    chunks: list[Chunk], *, source_url: str | None = None, html: str | None = None
) -> bool:
    """True when extracted chunks are sparse, short, or nav-like.

    Detects four classes of bad-quality output:
      1. Empty / sparse — nothing or 1 chunk
      2. Short titles — most chunks have < 14-char titles
      3. Top-level paths — most URLs are 1-segment (likely nav)
      4. Megamenu pattern — most chunks share a path prefix that looks like
         a category section (``/topics/``, ``/resources/``, ``/category/``)
      5. Recursive — first chunk URL is approximately the search URL itself
      6. No-results page — HTML body says "no results", "0 results", "did you mean"
    """
    if not chunks:
        return True
    n = len(chunks)
    if n < 2:
        return True

    short_titles = sum(1 for c in chunks if len(c.title) < 14)
    if (short_titles / n) > 0.5:
        return True

    one_seg_urls = sum(
        1 for c in chunks if len([s for s in urlparse(c.source_url).path.split("/") if s]) <= 1
    )
    if (one_seg_urls / n) > 0.5:
        return True

    # Megamenu / category pattern: 80%+ of chunks share a category-like prefix.
    prefixes = []
    for c in chunks:
        segs = [s for s in urlparse(c.source_url).path.split("/") if s]
        if segs:
            prefixes.append(segs[0].lower())
    if prefixes:
        from collections import Counter

        common, count = Counter(prefixes).most_common(1)[0]
        if count / n >= 0.8 and common in {
            "topics",
            "topic",
            "category",
            "categories",
            "section",
            "sections",
            "resources",
            "resource",
            "tag",
            "tags",
            "browse",
            "explore",
        }:
            return True

    # Recursive — first chunk points to (essentially) the search URL.
    if source_url and chunks[0].source_url.split("?")[0] == source_url.split("?")[0]:
        return True

    # No-results sentinel.
    if html and len(html) < 200_000:
        body_lower = html.lower()
        for needle in (
            "no results found",
            "0 results",
            "did you mean",
            "we couldn't find",
            "no se encontraron",
            "nenhum resultado",
            "sem resultados",
            "nada coincide",
        ):
            if needle in body_lower:
                return True

    # Generic 1-3 word categorical titles (e.g. "Benefits", "History & Society").
    short_categorical = sum(1 for c in chunks if len(c.title.split()) <= 3 and c.title.istitle())
    if (short_categorical / n) > 0.6:
        return True

    return False


# ----------------------------------------------------------------------
# Candidate harvesting
# ----------------------------------------------------------------------


def harvest_candidates(html: str, *, source_url: str, site: Site, cap: int = 120) -> list[dict]:
    """Pull every plausible <a href=...>text</a> from html, with DOM context.

    For each candidate, also captures:
      * ``dom_path`` — chain of parent tags + main classes leading to the link
      * ``siblings`` — sibling tags+classes inside the closest container

    Filters obvious nav anchors and sorts by depth so the LLM sees the most
    "result-ish" links first under the cap.
    """
    from .trafilatura import _is_nav_anchor

    site_host = site.url
    by_url: dict[str, dict] = {}

    # Try lxml-based scanning first (gives us DOM path); fall back to regex.
    try:
        from lxml import html as lxml_html

        tree = lxml_html.fromstring(html)
        for a in tree.iter("a"):
            href = a.get("href") or ""
            body = " ".join((a.text_content() or "").split())
            if not href or not body or len(body) < 4:
                continue
            url = href if href.startswith("http") else urljoin(source_url, href)
            host = urlparse(url).netloc.lower().lstrip("www.")
            if host and host != site_host and not host.endswith("." + site_host):
                continue
            if url in by_url:
                continue
            if _is_nav_anchor(body, url):
                continue
            path = urlparse(url).path
            by_url[url] = {
                "url": url,
                "title": body[:140],
                "path": path,
                "depth": len([s for s in path.split("/") if s]),
                "dom_path": _dom_path(a),
                "siblings": _sibling_tags(a),
            }
    except Exception:
        for m in _HREF.finditer(html):
            href = m.group("href")
            body = _strip(m.group("body"))
            if not body or len(body) < 4:
                continue
            url = href if href.startswith("http") else urljoin(source_url, href)
            host = urlparse(url).netloc.lower().lstrip("www.")
            if host and host != site_host and not host.endswith("." + site_host):
                continue
            if url in by_url:
                continue
            if _is_nav_anchor(body, url):
                continue
            path = urlparse(url).path
            by_url[url] = {
                "url": url,
                "title": body[:140],
                "path": path,
                "depth": len([s for s in path.split("/") if s]),
                "dom_path": "",
                "siblings": [],
            }

    out = list(by_url.values())
    out.sort(key=lambda c: (-c["depth"], -len(c["title"])))
    out = out[:cap]
    for i, c in enumerate(out):
        c["i"] = i
    return out


def _dom_path(node, *, max_depth: int = 6) -> str:
    """Return a compact ancestor path like ``main.results > div.card > h3 > a``."""
    parts: list[str] = []
    n = node
    while n is not None and len(parts) < max_depth:
        tag = getattr(n, "tag", None)
        if not isinstance(tag, str):
            break
        cls = (n.get("class") or "").split()
        head = tag
        if cls:
            head += "." + cls[0]
        parts.append(head)
        n = n.getparent() if hasattr(n, "getparent") else None
    return " > ".join(reversed(parts))


def _sibling_tags(node, *, max_siblings: int = 6) -> list[str]:
    """Return a small list of nearby siblings inside the closest container, e.g. ``["span.author", "p.snippet", "time.date"]``."""
    out: list[str] = []
    parent = node.getparent() if hasattr(node, "getparent") else None
    if parent is None:
        return out
    for el in parent.iter():
        if el is node:
            continue
        tag = getattr(el, "tag", None)
        if not isinstance(tag, str):
            continue
        cls = (el.get("class") or "").split()
        head = tag + ("." + cls[0] if cls else "")
        if head not in out:
            out.append(head)
        if len(out) >= max_siblings:
            break
    return out


# ----------------------------------------------------------------------
# LLM picker
# ----------------------------------------------------------------------

_SYS = (
    "You inspect a list of links extracted from a search results page and pick the ones that "
    "are *actual search results* for the user's query — not navigation, ads, footer, or "
    "site-section links. Output strict JSON only."
)

_USER_TMPL = """User query: {query}
Site: {site}
Result-page URL: {page}

Candidate links extracted from the page (one per line, JSON):
{candidates}

Return JSON:
{{
  "results": [
    {{"i": <integer index from above>, "title_clean": "<better title if available, else null>"}},
    ...
  ],
  "url_pattern": "<a path SUBSTRING that real result URLs share, e.g. '/abs/' or '/models/' — empty string if no clean pattern>"
}}

Pick at most 10 indices. Order them by relevance (most relevant first).
If none of the links look like real results, return empty arrays.
"""


def llm_pick_results(
    candidates: list[dict],
    *,
    query: str,
    site: Site,
    page_url: str,
    llm: LLMClient,
    max_keep: int = 10,
) -> tuple[list[int], str]:
    """Ask the LLM which candidates are real results. Returns (indices, learned_pattern)."""
    if not candidates:
        return [], ""
    # Compact serialization — keep tokens low.
    compact = [
        {"i": c["i"], "url": c["path"] or "/", "title": c["title"], "d": c["depth"]}
        for c in candidates
    ]
    prompt = _USER_TMPL.format(
        query=query,
        site=site.url,
        page=page_url,
        candidates=json.dumps(compact, ensure_ascii=False),
    )
    try:
        data = llm.chat_json(
            [{"role": "system", "content": _SYS}, {"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=600,
        )
    except Exception as e:
        log.warning("LLM result-extraction failed for %s: %s", site.url, e)
        return [], ""
    raw = data.get("results") if isinstance(data, dict) else []
    if not isinstance(raw, list):
        return [], ""
    indices: list[int] = []
    for item in raw:
        if isinstance(item, dict) and "i" in item:
            try:
                indices.append(int(item["i"]))
            except (ValueError, TypeError):
                pass
        elif isinstance(item, int):
            indices.append(item)
    indices = [i for i in indices if 0 <= i < len(candidates)][:max_keep]
    pattern = ""
    if isinstance(data, dict):
        pattern = str(data.get("url_pattern") or "").strip()
    # Reject obvious nav-y patterns even if the LLM suggested them.
    if pattern and (pattern in _BAD_PATTERNS or len(pattern) < 4):
        pattern = ""
    if not pattern and indices:
        pattern = _infer_pattern([candidates[i]["path"] for i in indices])
    return indices, pattern


_BAD_PATTERNS = {
    "/search/",
    "/about/",
    "/pricing/",
    "/login/",
    "/signin/",
    "/signup/",
    "/join/",
    "/help/",
    "/docs/",
    "/blog/",
    "/contact/",
    "/topics/",
    "/tags/",
    "/resources/",
    "/community/",
    "/en/",
    "/pt/",
    "/en-US/",
    "/static/",
}


def _infer_pattern(paths: list[str]) -> str:
    """Find a common path substring across selected results, skipping nav-y patterns."""
    if not paths or len(paths) < 3:
        # Need 3+ picks before claiming we've learned something.
        return ""
    first_segs = []
    for p in paths:
        segs = [s for s in p.split("/") if s]
        if segs:
            first_segs.append("/" + segs[0] + "/")
    if not first_segs:
        return ""
    common, count = Counter(first_segs).most_common(1)[0]
    if count < max(3, len(paths) // 2):
        return ""
    if common in _BAD_PATTERNS:
        return ""
    return common


# ----------------------------------------------------------------------
# Main entry point — used by to_chunks as a fallback
# ----------------------------------------------------------------------


def extract_with_llm_fallback(
    html: str,
    *,
    source_url: str,
    site: Site,
    query: str,
    llm: LLMClient,
    cache: SelectorCache | None = None,
    max_results: int = 10,
) -> list[Chunk]:
    """Multi-tier fallback for pages the static heuristic can't parse.

    Tier order on each call (cheapest first):
      1. Cached **CSS selector tuple** → ``lxml.cssselect`` replay, no LLM.
      2. Cached **URL substring pattern** → filter candidates, no LLM.
      3. **LLM picks** indices + URL pattern, then **LLM discovers selectors**
         from the picks' DOM context. Both get cached.
    """
    from . import css_selectors as css

    # 1) CSS selector cache — best replay path.
    cached_css = css.get_cached(cache, site.url)
    if cached_css:
        chunks = css.apply_selectors(
            html, cached_css, source_url=source_url, site=site, max_results=max_results
        )
        if chunks:
            log.info("CSS selector cache hit for %s (%d chunks)", site.url, len(chunks))
            return chunks
        log.info("CSS selectors stale for %s — will re-discover", site.url)

    candidates = harvest_candidates(html, source_url=source_url, site=site, cap=80)
    if not candidates:
        return []

    # 2) URL pattern cache — fallback if CSS selectors aren't cached yet.
    cached_pattern = _read_cached_pattern(cache, site.url)
    if cached_pattern and not cached_css:
        keep = [c for c in candidates if cached_pattern in c["path"]]
        if keep:
            log.info("URL-pattern cache hit for %s (%r)", site.url, cached_pattern)
            return _to_chunks(keep[:max_results], site=site, source="url-cache")

    # 3) LLM picks the real results.
    indices, pattern = llm_pick_results(
        candidates, query=query, site=site, page_url=source_url, llm=llm, max_keep=max_results
    )
    if not indices:
        return []
    picked = [candidates[i] for i in indices]

    # 4) LLM discovers reusable CSS selectors from the picks' DOM context.
    if cache is not None and any(c.get("dom_path") for c in picked):
        try:
            selectors = css.discover_selectors(
                picked, query=query, site=site, page_url=source_url, llm=llm, html=html
            )
        except Exception as e:
            log.warning("css.discover_selectors raised for %s: %s", site.url, e)
            selectors = None
        if selectors and css.selectors_validate(html, selectors, source_url=source_url, site=site):
            css.store(cache, site.url, selectors)
            log.info("Cached CSS selectors for %s: %s", site.url, selectors)
            chunks = css.apply_selectors(
                html, selectors, source_url=source_url, site=site, max_results=max_results
            )
            if chunks:
                return chunks

    if cache and pattern:
        _store_pattern(cache, site.url, pattern)
        log.info("LLM-extract learned URL pattern %r for %s", pattern, site.url)
    return _to_chunks(picked, site=site, source="llm-pick")


def _to_chunks(picked: list[dict], *, site: Site, source: str) -> list[Chunk]:
    return [
        Chunk(
            source_url=c["url"],
            site=site.url,
            site_category=site.category,
            title=c["title"],
            relevance_score=0.65,
            metadata={"adapter": "browser/http", "source": source},
        )
        for c in picked
    ]


# ----------------------------------------------------------------------
# Cache plumbing — stores result-url pattern alongside search-bar selectors
# ----------------------------------------------------------------------


def _read_cached_pattern(cache: SelectorCache | None, domain: str) -> str:
    if not cache:
        return ""
    try:
        existing = cache.get(domain) or {}
    except Exception:
        return ""
    return str(existing.get("result_url_contains") or "")


def _store_pattern(cache: SelectorCache, domain: str, pattern: str) -> None:
    try:
        existing = cache.get(domain) or {}
    except Exception:
        existing = {}
    existing["result_url_contains"] = pattern
    try:
        cache.set(domain, existing)
    except Exception as e:
        log.warning("Could not persist learned pattern for %s: %s", domain, e)


__all__ = [
    "extract_with_llm_fallback",
    "harvest_candidates",
    "llm_pick_results",
    "looks_low_quality",
]
