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
    site: Site,
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
    except Exception as e:
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
    except Exception as e:
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
    except Exception:
        return ""


def _attr_of(node, name: str) -> str:
    if node is None:
        return ""
    try:
        return node.get(name) or ""
    except Exception:
        return ""


# ----------------------------------------------------------------------
# Discovery — turn a list of LLM-picked candidates into a selector tuple
# ----------------------------------------------------------------------

_SYS = (
    "You are a web-scraping engineer. Given DOM context for candidate result "
    "links you produce a CSS selector tuple that captures every card. "
    "Output strict JSON only — no prose."
)


_USER_TMPL = """User query: {query}
Site: {site}
Page URL: {page}

You see {n_picks} link candidates that the user picked as real results.

For each pick I show:
  - title:    visible text of the link
  - href:     URL it points to
  - dom_path: ancestor tag chain (tag.first-class), root-first
              e.g. "html > body > main.results > article.card > h3 > a"
  - siblings: tag.class of siblings near the link

Picks (JSON):
{candidates}

Below is **one full result card's HTML** so you can see the inner structure
(title, snippet, date, author may live as siblings or descendants of the link):

```html
{sample_card_html}
```

Return strict JSON in this exact shape:
{{
  "container": "<CSS selector that matches *every* result card on this page>",
  "title":    "<selector for the title element, RELATIVE to container>",
  "url":      "<selector for the <a> element holding href, RELATIVE to container>",
  "snippet":  "<selector for description/excerpt text, or null>",
  "date":     "<selector for date/time, or null>",
  "author":   "<selector for byline/author, or null>",
  "confidence": 0.0-1.0,
  "rationale": "<one sentence>"
}}

Rules:
- Selectors must be valid CSS3 (lxml.cssselect supports class, id, tag, descendant, `>`, `,`).
- Container must match every card generically — pick a class that appears on
  multiple cards (look at dom_paths of several picks). Avoid IDs.
- title/url/snippet/date/author are RELATIVE to container (e.g. "h3 a", not ".card h3 a").
- Avoid `:nth-child(N)` unless absolutely required.
- If picks have inconsistent structure or you can't identify a repeating shape,
  set container=null and confidence=0.
"""


def discover_selectors(
    candidates_with_dom: list[dict],
    *,
    query: str,
    site: Site,
    page_url: str,
    llm: LLMClient,
    html: str | None = None,
) -> dict | None:
    """Ask the LLM for a CSS selector tuple covering all result cards.

    If raw page ``html`` is provided, we extract one example card's outer HTML
    (its closest ``article|li|div`` ancestor) and pass it to the LLM. That dramatically
    improves the LLM's ability to identify the right snippet/date selectors,
    because it sees the actual DOM structure, not just dom_path strings.
    """
    if not candidates_with_dom:
        return None
    compact = []
    for c in candidates_with_dom[:15]:
        compact.append(
            {
                "title": (c.get("title") or "")[:80],
                "href": (c.get("url") or "")[:80],
                "dom_path": c.get("dom_path", ""),
                "siblings": list(c.get("siblings", []))[:6],
            }
        )

    sample_card_html = _sample_card_html(html, candidates_with_dom)

    prompt = _USER_TMPL.format(
        query=query,
        site=site.url,
        page=page_url,
        n_picks=len(candidates_with_dom),
        candidates=json.dumps(compact, ensure_ascii=False, indent=1),
        sample_card_html=sample_card_html,
    )
    try:
        data = llm.chat_json(
            [{"role": "system", "content": _SYS}, {"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=600,
        )
    except Exception as e:
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
        "rationale": (data.get("rationale") or "")[:200],
    }
    return out


_CARD_TAGS = ("article", "li", "div")


def _sample_card_html(html: str | None, candidates: list[dict], *, max_chars: int = 1800) -> str:
    """Return the outer HTML of one candidate's closest container, truncated."""
    if not html:
        return "(no html available)"
    try:
        from lxml import html as lxml_html
        from lxml.etree import tostring
    except ImportError:
        return "(lxml unavailable)"

    try:
        tree = lxml_html.fromstring(html)
    except Exception:
        return "(html parse failed)"

    # Find an <a> matching the first candidate's title; walk up to a card-like container.
    target = None
    for cand in candidates[:5]:
        title = (cand.get("title") or "")[:80].strip()
        if not title:
            continue
        for a in tree.iter("a"):
            text = " ".join((a.text_content() or "").split())
            if title in text or text in title:
                target = a
                break
        if target is not None:
            break

    if target is None:
        return "(no card matched)"

    node = target
    for _ in range(8):
        parent = node.getparent() if hasattr(node, "getparent") else None
        if parent is None:
            break
        if getattr(parent, "tag", "") in _CARD_TAGS and (parent.get("class") or ""):
            node = parent
            break
        node = parent

    try:
        raw = tostring(node, encoding="unicode", pretty_print=False)
    except Exception:
        return "(tostring failed)"
    raw = " ".join(raw.split())  # collapse whitespace
    if len(raw) > max_chars:
        raw = raw[:max_chars] + " ...(truncated)"
    return raw


# ----------------------------------------------------------------------
# Validation — try the selector and check it returns multiple results
# ----------------------------------------------------------------------


def selectors_validate(html: str, selectors: dict, *, source_url: str, site: Site) -> bool:
    """Apply selectors; consider valid if we can extract 2+ chunks with non-empty titles."""
    chunks = apply_selectors(html, selectors, source_url=source_url, site=site, max_results=10)
    if len(chunks) < 2:
        return False
    return any(len(c.title) >= 8 for c in chunks)


# ----------------------------------------------------------------------
# Cache helpers (stored alongside search-bar selectors in selectors.db)
# ----------------------------------------------------------------------


def get_cached(cache: SelectorCache | None, domain: str) -> dict | None:
    if not cache:
        return None
    try:
        existing = cache.get(domain) or {}
    except Exception:
        return None
    sel = existing.get("result_selectors")
    return sel if isinstance(sel, dict) else None


def store(cache: SelectorCache, domain: str, selectors: dict) -> None:
    try:
        existing = cache.get(domain) or {}
    except Exception:
        existing = {}
    existing["result_selectors"] = selectors
    try:
        cache.set(domain, existing)
    except Exception as e:
        log.warning("could not persist css selectors for %s: %s", domain, e)


__all__ = [
    "apply_selectors",
    "discover_selectors",
    "get_cached",
    "selectors_validate",
    "store",
]
