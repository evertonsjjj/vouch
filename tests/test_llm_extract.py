"""LLM-assisted result extraction — uses a fake LLMClient (no network)."""

from __future__ import annotations

from vouch import Site
from vouch.discovery.cache import SelectorCache
from vouch.extraction.llm_extract import (
    extract_with_llm_fallback,
    harvest_candidates,
    looks_low_quality,
)
from vouch.models import Chunk


class _FakeLLM:
    """Stand-in for LLMClient.

    Pass a single dict (returned for every call) or a sequence of payloads
    (consumed in order, with the last one repeated if more calls happen).
    """

    def __init__(self, payload):
        if isinstance(payload, list):
            self._payloads = payload
        else:
            self._payloads = [payload]
        self.calls = 0
        self.tokens = type("T", (), {"input": 0, "output": 0})()
        self.cost_usd = 0.0

    def chat_json(self, messages, **kwargs):
        i = min(self.calls, len(self._payloads) - 1)
        self.calls += 1
        return self._payloads[i]


_HTML = """
<html><body>
  <header><a href="/pricing">Pricing</a><a href="/about">About</a></header>
  <main>
    <a href="/models/llama">Llama-3.2 instruct</a>
    <a href="/models/qwen">Qwen2.5 14B</a>
    <a href="/models/mistral">Mistral 7B</a>
  </main>
  <footer><a href="/careers">Careers</a></footer>
</body></html>
"""


def test_looks_low_quality_empty():
    assert looks_low_quality([]) is True


def test_looks_low_quality_short_titles():
    chunks = [
        Chunk(source_url="https://x.com/a", site="x.com", title="Hi"),
        Chunk(source_url="https://x.com/b", site="x.com", title="Yo"),
    ]
    assert looks_low_quality(chunks) is True


def test_looks_low_quality_real_results_pass():
    chunks = [
        Chunk(
            source_url=f"https://x.com/papers/{i}",
            site="x.com",
            title=f"A meaningful paper title number {i}",
        )
        for i in range(5)
    ]
    assert looks_low_quality(chunks) is False


def test_harvest_candidates_excludes_other_domains():
    site = Site("example.com")
    cands = harvest_candidates(_HTML, source_url="https://example.com/", site=site)
    urls = [c["url"] for c in cands]
    assert all("example.com" in u for u in urls)


def test_extract_with_llm_fallback_picks_via_llm():
    site = Site("example.com")
    # After nav filtering, only the 3 /models/ links remain → indices 0,1,2.
    llm = _FakeLLM(
        {
            "results": [{"i": 0, "title_clean": None}, {"i": 1}, {"i": 2}],
            "url_pattern": "/models/",
        }
    )
    out = extract_with_llm_fallback(
        _HTML, source_url="https://example.com/search", site=site, query="LLMs", llm=llm
    )
    assert len(out) == 3
    assert all("/models/" in c.source_url for c in out)
    assert llm.calls == 1


def test_pattern_is_cached_after_first_llm_call(tmp_path):
    site = Site("example.com")
    cache = SelectorCache(tmp_path / "sel.db")
    # Two LLM calls per discovery turn:
    #   1) llm_pick_results → indices + url_pattern
    #   2) css.discover_selectors → returns no container (so no CSS cache stored)
    llm = _FakeLLM(
        [
            {"results": [{"i": 0}, {"i": 1}, {"i": 2}], "url_pattern": "/models/"},
            {"container": None},
        ]
    )
    # First call: hits LLM (pick + selector discovery).
    extract_with_llm_fallback(
        _HTML,
        source_url="https://example.com/search",
        site=site,
        query="LLMs",
        llm=llm,
        cache=cache,
    )
    assert llm.calls == 2
    # Second call: URL-pattern cache replays without any LLM call.
    second = extract_with_llm_fallback(
        _HTML,
        source_url="https://example.com/search",
        site=site,
        query="LLMs",
        llm=llm,
        cache=cache,
    )
    assert llm.calls == 2, "second call should hit cache, not LLM"
    assert all("/models/" in c.source_url for c in second)


def test_to_chunks_invokes_llm_when_heuristic_is_weak(tmp_path):
    """End-to-end: to_chunks() with weak heuristic should use the LLM fallback."""
    from vouch.extraction.trafilatura import to_chunks

    site = Site("example.com")
    cache = SelectorCache(tmp_path / "sel.db")
    llm = _FakeLLM(
        {
            "results": [{"i": 0}, {"i": 1}, {"i": 2}],
            "url_pattern": "/models/",
        }
    )
    chunks = to_chunks(
        _HTML,
        source_url="https://example.com/search",
        site=site,
        llm=llm,
        query="LLMs",
        cache=cache,
    )
    assert chunks
    assert any("/models/" in c.source_url for c in chunks)


def test_bad_url_pattern_not_cached(tmp_path):
    """When the LLM returns a nav-y url_pattern (/search/, /about/), don't store it."""
    site = Site("example.com")
    cache = SelectorCache(tmp_path / "sel.db")
    llm = _FakeLLM(
        {
            "results": [{"i": 0}, {"i": 1}],
            "url_pattern": "/search/",
        }
    )
    extract_with_llm_fallback(
        _HTML,
        source_url="https://example.com/search",
        site=site,
        query="x",
        llm=llm,
        cache=cache,
    )
    assert "result_url_contains" not in (cache.get("example.com") or {})


def test_inferred_pattern_requires_3_plus_picks(tmp_path):
    """Don't generalize from 1-2 picks — need confidence."""
    site = Site("example.com")
    cache = SelectorCache(tmp_path / "sel.db")
    llm = _FakeLLM({"results": [{"i": 0}], "url_pattern": ""})
    extract_with_llm_fallback(
        _HTML,
        source_url="https://example.com/search",
        site=site,
        query="x",
        llm=llm,
        cache=cache,
    )
    assert "result_url_contains" not in (cache.get("example.com") or {})


def test_to_chunks_skips_llm_if_no_query():
    """No query → no LLM call, just heuristic."""
    from vouch.extraction.trafilatura import to_chunks

    site = Site("example.com")
    llm = _FakeLLM({})
    to_chunks(_HTML, source_url="https://example.com/search", site=site, llm=llm)
    assert llm.calls == 0
