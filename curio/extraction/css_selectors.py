"""LLM-driven CSS selector discovery + cache + replay.

The LLM looks at the DOM context of candidate result links and emits a tuple
of CSS selectors:

    {
      "container": ".search-result",
      "title":     "h3 a",
      "url":       "h3 a",
      "snippet":   "p.description",
      "date":      "time.published",
      "author":    ".byline",
    }

Subsequent calls replay the selectors via lxml.cssselect — deterministic,
fast, no LLM. Snippets/dates/authors come "for free" if the site exposes them.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse

from ..models import Chunk

if TYPE_CHECKING:
    from .._llm import LLMClient
    from ..catalog import Site
    from ..discovery.cache import SelectorCache

log = logging.getLogger("curio.css")


# ----------------------------------------------------------------------
# Apply cached selectors (no LLM)
# ----------------------------------------------------------------------


def apply_selectors(
    html: str,
    selectors: dict,
    *,
    source_url: str,
    site: "Site",
    max_results: int = 10,
) -> list[Chunk]:
    """Replay a cached selector tuple on a fresh HTML page."""
    try:
        from lxml import html as lxml_html
    except ImportError:
        log.warning("lxml not installed — CSS selector replay skipped.")
        return []

    container_sel = selectors.get("container")
    if not container_sel:
        return []

    try:
        tree = lxml_html.fromstring(html)
    except Exception as e:  # noqa: BLE001
        log.warning("html parse failed: %s", e)
        return []

    chunks: list[Chunk] = []
    seen: set[str] = set()
    for el in _safe_cssselect(tree, container_sel)[: max_results * 2]:
        title = _text_of(_first(el, selectors.get("title"))) or _text_of(el)[:120]
        href = _attr_of(_first(el, selectors.get("url") or selectors.get("title") or "a"), "href")
        if not href:
            continue
        url = href if href.startswith("http") else urljoin(source_url, href)
        host = urlparse(url).netloc.lower().lstrip("www.")
        if host and host != site.url and not host.endswith("." + site.url):
            continue
        if url in seen:
            continue
        seen.add(url)
        snippet = _text_of(_first(el, selectors.get("snippet"))) or ""
        date = _text_of(_first(el, selectors.get("date"))) or ""
        author = _text_of(_first(el, selectors.get("author"))) or ""
        if not title:
            continue
        meta: dict[str, Any] = {"adapter": "browser/http", "source": "css-cache"}
        if date:
            meta["date"] = date
        if author:
            meta["author"] = author
        chunks.append(
            Chunk(
                source_url=url,
                site=site.url,
                site_category=site.category,
                title=title.strip()[:160],
                snippet=snippet.strip()[:400],
                relevance_score=0.7,
                metadata=meta,
            )
        )
        if len(chunks) >= max_results:
            break
    return chunks


def _safe_cssselect(node, selector: str | None):
    if not selector:
        return []
    try:
        return list(node.cssselect(selector))
    except Exception as e:  # noqa: BLE001
        log.debug("cssselect %r failed: %s", selector, e)
        return []


def _first(node, selector: str | None):
    if not selector:
        return None
    matches = _safe_cssselect(node, selector)
    return matches[0] if matches else None


def _text_of(node) -> str:
    if node is None:
        return ""
    try:
        return " ".join((node.text_content() or "").split())
    except Exception:  # noqa: BLE001
        return ""


def _attr_of(node, name: str) -> str:
    if node is None:
        return ""
    try:
        return node.get(name) or ""
    except Exception:  # noqa: BLE001
        return ""


# ----------------------------------------------------------------------
# Discovery — turn a list of LLM-picked candidates into a selector tuple
# ----------------------------------------------------------------------

_SYS = (
    "You receive DOM-path information about candidate search-result links and produce a "
    "CSS selector tuple that captures every result on the page. Output strict JSON only."
)


_USER_TMPL = """User query: {query}
Site: {site}
Page URL: {page}

