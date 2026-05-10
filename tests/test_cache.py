"""Selector cache CRUD."""

from __future__ import annotations

from curio.discovery.cache import SelectorCache, fingerprint_html


def test_fingerprint_stable():
    a = fingerprint_html("<html><body>x</body></html>")
    b = fingerprint_html("<html><body>x</body></html>")
    c = fingerprint_html("<html><body>y</body></html>")
    assert a == b
    assert a != c


def test_set_get_invalidate(tmp_path):
    cache = SelectorCache(tmp_path / "sel.db")
    assert cache.get("example.com") is None
    cache.set("example.com", {"input": "#q", "submit": "#go"})
    got = cache.get("example.com")
    assert got and got["input"] == "#q"
    n = cache.invalidate("example.com")
    assert n == 1
    assert cache.get("example.com") is None


def test_stats(tmp_path):
    cache = SelectorCache(tmp_path / "sel.db")
    cache.set("a.com", {"input": "#q"})
    cache.set("b.com", {"input": "#q"})
    stats = cache.stats()
    assert {"a.com", "b.com"} <= set(stats)


def test_empty_cache_is_truthy(tmp_path):
    """Regression: empty cache must remain truthy so adapters don't skip it."""
    cache = SelectorCache(tmp_path / "sel.db")
    assert len(cache) == 0
    assert bool(cache) is True
    # Adapter pattern: ``if self.cache and selectors`` must work on fresh cache.
    selectors = {"input": "#q"}
    assert cache and selectors
