"""CSS selector pinning module — apply, validate, cache."""

from __future__ import annotations

from curio import Site
from curio.discovery.cache import SelectorCache
from curio.extraction import css_selectors as css

_HTML = """
<html><body>
  <header>
    <a href="/about">About</a>
    <a href="/pricing">Pricing</a>
  </header>
  <main class="search-results">
    <div class="result-card">
      <h3><a href="/papers/123">Attention Is All You Need</a></h3>
      <p class="snippet">A paper introducing the Transformer.</p>
      <time class="date">2017-06-12</time>
      <span class="byline">Vaswani et al.</span>
    </div>
    <div class="result-card">
      <h3><a href="/papers/456">BERT pretraining</a></h3>
      <p class="snippet">Bidirectional encoder.</p>
      <time class="date">2018-10-11</time>
      <span class="byline">Devlin et al.</span>
    </div>
    <div class="result-card">
      <h3><a href="/papers/789">GPT-3 few-shot learners</a></h3>
      <p class="snippet">Large model in-context learning.</p>
      <time class="date">2020-05-28</time>
      <span class="byline">Brown et al.</span>
    </div>
  </main>
  <footer><a href="/contact">Contact</a></footer>
</body></html>
"""


def test_apply_selectors_extracts_three_results():
    site = Site("example.com")
    selectors = {
        "container": ".result-card",
        "title": "h3 a",
        "url": "h3 a",
        "snippet": "p.snippet",
        "date": "time.date",
        "author": "span.byline",
    }
    chunks = css.apply_selectors(
        _HTML, selectors, source_url="https://example.com/search", site=site, max_results=10
    )
    assert len(chunks) == 3
    assert chunks[0].title == "Attention Is All You Need"
    assert "Transformer" in chunks[0].snippet
    assert chunks[0].metadata.get("date") == "2017-06-12"
    assert chunks[0].metadata.get("author") == "Vaswani et al."
    assert chunks[0].source_url == "https://example.com/papers/123"


def test_apply_handles_missing_optional_selectors():
    site = Site("example.com")
    selectors = {"container": ".result-card", "title": "h3 a", "url": "h3 a"}
    chunks = css.apply_selectors(
        _HTML, selectors, source_url="https://example.com/search", site=site, max_results=10
    )
    assert len(chunks) == 3
    for c in chunks:
        assert "date" not in c.metadata
        assert "author" not in c.metadata


def test_validate_passes_when_3_results_match():
    site = Site("example.com")
    selectors = {"container": ".result-card", "title": "h3 a", "url": "h3 a"}
    assert css.selectors_validate(_HTML, selectors, source_url="https://example.com", site=site)


def test_validate_fails_when_selector_matches_nothing():
    site = Site("example.com")
    selectors = {"container": ".no-such-class", "title": "h3 a", "url": "h3 a"}
    assert not css.selectors_validate(_HTML, selectors, source_url="https://example.com", site=site)


def test_apply_filters_other_domains():
    site = Site("example.com")
    html = """
    <main class="search-results">
      <div class="result-card">
        <h3><a href="https://other.com/page">External link</a></h3>
      </div>
      <div class="result-card">
        <h3><a href="/internal">Internal</a></h3>
      </div>
    </main>
    """
    selectors = {"container": ".result-card", "title": "h3 a", "url": "h3 a"}
    chunks = css.apply_selectors(html, selectors, source_url="https://example.com/", site=site)
    assert len(chunks) == 1
    assert chunks[0].title == "Internal"


def test_cache_store_and_get(tmp_path):
    cache = SelectorCache(tmp_path / "sel.db")
    selectors = {"container": ".result-card", "title": "h3 a", "url": "h3 a"}
    css.store(cache, "example.com", selectors)
    got = css.get_cached(cache, "example.com")
    assert got == selectors


def test_cache_get_missing_returns_none(tmp_path):
    cache = SelectorCache(tmp_path / "sel.db")
    assert css.get_cached(cache, "example.com") is None