Below are candidate result links along with their DOM context — the chain of parent
elements (tag + main class) leading up to the link. Identify the CSS selector that
captures *every* result card on this page (not a single one).

Candidates (LLM previously chose these as real results):
{candidates}

Return JSON:
{{
  "container": "<CSS selector matching one entire result card>",
  "title":     "<selector for the title element, RELATIVE to container>",
  "url":       "<selector for the link element, RELATIVE to container>",
  "snippet":   "<selector for the description/excerpt, RELATIVE to container, or null>",
  "date":      "<selector for date/time, or null>",
  "author":    "<selector for byline/author, or null>",
  "confidence": 0.0-1.0
}}

Rules:
- Selectors must be valid CSS3 (works in lxml.cssselect).
- Container should match all result cards on the page — generic enough to
  generalize. Avoid IDs (those are usually unique to one card).
- Avoid `:nth-child(N)` unless absolutely required.
- If you cannot identify a clean structural pattern, return all-null with
  confidence 0.
"""


def discover_selectors(
    candidates_with_dom: list[dict],
    *,
    query: str,
    site: "Site",
    page_url: str,
    llm: "LLMClient",
) -> dict | None:
    """Ask the LLM for a CSS selector tuple covering all result cards."""
    if not candidates_with_dom:
        return None
    # Compact serialization for tokens.
    compact = []
    for c in candidates_with_dom[:15]:
        compact.append(
            {
                "title": c.get("title", "")[:80],
                "url": c.get("path") or c.get("url", "")[:80],
                "dom_path": c.get("dom_path", ""),
                "siblings": c.get("siblings", [])[:6],
            }
        )

    prompt = _USER_TMPL.format(
        query=query,
        site=site.url,
        page=page_url,
        candidates=json.dumps(compact, ensure_ascii=False, indent=1),
    )
    try:
        data = llm.chat_json(
            [{"role": "system", "content": _SYS}, {"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=500,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("CSS selector discovery LLM call failed: %s", e)
        return None
    if not isinstance(data, dict):
        return None
    container = data.get("container")
    if not container or not isinstance(container, str):
        return None
    out = {
        "container": container,
        "title": data.get("title"),
        "url": data.get("url"),
        "snippet": data.get("snippet"),
        "date": data.get("date"),
        "author": data.get("author"),
        "confidence": float(data.get("confidence", 0.6) or 0.6),
    }
    return out


# ----------------------------------------------------------------------
# Validation — try the selector and check it returns multiple results
# ----------------------------------------------------------------------


def selectors_validate(html: str, selectors: dict, *, source_url: str, site: "Site") -> bool:
    """Apply selectors; consider valid if we can extract 2+ chunks with non-empty titles."""
    chunks = apply_selectors(html, selectors, source_url=source_url, site=site, max_results=10)
    if len(chunks) < 2:
        return False
    return any(len(c.title) >= 8 for c in chunks)


# ----------------------------------------------------------------------
# Cache helpers (stored alongside search-bar selectors in selectors.db)
# ----------------------------------------------------------------------


def get_cached(cache: "SelectorCache | None", domain: str) -> dict | None:
    if not cache:
        return None
    try:
        existing = cache.get(domain) or {}
    except Exception:  # noqa: BLE001
        return None
    sel = existing.get("result_selectors")
    return sel if isinstance(sel, dict) else None


def store(cache: "SelectorCache", domain: str, selectors: dict) -> None:
    try:
        existing = cache.get(domain) or {}
    except Exception:  # noqa: BLE001
        existing = {}
    existing["result_selectors"] = selectors
    try:
        cache.set(domain, existing)
    except Exception as e:  # noqa: BLE001
        log.warning("could not persist css selectors for %s: %s", domain, e)


__all__ = [
    "apply_selectors",
    "discover_selectors",
    "get_cached",
    "selectors_validate",
    "store",
]
