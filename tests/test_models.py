"""Result models — token addition, dedup, rendering."""

from __future__ import annotations

from vouch.models import Chunk, SearchResult, TokenUsage


def test_token_addition():
    a = TokenUsage(input=10, output=5)
    b = TokenUsage(input=3, output=7)
    c = a.add(b)
    assert c.input == 13 and c.output == 12


def test_search_result_iteration_and_text():
    chunks = [
        Chunk(source_url="https://x.com/1", site="x.com", title="One", snippet="snip one"),
        Chunk(source_url="https://x.com/2", site="x.com", title="Two", snippet="snip two"),
    ]
    r = SearchResult(query="q", chunks=chunks)
    assert len(r) == 2
    assert r[0].title == "One"
    out = r.to_text()
    assert "snip one" in out and "snip two" in out
    assert "## [x.com] One" in out
