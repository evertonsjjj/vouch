"""End-to-end extraction tests against bundled HTML fixtures.

These tests don't hit the network. They exercise the full
heuristic-then-LLM pipeline against a saved HTML page so we can iterate on
extraction logic without depending on flaky live sites.
"""

from __future__ import annotations

from pathlib import Path

from curio import Site
from curio.discovery.cache import SelectorCache
from curio.extraction import css_selectors as css
from curio.extraction.trafilatura import to_chunks

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_arxiv_heuristic_finds_real_paper_titles():
    html = _read("arxiv_search.html")
    site = Site("arxiv.org")
    chunks = to_chunks(
        html, source_url="https://arxiv.org/search/?query=attention", site=site, max_results=10
    )
    titles = {c.title for c in chunks}
    # The heuristic should extract at least one of the arXiv IDs
    # (the closest <a> per result is the ID anchor).
    assert any("arXiv:" in t or "1706.03762" in c.source_url for c in chunks for t in [c.title]), (
        f"got titles: {titles}"
    )


def test_apply_explicit_selectors_recovers_full_titles_and_authors():
    """When CSS selectors are pinned, we get the proper title + author + date."""
    html = _read("arxiv_search.html")
    site = Site("arxiv.org")
    selectors = {
        "container": "li.arxiv-result",
        "title": "p.title",
        "url": "p.list-title a",
        "snippet": "p.abstract",
        "date": "p.is-size-7",
        "author": "p.authors",
    }
    chunks = css.apply_selectors(
        html, selectors, source_url="https://arxiv.org/", site=site, max_results=10
    )
    assert len(chunks) == 3
    titles = [c.title for c in chunks]
    assert "Attention Is All You Need" in titles
    assert "Efficient Transformers: A Survey" in titles
    # Snippet and author metadata also captured
    assert any("Vaswani" in c.metadata.get("author", "") for c in chunks)
    assert any("Submitted" in c.metadata.get("date", "") for c in chunks)


def test_validate_succeeds_for_arxiv_with_pinned_selectors():
    html = _read("arxiv_search.html")
    site = Site("arxiv.org")
    selectors = {"container": "li.arxiv-result", "title": "p.title", "url": "p.list-title a"}
    assert css.selectors_validate(html, selectors, source_url="https://arxiv.org/", site=site)


def test_cache_replay_skips_llm_when_selectors_present(tmp_path):
    """Once CSS selectors are stored, the next extract_with_llm_fallback call uses them."""
    from curio.extraction.llm_extract import extract_with_llm_fallback

    class _ShouldNotBeCalledLLM:
        tokens = type("T", (), {"input": 0, "output": 0})()
        cost_usd = 0.0

        def chat_json(self, *a, **kw):  # pragma: no cover
            raise AssertionError("LLM was called when CSS cache should have served")

    html = _read("arxiv_search.html")
    site = Site("arxiv.org")
    cache = SelectorCache(tmp_path / "sel.db")
    css.store(
        cache,
        "arxiv.org",
        {
            "container": "li.arxiv-result",
            "title": "p.title",
            "url": "p.list-title a",
        },
    )
    chunks = extract_with_llm_fallback(
        html,
        source_url="https://arxiv.org/search/?q=attention",
        site=site,
        query="attention",
        llm=_ShouldNotBeCalledLLM(),
        cache=cache,
    )
    assert len(chunks) == 3
    assert any("Attention Is All You Need" in c.title for c in chunks)
