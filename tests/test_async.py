"""Async API — engine.asearch() runs sync engine in a thread."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from farol import Chunk, SearchEngine
from farol.adapters.base import AdapterContext, SiteAdapter


class _StubAdapter(SiteAdapter):
    def __init__(self, *args, **kwargs):
        pass

    def search(self, ctx: AdapterContext) -> list[Chunk]:
        return [
            Chunk(
                source_url=f"https://{ctx.site.url}/result",
                site=ctx.site.url,
                title=f"{ctx.site.url} async result for {ctx.query}",
                snippet="lorem ipsum",
                relevance_score=0.6,
            )
        ]

    def close(self) -> None:
        pass


@pytest.fixture
def engine(tmp_path, populated_catalog):
    return SearchEngine(
        llm="openai/gpt-4o-mini",
        cache_dir=str(tmp_path / "cache"),
        catalog=populated_catalog,
        router_strategy="all",
        auto_escalate_adapter=False,
    )


@pytest.mark.asyncio
async def test_asearch_returns_search_result(engine):
    with patch("farol.engine.build_adapter", lambda *a, **kw: _StubAdapter()):
        result = await engine.asearch("hello async", depth=0, max_results=3)
    assert result.query == "hello async"
    assert len(result.chunks) > 0


@pytest.mark.asyncio
async def test_asearch_passes_kwargs(engine):
    with patch("farol.engine.build_adapter", lambda *a, **kw: _StubAdapter()):
        result = await engine.asearch("foo", sites=["arxiv.org"], depth=1)
    assert all(c.site == "arxiv.org" for c in result.chunks)
